"""One inference entry point, shared by the CLI and the Flask API (docs/api_contract.md).

Input: a CIC-style flow CSV (or a PCAP once track D's aggregator lands).
Output: the JSON payload the dashboard renders - per-window forecast, stage prediction, explanation,
flagged flows and, when the file carries labels, the ground truth to compare against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from netwm.data.cicids2017 import COLUMN_MAP, PACKET_STAT_MAP, VICTIM_SUBNET
from netwm.engine.explain import explain_window, global_attribution, top_features
from netwm.features.flow_features import feature_flags_from_names, window_features
from netwm.features.windowing import (
    WindowSpec,
    compromise_flags,
    expand_to_windows,
    onset_windows,
    window_stages,
)
from netwm.features.packet_windows import (
    HAS_PCAP,
    PACKET_INPUTS,
    read_packets,
    window_packet_features,
    with_packets,
)
from netwm.metrics import CAUSAL_WARMUP, causal_threshold, lead_times
from netwm.models.leadtime import circular_shift_null
from netwm.labels.mitre_map import (
    COMPROMISE_THRESHOLD,
    STAGE_LABELS,
    Stage,
    TACTIC_IDS,
    is_attempted,
    refine_scan_direction,
    stage_of,
)
from netwm.models.world_model import WorldModelConfig, build_model

STAGE_COLORS = {
    0: "#9aa7b1", 1: "#4c9be8", 2: "#f2a541", 3: "#e2574c",
    4: "#8e5bd9", 5: "#2fa87a", 6: "#6b6b6b",
}


def stage_catalogue() -> list[dict[str, Any]]:
    """The stage list served by ``GET /api/model`` - the frontend never hard-codes these."""
    return [
        {
            "id": int(s),
            "key": s.name,
            "label": STAGE_LABELS[s],
            "tactic": TACTIC_IDS[s],
            "color": STAGE_COLORS[int(s)],
        }
        for s in Stage
    ]


#: D-038: the PCAP route's threshold, set explicitly. The E20r checkpoints name no policy, and the
#: single-checkpoint fallback below ("fixed") would serve their train-tuned scalar, which E14 found
#: ~100x too high on a held-out day. The route uses D-034's causal budget instead.
ENSEMBLE_POLICY = "expanding-10pct"


def load_checkpoint(path: Path | str, device: torch.device | None = None) -> dict:
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(Path(path), map_location=device, weights_only=False)
    model = build_model(WorldModelConfig(**ckpt["model_config"])).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    ckpt["model"], ckpt["device"], ckpt["path"] = model, device, str(path)
    return ckpt


def load_ensemble(paths: "list[Path | str]", device: torch.device | None = None) -> dict:
    """D-038: several checkpoints of one method served as one model - one state, one mean score.

    The members must read the same features in the same order at the same horizon and stride, and
    share their training days (one fold), or averaging their windows would mix different questions.
    The threshold policy is set here, explicitly: the members' stored train-tuned thresholds are
    never used (D-034).
    """
    members = [load_checkpoint(p, device) for p in paths]
    first = members[0]
    for m in members[1:]:
        for key in ("feature_names", "horizon_k", "stride_s"):
            if list(np.atleast_1d(m[key])) != list(np.atleast_1d(first[key])):
                raise ValueError(f"{m['path']}: {key} differs from {first['path']} - not one method")
        if sorted(m.get("train_days", [])) != sorted(first.get("train_days", [])):
            raise ValueError(f"{m['path']}: trained on other days than {first['path']} - not one fold")
    return {
        "members": members,
        "feature_names": list(first["feature_names"]),
        "horizon_k": first["horizon_k"],
        "stride_s": first["stride_s"],
        "train_days": list(first.get("train_days", [])),
        "threshold_policy": ENSEMBLE_POLICY,
        "path": [m["path"] for m in members],
        "git_sha": [str(m.get("git_sha", "unknown")) for m in members],
    }


def reads_packets(names: "list[str]") -> bool:
    """Whether a model's inputs include the packet block measured from a capture (E20r, E26)."""
    return any(n in PACKET_INPUTS for n in names)


