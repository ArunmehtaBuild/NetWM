"""Build the per-window state matrix S_t (+ labels and forecast targets) from flow records.

    python scripts/build_features.py --config configs/cicids2017.yaml

Writes one parquet per split to ``data/processed/<dataset>/<split>.parquet`` with:
  w, ts                 window index and window start (UTC)
  <feature columns>     the state vector S_t (flow-level; packet-level appended when a PCAP is given)
  stage                 dominant ATT&CK stage of the window (ground truth)
  stage_<NAME>          multi-label stage presence (D-010)
  compromise            1 if the window is at/after Lateral Movement (non-attempted only, D-009)
  hazard_k{1..K}        1 if a compromise window occurs exactly k windows ahead (D-005)
  y_within_K            1 if a compromise occurs within the next K windows (the headline target)
plus ``meta.json`` recording the window spec, horizon, feature names and git SHA.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.cicids2017 import CICIDS2017Adapter
from netwm.features.flow_features import feature_flags_from_names, window_features
from netwm.features.windowing import (
    WindowSpec,
    any_within,
    attack_flags,
    compromise_flags,
    escalation_steps,
    escalation_targets,
    expand_to_windows,
    hazard_targets,
    onset_windows,
    window_stage_matrix,
    window_stages,
)
from netwm.labels.mitre_map import COMPROMISE_THRESHOLD, Stage
from netwm.utils import git_sha, set_seed

ADAPTERS = {"cicids2017": CICIDS2017Adapter}


def build_split(adapter, split: str, cfg: dict) -> tuple[pd.DataFrame, dict]:
    spec = WindowSpec(cfg["window"]["length_s"], cfg["window"]["stride_s"])
    horizon = int(cfg["horizon_k"])
    internal = tuple(cfg["internal_prefixes"])

    flows = adapter.load(split)
    expanded, t0 = expand_to_windows(flows, spec)
    n_windows = int(expanded["w"].max()) + 1

    use_trend = cfg["window"].get("use_trend_features", False)
    feats = window_features(expanded, spec.length_s, internal, n_windows=n_windows, use_trend=use_trend)
    stages = window_stages(expanded, n_windows=n_windows)
    stage_mat = window_stage_matrix(expanded, n_windows=n_windows)
    comp = compromise_flags(stages, int(COMPROMISE_THRESHOLD))
    hazard = hazard_targets(stages, horizon, int(COMPROMISE_THRESHOLD))

    # Two extra supervision signals (D-016): "anything hostile ahead" and "the attacker advances a
    # stage". Unlike compromise, both have positive examples on every day of the week.
    attack_now = attack_flags(stages)
    attack_future = np.zeros((len(stages), horizon), dtype=np.float32)
    for k in range(1, horizon + 1):
        attack_future[: len(stages) - k, k - 1] = attack_now[k:]
    escalate = escalation_targets(stages, horizon)
    escalate_step = escalation_steps(stages)

    out = feats.copy()
    out.insert(0, "ts", spec.window_start(t0, out.index.to_numpy()))
    out["stage"] = stages.to_numpy()
    for name in stage_mat.columns:
        out[f"stage_{name}"] = stage_mat[name].to_numpy()
    out["compromise"] = comp.astype("int8")
    for k in range(1, horizon + 1):
        out[f"hazard_k{k}"] = hazard[:, k - 1].astype("int8")
    out["y_within_K"] = (hazard.sum(axis=1) > 0).astype("int8")
    out["attack_now"] = attack_now.astype("int8")
    out["y_attack_within_K"] = any_within(attack_future)
    out["escalate_step"] = escalate_step.astype("int8")
    # "an escalation happens at some point in the next K windows", defined from the per-window step
    # flag so it matches the cumulative-product formula the rollout uses.
    step_future = np.zeros((len(stages), horizon), dtype=np.float32)
    for k in range(1, horizon + 1):
        step_future[: len(stages) - k, k - 1] = escalate_step[k:]
    out["y_escalate_within_K"] = any_within(step_future)
    for k in range(1, horizon + 1):
        out[f"attack_k{k}"] = attack_future[:, k - 1].astype("int8")
        out[f"escalate_k{k}"] = escalate[:, k - 1].astype("int8")
    out["split"] = split

    onsets = onset_windows(stages, int(COMPROMISE_THRESHOLD))
    meta = {
        "split": split,
        "t0": str(t0),
        "flows": int(len(flows)),
        "windows": int(len(out)),
        "positive_windows": int(out["y_within_K"].sum()),
        "positive_rate": round(float(out["y_within_K"].mean()), 5),
        "attack_rate": round(float(out["y_attack_within_K"].mean()), 5),
        "escalate_rate": round(float(out["y_escalate_within_K"].mean()), 5),
        "onsets": onsets,
        "onset_times": [str(spec.window_start(t0, w)) for w in onsets],
        "stage_counts": {Stage(s).name: int((stages == s).sum()) for s in range(len(Stage))},
    }
    return out.reset_index(), meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/cicids2017.yaml")
    ap.add_argument("--splits", nargs="*", default=None, help="subset of splits to build")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    adapter = ADAPTERS[cfg["dataset"]](cfg["raw_dir"])
    out_dir = Path(cfg["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    splits = args.splits or adapter.splits()
    metas, feature_names = [], None
    for split in splits:
        started = time.perf_counter()
        frame, meta = build_split(adapter, split, cfg)
        # load + window + features + labels for one split, excluding the parquet write; results.md
        # F-entries quote this number, so it lives in meta.json rather than in a terminal
        meta["build_s"] = round(time.perf_counter() - started, 3)
        frame.to_parquet(out_dir / f"{split}.parquet", index=False)
        metas.append(meta)
        feature_names = [
            c
            for c in frame.columns
            if c not in {"w", "ts", "stage", "compromise", "y_within_K", "split", "attack_now",
                         "y_attack_within_K", "y_escalate_within_K", "escalate_step"}
            and not c.startswith(("stage_", "hazard_k", "attack_k", "escalate_k"))
        ]
        print(f"{split:10s} windows={meta['windows']:>5,} compromise={meta['positive_rate']:.2%} "
              f"attack={meta['attack_rate']:.2%} escalate={meta['escalate_rate']:.2%} "
              f"onsets={len(meta['onsets'])} build={meta['build_s']:.2f}s")

    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "dataset": cfg["dataset"],
                "config": cfg,
                "git_sha": git_sha(),
                "seed": args.seed,
                "feature_names": feature_names,
                "n_features": len(feature_names or []),
                # what inference will reconstruct from the names alone (D-026)
                "feature_flags": feature_flags_from_names(feature_names or []),
                "splits": metas,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out_dir}/*.parquet ({len(feature_names or [])} features) + meta.json")


if __name__ == "__main__":
    main()
