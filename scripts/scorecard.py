"""The D-035 scorecard: S1-S4 for every run, and the adoption bar between two variants.

    python scripts/scorecard.py --data data/processed/cicids2017_m1v2 \
        --variant E19=m1v2-e19-s42,m1v2-e19-s43,m1v2-e19-s44 \
        --variant E20=m1v2-e20-s42,m1v2-e20-s43,m1v2-e20-s44 \
        --compare E20:E19 --tag e20

Reads only ``results/runs/<run>/metrics.json`` (the held-out scores ``scripts/train.py`` stores per
fold) and the processed labels, so it needs no GPU and scores every run identically.

  S1  causal alarm cost: ``comp`` at the expanding q90 (D-034), pooled over Thursday + Friday, against
      ``y_within_K`` - precision and FPR.
  S2  anticipation by lead bin: eligible (non-attack) windows 1-4 / 5-8 / 9-12 / 13-20 windows before
      each non-Impact attack onset, scored by ``threat`` as a percentile among the same day's reference
      windows (eligible, >= 20 windows from every onset). 0.5 = chance. S2* = mean of the 2-10 min bins.
  S3  early warning: strict warned-early at the causal q90 on ``threat`` against a 2,000-shift circular
      null of the alarm series, per attack fold, Fisher-combined.
  S4  S2* per held-out day; the worst day beside the pooled value.

The bar (D-035): candidate adopted iff the 3-seed mean S2* rises >= 0.03 and rises on >= 2 of 3 seeds;
S1 precision falls < 0.05 and S1 FPR rises < 0.02 (3-seed means); and no candidate seed has Thursday
``comp`` PR-AUC < 0.20.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.features.windowing import attack_flags
from netwm.metrics import causal_threshold, forecast_metrics
from netwm.models.leadtime import circular_shift_null, fisher_combine, strict_lead_times
from netwm.models.targets import episode_labels, windows_since_previous_attack
from netwm.utils import RUNS, TABLES, ensure_dirs, save_run

BINS = {"0-2min": (1, 4), "2-4min": (5, 8), "4-6min": (9, 12), "6-10min": (13, 20)}
GATING_BINS = ("2-4min", "4-6min", "6-10min")
REF_GAP = 20


def split_roles(ds: ProcessedDataset) -> tuple[list[str], list[str]]:
    """Splits with a non-Impact attack onset (S2-S4) and splits with a compromise onset (S1).

    Read from the labels, so CIC-IDS2017 gives Tue-Fri and Thu+Fri - the D-035 sets - and CTU-13
    gives its scenarios without a second code path.
    """
    attack, compromise = [], []
    for day in ds.splits:
        stages = ds.frame(day)["stage"]
        if episode_labels(stages, ds.horizon, source="attack").without("IMPACT").onsets:
            attack.append(day)
        if ds.onsets(day):
            compromise.append(day)
    return attack, compromise


def load_scores(run: str) -> dict:
    m = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))
    per_day = (m.get("metrics") or m)["per_day"]
    out = {}
    for day, d in per_day.items():
        if d.get("threat_scores") is None:
            raise SystemExit(f"{run}/{day}: no threat_scores - trained before the D-035 harness")
        out[day] = {"comp": np.asarray(d["scores"], float), "threat": np.asarray(d["threat_scores"], float)}
    return out


def percentiles(score: np.ndarray, onsets: "list[int]", eligible: np.ndarray, ref_mask: np.ndarray) -> dict:
    """{bin: [percentile of each eligible pre-onset window]} against the day's reference windows."""
    ref = np.sort(score[ref_mask])
    out = {b: [] for b in BINS}
    if ref.size == 0:
        return out
    for onset in onsets:
        for b, (lo, hi) in BINS.items():
            for off in range(lo, hi + 1):
                t = onset - off
                if t < 0 or not eligible[t]:
                    continue
                below = np.searchsorted(ref, score[t], side="left")
                equal = np.searchsorted(ref, score[t], side="right") - below
                out[b].append((below + 0.5 * equal) / ref.size)
    return out


def reference_mask(n: int, all_onsets: "list[int]", eligible: np.ndarray) -> np.ndarray:
    mask = eligible.copy()
    for o in all_onsets:
        mask[max(0, o - REF_GAP + 1): o + REF_GAP] = False
    return mask