def read_flow_csv(path: Path | str) -> pd.DataFrame:
    """Read a CIC-style flow CSV into the canonical schema, labels included when present."""
    raw = pd.read_csv(path, low_memory=False)
    raw.columns = [c.strip() for c in raw.columns]
    usable = {src: dst for src, dst in {**COLUMN_MAP, **PACKET_STAT_MAP}.items() if src in raw.columns}
    missing = {"Timestamp", "Src IP", "Dst IP", "Dst Port"} - set(usable)
    if missing:
        raise ValueError(
            f"{Path(path).name}: missing required columns {sorted(missing)}. "
            "This pipeline needs a flow CSV with timestamps and addresses (the corrected "
            "CIC-IDS2017 release, or CICFlowMeter output)."
        )
    df = raw[list(usable)].rename(columns=usable)
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts", kind="stable").reset_index(drop=True)

    for col in ("fwd_pkts", "bwd_pkts", "fwd_bytes", "bwd_bytes", "syn_cnt", "ack_cnt", "rst_cnt",
                "fin_cnt", "psh_cnt", "urg_cnt", "cwr_cnt", "ece_cnt", "duration_us"):
        if col not in df.columns:
            df[col] = 0
    if "label" in df.columns:
        labels = df["label"].astype(str)
        lut = {lbl: int(stage_of(lbl)) for lbl in labels.unique()}
        df["stage"] = labels.map(lut).astype("int8")
        df["attempted"] = labels.map({lbl: is_attempted(lbl) for lbl in labels.unique()}).astype(bool)
        df["stage"] = refine_scan_direction(labels, df["stage"], df["src_ip"], (VICTIM_SUBNET,))
    return df


def state_matrix(flows: pd.DataFrame, names: "list[str]", spec: WindowSpec,
                 pcap_path: Path | str | None = None):
    """The raw (unscaled) state a checkpoint with feature ``names`` reads, built from a flow table.

    Rebuilds exactly the blocks the checkpoint was trained on (v1, trend, host slots, CSV packet
    statistics, host-relative - read off its names) and, for a packet model, the packet block from
    ``pcap_path`` or its absent form (D-037). Returns ``(features, expanded, t0, n_windows)``.
    ``scripts/parity_check.py`` compares this with the training matrix on real days.
    """
    expanded, t0 = expand_to_windows(flows, spec)
    n_windows = int(expanded["w"].max()) + 1
    feats = window_features(expanded, spec.length_s, (VICTIM_SUBNET,), n_windows=n_windows,
                            **feature_flags_from_names(names))
    if reads_packets(names):
        if pcap_path is None and HAS_PCAP not in names:
            # E20r trained only on measured packets: a flow CSV would hand it zeros it has never
            # seen, and its forecast would look like a packet model's while being nothing of the sort
            raise ValueError("this model reads packet features measured from a capture and has no "
                             "absent-packet input: it serves PCAP uploads only (D-038)")
        packet_feats = None
        if pcap_path is not None:
            packet_feats = window_packet_features(read_packets(pcap_path), t0, n_windows,
                                                  spec.length_s, spec.stride_s)
        feats = with_packets(feats, packet_feats)
    return feats, expanded, t0, n_windows


