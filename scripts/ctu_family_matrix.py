"""D-037 Step 7: CTU-13 family by family - world model vs logistic regression, never one average.

    python scripts/ctu_family_matrix.py

For every held-out scenario: detection (ROC-AUC, PR-AUC and causal F1 of ``comp`` on
``y_within_K``, with the base rate), anticipation (the S2 percentile of pre-onset windows, only where
the scenario contributes >= 20 pre-onset cells) and the strict warned-early count against the
circular null (S3). The world model (seeds 42/43/44) and LR (deterministic) are scored by the same
functions as every CIC-IDS2017 row.

Each family is classified by D-037's rule, fixed before these runs:
  transfers  world-model ROC-AUC >= 0.70 on >= 2 of 3 seeds, for every scenario of the family
  inverted   ROC-AUC < 0.50 on >= 2 of 3 seeds, for any scenario of the family
  partial    everything else

Writes results/tables/e25b_ctu13_scenarios.csv, e25b_ctu13_families.csv and results/runs/e25b-ctu13-matrix/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.data.processed import ProcessedDataset
from netwm.metrics import causal_threshold
from netwm.models.leadtime import circular_shift_null
from netwm.models.targets import episode_labels
from netwm.utils import TABLES, ensure_dirs, save_run
from scorecard import GATING_BINS, load_scores, percentiles, reference_mask

WM = [f"e25-ctu13-s{s}" for s in (42, 43, 44)]
LR = ["lr-ctu13-s42"]
MIN_CELLS = 20


def scenario_rows(run: str, model: str, ds: ProcessedDataset) -> list[dict]:
    scores = load_scores(run)
    out = []
    for s in ds.splits:
        f = ds.frame(s)
        y = f["y_within_K"].to_numpy().astype(int)
        comp, threat = scores[s]["comp"], scores[s]["threat"]
        alarm = comp >= causal_threshold(comp, 0.90)
        tp, fp, fn = int((alarm & (y == 1)).sum()), int((alarm & (y == 0)).sum()), int((~alarm & (y == 1)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        both = 0 < y.sum() < len(y)
        attack = episode_labels(f["stage"], ds.horizon, source="attack")
        non_impact = attack.without("IMPACT")
        ref = reference_mask(len(f), attack.onsets, attack.eligible)
        cells = percentiles(threat, non_impact.onsets, attack.eligible, ref)
        gating = [v for b in GATING_BINS for v in cells[b]]
        margin = threat - causal_threshold(threat, 0.90)
        margin = np.where(np.isfinite(margin), margin, -1.0)
        null = (circular_shift_null(margin, non_impact.onsets, 0.0, ds.horizon, n_shifts=2000, seed=42,
                                    persistence=2, eligible=attack.eligible) if non_impact.onsets else {})
        meta = next(m for m in ds.meta["splits"] if m["split"] == s)
        out.append({
            "model": model, "run": run, "scenario": s, "family": meta["family"], "windows": len(f),
            "base_rate": round(float(y.mean()), 3),
            "roc_auc": round(float(roc_auc_score(y, comp)), 4) if both else None,
            "pr_auc": round(float(average_precision_score(y, comp)), 4) if both else None,
            "causal_f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "s2_cells": len(gating),
            "s2_star": round(float(np.mean(gating)), 4) if len(gating) >= MIN_CELLS else None,
            "s3": f"{null.get('observed', 0)}/{len(non_impact.onsets)} p={null.get('p_value', 1.0):.3f}",
        })
    return out


def classify(fam: pd.DataFrame) -> str:
    """D-037's rule on the world-model rows of one family."""
    per_scen = fam.groupby("scenario")["roc_auc"]
    transfers = all((g.dropna() >= 0.70).sum() >= 2 for _, g in per_scen)
    inverted = any((g.dropna() < 0.50).sum() >= 2 for _, g in per_scen)
    return "inverted" if inverted else "transfers" if transfers else "partial"


def main() -> None:
    ensure_dirs()
    ds = ProcessedDataset("data/processed/ctu13")
    rows = [r for run in WM for r in scenario_rows(run, "world model", ds)]
    rows += [r for run in LR for r in scenario_rows(run, "logistic regression", ds)]
    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "e25b_ctu13_scenarios.csv", index=False)

    wm, lr = table[table["model"] == "world model"], table[table["model"] == "logistic regression"]
    scen = (wm.groupby(["family", "scenario"])
            .agg(windows=("windows", "first"), base_rate=("base_rate", "first"),
                 wm_roc_mean=("roc_auc", "mean"), wm_roc_min=("roc_auc", "min"), wm_roc_max=("roc_auc", "max"),
                 wm_pr_mean=("pr_auc", "mean"), wm_f1_mean=("causal_f1", "mean"),
                 wm_s2_mean=("s2_star", "mean"), s2_cells=("s2_cells", "first"),
                 wm_s3=("s3", lambda v: " | ".join(v)))
            .join(lr.set_index(["family", "scenario"])[["roc_auc", "pr_auc", "causal_f1", "s2_star", "s3"]]
                  .add_prefix("lr_"))
            .round(3).reset_index())
    fams = []
    for family, g in wm.groupby("family"):
        l = lr[lr["family"] == family]
        fams.append({
            "family": family, "scenarios": ", ".join(sorted(g["scenario"].unique())),
            "verdict": classify(g),
            "wm_roc_auc_mean": round(float(g["roc_auc"].mean()), 3),
            "lr_roc_auc_mean": round(float(l["roc_auc"].mean()), 3) if len(l) else None,
            "wm_s2_star_mean": round(float(g["s2_star"].dropna().mean()), 3) if g["s2_star"].notna().any() else None,
            "lr_s2_star_mean": round(float(l["s2_star"].dropna().mean()), 3) if l["s2_star"].notna().any() else None,
        })
    families = pd.DataFrame(fams)
    scen.to_csv(TABLES / "e25b_ctu13_scenario_matrix.csv", index=False)
    families.to_csv(TABLES / "e25b_ctu13_families.csv", index=False)
    pd.set_option("display.width", 250)
    print(scen.to_string(index=False))
    print("\n" + families.to_string(index=False))
    save_run("e25b-ctu13-matrix", {"scenarios": scen.to_dict("records"), "families": fams},
             config={"world_model_runs": WM, "lr_runs": LR, "min_s2_cells": MIN_CELLS})


if __name__ == "__main__":
    main()
