"""E15a / E15 - lead time measured against a null, per episode family (D-022, board card Y-5).

Two modes, one measurement harness:

  # E15a - calibrate the null against the *published* E14 scores. No model, no GPU, no MC noise:
  # the p-value then attaches to the number in results.md, not to a re-run of it.
  python scripts/precursor_eval.py --scores-from-run e14-pmax-rescore-e4e7-worldmodel-r2

  # E15 - score round-3 checkpoints, including the two new precursor statistics.
  python scripts/precursor_eval.py --run r3-precursor-s42

Every lead-time count is emitted with the false-positive rate and the alarm rate at the same
threshold (Y-5), on three episode denominators (all attack episodes / Impact excluded / the five
compromise onsets), broken down per attack family, and beside a circular-shift null.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.metrics import best_threshold, forecast_metrics, summarise_lead
from netwm.models.leadtime import alarm_rate, circular_shift_null, fisher_combine, strict_lead_times
from netwm.features.windowing import attack_flags
from netwm.models.targets import episode_labels, windows_since_previous_attack
from netwm.utils import RUNS, TABLES, ensure_dirs, save_run, set_seed

#: Raw features that already produce "warned early" counts on their own. If the model cannot beat
#: an unscaled single column, there is no result (E12 ranked these highest).
FLOOR_FEATURES = ("uniq_dst_port", "uniq_dst_ip", "fanout_mean")


def episode_sets(ds: ProcessedDataset, day: str) -> dict:
    """The three denominators every table row is reported on."""
    frame = ds.frame(day)
    attack = episode_labels(frame["stage"], ds.horizon, source="attack")
    return {
        "attack": attack,
        "attack_no_impact": attack.without("IMPACT"),
        "compromise": episode_labels(frame["stage"], ds.horizon, source="compromise"),
    }


def family_breakdown(rows: "list[dict]", families: "list[str]") -> dict:
    """warned/total per attack family, so an aggregate carried by DoS cannot hide in a mean."""
    out: dict = {}
    for row, fam in zip(rows, families):
        w, t = out.get(fam, (0, 0))
        out[fam] = (w + int(row["detected_early"]), t + 1)
    return {k: str(w) + "/" + str(t) for k, (w, t) in sorted(out.items())}


def score_rows(
    day: str,
    statistic: str,
    score: np.ndarray,
    thresholds: dict,
    ds: ProcessedDataset,
    sets: dict,
    experiment: str,
    run: str,
    n_shifts: int,
    seed: int,
) -> list[dict]:
    y = ds.target(day)                                   # y_within_K - the E14-comparable label
    prec_y = sets["attack"].precursor.astype(int)        # the round-3 supervision target
    eligible = sets["attack"].eligible
    rows: list[dict] = []

    for policy, thr in thresholds.items():
        m = forecast_metrics(y, score, thr)
        prec_m = forecast_metrics(prec_y, score, thr)
        base = {
            "experiment": experiment,
            "run": run,
            "test_day": day,
            "statistic": statistic,
            "threshold_mode": policy,
            "threshold": round(float(thr), 4),
            # Y-5: the alarm rate and the FPR travel with every early-warning count, on this row.
            "alarm_rate": round(alarm_rate(score, thr), 4),
            "base_rate": round(float(y.mean()), 4),
            **{k: round(v, 4) if isinstance(v, float) else v for k, v in m.as_dict().items()},
            "precursor_base_rate": round(float(prec_y.mean()), 4),
            "precursor_pr_auc": round(float(prec_m.pr_auc), 4),
            "precursor_roc_auc": round(float(prec_m.roc_auc), 4),
        }

        for set_name, labels in sets.items():
            lead_rows = strict_lead_times(
                score, labels.onsets, thr, ds.horizon, persistence=2, eligible=eligible
            )
            lead = summarise_lead(lead_rows, ds.stride_s)
            null = (
                circular_shift_null(
                    score, labels.onsets, thr, ds.horizon, n_shifts=n_shifts, seed=seed,
                    persistence=2, eligible=eligible,
                )
                if labels.onsets
                else {}
            )
            rows.append(
                {
                    **base,
                    "episode_set": set_name,
                    "episodes": lead["episodes"],
                    "warned_early": lead["episodes_warned_early"],
                    "mean_lead_windows": round(lead["mean_lead_windows"], 2),
                    "mean_lead_seconds": round(lead["mean_lead_seconds"], 1),
                    # D-019: only the first onset of a chain is a genuine "before they got in" case
                    "first_onset_lead_windows": lead_rows[0]["lead_windows"] if lead_rows else 0,
                    "null_mean": round(null.get("null_mean", float("nan")), 2),
                    "null_p95": null.get("null_p95", 0),
                    "null_p_value": round(null.get("p_value", float("nan")), 4),
                    "exceeds_null_p95": null.get("exceeds_null_p95", False),
                    "families": json.dumps(family_breakdown(lead_rows, labels.families)),
                }
            )
    return rows


def per_onset_rows(
    day: str, statistic: str, score: np.ndarray, threshold: float, policy: str,
    ds: ProcessedDataset, sets: dict, run: str,
) -> list[dict]:
    """One row per onset: family, quiet run-up, and whether this score warned.

    Post-hoc diagnostic (not part of the D-023 bar). An r4-vs-r2 gap on Thursday can mean "lost a
    precursor" or "lost campaign residue"; those read oppositely for a forecasting claim and an
    aggregate cannot distinguish them.
    """
    labels = sets["attack"]
    gaps = windows_since_previous_attack(labels.onsets, attack_flags(ds.frame(day)["stage"]))
    lead_rows = strict_lead_times(
        score, labels.onsets, threshold, ds.horizon, persistence=2, eligible=labels.eligible
    )
    return [
        {
            "run": run, "test_day": day, "statistic": statistic, "threshold_mode": policy,
            "onset": r["onset"], "family": fam, "quiet_windows_before": gap,
            "warned_early": int(r["detected_early"]), "lead_windows": r["lead_windows"],
            "first_alarm": r["first_alarm"], "eligible_windows": r["eligible_windows"],
        }
        for r, fam, gap in zip(lead_rows, labels.families, gaps)
    ]


def load_published_scores(run_id: str) -> dict:
    """Read the exact score arrays and thresholds a previous run wrote, so nothing is re-sampled."""
    path = RUNS / run_id / "metrics.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    per_day = payload["metrics"]["per_day"]
    return {
        day: {
            "scores": {"p_max": np.asarray(v["scores"], dtype=float)},
            "thresholds": dict(v["thresholds"]),
        }
        for day, v in per_day.items()
    }


def forecast_all(
    run: str, ds: ProcessedDataset, samples: int, budget: float, deterministic: bool
) -> dict:
    """Roll out every checkpoint in ``models/<run>/`` and derive each available alarm statistic."""
    import torch

    from netwm.engine.predict import load_checkpoint

    out: dict = {}
    for ckpt_path in sorted(Path("models", run).glob("*.pt")):
        day = ckpt_path.stem
        ckpt = load_checkpoint(ckpt_path)
        model, device, scaler = ckpt["model"], ckpt["device"], ckpt["scaler"]

        def forecast(split: str, n: int) -> dict:
            x = scaler.transform(ds.states(split))
            kwargs = {"sample": False} if deterministic else {}
            return model.forecast(
                torch.from_numpy(x).unsqueeze(0).to(device), horizon=ds.horizon,
                n_samples=n, **kwargs,
            )

        fc = forecast(day, samples)
        stats = {"p_max": fc["p_max"].numpy()}
        # Round-3 statistics. p_onset_cum is the forecasting claim (a first-occurrence hazard
        # unioned over the rollout); p_precursor is read off the filtered posterior and is a
        # representation result, not a rollout - reported separately, never merged (D-022).
        if "p_onset_cum" in fc:
            stats["p_onset_cum"] = fc["p_onset_cum"].numpy()[:, -1]
            stats["p_onset_max"] = fc["p_onset_max"].numpy()
            stats["p_precursor"] = fc["risk_now"].numpy()[:, 4]

        train_days = [d for d in ds.splits if d != day]
        train_score = np.concatenate(
            [forecast(d, max(4, samples // 4))["p_max"].numpy() for d in train_days]
        )
        train_y = np.concatenate([ds.target(d) for d in train_days])
        y = ds.target(day)
        out[day] = {
            "scores": stats,
            "thresholds": {
                "train-tuned": best_threshold(train_y, train_score),
                f"alert-budget-{int((1 - budget) * 100)}pct": float(
                    np.quantile(train_score, budget)
                ),
                "self-budget-10pct": float(np.quantile(stats["p_max"], 0.90)),
                "self-budget-5pct": float(np.quantile(stats["p_max"], 0.95)),
                "self-budget-2pct": float(np.quantile(stats["p_max"], 0.98)),
                "oracle": best_threshold(y, stats["p_max"]),
            },
        }
    return out


def logreg_precursor_score(
    ds: ProcessedDataset, day: str, seed: int, scaler_kwargs: dict | None = None
) -> np.ndarray:
    """Logistic regression on S_t, trained leave-one-day-out on the *same* precursor label.

    This is the baseline E12 does not provide. E12's 0.88-0.96 probe is cross-validated within a
    single day with a scaler fitted on that day - it shows a signal exists, not that a model trained
    on other days finds it. That is the entire question round 3 is asking, so it needs a baseline
    measured the same way the world model is.

    ``scaler_kwargs`` selects the feature transform, so the floor can be matched to whichever
    representation the model under test used (D-025): the default reproduces E15's row, and
    ``{"mode": "rank", "rank_window": 120}`` is the like-for-like floor for r4. Each day is
    transformed on its own, so rank mode keeps its per-capture property without needing ``groups``.
    """
    from sklearn.linear_model import LogisticRegression

    from netwm.features.scaler import StateScaler

    train_days = [d for d in ds.splits if d != day]
    scaler = StateScaler(**(scaler_kwargs or {})).fit(ds.concat(train_days)[ds.feature_names])
    x_train = np.vstack([scaler.transform(ds.states(d)) for d in train_days])
    y_train = np.concatenate([
        episode_labels(ds.frame(d)["stage"], ds.horizon, source="attack").precursor
        for d in train_days
    ])
    if len(np.unique(y_train)) < 2:
        return np.zeros(len(ds.frame(day)), dtype=float)
    model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)
    model.fit(x_train, y_train)
    return model.predict_proba(scaler.transform(ds.states(day)))[:, 1]


def floor_rows(
    day: str, ds: ProcessedDataset, sets: dict, experiment: str, run: str, n_shifts: int, seed: int
) -> list[dict]:
    """The floors the model must clear: single unscaled features, and LODO logistic regression."""
    frame = ds.frame(day)
    y = ds.target(day)
    rows: list[dict] = []

    # Two logistic floors: log_standard keeps E15's row comparable, rank is the like-for-like
    # floor for a rank-normalised model (D-025). If rank helps the linear model but not the world
    # model, the problem is the model; if it helps neither, the transform is not the answer.
    for name, kwargs in (
        ("logreg:precursor", None),
        ("logreg:precursor-rank", {"mode": "rank", "rank_window": 120, "rank_min_periods": 10}),
    ):
        lr = logreg_precursor_score(ds, day, seed, kwargs)
        rows.extend(score_rows(
            day, name, lr,
            {f"self-budget-{p}pct": float(np.quantile(lr, 1 - p / 100)) for p in (10, 5, 2)},
            ds, sets, experiment, run, n_shifts, seed,
        ))

    for name in FLOOR_FEATURES:
        if name not in frame.columns:
            continue
        score = frame[name].to_numpy(dtype=float)
        thresholds = {
            "self-budget-10pct": float(np.quantile(score, 0.90)),
            "self-budget-5pct": float(np.quantile(score, 0.95)),
            # No label-tuned policy for a raw feature: the point is what it gets for free.
            "self-budget-2pct": float(np.quantile(score, 0.98)),
        }
        rows.extend(
            score_rows(day, f"feature:{name}", score, thresholds, ds, sets,
                       experiment, run, n_shifts, seed)
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", nargs="+", default=None,
                    help="model run(s) under models/ to roll out; several = one per training seed")
    ap.add_argument("--scores-from-run", default=None,
                    help="reuse the score arrays a previous run wrote (no model, no MC noise)")
    ap.add_argument("--experiment", default=None, help="experiment id for the rows (default E15a/E15)")
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--budget", type=float, default=0.95)
    ap.add_argument("--deterministic", action="store_true",
                    help="mean-path rollout (sample=False): no MC seed variance")
    ap.add_argument("--n-shifts", type=int, default=2000)
    ap.add_argument("--no-floors", action="store_true", help="skip the single-feature floor rows")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if (args.run is None) == (args.scores_from_run is None):
        ap.error("pass exactly one of --run or --scores-from-run")

    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)

    rows: list[dict] = []
    if args.scores_from_run:
        source, experiment = args.scores_from_run, args.experiment or "E15a"
        sources = {args.scores_from_run: load_published_scores(args.scores_from_run)}
    else:
        experiment = args.experiment or "E15"
        # One entry per training seed. D-023 measures stability over training seeds, not Monte-Carlo
        # seeds: onset_now fires on ~18 windows per fold, which is the regime where one seed lands
        # and the next does not.
        source = args.run[0] if len(args.run) == 1 else (
            os.path.commonprefix(args.run).rstrip("-s0123456789") + f"-{len(args.run)}seeds"
        )
        sources = {
            run: forecast_all(run, ds, args.samples, args.budget, args.deterministic)
            for run in args.run
        }

    onset_rows: list[dict] = []
    for run, per_day in sources.items():
        for day, payload in sorted(per_day.items()):
            sets = episode_sets(ds, day)
            for statistic, score in payload["scores"].items():
                rows.extend(score_rows(day, statistic, score, payload["thresholds"], ds, sets,
                                       experiment, run, args.n_shifts, args.seed))
                for policy in ("self-budget-10pct", "self-budget-5pct"):
                    if policy in payload["thresholds"]:
                        onset_rows.extend(per_onset_rows(
                            day, statistic, score, payload["thresholds"][policy], policy,
                            ds, sets, run,
                        ))
            if not args.no_floors:
                rows.extend(floor_rows(day, ds, sets, experiment, run, args.n_shifts, args.seed))

    table = pd.DataFrame(rows)
    kind = "null-calibration" if args.scores_from_run else "precursor"
    run_id = f"{experiment.lower()}-{kind}-{source}"
    out_csv = TABLES / f"{run_id}.csv"
    table.to_csv(out_csv, index=False)

    # Fisher across folds, per run - the primary bar of D-023. Folds with no episodes (Monday)
    # carry no p-value and are dropped rather than counted as a failure to warn.
    combined = []
    for (run, stat, policy, eset), grp in table.groupby(
        ["run", "statistic", "threshold_mode", "episode_set"]
    ):
        valid = grp.dropna(subset=["null_p_value"])
        if valid.empty:
            continue
        f = fisher_combine(list(valid["null_p_value"]))
        combined.append({
            "run": run, "statistic": stat, "threshold_mode": policy, "episode_set": eset,
            "folds": int(len(valid)),
            "warned_early": int(valid["warned_early"].sum()),
            "episodes": int(valid["episodes"].sum()),
            "folds_exceeding_null_p95": int(valid["exceeds_null_p95"].sum()),
            "fisher_chi2": round(f["chi2"], 3), "fisher_p": round(f["p_value"], 5),
            "mean_precursor_roc_auc": round(float(valid["precursor_roc_auc"].mean()), 4),
        })
    pd.DataFrame(combined).to_csv(TABLES / f"{run_id}_combined.csv", index=False)
    pd.DataFrame(onset_rows).to_csv(TABLES / f"{run_id}_per_onset.csv", index=False)
    save_run(run_id, {"rows": rows, "combined": combined}, config=vars(args))

    show = table[table["threshold_mode"].isin(["self-budget-10pct", "oracle"])]
    show = show[show["episode_set"].isin(["attack", "compromise"])]
    cols = ["test_day", "statistic", "threshold_mode", "episode_set", "threshold", "alarm_rate",
            "fpr", "f1", "warned_early", "episodes", "null_mean", "null_p95", "null_p_value"]
    print(show[cols].to_string(index=False))
    print(f"\nwrote {out_csv} and results/runs/{run_id}/")


if __name__ == "__main__":
    main()