def analyze_flows(
    flows: pd.DataFrame,
    ckpt: dict,
    n_samples: int = 16,
    mean_path_score: bool = True,
    explain_limit: int = 24,
    explain_every: int = 8,
    threshold_override: float | None = None,
    override_note: str | None = None,
    progress=None,
    pcap_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run the world model over a flow table and build the API result payload.

    ``pcap_path``: the capture the flows came from. A checkpoint that reads packet features (D-037)
    gets them from it, measured by the same functions that built its training data; without one
    (a flow-CSV upload) they are absent and ``has_pcap`` = 0, exactly as in its CSV-mode training.

    ``ckpt`` is one checkpoint or a :func:`load_ensemble` (D-038). An ensemble's members read the
    same state; every per-window output is the arithmetic mean over members, and the alarm threshold
    is applied once, to the mean score.
    """
    members = ckpt.get("members") or [ckpt]
    names = list(ckpt["feature_names"])
    horizon, stride_s = int(ckpt["horizon_k"]), float(ckpt["stride_s"])
    threshold = float(ckpt.get("threshold", 0.5))
    policy = str(ckpt.get("threshold_policy", "fixed"))
    if policy.startswith("self-budget"):
        # D-034 / G-9: the whole-capture budget these checkpoints name let windows after t set t's
        # threshold. The engine serves its causal counterpart at the same percentage instead.
        policy = "expanding-" + policy.rsplit("-", 1)[-1]
    spec = WindowSpec(2 * stride_s, stride_s)

    feats, expanded, t0, n_windows = state_matrix(flows, names, spec, pcap_path)
    packets_used = reads_packets(names)
    # each member applies its own fitted scaler to the one shared state
    xs = [m["scaler"].transform(feats[names]) for m in members]
    x = xs[0]
    scaler = members[0]["scaler"]
    # what the model's inputs are called: the feature names, or four views of each (D-035, E21)
    input_names = scaler.output_names() if hasattr(scaler, "output_names") else list(names)
    if progress:
        progress(0.35, f"{len(flows):,} flows -> {n_windows:,} windows")

    outs = [_forecast(m, xm, horizon, n_samples, mean_path_score) for m, xm in zip(members, xs)]
    out = _mean_outputs(outs)
    statistic = "p_max (mean path)" if mean_path_score else "p_max"
    if len(members) > 1:
        statistic += f", mean of {len(members)} checkpoints"
    score = out["p_max"]
    # One threshold per window. Fixed policies repeat a scalar; the deployable policy is a series.
    thresholds = np.full(n_windows, threshold)
    if threshold_override is not None:
        # Only for fixtures: a threshold chosen with knowledge of the labels is not something a
        # deployed sensor can pick (E14). Payloads produced this way are marked dev_only.
        threshold, policy = float(threshold_override), "fixed-override"
        thresholds = np.full(n_windows, threshold)
    elif policy.startswith("expanding"):
        # Alert budget on this capture's own scores *so far* (D-034, E18): the quantile of windows
        # 0..t-1, silent for the first CAUSAL_WARMUP windows. No labels and no future windows, so a
        # sensor can run it on a live stream. Absolute probabilities do not transfer between days
        # (E14: the train-tuned threshold is ~100x too high on a held-out day).
        budget_pct = float(policy.rsplit("-", 1)[-1].rstrip("pct")) / 100.0
        thresholds = causal_threshold(score, 1.0 - budget_pct)
        finite = thresholds[np.isfinite(thresholds)]
        # the scalar is the threshold in force at the end of the capture (1.0 while still warming up)
        threshold = float(finite[-1]) if finite.size else 1.0
    if progress:
        progress(0.7, "forecast complete, explaining alarms")

    # Explain the windows a defender would actually open: the strongest alarms first, plus a regular
    # sample so the global attribution is not computed only on alarms (D-017).
    alarm_idx = np.flatnonzero(score >= thresholds)
    ranked = alarm_idx[np.argsort(score[alarm_idx])[::-1][:explain_limit]] if alarm_idx.size else np.array([], int)
    sampled = np.arange(0, n_windows, explain_every)
    explain_at = sorted(set(ranked.tolist()) | set(sampled.tolist()))
    explanations = {t: _explain(members, xs, int(t), horizon) for t in explain_at}

    ts = spec.window_start(t0, np.arange(n_windows))
    has_labels = "stage" in flows.columns
    stages = window_stages(expanded, n_windows=n_windows) if has_labels else None
    talkers = _top_talkers(expanded)

    timeline = []
    for t in range(n_windows):
        expl = explanations.get(t)
        entry = {
            "t": int(t),
            "ts": ts[t].isoformat() + "Z",
            "pred_stage": int(np.argmax(out["stage_now"][t])),
            "stage_probs": [round(float(p), 4) for p in out["stage_now"][t]],
            "forecast": {
                "p_cum": [round(float(p), 4) for p in out["p_cum"][t]],
                "p_lo": [round(float(p), 4) for p in out["p_lo"][t]],
                "p_hi": [round(float(p), 4) for p in out["p_hi"][t]],
                "p_step": [round(float(p), 4) for p in out["p_raw"][t, :, 0]],
                "p_cum_attack": [round(float(p), 4) for p in out["p_cum_attack"][t]],
                "p_cum_escalate": [round(float(p), 4) for p in out["p_cum_escalate"][t]],
            },
            "alarm": bool(score[t] >= thresholds[t]),
            # null during the warm-up, when the causal budget has too little history to fire
            "threshold": round(float(thresholds[t]), 6) if np.isfinite(thresholds[t]) else None,
            "surprise": round(float(out["surprise"][t]), 4),
            "attention": [round(float(a), 4) for a in out["attention"][t]],
            "p_max": round(float(score[t]), 4),
            "p_max_mc": round(float(out["p_max_mc"][t]), 4) if "p_max_mc" in out else None,
            "flow_count": int(feats["n_flows"].iloc[t]),
            "top_talkers": talkers.get(t, []),
            "top_features": (
                top_features(expl["feature_attribution"], x[t], input_names) if expl is not None else []
            ),
        }
        if has_labels:
            observed = int(stages.iloc[t])
            entry["observed_stage"] = observed
            # How much probability the model put on the stage that was actually happening.
            entry["observed_stage_conf"] = round(float(out["stage_now"][t][observed]), 4)
        timeline.append(entry)

    payload: dict[str, Any] = {
        "payload_version": "1.1",
        "alarm_statistic": statistic,
        "threshold_policy": policy,
        "source": {
            "flows": int(len(flows)),
            "windows": int(n_windows),
            # D-037 / D-038: whether the model read packet features, and whether they were measured
            "packet_features": _packet_note(packets_used, pcap_path),
            "t0": t0.isoformat() + "Z",
            "window_s": spec.length_s,
            "stride_s": spec.stride_s,
        },
        # D-038: which route served this file - the dashboard's modality indicator reads this
        "inference": {
            "input_modality": "pcap" if pcap_path is not None else "csv",
            "telemetry": "flow + packet" if packets_used and pcap_path is not None else "flow",
            "model_mode": ("packet-enriched" if packets_used else "flow-only")
            + (f" ensemble of {len(members)}" if len(members) > 1 else ""),
            "checkpoints": [str(m.get("path", "unknown")) for m in members],
            "aggregation": "arithmetic mean per window, threshold applied to the mean" if len(members) > 1 else None,
            "packet_features": _packet_note(packets_used, pcap_path),
            "feature_count": len(names),
        },
        "threshold": threshold,
        "threshold_warmup_windows": CAUSAL_WARMUP if policy.startswith("expanding") else 0,
        "horizon_k": horizon,
        "stages": stage_catalogue(),
        "timeline": timeline,
        "explanation_global": global_attribution(list(explanations.values()), input_names),
    }
    if has_labels:
        onsets = onset_windows(stages, int(COMPROMISE_THRESHOLD))
        comp = compromise_flags(stages, int(COMPROMISE_THRESHOLD))
        payload["ground_truth"] = {
            "available": True,
            "onsets": [{"t": int(o), "ts": ts[o].isoformat() + "Z"} for o in onsets],
            "compromise_windows": int(comp.sum()),
            "spans": _stage_spans(stages, expanded, ts),
        }
        payload["alarms"] = _alarm_rows(score, thresholds, onsets, ts, stride_s, horizon)
        payload["lead_time_summary"] = _lead_summary(
            score, thresholds, onsets, ts, stride_s, horizon
        )
    else:
        payload["ground_truth"] = {"available": False}
        payload["alarms"] = _alarm_rows(score, thresholds, [], ts, stride_s, horizon)
        payload["lead_time_summary"] = None
    if override_note:
        payload["dev_only"] = True
        payload["note"] = override_note
    if progress:
        progress(1.0, "done")
    return payload


@torch.no_grad()
def _forecast(member: dict, x: np.ndarray, horizon: int, n_samples: int, mean_path_score: bool) -> dict:
    """One checkpoint's per-window forecast over the whole capture.

    Alarm statistic is max over the horizon, not the cumulative union: the compromise head answers
    "is this state compromised", a property that persists, so the union multiplies one event K times
    and saturates (D-019, E13).

    The curves and their Monte-Carlo band come from sampled rollouts, but the *alarm score* is read off
    the deterministic mean path: a lead-time count must not move between runs of the same checkpoint on
    the same file (E14 saw 1 of 4 and then 2 of 4 at one threshold). Sampling stays for the band,
    because a cone drawn from a single deterministic path would be a flat line.
    """
    model, device = member["model"], member["device"]
    tensor = torch.from_numpy(x).unsqueeze(0).to(device)
    out = {k: v.cpu().numpy() for k, v in model.forecast(tensor, horizon=horizon, n_samples=n_samples).items()}
    if mean_path_score:
        mean_out = model.forecast(tensor, horizon=horizon, n_samples=1, sample=False)
        out["p_max_mc"] = out["p_max"]
        out["p_max"] = mean_out["p_max"].cpu().numpy()
    return out


def _mean_outputs(outs: "list[dict]") -> dict:
    """D-038: the ensemble's output is the arithmetic mean of its members', array by array, per window.
    One member is returned untouched, so the single-checkpoint path is unchanged."""
    if len(outs) == 1:
        return outs[0]
    return {k: np.mean(np.stack([o[k] for o in outs]), axis=0) for k in outs[0]}


def _explain(members: "list[dict]", xs: "list[np.ndarray]", t: int, horizon: int) -> dict:
    """Integrated Gradients for window ``t``, averaged over members. IG is linear in the model, so the
    mean of the members' attributions is the attribution of the mean score (D-038)."""
    parts = [explain_window(m["model"], xm, t, horizon, m["device"]) for m, xm in zip(members, xs)]
    if len(parts) == 1:
        return parts[0]
    out = {"t": t, "score": float(np.mean([p["score"] for p in parts]))}
    for key in ("feature_attribution", "history_attribution", "total_attribution"):
        if len({np.shape(p[key]) for p in parts}) == 1:
            out[key] = np.mean(np.stack([p[key] for p in parts]), axis=0)
    return out


def _packet_note(packets_used: bool, pcap_path) -> str:
    """What the payload says about packet telemetry - never that a flow-only model used it."""
    if packets_used:
        return "measured from the capture" if pcap_path is not None else "absent (flow input)"
    return "unavailable (flow input)" if pcap_path is None else "not used by this model (flow-only)"


def _alarm_rows(score, threshold, onsets, ts, stride_s, horizon, persistence: int = 2) -> list[dict]:
    """Contiguous alarm runs, annotated with lead time to the next known onset.

    A run shorter than ``persistence`` windows is still reported - the operator saw it - but it earns
    no lead time, because a single spike above the threshold is not a warning. This is the same rule
    ``lead_time_summary`` applies, so the two never disagree about how many episodes were warned.
    ``threshold`` is a scalar or one value per window (the causal budget, D-034).
    """
    thresholds = np.broadcast_to(np.asarray(threshold, dtype=float), np.shape(score))
    above = score >= thresholds
    rows, start = [], None
    for t, flag in enumerate(above):
        if flag and start is None:
            start = t
        elif not flag and start is not None:
            rows.append((start, t - 1))
            start = None
    if start is not None:
        rows.append((start, len(above) - 1))

    out = []
    for begin, end in rows:
        length = end - begin + 1
        nxt = [o for o in onsets if begin <= o <= begin + horizon] if length >= persistence else []
        lead = (nxt[0] - begin) if nxt else None
        out.append(
            {
                "t": int(begin),
                "ts": ts[begin].isoformat() + "Z",
                "until_t": int(end),
                "windows": int(length),
                "sustained": bool(length >= persistence),
                "p": round(float(score[begin : end + 1].max()), 4),
                # the threshold in force when the run started, so "how far above" needs no scalar
                "threshold": round(float(thresholds[begin]), 6),
                "onset_t": int(nxt[0]) if nxt else None,
                "lead_windows": int(lead) if lead is not None else None,
                "lead_seconds": float(lead * stride_s) if lead is not None else None,
            }
        )
    return out


def _lead_summary(score, threshold, onsets, ts, stride_s, horizon) -> dict[str, Any]:
    """Per-episode early-warning result, including the episodes we missed.

    The alarm panel must be able to say "0 of 4 episodes warned early" as clearly as it says
    "fired 5 windows early", because today that is the honest answer (E14).
    """
    rows = lead_times(np.asarray(score), list(onsets), np.asarray(threshold, dtype=float), int(horizon),
                      persistence=2)
    for row in rows:
        row["onset_ts"] = ts[row["onset"]].isoformat() + "Z"
        row["first_alarm_ts"] = (
            ts[row["first_alarm"]].isoformat() + "Z" if row["first_alarm"] is not None else None
        )
        row["lead_seconds"] = float(row["lead_windows"] * stride_s)
    early = [r for r in rows if r["detected_early"]]
    # D-022: a warned-early count is only a result if it beats an unaligned alarm series of the same
    # shape. Rolling the margin score - threshold rolls the alarm series itself, so the alarm rate is
    # held fixed even though the causal threshold moves; same counting rule as the rows above.
    margin = np.asarray(score, dtype=float) - np.asarray(threshold, dtype=float)
    margin = np.where(np.isfinite(margin), margin, -1.0)
    null = circular_shift_null(margin, list(onsets), 0.0, int(horizon), n_shifts=2000, seed=42,
                               persistence=2, confirm_before_onset=False) if onsets else {}
    return {
        "episodes": len(rows),
        "persistence_windows": 2,
        "warned_early": len(early),
        "mean_lead_windows": round(float(np.mean([r["lead_windows"] for r in early])), 2) if early else 0.0,
        "mean_lead_seconds": round(float(np.mean([r["lead_seconds"] for r in early])), 1) if early else 0.0,
        "null_mean": round(float(null.get("null_mean", 0.0)), 2),
        "null_p95": int(null.get("null_p95", 0)),
        "p_value": round(float(null.get("p_value", 1.0)), 3),
        # the only condition under which the dashboard may call an early warning verified
        "beats_null": bool(null.get("exceeds_null_p95", False)),
        "per_episode": rows,
    }


def analyze_file(path: Path | str, ckpt: dict, **kwargs) -> dict[str, Any]:
    """Dispatch on file type. A PCAP is turned into flows by ``flow_aggregator.pcap_to_flows`` (D-033, D-043)."""
    path = Path(path)
    if path.suffix.lower() in {".csv", ".txt"}:
        flows = read_flow_csv(path)
    elif path.suffix.lower() in {".pcap", ".pcapng"}:
        try:
            from netwm.features.flow_aggregator import pcap_to_flows
        except ImportError as exc:  # pragma: no cover - until the aggregator lands
            raise NotImplementedError(
                "PCAP ingestion needs netwm.features.flow_aggregator.pcap_to_flows"
            ) from exc
        # A capture carries no ground truth. The aggregator fills label/stage with BENIGN/0 to satisfy
        # the canonical schema, and a stage column is what marks a payload as labelled, so without
        # this the dashboard would report "no attacks" as the truth for any PCAP.
        flows = pcap_to_flows(path).drop(columns=["label", "stage", "attempted"], errors="ignore")
        if flows.empty:
            # single-packet flows are not emitted (D-043), so a tiny capture can hold no flow at all
            raise ValueError(f"{path.name}: no TCP/UDP flow of two or more packets in the capture")
        kwargs.setdefault("pcap_path", path)
    else:
        raise ValueError(f"unsupported file type: {path.suffix}")
    payload = analyze_flows(flows, ckpt, **kwargs)
    payload["source"]["filename"] = path.name
    payload["source"]["kind"] = path.suffix.lower().lstrip(".")
    return payload


def _top_talkers(expanded: pd.DataFrame, k: int = 3) -> dict[int, list[dict[str, Any]]]:
    """The k busiest sources per window - what the flagged-flows panel leads with."""
    frame = expanded.assign(_bytes=expanded["fwd_bytes"] + expanded["bwd_bytes"])
    grouped = (
        frame.groupby(["w", "src_ip"], sort=False)
        .agg(flows=("src_ip", "size"), bytes_out=("_bytes", "sum"))
        .reset_index()
    )
    grouped = grouped.sort_values(["w", "flows"], ascending=[True, False])
    top = grouped.groupby("w", sort=False).head(k)
    out: dict[int, list[dict[str, Any]]] = {}
    for w, ip, flows_n, bytes_out in top.itertuples(index=False):
        out.setdefault(int(w), []).append(
            {"ip": str(ip), "flows": int(flows_n), "bytes_out": int(bytes_out)}
        )
    return out


def _stage_spans(stages, expanded: pd.DataFrame, ts) -> list[dict[str, Any]]:
    """Contiguous runs of a non-benign stage, labelled with the attack that dominates them."""
    values = stages.to_numpy()
    spans: list[dict[str, Any]] = []
    start = None
    for t in range(len(values) + 1):
        current = values[t] if t < len(values) else 0
        if start is not None and (current != values[start]):
            spans.append((start, t - 1, int(values[start])))
            start = None
        if start is None and current > 0:
            start = t

    labelled = "label" in expanded.columns
    out = []
    for begin, end, stage in spans:
        label = STAGE_LABELS[Stage(stage)]
        if labelled:
            # Attempted traffic does not set the stage (D-009), so it must not name the span either:
            # otherwise a span driven by 73 real brute-force flows gets labelled "- Attempted"
            # because 1 292 ineffective ones outnumber them.
            in_span = expanded["w"].between(begin, end) & (expanded["stage"] > 0)
            if "attempted" in expanded.columns:
                in_span &= ~expanded["attempted"].to_numpy()
            window_labels = expanded.loc[in_span, "label"]
            if len(window_labels):
                label = str(window_labels.value_counts().idxmax())
        out.append(
            {
                "start_t": int(begin),
                "end_t": int(end),
                "start_ts": ts[begin].isoformat() + "Z",
                "end_ts": ts[end].isoformat() + "Z",
                "stage": int(stage),
                "label": label,
            }
        )
    return out