def score_run(run: str, ds: ProcessedDataset, n_shifts: int) -> dict:
    scores = load_scores(run)
    ATTACK_DAYS, COMPROMISE_DAYS = split_roles(ds)
    row: dict = {"run": run}
    # ---- S1: causal alarm cost on compromise, Thursday + Friday pooled
    ys, alarms = [], []
    for day in COMPROMISE_DAYS:
        if day not in scores:
            continue
        comp = scores[day]["comp"]
        y = ds.target(day)
        alarm = comp >= causal_threshold(comp, 0.90)
        m = forecast_metrics(y, comp, 0.5)  # threshold-free parts only (PR-AUC)
        tp, fp = int((alarm & (y == 1)).sum()), int((alarm & (y == 0)).sum())
        fn = int((~alarm & (y == 1)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        row[f"{day}_comp_pr_auc"] = round(m.pr_auc, 4)
        row[f"{day}_causal_f1"] = round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0
        row[f"{day}_causal_alarm_rate"] = round(float(alarm.mean()), 4)
        ys.append(y)
        alarms.append(alarm)
    if not ys:
        raise SystemExit(f"{run}: no held-out split with a compromise onset")
    y, a = np.concatenate(ys), np.concatenate(alarms)
    tp, fp, tn = int((a & (y == 1)).sum()), int((a & (y == 0)).sum()), int((~a & (y == 0)).sum())
    row["S1_precision"] = round(tp / (tp + fp), 4) if tp + fp else 0.0
    row["S1_fpr"] = round(fp / (fp + tn), 4) if fp + tn else 0.0

    # ---- S2 / S4 (threat, non-Impact attack onsets) and the compromise table (comp)
    pooled = {b: [] for b in BINS}
    pooled_comp = {b: [] for b in BINS}
    # diagnostic, not part of the bar: onsets with a quiet run-up of >= REF_GAP windows, so a raised
    # score cannot be the tail of the previous episode (the E16 per-onset concern)
    pooled_isolated = {b: [] for b in BINS}
    n_isolated = 0
    p_values, above_p95, warned, episodes = [], 0, 0, 0
    for day in ATTACK_DAYS:
        if day not in scores:
            continue
        frame = ds.frame(day)
        attack = episode_labels(frame["stage"], ds.horizon, source="attack")
        eligible = attack.eligible
        non_impact = attack.without("IMPACT")
        ref = reference_mask(len(frame), attack.onsets, eligible)
        per_day = percentiles(scores[day]["threat"], non_impact.onsets, eligible, ref)
        for b in BINS:
            pooled[b] += per_day[b]
        quiet = windows_since_previous_attack(non_impact.onsets, attack_flags(frame["stage"]))
        isolated = [o for o, q in zip(non_impact.onsets, quiet) if q >= REF_GAP]
        n_isolated += len(isolated)
        for b, v in percentiles(scores[day]["threat"], isolated, eligible, ref).items():
            pooled_isolated[b] += v
        gating = [v for b in GATING_BINS for v in per_day[b]]
        row[f"S4_{day}"] = round(float(np.mean([np.mean(per_day[b]) for b in GATING_BINS if per_day[b]])), 4) \
            if gating else None
        if day in COMPROMISE_DAYS:
            comp_onsets = ds.onsets(day)
            for b, v in percentiles(scores[day]["comp"], comp_onsets, eligible, ref).items():
                pooled_comp[b] += v

        # ---- S3: strict warned-early at the causal q90 on threat, against the alarm-series null
        threat = scores[day]["threat"]
        margin = threat - causal_threshold(threat, 0.90)
        margin = np.where(np.isfinite(margin), margin, -1.0)
        if non_impact.onsets:
            rows = strict_lead_times(margin, non_impact.onsets, 0.0, ds.horizon, persistence=2, eligible=eligible)
            null = circular_shift_null(margin, non_impact.onsets, 0.0, ds.horizon, n_shifts=n_shifts, seed=42,
                                       persistence=2, eligible=eligible)
            warned += sum(r["detected_early"] for r in rows)
            episodes += len(rows)
            p_values.append(null["p_value"])
            above_p95 += int(null.get("exceeds_null_p95", False))
            row[f"S3_{day}"] = f"{null['observed']}/{len(rows)} p={null['p_value']:.3f}"
    for b in BINS:
        row[f"S2_{b}"] = round(float(np.mean(pooled[b])), 4) if pooled[b] else None
        row[f"S2_n_{b}"] = len(pooled[b])
        row[f"comp_S2_{b}"] = round(float(np.mean(pooled_comp[b])), 4) if pooled_comp[b] else None
    row["S2_star"] = round(float(np.mean([row[f"S2_{b}"] for b in GATING_BINS])), 4)
    iso = [np.mean(pooled_isolated[b]) for b in GATING_BINS if pooled_isolated[b]]
    row["diag_S2_star_isolated"] = round(float(np.mean(iso)), 4) if iso else None
    row["diag_isolated_onsets"] = n_isolated
    day_vals = [row[f"S4_{d}"] for d in ATTACK_DAYS if row.get(f"S4_{d}") is not None]
    row["S4_worst_day"] = round(float(min(day_vals)), 4) if day_vals else None
    fisher = fisher_combine(p_values)
    row["S3_warned"] = f"{warned}/{episodes}"
    row["S3_folds_above_p95"] = above_p95
    row["S3_fisher_p"] = round(fisher["p_value"], 4)
    row["S3_passes"] = bool(fisher["p_value"] < 0.05 and above_p95 >= 2)
    return row


def bar(candidate: pd.DataFrame, base: pd.DataFrame) -> dict:
    """D-035's three clauses, seed-paired."""
    c = candidate.set_index("seed").sort_index()
    b = base.set_index("seed").sort_index()
    seeds = sorted(set(c.index) & set(b.index))
    d_s2 = (c.loc[seeds, "S2_star"] - b.loc[seeds, "S2_star"])
    clause1 = bool(d_s2.mean() >= 0.03 and (d_s2 > 0).sum() >= 2)
    d_prec = c.loc[seeds, "S1_precision"].mean() - b.loc[seeds, "S1_precision"].mean()
    d_fpr = c.loc[seeds, "S1_fpr"].mean() - b.loc[seeds, "S1_fpr"].mean()
    clause2 = bool(d_prec > -0.05 and d_fpr < 0.02)
    clause3 = bool((c.loc[seeds, "thursday_comp_pr_auc"] >= 0.20).all()) if "thursday_comp_pr_auc" in c else None
    return {
        "seeds": seeds,
        "delta_S2_star_mean": round(float(d_s2.mean()), 4),
        "delta_S2_star_per_seed": [round(float(v), 4) for v in d_s2],
        "clause1_anticipation": clause1,
        "delta_S1_precision": round(float(d_prec), 4),
        "delta_S1_fpr": round(float(d_fpr), 4),
        "clause2_alarm_cost": clause2,
        "clause3_stability": clause3,
        "adopted": clause1 and clause2 and clause3,
        "non_inferior": clause2 and clause3,   # the packet-block rule
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/processed/cicids2017_m1v2")
    ap.add_argument("--variant", action="append", required=True, help="NAME=run,run,run")
    ap.add_argument("--compare", action="append", default=[], help="CANDIDATE:BASE")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--shifts", type=int, default=2000)
    args = ap.parse_args()

    ensure_dirs()
    ds = ProcessedDataset(args.data)
    rows = []
    for spec in args.variant:
        name, runs = spec.split("=", 1)
        for run in runs.split(","):
            row = score_run(run, ds, args.shifts)
            row["variant"] = name
            row["seed"] = int(re.search(r"-s(\d+)(?:-|$)", run).group(1))  # m1v2-e26-s42-csvmode -> 42
            rows.append(row)
            print(f"{name:6s} {run:24s} S1 prec={row['S1_precision']:.3f} fpr={row['S1_fpr']:.3f} | "
                  f"S2 {[row[f'S2_{b}'] for b in BINS]} S2*={row['S2_star']:.3f} | worst day {row['S4_worst_day']} | "
                  f"S3 {row['S3_warned']} p={row['S3_fisher_p']} | Thu PR-AUC {row.get('thursday_comp_pr_auc')}")
    table = pd.DataFrame(rows)
    front = ["variant", "run", "seed", "S1_precision", "S1_fpr", *[f"S2_{b}" for b in BINS], "S2_star",
             "S4_worst_day", "S3_warned", "S3_folds_above_p95", "S3_fisher_p", "S3_passes"]
    table = table[front + [c for c in table.columns if c not in front]]
    table.to_csv(TABLES / f"scorecard_{args.tag}.csv", index=False)

    cols = ["S1_precision", "S1_fpr", *[f"S2_{b}" for b in BINS], "S2_star", "S4_worst_day",
            *[c for c in ("thursday_comp_pr_auc", "thursday_causal_f1") if c in table]]
    summary = (table.groupby("variant")[cols]
               .agg(["mean", "min", "max"]).round(4))
    pd.set_option("display.width", 250)
    print("\n" + summary.to_string())
    verdicts = {}
    for spec in args.compare:
        cand, base = spec.split(":")
        verdicts[spec] = bar(table[table["variant"] == cand], table[table["variant"] == base])
        print(f"\n{cand} vs {base}: {json.dumps(verdicts[spec])}")
    save_run(f"scorecard-{args.tag}", {"rows": rows, "verdicts": verdicts,
                                       "summary": json.loads(summary.to_json(orient="index"))},
             config=vars(args))


if __name__ == "__main__":
    main()
