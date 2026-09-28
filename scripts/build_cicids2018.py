"""M3: the CIC-IDS2018 window matrix, built in two passes so a 3-4 GB day never sits in memory whole.

    python scripts/build_cicids2018.py --config configs/cicids2018.yaml [--splits feb14 ...]

Same state and labels as ``build_features.py`` and ``build_ctu13.py``: S_t v1 (70 features,
``window_features``), window stages with ``- Attempted`` demoted (D-009), and the compromise, attack
and escalation targets.

- **Pass 1** streams a day's CSV in row chunks and writes the canonical flows to hourly parquet shards
  (``interim_dir``), keyed by the hour each flow starts in.
- **Pass 2** walks the day's windows an hour at a time. It reads only the shards that can hold flows of
  those windows (a flow belongs to every window its start time falls in), exactly as ``build_ctu13``'s
  time chunks do. Every S_t v1 feature depends only on the flows inside its window, so the result equals
  a single pass (checked by ``--check-chunking`` on a slice).
- **Check, per day:** the per-window flow counts add up to the file's row count times the windows each
  flow falls in. The build stops if not.

Writes ``data/processed/cicids2018/<split>.parquet`` + ``meta.json`` (with each day's attack family).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.cicids2018 import CICIDS2018Adapter
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

HOUR = pd.Timedelta(hours=1)


def pass1(adapter: CICIDS2018Adapter, split: str, shard_dir: Path, chunk: int) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    """Stream the day into hourly shards; return (first ts, last ts, rows)."""
    if shard_dir.exists():
        shutil.rmtree(shard_dir)
    shard_dir.mkdir(parents=True)
    lo = hi = None
    rows = 0
    for i, df in enumerate(adapter.iter_chunks(split, chunk)):
        rows += len(df)
        lo = df["ts"].min() if lo is None else min(lo, df["ts"].min())
        hi = df["ts"].max() if hi is None else max(hi, df["ts"].max())
        for hour, g in df.groupby(df["ts"].dt.floor("h")):
            g.to_parquet(shard_dir / f"{hour:%Y%m%d%H}_{i:04d}.parquet", index=False)
    return lo, hi, rows


def load_hours(shard_dir: Path, start: pd.Timestamp, stop: pd.Timestamp) -> pd.DataFrame:
    """Flows with start <= ts < stop, from the shards of the hours that overlap it."""
    hours = pd.date_range(start.floor("h"), (stop - pd.Timedelta(microseconds=1)).floor("h"), freq="h")
    parts = [pd.read_parquet(p) for h in hours for p in sorted(shard_dir.glob(f"{h:%Y%m%d%H}_*.parquet"))]
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    df = df[(df["ts"] >= start) & (df["ts"] < stop)]
    return df.sort_values("ts", kind="stable").reset_index(drop=True)


def pass2(shard_dir: Path, spec: WindowSpec, t0: pd.Timestamp, n: int, internal: tuple, chunk: int):
    feats, stages, mats, counts = [], [], [], np.zeros(n, dtype=np.int64)
    empty = pd.read_parquet(next(iter(sorted(shard_dir.glob("*.parquet"))))).iloc[0:0]  # the schema, no rows
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        start = t0 + pd.Timedelta(seconds=a * spec.stride_s)
        stop = t0 + pd.Timedelta(seconds=(b - 1) * spec.stride_s + spec.length_s)
        flows = load_hours(shard_dir, start, stop)
        if flows.empty:  # a quiet stretch: its windows are empty states, not missing ones
            flows = empty
        exp, _ = expand_to_windows(flows, spec, t0)
        exp = exp[(exp["w"] >= a) & (exp["w"] < b)]
        feats.append(window_features(exp, spec.length_s, internal, n_windows=b).iloc[a:b])
        stages.append(window_stages(exp, n_windows=b).iloc[a:b])
        mats.append(window_stage_matrix(exp, n_windows=b).iloc[a:b])
        counts[a:b] = np.bincount(exp["w"].to_numpy() - a, minlength=b - a)[: b - a]
    return pd.concat(feats), pd.concat(stages), pd.concat(mats), counts


def targets(feats, stages, stage_mat, spec, t0, horizon, split, family) -> tuple[pd.DataFrame, dict]:
    """The same target block as build_ctu13.build_split (compromise hazard, attack, escalation)."""
    n = len(feats)
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
        "split": split, "family": family, "t0": str(t0), "windows": int(n),
        "positive_windows": int(out["y_within_K"].sum()), "positive_rate": round(float(out["y_within_K"].mean()), 5),
        "attack_rate": round(float(out["y_attack_within_K"].mean()), 5),
        "escalate_rate": round(float(out["y_escalate_within_K"].mean()), 5),
        "onsets": onsets, "onset_times": [str(spec.window_start(t0, w)) for w in onsets],
        "stage_counts": {Stage(s).name: int((stages == s).sum()) for s in range(len(Stage))},
    }
    return out.reset_index(), meta


def build_split(adapter, split: str, cfg: dict, chunk_rows: int, chunk_windows: int) -> tuple[pd.DataFrame, dict]:
    spec = WindowSpec(cfg["window"]["length_s"], cfg["window"]["stride_s"])
    shard_dir = Path(cfg["interim_dir"]) / split
    lo, hi, rows = pass1(adapter, split, shard_dir, chunk_rows)
    t0 = lo.floor("min")
    n = spec.n_windows((hi - t0).total_seconds())
    feats, stages, mats, counts = pass2(shard_dir, spec, t0, n, tuple(cfg["internal_prefixes"]), chunk_windows)
    # every flow lands in the windows its start time falls in: 2 for a 60 s window at a 30 s stride,
    # except flows in the first 30 s, which fall in window 0 only
    first = int((len(load_hours(shard_dir, t0, t0 + pd.Timedelta(seconds=spec.stride_s)))))
    if int(counts.sum()) != 2 * rows - first:
        raise SystemExit(f"{split}: window flow counts {counts.sum()} != 2 x {rows} rows - {first} - stop")
    frame, meta = targets(feats, stages, mats, spec, t0, int(cfg["horizon_k"]), split, cfg["families"][split])
    meta |= {"flows": int(rows), "first_ts": str(lo), "last_ts": str(hi), "dropped": adapter.dropped.get(split, {})}
    if not cfg.get("keep_interim"):
        shutil.rmtree(shard_dir)
    return frame, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/cicids2018.yaml")
    ap.add_argument("--splits", nargs="*", default=None)
    ap.add_argument("--chunk-rows", type=int, default=1_000_000)
    ap.add_argument("--chunk-windows", type=int, default=120)
    ap.add_argument("--check-chunking", default=None, metavar="SPLIT",
                    help="build one split with 120- and 17-window chunks and require identical matrices")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    set_seed(args.seed)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    adapter = CICIDS2018Adapter(cfg["raw_dir"])
    if args.check_chunking:
        split = args.check_chunking
        spec = WindowSpec(cfg["window"]["length_s"], cfg["window"]["stride_s"])
        shard_dir = Path(cfg["interim_dir"]) / split
        lo, hi, _ = pass1(adapter, split, shard_dir, args.chunk_rows)
        t0 = lo.floor("min")
        n = spec.n_windows((hi - t0).total_seconds())
        internal = tuple(cfg["internal_prefixes"])
        a = pass2(shard_dir, spec, t0, n, internal, 120)
        b = pass2(shard_dir, spec, t0, n, internal, 17)
        same = (np.allclose(a[0].to_numpy(float), b[0].to_numpy(float), equal_nan=True)
                and np.array_equal(a[1].to_numpy(), b[1].to_numpy()) and np.array_equal(a[3], b[3]))
        print(f"{split}: 120-window chunks == 17-window chunks over {n} windows: {same}")
        shutil.rmtree(shard_dir, ignore_errors=True)
        raise SystemExit(0 if same else 1)

    out_dir = Path(cfg["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    old = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"splits": []}
    metas = {m["split"]: m for m in old["splits"]}
    feature_names = old.get("feature_names")
    for split in args.splits or adapter.splits():
        started = time.perf_counter()
        frame, meta = build_split(adapter, split, cfg, args.chunk_rows, args.chunk_windows)
        meta["build_s"] = round(time.perf_counter() - started, 1)
        frame.to_parquet(out_dir / f"{split}.parquet", index=False)
        metas[split] = meta
        feature_names = [c for c in frame.columns
                         if c not in {"w", "ts", "stage", "compromise", "y_within_K", "split", "attack_now",
                                      "y_attack_within_K", "y_escalate_within_K", "escalate_step"}
                         and not c.startswith(("stage_", "hazard_k", "attack_k", "escalate_k"))]
        print(f"{split} ({meta['family']:12s}) flows={meta['flows']:>10,} windows={meta['windows']:>5,} "
              f"compromise={meta['positive_rate']:.2%} attack={meta['attack_rate']:.2%} onsets={meta['onsets'][:5]} "
              f"stages={ {k: v for k, v in meta['stage_counts'].items() if v} } build={meta['build_s']}s", flush=True)
        order = list(cfg["families"])
        meta_path.write_text(json.dumps({
            "dataset": "cicids2018", "config": cfg, "git_sha": git_sha(), "seed": args.seed,
            "feature_names": feature_names, "n_features": len(feature_names or []),
            "splits": [metas[k] for k in order if k in metas],
        }, indent=2), encoding="utf-8")
    print(f"wrote {out_dir} ({len(metas)} days)")


if __name__ == "__main__":
    main()
