"""D-038 Steps 6-7 (E27): the PCAP route - the mean of the three E20r seeds - scored from stored outputs.

    python scripts/pcap_route_eval.py

The aggregation rule and the acceptance bar were committed before this script first ran (D-038,
86dbaa3). Nothing is trained and nothing is tuned:

- For every held-out day, the per-window ``scores`` (compromise, ``p_max`` over 16 Monte-Carlo
  rollouts) and ``threat_scores`` stored by ``m1v2-e20r-s42/43/44`` are averaged across the three
  seeds and written as the run folder ``results/runs/e27-e20r-mean/``.
- That run, each seed and the flow-only reference E19 are scored by ``scorecard.score_run`` (S1-S4)
  and ``benchmark_table.metrics`` (causal F1, precision, recall, FPR, PR-AUC per day), unchanged.
- r2, the shipped flow-only model for CSV input, is read from ``results/tables/benchmark_final.csv``.
  It is a different input modality from E20r, shown as the reference the PCAP route sits beside.
- D-038's acceptance: (1) the parity check passed (``results/runs/e27-parity/``) and the routing
  tests pass; (2) ensemble Thursday PR-AUC >= 0.20; (3) ensemble S2* >= E19's S2* - 0.03.

Writes results/runs/e27-e20r-mean/, results/runs/e27-pcap-route/ (rows + verdict; the API's model
card reads the PCAP route's Thursday row from it) and results/tables/e27_pcap_route.{csv,md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ablation_matrix import rollout_gain
from benchmark_table import metrics
from netwm.data.processed import ProcessedDataset
from netwm.utils import RUNS, TABLES, ensure_dirs, save_run
from scorecard import load_scores, score_run

SEEDS = (42, 43, 44)
MEMBERS = [f"m1v2-e20r-s{s}" for s in SEEDS]
ENSEMBLE_RUN = "e27-e20r-mean"
ROUTE_RUN = "e27-pcap-route"
#: backend/inference.py reads the PCAP route's model-card row by this label
ENSEMBLE_LABEL = "E20r mean of seeds 42/43/44 (PCAP route)"
PACKET_DATA = "data/processed/cicids2017_m1v2p"
FLOW_DATA = "data/processed/cicids2017_m1v2"
FLOW_REF = [f"m1v2-e19-s{s}" for s in SEEDS]
DAYS = ("thursday", "friday")
N_SHIFTS = 2000


def write_ensemble_run() -> None:
    """The pre-registered rule, and nothing else: an unweighted per-window mean over all three seeds."""
    members = [json.loads((RUNS / r / "metrics.json").read_text(encoding="utf-8"))["metrics"]["per_day"] for r in MEMBERS]
    days = sorted(members[0])
    if any(sorted(m) != days for m in members):
        raise SystemExit("the E20r runs do not cover the same held-out days")
    per_day = {}
    for day in days:
        arrays = {}
        for key in ("scores", "threat_scores"):
            stack = [np.asarray(m[day][key], float) for m in members]
            if len({a.shape for a in stack}) != 1:
                raise SystemExit(f"{day}/{key}: the seeds disagree on the window count")
            arrays[key] = np.mean(stack, axis=0).tolist()
        per_day[day] = {**arrays, "members": MEMBERS}
    save_run(ENSEMBLE_RUN, {
        "per_day": per_day, "complete": True,
        "aggregation": "arithmetic mean over seeds 42/43/44, per window (D-038)",
        "alarm_statistic": "p_max over 16 Monte-Carlo rollouts, as each seed's run stored it",
    }, config={"decision": "D-038", "members": MEMBERS, "command": "python scripts/pcap_route_eval.py"})


def score(label: str, run: str, ds: ProcessedDataset) -> tuple[dict, list[dict]]:
    sc = {"model": label, **score_run(run, ds, N_SHIFTS)}
    sc["rollout_gain_thursday"] = rollout_gain(run, "thursday") if run != ENSEMBLE_RUN else None
    sc["rollout_gain_friday"] = rollout_gain(run, "friday") if run != ENSEMBLE_RUN else None
    comp = load_scores(run)
    det = [{"model": label, "run": run, "day": day, **metrics(ds.target(day), comp[day]["comp"])} for day in DAYS]
    return sc, det


def main() -> None:
    ensure_dirs()
    write_ensemble_run()
    packet, flow = ProcessedDataset(PACKET_DATA), ProcessedDataset(FLOW_DATA)
    plan = [("E19 flow-only (r2 method)", run, flow) for run in FLOW_REF]
    plan += [(f"E20r seed {s}", f"m1v2-e20r-s{s}", packet) for s in SEEDS]
    plan += [(ENSEMBLE_LABEL, ENSEMBLE_RUN, packet)]
    cards, det_rows = [], []
    for label, run, ds in plan:
        sc, det = score(label, run, ds)
        cards.append(sc)
        det_rows += det
        print(f"{label:44s} {run:18s} S2*={sc['S2_star']:.3f} Thu PR-AUC={sc['thursday_comp_pr_auc']:.3f} "
              f"prec={sc['S1_precision']:.3f} fpr={sc['S1_fpr']:.3f} S3 {sc['S3_warned']} p={sc['S3_fisher_p']}")

    bench = pd.read_csv(TABLES / "benchmark_final.csv")
    r2 = bench[bench["model"] == "NetWM r2 - shipped checkpoint"]
    det_rows += [{**r, "model": "r2 shipped, flow-only (CSV route)"} for r in r2.to_dict("records")]

    cards_df, det_df = pd.DataFrame(cards), pd.DataFrame(det_rows)
    ens = cards_df[cards_df["run"] == ENSEMBLE_RUN].iloc[0]
    e19_s2 = float(cards_df[cards_df["run"].isin(FLOW_REF)]["S2_star"].mean())
    parity_path = RUNS / "e27-parity" / "metrics.json"
    parity = json.loads(parity_path.read_text(encoding="utf-8"))["metrics"]["verdict"] if parity_path.exists() else None
    verdict = {
        "c1_engineering_parity": parity["passed"] if parity else None,
        "c1_note": "and the routing tests (backend/tests/test_pcap_route.py) - recorded in results.md",
        "c2_stability": bool(ens["thursday_comp_pr_auc"] >= 0.20),
        "ensemble_thursday_pr_auc": float(ens["thursday_comp_pr_auc"]),
        "c3_anticipation_non_inferior": bool(ens["S2_star"] >= e19_s2 - 0.03),
        "ensemble_S2_star": float(ens["S2_star"]),
        "e19_S2_star": round(e19_s2, 4),
        "bar_S2_star": round(e19_s2 - 0.03, 4),
    }
    verdict["accepted"] = bool(verdict["c1_engineering_parity"] and verdict["c2_stability"]
                               and verdict["c3_anticipation_non_inferior"])
    verdict["outcome"] = ("accepted: the E20r mean serves PCAP uploads, r2 serves CSV (D-038)" if verdict["accepted"]
                          else "not accepted: the team decides; no seed selection, re-weighting, threshold change or retraining (D-038)")

    cards_df.to_csv(TABLES / "e27_pcap_route_scorecard.csv", index=False)
    det_df.to_csv(TABLES / "e27_pcap_route.csv", index=False)
    lines = ["| model | input | Thu PR-AUC | Thu F1 | Thu precision | Thu recall | Thu FPR | Fri PR-AUC | Fri F1 | S1 precision | S1 FPR | S2* | S3 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for label, g in det_df.groupby("model", sort=False):
        c = cards_df[cards_df["model"] == label]
        thu, fri = g[g["day"] == "thursday"], g[g["day"] == "friday"]

        def cell(v):
            return f"{v.mean():.3f}" if len(v) == 1 else f"{v.mean():.3f} [{v.min():.2f}-{v.max():.2f}]"

        s = [cell(thu[k]) for k in ("pr_auc", "f1", "precision", "recall", "fpr")] + [cell(fri["pr_auc"]), cell(fri["f1"])]
        s += [cell(c[k]) for k in ("S1_precision", "S1_fpr", "S2_star")] if len(c) else ["-", "-", "-"]
        s += ["; ".join(f"{w} p={p}" for w, p in zip(c["S3_warned"], c["S3_fisher_p"])) if len(c) else "-"]
        modality = "PCAP (flow + packet)" if "E20r" in label else "CSV (flow)"
        lines.append(f"| {label} | {modality} | " + " | ".join(s) + " |")
    note = ("\n\nCausal expanding q90 threshold (D-034) on the compromise score, label `y_within_K`. r2 has two folds "
            "and one seed, so it has no scorecard row; E19 is the r2 method on the D-035 contract and D-038's "
            "anticipation reference. Generated by `scripts/pcap_route_eval.py` from `results/runs/`.\n")
    (TABLES / "e27_pcap_route.md").write_text("\n".join(lines) + note, encoding="utf-8")
    save_run(ROUTE_RUN, {"rows": det_rows, "scorecard": cards, "verdict": verdict},
             config={"decision": "D-038", "members": MEMBERS, "flow_reference": FLOW_REF,
                     "command": "python scripts/pcap_route_eval.py"})
    print("\n" + "\n".join(lines))
    print("\nD-038 acceptance:\n" + json.dumps(verdict, indent=1))


if __name__ == "__main__":
    main()
