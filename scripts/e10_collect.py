"""E10 - collect the ablation runs into the table D-030 is scored on.

    python scripts/e10_collect.py

For every arm (full / no-stochastic / no-multistep) x seed (42, 43, 44) x fold (Thursday, Friday):

  * ``rollout_R``: mean over k = 2..K of (world_model_mse - persistence_mse), read from
    ``results/runs/<run>/metrics.json``. This is E5's measure; lower is better.
  * ``pmax_f1_budget10``, ``pmax_pr_auc``: ``p_max`` at ``self-budget-10pct``, from
    ``results/tables/e14_pmax_rescore_<run>.csv`` (run ``scripts/rescore_pmax.py --run <run>`` first).
  * ``*_vs_full``: the same metric minus the full model's value *for the same seed* (D-030 pairs by
    seed). The sign convention is "positive = the ablation made it worse" for both metrics.

It computes, it does not judge: the verdict against D-030 is written in results.md (Y-4b).
Writes results/tables/e10_ablation_summary.csv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.utils import RUNS, TABLES

ARMS = ("full", "no-stochastic", "no-multistep")
SEEDS = (42, 43, 44)
FOLDS = ("thursday", "friday")


def rollout_r(run: str, fold: str) -> float:
    m = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))
    per_day = (m.get("metrics") or m)["per_day"]
    r = per_day[fold]["rollout"]
    k = np.asarray(r["k"])
    diff = np.asarray(r["world_model_mse"]) - np.asarray(r["persistence_mse"])
    return float(diff[k >= 2].mean())


def detection(run: str, fold: str) -> tuple[float, float]:
    t = pd.read_csv(TABLES / f"e14_pmax_rescore_{run}.csv")
    row = t[(t["test_day"] == fold) & (t["threshold_mode"] == "self-budget-10pct") & (t["statistic"] == "p_max")]
    if len(row) != 1:
        raise SystemExit(f"{run}/{fold}: expected one p_max self-budget-10pct row, found {len(row)}")
    return float(row["f1"].iloc[0]), float(row["pr_auc"].iloc[0])


def main() -> None:
    rows = []
    for arm in ARMS:
        for seed in SEEDS:
            run = f"e10-{arm}-s{seed}"
            for fold in FOLDS:
                f1, pr = detection(run, fold)
                rows.append({"arm": arm, "seed": seed, "fold": fold, "run": run,
                             "rollout_R": rollout_r(run, fold), "pmax_f1_budget10": f1, "pmax_pr_auc": pr})
    df = pd.DataFrame(rows)
    full = df[df["arm"] == "full"].set_index(["seed", "fold"])
    key = list(zip(df["seed"], df["fold"]))
    # positive = the ablation made it worse: a higher R is worse, a lower F1 / PR-AUC is worse
    df["rollout_R_vs_full"] = df["rollout_R"].to_numpy() - full.loc[key, "rollout_R"].to_numpy()
    df["f1_vs_full"] = full.loc[key, "pmax_f1_budget10"].to_numpy() - df["pmax_f1_budget10"].to_numpy()
    df["pr_auc_vs_full"] = full.loc[key, "pmax_pr_auc"].to_numpy() - df["pmax_pr_auc"].to_numpy()
    df = df.round(4)
    df.to_csv(TABLES / "e10_ablation_summary.csv", index=False)
    pd.set_option("display.width", 200)
    print(df.drop(columns="run").to_string(index=False))
    print(f"\nwrote {TABLES / 'e10_ablation_summary.csv'}")


if __name__ == "__main__":
    main()
