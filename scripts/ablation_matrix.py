"""D-037 Steps 4-5: the controlled comparison and the pre-registered ship decision for E26.

    python scripts/ablation_matrix.py

Scores every row of the matrix with ``scripts/scorecard.py``'s own functions (no second scoring
path), adds the world-model evidence each run stored (open-loop rollout MSE against persistence,
averaged over k = 2..10, per held-out day), applies D-037's composition bar to E26 against E22, and
names the ship outcome it implies. Nothing is chosen here; the rule was fixed before E26 ran.

Rows: LR flow-only, E19 (r2 method), E22 (anticipation reference), E20r (packet reference),
E24a (no latent dynamics), E26 in PCAP mode, E26 in CSV mode.

Writes results/tables/e26_ablation_matrix.csv (per run), e26_ablation_summary.csv (per row, mean and
range) and results/runs/e26-ship-decision/metrics.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.data.processed import ProcessedDataset
from netwm.utils import RUNS, TABLES, ensure_dirs, save_run
from scorecard import score_run

SEEDS = (42, 43, 44)
ROWS = {
    "LR flow-only": ("data/processed/cicids2017_m1v2", ["lr-flow-s42"]),
    "E19 flow-only (r2 method)": ("data/processed/cicids2017_m1v2", [f"m1v2-e19-s{s}" for s in SEEDS]),
    "E22 flow+CSV-pkt, factorised": ("data/processed/cicids2017_m1v2", [f"m1v2-e22-s{s}" for s in SEEDS]),
    "E20r flow+packets": ("data/processed/cicids2017_m1v2p", [f"m1v2-e20r-s{s}" for s in SEEDS]),
    "E24a no latent dynamics": ("data/processed/cicids2017_m1v2", [f"m1v2-e24a-s{s}" for s in SEEDS]),
    "E26 PCAP mode": ("data/processed/cicids2017_m1v2p", [f"m1v2-e26-s{s}" for s in SEEDS]),
    "E26 CSV mode": ("data/processed/cicids2017_m1v2p", [f"m1v2-e26-s{s}-csvmode" for s in SEEDS]),
}
SHOW = ["S1_precision", "S1_fpr", "S2_0-2min", "S2_2-4min", "S2_4-6min", "S2_6-10min", "S2_star",
        "diag_S2_star_isolated", "S4_worst_day", "thursday_comp_pr_auc", "thursday_causal_f1",
        "friday_comp_pr_auc", "friday_causal_f1", "rollout_gain_thursday", "rollout_gain_friday"]


def rollout_gain(run: str, day: str) -> float | None:
    """Mean over k = 2..10 of (persistence MSE - world-model MSE); > 0 means the rollout beats
    'nothing changes' (E10's form). None for models without dynamics."""
    per_day = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]["per_day"]
    r = per_day.get(day, {}).get("rollout")
    if not r:
        return None
    wm, pe = np.asarray(r["world_model_mse"]), np.asarray(r["persistence_mse"])
    return float((pe[1:] - wm[1:]).mean())


