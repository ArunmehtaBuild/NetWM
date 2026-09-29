"""E28 / M3 (D-044): CIC-IDS2018 family by family - world model (seeds 42/43/44) against LR, never one average.

    python scripts/m3_family_matrix.py

Everything here was fixed in decisions.md D-044 before any run:

- **Primary target and score per held-out day.** On compromise days (feb28, mar01, mar02): ROC-AUC of
  the stored ``comp`` score on ``y_within_K``, as E25b. On the seven attack-only days, where
  ``y_within_K`` is zero throughout: the stored ``threat`` score (the attack channel) on
  ``y_attack_within_K``.
- **Beside it:** PR-AUC and causal F1 (causal expanding q90) on the same target and score, background
  windows, S2* (threat percentile of non-Impact attack onsets, where a day has >= 20 cells) and S3 (the
  circular-shift null), with the E25b scorer's helpers unchanged.
- **Intervals:** D-042's moving-block bootstrap (blocks of 20 windows, 2,000 resamples) on each day's
  primary ROC-AUC, per seed, for the seed-mean score and for LR, on shared resamples.
- **Family verdicts:** D-037's rule (``ctu_family_matrix.classify``) on the primary ROC-AUC.
- **D-039's question:** "recurs" if >= 2 families are inverted and at least one inversion sits on a day
  with >= 100 background windows whose seed-mean interval is wholly below 0.5; "does not recur" if no
  family is inverted; "inconclusive" otherwise.

Writes results/tables/e28_m3_{days,families,ci}.csv and results/runs/e28-m3-matrix/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctu_family_matrix import MIN_CELLS, classify
from netwm.bootstrap import block_bootstrap_auc
from netwm.data.processed import ProcessedDataset
from netwm.metrics import causal_threshold
from netwm.models.leadtime import circular_shift_null
from netwm.models.targets import episode_labels
from netwm.utils import TABLES, ensure_dirs, git_sha, save_run, set_seed
from scorecard import GATING_BINS, load_scores, percentiles, reference_mask

DATA = "data/processed/cicids2018"
SEEDS = (42, 43, 44)
WM = [f"m3-s{s}" for s in SEEDS]
LR = "lr-m3"
COMPROMISE_DAYS = ("feb28", "mar01", "mar02")
BLOCK, N_BOOT = 20, 2000
WELL_MEASURED = 100


def primary(day: str) -> tuple[str, str]:
    """(score key, label column) for a held-out day, by D-044's rule."""
    return ("comp", "y_within_K") if day in COMPROMISE_DAYS else ("threat", "y_attack_within_K")


