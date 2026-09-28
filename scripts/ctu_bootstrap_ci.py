"""Confidence intervals for a CTU-13 per-scenario ROC-AUC table (D-042's uncertainty method).

    python scripts/ctu_bootstrap_ci.py --tag e25b --data data/processed/ctu13 \
        --wm s42=e25-ctu13-s42 s43=e25-ctu13-s43 s44=e25-ctu13-s44 --lr LR=lr-ctu13-s42

Method, fixed in decisions.md D-042 before it ran: for each held-out scenario, a moving-block bootstrap
over its windows (blocks of 20 windows = 2K, 10 min), 2,000 resamples, percentile 95 % interval of the
ROC-AUC of the stored ``comp`` score on ``y_within_K``; resamples with one class only are dropped and
counted. Block lengths 10 and 40 are the sensitivity check. Every series of a scenario is scored on the
*same* resamples. The world-model rows are each seed and the three-seed mean score (per-window mean of
the seeds' scores); the seed range is a separate source of uncertainty and is reported beside them.

Writes results/tables/ctu_ci_<tag>.csv and results/runs/ctu-ci-<tag>/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.bootstrap import block_bootstrap_auc
from netwm.data.processed import ProcessedDataset
from netwm.utils import TABLES, ensure_dirs, git_sha, save_run, set_seed
from scorecard import load_scores

BLOCKS = (20, 10, 40)   # the first is the reported interval, the others the sensitivity check
N_BOOT = 2000


def pairs(items: "list[str]") -> "list[tuple[str, str]]":
    return [tuple(i.split("=", 1)) for i in items]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--wm", nargs="+", required=True, help="label=run for each world-model seed")
    ap.add_argument("--lr", nargs="*", default=[], help="label=run for deterministic baselines")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)
    fam = {m["split"]: m["family"] for m in ds.meta["splits"]}
    wm, lr = pairs(args.wm), pairs(args.lr)
    loaded = {run: load_scores(run) for _, run in [*wm, *lr]}

    rows = []
    for i, scen in enumerate(ds.splits):
        y = ds.target(scen).astype(int)
        series = {label: loaded[run][scen]["comp"] for label, run in wm}
        if len(wm) > 1:
            series["WM mean of seeds"] = np.mean([loaded[run][scen]["comp"] for _, run in wm], axis=0)
        series |= {label: loaded[run][scen]["comp"] for label, run in lr}
        per_block = {b: block_bootstrap_auc(y, series, b, N_BOOT, args.seed + 1000 * i + b) for b in BLOCKS}
        for label in series:
            r = {"tag": args.tag, "series": label, "scenario": scen, "family": fam[scen], "windows": len(y),
                 "background": int((y == 0).sum()), "roc_auc": round(per_block[BLOCKS[0]][label]["roc_auc"], 4)}
            for b in BLOCKS:
                res = per_block[b][label]
                r |= {f"lo_b{b}": round(res["lo"], 4), f"hi_b{b}": round(res["hi"], 4), f"dropped_b{b}": res["dropped"]}
            rows.append(r)
        print(f"{scen} {fam[scen]:8s} " + "  ".join(
            f"{r['series']}={r['roc_auc']:.3f}[{r['lo_b20']:.2f},{r['hi_b20']:.2f}]" for r in rows[-len(series):]), flush=True)

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / f"ctu_ci_{args.tag}.csv", index=False)
    save_run(f"ctu-ci-{args.tag}", {"rows": rows},
             config={**vars(args), "blocks": BLOCKS, "n_boot": N_BOOT, "git_sha_at_start": git_sha()})
    print(f"wrote results/tables/ctu_ci_{args.tag}.csv and results/runs/ctu-ci-{args.tag}/")


if __name__ == "__main__":
    main()
