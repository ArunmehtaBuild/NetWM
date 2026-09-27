"""E18 (G-8) - can the alert-budget threshold be computed in real time without losing the signal?

    python scripts/threshold_eval.py

E14's deployable point (Thursday F1 0.576) and the dashboard both set the threshold as the 90th
percentile of the scores of the *whole* capture (`rescore_pmax.py`, `engine/predict.py`), which
includes windows after the one being judged. A live sensor only has the past. This script scores the
same per-window `p_max` scores under thresholds that use only past windows, as pre-registered in
D-034, before any causal number was computed:

  whole-capture-10pct   reference, NON-CAUSAL: q90 of every score in the capture (E14's policy)
  expanding-10pct       PRIMARY: q90 of the scores of windows 0..t-1; no alarm while t < 20
  trailing120-10pct     q90 of the scores of windows t-120..t-1 (at least 20 of them)
  trailing60-10pct      the same over t-60..t-1
  expanding-5pct        q95 of windows 0..t-1 (the causal version of D-021's "5 % budget")
  train-quantile-5pct   reference: q95 of the training-day scores (E14's alert-budget-5pct)

Scores: the held-out-day `p_max` scores E14 published for r2 and for the three E10 full seeds (no
re-inference, so the whole-capture row reproduces E14 exactly). Training-day scores for r2 are
recomputed with E14's exact procedure (seed 42, the same checkpoint order and sample counts); the
held-out scores recomputed alongside must match the published ones, or the script stops.

Outputs:
  results/tables/e18_window_scores_<run>_<day>.csv   per-window score, label, every threshold, alarms
  results/tables/e18_score_distributions.csv         training-day (in-sample) vs held-out quantiles
  results/tables/e18_policy_summary.csv              every run x day x policy
  results/figures/e18_<day>_thresholds.png           r2: score, thresholds over time, attack windows
  results/figures/e18_score_distributions.png        r2: training-day vs held-out score ECDFs
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint
from netwm.metrics import lead_times, summarise_lead
from netwm.utils import FIGURES, RUNS, TABLES, ensure_dirs, set_seed
from rescore_pmax import scores_for

WARMUP = 20
R2 = "e4e7-worldmodel-r2"
SEEDS = {"e10-full-s42": 42, "e10-full-s43": 43, "e10-full-s44": 44}
DAYS = ("thursday", "friday")


def whole(score: np.ndarray, q: float) -> np.ndarray:
    return np.full(len(score), float(np.quantile(score, q)))


def expanding(score: np.ndarray, q: float, warmup: int = WARMUP) -> np.ndarray:
    thr = np.full(len(score), np.inf)  # inf = no alarm possible
    for t in range(warmup, len(score)):
        thr[t] = np.quantile(score[:t], q)
    return thr


def trailing(score: np.ndarray, q: float, n: int, warmup: int = WARMUP) -> np.ndarray:
    thr = np.full(len(score), np.inf)
    for t in range(warmup, len(score)):
        thr[t] = np.quantile(score[max(0, t - n):t], q)
    return thr


def binary_metrics(y: np.ndarray, alarm: np.ndarray) -> dict:
    y, a = y.astype(bool), alarm.astype(bool)
    tp, fp = int((a & y).sum()), int((a & ~y).sum())
    fn, tn = int((~a & y).sum()), int((~a & ~y).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {
        "alarm_rate": round(float(a.mean()), 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
        "fpr": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "tp": tp, "fp": fp, "fn": fn,
    }


def published_scores(run: str) -> dict:
    m = json.loads((RUNS / f"e14-pmax-rescore-{run}" / "metrics.json").read_text(encoding="utf-8"))
    per_day = (m.get("metrics") or m)["per_day"]
    return {d: (np.asarray(per_day[d]["scores"], float), per_day[d]["thresholds"]) for d in DAYS}


def policies(score: np.ndarray, train_q95: float) -> dict[str, np.ndarray]:
    return {
        "whole-capture-10pct": whole(score, 0.90),
        "expanding-10pct": expanding(score, 0.90),
        "trailing120-10pct": trailing(score, 0.90, 120),
        "trailing60-10pct": trailing(score, 0.90, 60),
        "expanding-5pct": expanding(score, 0.95),
        "train-quantile-5pct": np.full(len(score), train_q95),
    }


def r2_training_scores(ds: ProcessedDataset, published: dict) -> dict:
    """E14's exact procedure, so its training-day scores are the ones behind its train thresholds."""
    set_seed(42)
    out = {}
    for ckpt_path in sorted(Path("models", R2).glob("*.pt")):
        day = ckpt_path.stem
        ckpt = load_checkpoint(ckpt_path)
        train_days = [d for d in ds.splits if d != day]
        train = {d: scores_for(ckpt["model"], ckpt["scaler"], ds, d, ckpt["device"], 4) for d in train_days}
        held = scores_for(ckpt["model"], ckpt["scaler"], ds, day, ckpt["device"], 16)
        if not np.allclose(held, published[day][0], atol=1e-6):
            raise SystemExit(f"{day}: recomputed held-out scores differ from E14's published ones - "
                             "the training-day scores would not be E14's either")
        out[day] = train
    return out