def day_row(run: str, model: str, ds: ProcessedDataset, day: str, scores: dict) -> dict:
    f = ds.frame(day)
    key, col = primary(day)
    y = f[col].to_numpy().astype(int)
    s = scores[day][key]
    alarm = s >= causal_threshold(s, 0.90)
    tp, fp, fn = int((alarm & (y == 1)).sum()), int((alarm & (y == 0)).sum()), int((~alarm & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    both = 0 < y.sum() < len(y)
    threat = scores[day]["threat"]
    attack = episode_labels(f["stage"], ds.horizon, source="attack")
    non_impact = attack.without("IMPACT")
    ref = reference_mask(len(f), attack.onsets, attack.eligible)
    cells = percentiles(threat, non_impact.onsets, attack.eligible, ref)
    gating = [v for b in GATING_BINS for v in cells[b]]
    margin = threat - causal_threshold(threat, 0.90)
    margin = np.where(np.isfinite(margin), margin, -1.0)
    null = (circular_shift_null(margin, non_impact.onsets, 0.0, ds.horizon, n_shifts=2000, seed=42,
                                persistence=2, eligible=attack.eligible) if non_impact.onsets else {})
    meta = next(m for m in ds.meta["splits"] if m["split"] == day)
    return {
        "model": model, "run": run, "day": day, "family": meta["family"], "target": col, "score": key,
        "windows": len(f), "background": int((y == 0).sum()), "positives": int(y.sum()),
        "roc_auc": round(float(roc_auc_score(y, s)), 4) if both else None,
        "pr_auc": round(float(average_precision_score(y, s)), 4) if both else None,
        "causal_f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
        "s2_cells": len(gating), "s2_star": round(float(np.mean(gating)), 4) if len(gating) >= MIN_CELLS else None,
        "s3": f"{null.get('observed', 0)}/{len(non_impact.onsets)} p={null.get('p_value', 1.0):.3f}",
    }


def main() -> None:
    set_seed(42)
    ensure_dirs()
    ds = ProcessedDataset(DATA)
    loaded = {run: load_scores(run) for run in [*WM, LR]}
    rows = [day_row(run, "world model", ds, d, loaded[run]) for run in WM for d in ds.splits]
    rows += [day_row(LR, "logistic regression", ds, d, loaded[LR]) for d in ds.splits]
    days = pd.DataFrame(rows)

    ci_rows = []
    for i, d in enumerate(ds.splits):
        key, col = primary(d)
        y = ds.frame(d)[col].to_numpy().astype(int)
        if not 0 < y.sum() < len(y):
            continue
        series = {f"s{s}": loaded[r][d][key] for s, r in zip(SEEDS, WM)}
        series["WM mean of seeds"] = np.mean([loaded[r][d][key] for r in WM], axis=0)
        series["LR"] = loaded[LR][d][key]
        res = block_bootstrap_auc(y, series, BLOCK, N_BOOT, 42 + 1000 * i)
        for label, r in res.items():
            ci_rows.append({"day": d, "series": label, "roc_auc": round(r["roc_auc"], 4), "lo": round(r["lo"], 4),
                            "hi": round(r["hi"], 4), "dropped": r["dropped"]})
    ci = pd.DataFrame(ci_rows)

    wm = days[days["model"] == "world model"]
    fams = []
    for family, g in wm.groupby("family", sort=False):
        lr = days[(days["model"] == "logistic regression") & (days["family"] == family)]
        verdict = classify(g.rename(columns={"day": "scenario"}))  # classify() reads E25b's column name
        well = []
        for d in g["day"].unique():
            m = ci[(ci["day"] == d) & (ci["series"] == "WM mean of seeds")]
            bg = int(g[g["day"] == d]["background"].iloc[0])
            if len(m) and bg >= WELL_MEASURED and float(m["hi"].iloc[0]) < 0.5:
                well.append(d)
        fams.append({"family": family, "days": ", ".join(g["day"].unique()), "verdict": verdict,
                     "wm_roc_auc_mean": round(float(g["roc_auc"].mean()), 3),
                     "lr_roc_auc_mean": round(float(lr["roc_auc"].mean()), 3) if len(lr) else None,
                     "well_measured_inverted_days": ", ".join(well)})
    families = pd.DataFrame(fams)
    inverted = families[families["verdict"] == "inverted"]
    well_any = bool((inverted["well_measured_inverted_days"] != "").any())
    answer = ("recurs" if len(inverted) >= 2 and well_any else
              "does not recur" if len(inverted) == 0 else "inconclusive")

    days.to_csv(TABLES / "e28_m3_days.csv", index=False)
    families.to_csv(TABLES / "e28_m3_families.csv", index=False)
    ci.to_csv(TABLES / "e28_m3_ci.csv", index=False)
    save_run("e28-m3-matrix", {"days": rows, "families": fams, "ci": ci_rows,
                               "d039_answer": answer, "inverted_families": inverted["family"].tolist()},
             config={"decision": "D-044", "world_model_runs": WM, "lr_run": LR, "compromise_days": COMPROMISE_DAYS,
                     "block": BLOCK, "n_boot": N_BOOT, "well_measured_background": WELL_MEASURED,
                     "git_sha_at_start": git_sha()})
    pd.set_option("display.width", 250)
    print(days.drop(columns=["target"]).to_string(index=False))
    print("\n" + families.to_string(index=False))
    print(f"\nD-039 via D-044: the inversion pattern on the full state -> {answer}")


if __name__ == "__main__":
    main()
