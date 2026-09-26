"""S-8 - what is actually in the K windows before an attack onset?

A per-onset lead-time row says a score was high before an onset. It does not say *why*. This script
goes back to the raw flows for one onset and answers the questions a reader of that row will ask:

  * Is any of the run-up traffic attack traffic, including ``- Attempted`` flows that D-009 keeps
    out of the stage label?
  * Is the run-up actually different from the hour before it, on a given feature?
  * Which hosts carry the difference - the hosts the attack later touches, or bystanders?

    python scripts/onset_audit.py --day thursday --onset 602

Outputs results/tables/s8_<day>_onset<N>_windows.csv (one row per window around the onset) and
results/tables/s8_<day>_onset<N>_hosts.csv (per-host contribution to the feature, benign flows only).
Reads the raw CSV, so it needs ``python scripts/get_data.py`` first. CPU only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.cicids2017 import CICIDS2017Adapter
from netwm.data.processed import ProcessedDataset
from netwm.features.windowing import WindowSpec, expand_to_windows
from netwm.utils import TABLES, ensure_dirs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", default="thursday")
    ap.add_argument("--onset", type=int, default=602)
    ap.add_argument("--baseline", type=int, default=120, help="windows before the run-up to compare against")
    ap.add_argument("--after", type=int, default=35, help="windows after the onset to show the level persisting")
    ap.add_argument("--feature", default="uniq_dst_port", help="only uniq_dst_port / uniq_dst_ip are recomputed per host")
    ap.add_argument("--raw", default="data/raw/cicids2017_improved")
    ap.add_argument("--data", default="data/processed/cicids2017")
    args = ap.parse_args()
    ensure_dirs()

    ds = ProcessedDataset(args.data)
    k, o = ds.horizon, args.onset
    meta = next(m for m in ds.meta["splits"] if m["split"] == args.day)
    t0 = pd.Timestamp(meta["t0"])
    spec = WindowSpec(length_s=ds.meta["config"]["window"]["length_s"], stride_s=ds.stride_s)
    col = {"uniq_dst_port": "dst_port", "uniq_dst_ip": "dst_ip"}[args.feature]

    flows = CICIDS2017Adapter(Path(args.raw)).load(args.day)
    ex, _ = expand_to_windows(flows, spec, t0)
    ex["benign"] = ex["label"].astype(str).str.upper().eq("BENIGN")
    proc = ds.frame(args.day)

    # The per-window feature must be the one in the matrix, or nothing below describes the model input.
    recomputed = ex.groupby("w")[col].nunique().reindex(range(len(proc)), fill_value=0).to_numpy()
    if not np.array_equal(recomputed, proc[args.feature].to_numpy()):
        raise SystemExit(f"{args.feature} recomputed from raw flows does not match {args.data} - stale matrix?")

    lo, hi = max(0, o - k - args.baseline), min(len(proc), o + args.after)
    rows = []
    for w in range(lo, hi):
        s = ex[ex["w"] == w]
        rows.append({
            "window": w,
            "start_utc": str(spec.window_start(t0, w)),
            "segment": "baseline" if w < o - k else "run-up" if w < o else "onset+",
            "stage": int(proc["stage"].iloc[w]),
            "flows": len(s),
            "attempted_flows": int(s["attempted"].sum()),
            "attack_flows": int((~s["benign"] & ~s["attempted"]).sum()),
            args.feature: int(proc[args.feature].iloc[w]),
            f"{args.feature}_benign_only": int(s.loc[s["benign"], col].nunique()),
            "labels": "; ".join(f"{a}:{b}" for a, b in s.loc[~s["benign"], "label"].value_counts().items()),
        })
    table = pd.DataFrame(rows)
    stem = f"s8_{args.day}_onset{o}"
    table.to_csv(TABLES / f"{stem}_windows.csv", index=False)

    ben = ex[ex["benign"]]
    def per_host(a: int, b: int, by: str) -> pd.Series:
        s = ben[(ben["w"] >= a) & (ben["w"] < b)]
        return s.groupby(["w", by])[col].nunique().groupby(by).sum() / max(1, b - a)
    hosts = []
    for by in ("src_ip", "dst_ip"):
        t = pd.DataFrame({
            "baseline": per_host(o - k - args.baseline, o - k, by),
            "run_up": per_host(o - k, o, by),
            "after": per_host(o + 2, o + args.after, by),
        }).fillna(0.0)
        t["delta"] = t["run_up"] - t["baseline"]
        hosts.append(t.assign(side=by).rename_axis("host").reset_index())
    host_table = pd.concat(hosts).sort_values("delta", ascending=False)
    host_table.round(3).to_csv(TABLES / f"{stem}_hosts.csv", index=False)

    seg = table.groupby("segment", sort=False)
    print(f"{args.day} onset {o} ({spec.window_start(t0, o)} UTC), K={k}")
    print(seg[[args.feature, "attempted_flows", "attack_flows"]].agg(["mean", "sum"]).round(2).to_string())
    runup = table[table["segment"] == "run-up"]
    print(f"\nrun-up: {int(runup['attempted_flows'].sum())} attempted flows, {int(runup['attack_flows'].sum())} attack flows")
    print(f"onset window labels: {table.loc[table['window'] == o, 'labels'].item()}")
    print("\ntop hosts by increase in", args.feature, "(benign flows, per window):")
    print(host_table.head(6).round(2).to_string(index=False))
    print(f"\nwrote {TABLES / (stem + '_windows.csv')} and {TABLES / (stem + '_hosts.csv')}")


if __name__ == "__main__":
    main()