def main() -> None:
    ensure_dirs()
    ds = ProcessedDataset("data/processed/cicids2017")
    runs = {R2: published_scores(R2), **{r: published_scores(r) for r in SEEDS}}
    train_scores = r2_training_scores(ds, runs[R2])

    summary, dist_rows = [], []
    for run, per_day in runs.items():
        for day in DAYS:
            score, thresholds = per_day[day]
            frame = ds.frame(day)
            y = ds.target(day).astype(int)
            pols = policies(score, float(thresholds["alert-budget-5pct"]))
            for name, thr in pols.items():
                alarm = score >= thr
                lead = summarise_lead(lead_times(alarm.astype(float), ds.onsets(day), 0.5, ds.horizon,
                                                 persistence=2), ds.stride_s)
                summary.append({"run": run, "test_day": day, "policy": name,
                                "causal": name != "whole-capture-10pct", "primary": name == "expanding-10pct",
                                **binary_metrics(y, alarm),
                                "warned_early": lead["episodes_warned_early"], "episodes": lead["episodes"]})
            if run == R2:
                table = pd.DataFrame({"t": np.arange(len(score)), "ts": frame["ts"].values, "score": score,
                                      "y_within_K": y, "stage": frame["stage"].values})
                for name, thr in pols.items():
                    table[f"thr_{name}"] = np.where(np.isinf(thr), np.nan, thr)
                    table[f"alarm_{name}"] = (score >= thr).astype(int)
                table.to_csv(TABLES / f"e18_window_scores_{run}_{day}.csv", index=False)

    qs = [0.0, 0.1, 0.5, 0.9, 0.95, 0.99, 1.0]
    for day in DAYS:
        pools = {f"training days (in-sample): {', '.join(train_scores[day])}": np.concatenate(list(train_scores[day].values())),
                 f"held-out {day}": runs[R2][day][0]}
        for name, s in pools.items():
            dist_rows.append({"fold": day, "scores": name, "n": len(s), "mean": round(float(s.mean()), 5),
                              **{f"q{int(q * 100)}": round(float(np.quantile(s, q)), 5) for q in qs}})
    pd.DataFrame(dist_rows).to_csv(TABLES / "e18_score_distributions.csv", index=False)
    out = pd.DataFrame(summary)
    out.to_csv(TABLES / "e18_policy_summary.csv", index=False)
    plot_timelines(ds)
    plot_distributions(train_scores, runs[R2])

    pd.set_option("display.width", 220)
    show = out[out["run"] == R2].drop(columns=["run", "causal", "tp", "fp", "fn"])
    print(show.to_string(index=False))
    seeds = out[out["run"].isin(SEEDS) & (out["test_day"] == "thursday")]
    print("\nThursday F1 over E10 seeds (42/43/44):")
    print(seeds.pivot(index="policy", columns="run", values="f1").to_string())
    print(pd.DataFrame(dist_rows).to_string(index=False))


def plot_timelines(ds: ProcessedDataset) -> None:
    for day in DAYS:
        t = pd.read_csv(TABLES / f"e18_window_scores_{R2}_{day}.csv", parse_dates=["ts"])
        fig, ax = plt.subplots(figsize=(13, 4), dpi=130)
        ax.fill_between(t["ts"], 0, 1, where=t["y_within_K"] == 1, transform=ax.get_xaxis_transform(),
                        color="#e2574c", alpha=0.12, label="compromise within K (ground truth)")
        ax.plot(t["ts"], t["score"], color="#2f6fdb", lw=0.9, label="p_max score")
        styles = {"whole-capture-10pct": ("k", "--", "whole-capture q90 (non-causal, E14)"),
                  "expanding-10pct": ("#e2574c", "-", "expanding q90 (primary, causal)"),
                  "trailing120-10pct": ("#8e5bd9", ":", "trailing-120 q90 (causal)")}
        for name, (color, ls, label) in styles.items():
            ax.plot(t["ts"], t[f"thr_{name}"], color=color, ls=ls, lw=1.2, label=label)
        hit = t["alarm_expanding-10pct"] == 1
        ax.scatter(t.loc[hit, "ts"], t.loc[hit, "score"], s=8, color="#e2574c", zorder=3, label="alarm (expanding q90)")
        ax.set_yscale("log")
        ax.set_ylim(max(1e-4, t["score"].min() * 0.8), 1.0)
        ax.set_title(f"E18 - held-out {day}: r2 p_max against causal and non-causal alert budgets")
        ax.legend(fontsize=7, loc="upper left", ncol=2)
        fig.tight_layout()
        fig.savefig(FIGURES / f"e18_{day}_thresholds.png")
        plt.close(fig)


def plot_distributions(train_scores: dict, r2: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), dpi=130)
    for ax, day in zip(axes, DAYS):
        for label, s, color in (("training days (in-sample)", np.concatenate(list(train_scores[day].values())), "#888"),
                                (f"held-out {day}", r2[day][0], "#2f6fdb")):
            xs = np.sort(s)
            ax.plot(xs, np.arange(1, len(xs) + 1) / len(xs), color=color, label=label)
        th = r2[day][1]
        for name, color in (("train-tuned", "#e2574c"), ("alert-budget-5pct", "#f2a541"), ("self-budget-10pct", "k")):
            ax.axvline(th[name], color=color, ls="--", lw=1, label=f"{name} = {th[name]:.3g}")
        ax.set_xscale("log")
        ax.set_title(f"{day} fold: p_max score ECDF")
        ax.set_xlabel("p_max")
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(FIGURES / "e18_score_distributions.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
