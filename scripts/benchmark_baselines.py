"""E2 + E3 - the floors the world model has to beat.

E2 persistence: how well does "next state = current state" predict S_{t+1}? Traffic is autocorrelated,
so this is the honest floor for any claim about learned dynamics.
E3 logistic regression: the PS-mandated baseline, in two modes - ``detect`` (compromise now) and
``forecast`` (compromise within K windows) - evaluated leave-one-day-out with lead time.

    python scripts/benchmark_baselines.py --data data/processed/cicids2017
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.features.scaler import StateScaler
from netwm.metrics import best_threshold, forecast_metrics, lead_times, summarise_lead
from netwm.models.baseline import LogisticForecaster, PersistenceBaseline
from netwm.utils import FIGURES, TABLES, ensure_dirs, save_run, set_seed


def evaluate_day(ds: ProcessedDataset, test_day: str, lags: int, seed: int) -> tuple[list[dict], dict]:
    train_days = [s for s in ds.splits if s != test_day]
    train_frame = ds.concat(train_days)
    scaler = StateScaler().fit(train_frame[ds.feature_names])
    # ``groups`` matters only in rank mode, where a frame is treated as one capture: without it the
    # training days would be ranked against each other while the test day is ranked alone, so the
    # baseline would be fitted and scored under two different transforms (D-025). Ignored, and
    # therefore number-preserving, in the log_standard mode every published baseline used.
    x_train = scaler.transform(train_frame[ds.feature_names], groups=train_frame["split"])
    x_test = scaler.transform(ds.states(test_day))

    rows: list[dict] = []
    extras: dict = {"test_day": test_day, "train_days": train_days}

    # --- E2 persistence ---------------------------------------------------------------------
    persistence = PersistenceBaseline().fit(x_train)
    stats = persistence.nll_stats(x_test)
    rows.append(
        {
            "experiment": "E2",
            "model": "persistence",
            "target": "next_state",
            "test_day": test_day,
            "nll_mean": round(stats["mean"], 4),
            "nll_median": round(stats["median"], 4),
            "nll_p95": round(stats["p95"], 4),
        }
    )

    # --- E3 logistic regression -------------------------------------------------------------
    for target, label in (("compromise", "detect"), ("y_within_K", "forecast")):
        y_train = ds.concat(train_days)[target].to_numpy()
        y_test = ds.frame(test_day)[target].to_numpy()
        if y_train.sum() == 0 or y_test.sum() == 0:
            continue
        model = LogisticForecaster(lags=lags).fit(x_train, y_train)
        p_train, p_test = model.predict_proba(x_train), model.predict_proba(x_test)
        # Two thresholds per model: one tuned on train (the deployable setting) and one tuned on
        # the test day itself (an oracle upper bound). Reporting only the first would look like we
        # handicapped the baseline; reporting only the second would be leakage.
        for thr_name, thr in (
            ("train-tuned", best_threshold(y_train, p_train)),
            ("oracle", best_threshold(y_test, p_test)),
        ):
            m = forecast_metrics(y_test, p_test, thr)
            lead = summarise_lead(
                lead_times(p_test, ds.onsets(test_day), thr, ds.horizon, persistence=2), ds.stride_s
            )
            rows.append(
                {
                    "experiment": "E3",
                    "model": f"logreg(lags={lags})",
                    "target": label,
                    "threshold_mode": thr_name,
                    "test_day": test_day,
                    "base_rate": round(float(y_test.mean()), 4),
                    **{k: round(v, 4) if isinstance(v, float) else v for k, v in m.as_dict().items()},
                    "episodes": lead["episodes"],
                    "warned_early": lead["episodes_warned_early"],
                    "mean_lead_windows": round(lead["mean_lead_windows"], 2),
                    "mean_lead_seconds": round(lead["mean_lead_seconds"], 1),
                }
            )
            if thr_name == "train-tuned":
                extras[f"{label}_lead"] = lead
                extras[f"{label}_threshold"] = thr
        extras[f"{label}_top_features"] = model.coefficients(ds.feature_names)[:15]
        if label == "forecast":
            extras["forecast_scores"] = p_test.tolist()
    return rows, extras


def plot_day(ds: ProcessedDataset, day: str, scores: np.ndarray, threshold: float, out: Path) -> None:
    frame = ds.frame(day)
    fig, ax = plt.subplots(figsize=(12, 3.4), dpi=140)
    ax.plot(frame["ts"], scores, lw=1.2, color="#2f6fdb", label="P(compromise within K) - logreg")
    ax.axhline(threshold, ls="--", lw=0.9, color="#888", label=f"threshold {threshold:.2f}")
    ax.fill_between(
        frame["ts"], 0, 1, where=frame["y_within_K"] == 1, color="#e2574c", alpha=0.15,
        label="ground truth: compromise within K",
    )
    for onset in ds.onsets(day):
        ax.axvline(frame["ts"].iloc[onset], color="#e2574c", lw=1.0)
    ax.set_ylim(0, 1)
    ax.set_ylabel("probability")
    ax.set_title(f"E3 logistic-regression forecast - {day.capitalize()} (held out); red lines = compromise onsets")
    ax.legend(fontsize=7, frameon=False, ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--lags", type=int, default=0, help="0 = the PS baseline (current state only)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)

    all_rows, all_extras = [], {}
    for day in ds.splits:
        rows, extras = evaluate_day(ds, day, args.lags, args.seed)
        all_rows.extend(rows)
        all_extras[day] = extras
        if "forecast_scores" in extras:
            plot_day(
                ds, day, np.asarray(extras["forecast_scores"]), extras["forecast_threshold"],
                FIGURES / f"e3_{day}_logreg_forecast.png",
            )

    table = pd.DataFrame(all_rows)
    table.to_csv(TABLES / f"e2e3_baselines_lags{args.lags}.csv", index=False)

    lead_rows = []
    for day, extras in all_extras.items():
        for mode in ("detect", "forecast"):
            for episode in extras.get(f"{mode}_lead", {}).get("per_episode", []):
                lead_rows.append({"test_day": day, "mode": mode, **episode})
    if lead_rows:
        pd.DataFrame(lead_rows).to_csv(TABLES / f"e3_lead_times_lags{args.lags}.csv", index=False)

    save_run(
        f"e2e3-baselines-lags{args.lags}",
        {"rows": all_rows, "per_day": {d: {k: v for k, v in e.items() if k != "forecast_scores"}
                                       for d, e in all_extras.items()}},
        config=vars(args),
    )
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(table.to_string(index=False))
    print(f"\nwrote results/tables/e2e3_baselines_lags{args.lags}.csv and figures")


if __name__ == "__main__":
    main()