def composition_bar(e26: pd.DataFrame, e22: pd.DataFrame, e26_csv: pd.DataFrame) -> dict:
    """D-037's clauses (a)-(e), seed-paired, PCAP mode against E22; (d) also in CSV mode."""
    c, b = e26.set_index("seed").sort_index(), e22.set_index("seed").sort_index()
    seeds = sorted(set(c.index) & set(b.index))
    d_s2 = c.loc[seeds, "S2_star"] - b.loc[seeds, "S2_star"]
    d_pr = c.loc[seeds, "thursday_comp_pr_auc"] - b.loc[seeds, "thursday_comp_pr_auc"]
    d_prec = c.loc[seeds, "S1_precision"].mean() - b.loc[seeds, "S1_precision"].mean()
    d_fpr = c.loc[seeds, "S1_fpr"].mean() - b.loc[seeds, "S1_fpr"].mean()
    rollout_ok = ((c.loc[seeds, "rollout_gain_thursday"] > 0) & (c.loc[seeds, "rollout_gain_friday"] > 0))
    csv_min_pr = float(e26_csv["thursday_comp_pr_auc"].min())
    verdict = {
        "seeds": seeds,
        "a_anticipation_preserved": bool(d_s2.mean() >= -0.03),
        "delta_S2_star_mean": round(float(d_s2.mean()), 4),
        "delta_S2_star_per_seed": [round(float(v), 4) for v in d_s2],
        "b_detection_added": bool(d_pr.mean() >= 0.05 and (d_pr > 0).sum() >= 2),
        "delta_thursday_pr_auc_mean": round(float(d_pr.mean()), 4),
        "delta_thursday_pr_auc_per_seed": [round(float(v), 4) for v in d_pr],
        "c_alarm_cost": bool(d_prec > -0.05 and d_fpr < 0.02),
        "delta_S1_precision": round(float(d_prec), 4),
        "delta_S1_fpr": round(float(d_fpr), 4),
        "d_stability_pcap": bool((c.loc[seeds, "thursday_comp_pr_auc"] >= 0.20).all()),
        "d_stability_csv": bool(csv_min_pr >= 0.20),
        "csv_mode_min_thursday_pr_auc": round(csv_min_pr, 4),
        "e_world_model": bool(rollout_ok.sum() >= 2),
        "rollout_beats_persistence_seeds": int(rollout_ok.sum()),
    }
    core = all(verdict[k] for k in ("a_anticipation_preserved", "b_detection_added", "c_alarm_cost",
                                    "d_stability_pcap", "e_world_model"))
    if core and verdict["d_stability_csv"]:
        outcome = "1: ship E26 as the one model for PCAP and CSV inputs"
    elif core:
        outcome = "2: E26 serves PCAP uploads only; r2 stays shipped for CSV; no one-model claim"
    elif not verdict["a_anticipation_preserved"]:
        outcome = "3: the gains do not compose (anticipation lost); r2 stays shipped; diagnose, no tuning"
    elif not verdict["b_detection_added"]:
        outcome = "4: packets add nothing on top of E22; r2 stays shipped; E22 stays the anticipation reference"
    else:
        failed = [k for k in ("c_alarm_cost", "d_stability_pcap", "e_world_model") if not verdict[k]]
        outcome = f"not shipped: clause(s) {failed} fail; r2 stays shipped; diagnose, no tuning"
    verdict["outcome"] = outcome
    return verdict


def main() -> None:
    ensure_dirs()
    rows = []
    for label, (data, runs) in ROWS.items():
        ds = ProcessedDataset(data)
        for run in runs:
            r = score_run(run, ds, 2000)
            r["row"], r["seed"] = label, int(run.split("-s")[-1].split("-")[0])
            r["rollout_gain_thursday"] = rollout_gain(run, "thursday")
            r["rollout_gain_friday"] = rollout_gain(run, "friday")
            rows.append(r)
            print(f"{label:30s} {run:24s} S2*={r['S2_star']:.3f} Thu PR-AUC={r['thursday_comp_pr_auc']:.3f} "
                  f"prec={r['S1_precision']:.3f} fpr={r['S1_fpr']:.3f} S3 {r['S3_warned']} p={r['S3_fisher_p']}")
    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "e26_ablation_matrix.csv", index=False)
    summary = table.groupby("row", sort=False)[SHOW].agg(["mean", "min", "max"]).round(4)
    summary.to_csv(TABLES / "e26_ablation_summary.csv")
    s3 = table.groupby("row", sort=False).agg(S3_passes=("S3_passes", "sum"), S3_best_p=("S3_fisher_p", "min"))

    verdict = composition_bar(table[table["row"] == "E26 PCAP mode"], table[table["row"] == "E22 flow+CSV-pkt, factorised"],
                              table[table["row"] == "E26 CSV mode"])
    pd.set_option("display.width", 250)
    print("\n" + summary[[("S2_star", "mean"), ("S2_star", "min"), ("S2_star", "max"), ("S1_precision", "mean"),
                          ("S1_fpr", "mean"), ("thursday_comp_pr_auc", "mean"), ("thursday_comp_pr_auc", "min"),
                          ("thursday_comp_pr_auc", "max"), ("thursday_causal_f1", "mean"),
                          ("rollout_gain_thursday", "mean"), ("rollout_gain_friday", "mean")]].to_string())
    print("\n" + s3.to_string())
    print("\nD-037 composition bar, E26 vs E22:\n" + json.dumps(verdict, indent=1))
    save_run("e26-ship-decision", {"verdict": verdict, "S3": s3.reset_index().to_dict("records"),
                                   "summary": json.loads(summary.to_json(orient="index"))},
             config={"rows": {k: v[1] for k, v in ROWS.items()}})


if __name__ == "__main__":
    main()
