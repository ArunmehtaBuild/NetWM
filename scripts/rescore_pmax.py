"""E14 - re-score the trained checkpoints with the max-over-horizon alarm statistic (D-019).

No retraining: the same r2 checkpoints, the same rollouts, a different statistic read off them.
Reports every threshold policy side by side (D-015, D-017) and the per-episode lead time, and writes
the p_max thresholds back into the checkpoints so the demo app and the API agree with the benchmark.

    python scripts/rescore_pmax.py --run e4e7-worldmodel-r2
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
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint
from netwm.metrics import best_threshold, forecast_metrics, lead_times, summarise_lead
from netwm.utils import FIGURES, TABLES, ensure_dirs, save_run, set_seed


def scores_for(model, scaler, ds: ProcessedDataset, day: str, device, samples: int) -> np.ndarray:
    x = scaler.transform(ds.states(day))
    out = model.forecast(
        torch.from_numpy(x).unsqueeze(0).to(device), horizon=ds.horizon, n_samples=samples
    )
    return out["p_max"].numpy()


def plot(ds: ProcessedDataset, day: str, score: np.ndarray, thresholds: dict, out: Path) -> None:
    frame = ds.frame(day)
    fig, ax = plt.subplots(figsize=(12, 3.6), dpi=140)
    ax.fill_between(frame["ts"], 0, 1, where=frame["y_within_K"] == 1, color="#e2574c", alpha=0.12,
                    label="compromise within K (ground truth)")
    ax.plot(frame["ts"], score, lw=1.3, color="#2f6fdb", label="p_max = max_k P(compromised at t+k)")
    colors = {"train-tuned": "#f2a541", "alert-budget-5pct": "#2fa87a", "oracle": "#888"}
    for name, thr in thresholds.items():
        ax.axhline(thr, ls="--", lw=0.9, color=colors.get(name, "#888"), label=f"{name} {thr:.3f}")
    for onset in ds.onsets(day):
        ax.axvline(frame["ts"].iloc[onset], color="#e2574c", lw=1.0)
    ax.set_ylim(0, 1)
    ax.set_ylabel("p_max")
    ax.set_title(f"E14 - max-over-horizon alarm statistic, {day.capitalize()} (held out)")
    ax.legend(fontsize=7, frameon=False, ncol=3)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--budget", type=float, default=0.95, help="alert-budget quantile on train days")
    ap.add_argument("--write-thresholds", action="store_true", help="store p_max thresholds in the checkpoints")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)
    rows, per_day = [], {}

    for ckpt_path in sorted(Path("models", args.run).glob("*.pt")):
        day = ckpt_path.stem
        ckpt = load_checkpoint(ckpt_path)
        model, device, scaler = ckpt["model"], ckpt["device"], ckpt["scaler"]
        train_days = [d for d in ds.splits if d != day]

        train_score = np.concatenate(
            [scores_for(model, scaler, ds, d, device, max(4, args.samples // 4)) for d in train_days]
        )
        train_y = np.concatenate([ds.target(d) for d in train_days])
        score = scores_for(model, scaler, ds, day, device, args.samples)
        y = ds.target(day)
        onsets = ds.onsets(day)

        thresholds = {
            "train-tuned": best_threshold(train_y, train_score),
            f"alert-budget-{int((1 - args.budget) * 100)}pct": float(np.quantile(train_score, args.budget)),
            "oracle": best_threshold(y, score),
        }
        for name, thr in thresholds.items():
            m = forecast_metrics(y, score, thr)
            episodes = lead_times(score, onsets, thr, ds.horizon, persistence=2)
            lead = summarise_lead(episodes, ds.stride_s)
            first = episodes[0] if episodes else {}
            rows.append(
                {
                    "experiment": "E14",
                    "statistic": "p_max",
                    "test_day": day,
                    "threshold_mode": name,
                    "threshold": round(thr, 4),
                    "base_rate": round(float(y.mean()), 4),
                    **{k: round(v, 4) if isinstance(v, float) else v for k, v in m.as_dict().items()},
                    "episodes": lead["episodes"],
                    "warned_early": lead["episodes_warned_early"],
                    "mean_lead_windows": round(lead["mean_lead_windows"], 2),
                    "mean_lead_seconds": round(lead["mean_lead_seconds"], 1),
                    # the first onset of the day is the only genuine "before they got in" case (D-019)
                    "first_onset_lead_windows": first.get("lead_windows", 0),
                }
            )
            print(f"{day:9s} {name:20s} thr={thr:.3f} f1={m.f1:.3f} prec={m.precision:.3f} "
                  f"rec={m.recall:.3f} fpr={m.fpr:.3f} early={lead['episodes_warned_early']}/{lead['episodes']} "
                  f"first-onset lead={first.get('lead_windows', 0)}w")

        per_day[day] = {
            "thresholds": thresholds,
            "scores": score.tolist(),
            "episodes": {name: lead_times(score, onsets, thr, ds.horizon, persistence=2)
                         for name, thr in thresholds.items()},
        }
        plot(ds, day, score, thresholds, FIGURES / f"e14_{day}_pmax.png")

        if args.write_thresholds:
            raw = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            raw["threshold"] = thresholds["train-tuned"]
            raw["threshold_budget"] = thresholds[f"alert-budget-{int((1 - args.budget) * 100)}pct"]
            raw["alarm_statistic"] = "p_max"
            torch.save(raw, ckpt_path)
            print(f"           wrote p_max thresholds into {ckpt_path}")

    pd.DataFrame(rows).to_csv(TABLES / f"e14_pmax_rescore_{args.run}.csv", index=False)
    save_run(f"e14-pmax-rescore-{args.run}", {"rows": rows, "per_day": per_day}, config=vars(args))
    print(f"\nwrote results/tables/e14_pmax_rescore_{args.run}.csv and results/figures/e14_*.png")


if __name__ == "__main__":
    main()
