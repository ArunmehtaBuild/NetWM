"""E25 (D-035): the CTU-13 window matrix, built in time chunks.

    python scripts/build_ctu13.py --config configs/ctu13.yaml

Same state and labels as ``build_features.py`` - S_t v1 (``window_features``), ``window_stages``,
compromise / attack / escalation targets - but each scenario is processed in chunks of
``--chunk-windows`` windows. Scenario 3 is 4.7 M flows over 66 hours, and expanding it to windows in
one frame does not fit this machine's memory. Every window feature depends only on flows inside that
window, so the result is identical to a single pass (checked on the smallest scenario by
``--check-chunking``).

Writes ``data/processed/ctu13/s<NN>.parquet`` + ``meta.json`` (with each scenario's family).
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

from netwm.data.ctu13 import CTU13Adapter
from netwm.features.flow_features import window_features
from netwm.features.windowing import (
    WindowSpec,
    any_within,
    attack_flags,
    compromise_flags,
    escalation_steps,
    expand_to_windows,
    hazard_targets,
    onset_windows,
    window_stage_matrix,
    window_stages,
)
from netwm.labels.mitre_map import COMPROMISE_THRESHOLD, Stage
from netwm.utils import git_sha, set_seed


def chunked_windows(flows: pd.DataFrame, spec: WindowSpec, internal: tuple, chunk: int):
    t0 = flows["ts"].min().floor("min")
    span = (flows["ts"].max() - t0).total_seconds()
    n = spec.n_windows(span)
    feats, stages, mats = [], [], []
    offs = (flows["ts"] - t0).dt.total_seconds().to_numpy()
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        # flows that can land in windows a..b-1: start in [a*stride, (b-1)*stride + length)
        sel = (offs >= a * spec.stride_s) & (offs < (b - 1) * spec.stride_s + spec.length_s)
        exp, _ = expand_to_windows(flows.loc[sel], spec, t0)
        exp = exp[(exp["w"] >= a) & (exp["w"] < b)]
        f = window_features(exp, spec.length_s, internal, n_windows=b).iloc[a:b]
        feats.append(f)
        stages.append(window_stages(exp, n_windows=b).iloc[a:b])
        mats.append(window_stage_matrix(exp, n_windows=b).iloc[a:b])
    return t0, n, pd.concat(feats), pd.concat(stages), pd.concat(mats)


def build_split(adapter: CTU13Adapter, split: str, cfg: dict, chunk: int) -> tuple[pd.DataFrame, dict]:
    spec = WindowSpec(cfg["window"]["length_s"], cfg["window"]["stride_s"])
    horizon = int(cfg["horizon_k"])
    flows = adapter.load(split).drop(columns=["label"])
    t0, n, feats, stages, stage_mat = chunked_windows(flows, spec, tuple(cfg["internal_prefixes"]), chunk)
    stages = stages.reset_index(drop=True)
    comp = compromise_flags(stages, int(COMPROMISE_THRESHOLD))
    hazard = hazard_targets(stages, horizon, int(COMPROMISE_THRESHOLD))
    attack_now = attack_flags(stages)
    attack_future = np.zeros((n, horizon), dtype=np.float32)
    for k in range(1, horizon + 1):
        attack_future[: n - k, k - 1] = attack_now[k:]
    escalate_step = escalation_steps(stages)
    step_future = np.zeros((n, horizon), dtype=np.float32)
    for k in range(1, horizon + 1):
        step_future[: n - k, k - 1] = escalate_step[k:]

    out = feats.reset_index(drop=True)
    out.index.name = "w"
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
    out["y_escalate_within_K"] = any_within(step_future)
    out["split"] = split
    onsets = onset_windows(stages, int(COMPROMISE_THRESHOLD))
    meta = {
        "split": split,
        "family": adapter.family(split),
        "t0": str(t0),
        "flows": int(len(flows)),
        "windows": int(n),
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
    ap.add_argument("--config", default="configs/ctu13.yaml")
    ap.add_argument("--splits", nargs="*", default=None)
    ap.add_argument("--chunk-windows", type=int, default=1440)
    ap.add_argument("--check-chunking", action="store_true", help="compare chunked vs single pass on s11")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    adapter = CTU13Adapter(cfg["raw_dir"])
    if args.check_chunking:
        one, _ = build_split(adapter, "s11", cfg, chunk=10**9)
        many, _ = build_split(adapter, "s11", cfg, chunk=7)  # 5 chunks over its 34 windows
        cols = [c for c in one.columns if c not in ("ts", "split")]
        same = np.allclose(one[cols].to_numpy(float), many[cols].to_numpy(float), equal_nan=True)
        print(f"chunked == single pass on s11 ({len(one)} windows): {same}")
        if not same:
            raise SystemExit(1)
        return

    out_dir = Path(cfg["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"splits": []}
    metas = {m["split"]: m for m in old["splits"]}
    feature_names = old.get("feature_names")
    for split in args.splits or adapter.splits():
        started = time.perf_counter()
        frame, meta = build_split(adapter, split, cfg, args.chunk_windows)
        meta["build_s"] = round(time.perf_counter() - started, 1)
        frame.to_parquet(out_dir / f"{split}.parquet", index=False)
        metas[split] = meta
        feature_names = [c for c in frame.columns
                         if c not in {"w", "ts", "stage", "compromise", "y_within_K", "split", "attack_now",
                                      "y_attack_within_K", "y_escalate_within_K", "escalate_step"}
                         and not c.startswith(("stage_", "hazard_k", "attack_k", "escalate_k"))]
        print(f"{split} ({meta['family']:8s}) flows={meta['flows']:>9,} windows={meta['windows']:>5,} "
              f"compromise={meta['positive_rate']:.2%} attack={meta['attack_rate']:.2%} onsets={meta['onsets'][:5]} "
              f"stages={ {k: v for k, v in meta['stage_counts'].items() if v} } build={meta['build_s']}s", flush=True)
    meta_path.write_text(json.dumps({
        "dataset": "ctu13", "config": cfg, "git_sha": git_sha(), "seed": args.seed,
        "feature_names": feature_names, "n_features": len(feature_names or []),
        "splits": [metas[k] for k in sorted(metas)],
    }, indent=2), encoding="utf-8")
    print(f"wrote {out_dir} ({len(metas)} scenarios)")


if __name__ == "__main__":
    main()
