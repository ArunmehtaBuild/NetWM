"""One inference entry point, shared by the CLI and the Flask API (app/api_contract.md).

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

from netwm.data.cicids2017 import COLUMN_MAP, VICTIM_SUBNET
from netwm.engine.explain import explain_window, global_attribution, top_features
from netwm.features.flow_features import window_features
from netwm.features.windowing import (
    WindowSpec,
    compromise_flags,
    expand_to_windows,
    onset_windows,
    window_stages,
)
from netwm.labels.mitre_map import (
    COMPROMISE_THRESHOLD,
    STAGE_LABELS,
    Stage,
    TACTIC_IDS,
    is_attempted,
    refine_scan_direction,
    stage_of,
)
from netwm.models.world_model import NetWorldModel, WorldModelConfig

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


def load_checkpoint(path: Path | str, device: torch.device | None = None) -> dict:
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(Path(path), map_location=device, weights_only=False)
    model = NetWorldModel(WorldModelConfig(**ckpt["model_config"])).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    ckpt["model"], ckpt["device"] = model, device
    return ckpt


def read_flow_csv(path: Path | str) -> pd.DataFrame:
    """Read a CIC-style flow CSV into the canonical schema, labels included when present."""
    raw = pd.read_csv(path, low_memory=False)
    raw.columns = [c.strip() for c in raw.columns]
    usable = {src: dst for src, dst in COLUMN_MAP.items() if src in raw.columns}
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


def analyze_flows(
    flows: pd.DataFrame,
    ckpt: dict,
    n_samples: int = 16,
    explain_limit: int = 24,
    explain_every: int = 8,
    progress=None,
) -> dict[str, Any]:
    """Run the world model over a flow table and build the API result payload."""
    model, device = ckpt["model"], ckpt["device"]
    scaler, names = ckpt["scaler"], ckpt["feature_names"]
    horizon, stride_s = int(ckpt["horizon_k"]), float(ckpt["stride_s"])
    threshold = float(ckpt.get("threshold", 0.5))
    policy = str(ckpt.get("threshold_policy", "fixed"))
    spec = WindowSpec(2 * stride_s, stride_s)

    expanded, t0 = expand_to_windows(flows, spec)
    n_windows = int(expanded["w"].max()) + 1
    feats = window_features(expanded, spec.length_s, (VICTIM_SUBNET,), n_windows=n_windows)
    x = scaler.transform(feats[names])
    if progress:
        progress(0.35, f"{len(flows):,} flows -> {n_windows:,} windows")

    out = model.forecast(
        torch.from_numpy(x).unsqueeze(0).to(device), horizon=horizon, n_samples=n_samples
    )
    out = {k: v.numpy() for k, v in out.items()}
    # Alarm statistic is max over the horizon, not the cumulative union: the compromise head answers
    # "is this state compromised", a property that persists, so the union multiplies one event K
    # times and saturates (D-019, E13).
    score = out["p_max"]
    if policy.startswith("self-budget"):
        # Alert budget on this capture's own score distribution: no labels, so a sensor can set it
        # from its live stream. Absolute probabilities do not transfer between days (E14: the
        # train-tuned threshold is ~100x too high on a held-out day).
        budget_pct = float(policy.rsplit("-", 1)[-1].rstrip("pct")) / 100.0
        threshold = float(np.quantile(score, 1.0 - budget_pct))
    if progress:
        progress(0.7, "forecast complete, explaining alarms")

    # Explain the windows a defender would actually open: the strongest alarms first, plus a regular
    # sample so the global attribution is not computed only on alarms (D-017).
    alarm_idx = np.flatnonzero(score >= threshold)
    ranked = alarm_idx[np.argsort(score[alarm_idx])[::-1][:explain_limit]] if alarm_idx.size else np.array([], int)
    sampled = np.arange(0, n_windows, explain_every)
    explain_at = sorted(set(ranked.tolist()) | set(sampled.tolist()))
    explanations = {
        t: explain_window(model, x, int(t), horizon, device) for t in explain_at
    }

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
            "alarm": bool(score[t] >= threshold),
            "surprise": round(float(out["surprise"][t]), 4),
            "attention": [round(float(a), 4) for a in out["attention"][t]],
            "p_max": round(float(score[t]), 4),
            "flow_count": int(feats["n_flows"].iloc[t]),
            "top_talkers": talkers.get(t, []),
            "top_features": (
                top_features(expl["feature_attribution"], x[t], names) if expl is not None else []
            ),
        }
        if has_labels:
            entry["observed_stage"] = int(stages.iloc[t])
        timeline.append(entry)

    payload: dict[str, Any] = {
        "payload_version": "1.1",
        "alarm_statistic": "p_max",
        "threshold_policy": policy,
        "source": {
            "flows": int(len(flows)),
            "windows": int(n_windows),
            "t0": t0.isoformat() + "Z",
            "window_s": spec.length_s,
            "stride_s": spec.stride_s,
        },
        "threshold": threshold,
        "horizon_k": horizon,
        "stages": stage_catalogue(),
        "timeline": timeline,
        "explanation_global": global_attribution(list(explanations.values()), names),
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
        payload["alarms"] = _alarm_rows(score, threshold, onsets, ts, stride_s, horizon)
    else:
        payload["ground_truth"] = {"available": False}
        payload["alarms"] = _alarm_rows(score, threshold, [], ts, stride_s, horizon)
    if progress:
        progress(1.0, "done")
    return payload


def _alarm_rows(score, threshold, onsets, ts, stride_s, horizon) -> list[dict]:
    """Contiguous alarm runs, annotated with lead time to the next known onset."""
    above = score >= threshold
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
        nxt = [o for o in onsets if begin <= o <= begin + horizon]
        lead = (nxt[0] - begin) if nxt else None
        out.append(
            {
                "t": int(begin),
                "ts": ts[begin].isoformat() + "Z",
                "until_t": int(end),
                "p": round(float(score[begin : end + 1].max()), 4),
                "onset_t": int(nxt[0]) if nxt else None,
                "lead_windows": int(lead) if lead is not None else None,
                "lead_seconds": float(lead * stride_s) if lead is not None else None,
            }
        )
    return out


def analyze_file(path: Path | str, ckpt: dict, **kwargs) -> dict[str, Any]:
    """Dispatch on file type. PCAP support is track D's ``flow_aggregator`` (see teamtasks.md)."""
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
        flows = pcap_to_flows(path)
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
