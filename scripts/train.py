"""E4-E7 - train the world model leave-one-day-out and evaluate forecasting + rollout fidelity.

    python scripts/train.py --config configs/cicids2017.yaml --test-days thursday friday
    python scripts/train.py --smoke            # 2 epochs, one fold - checks the plumbing

Saves per fold: ``models/<run>/<test_day>.pt`` (weights + config + scaler + feature names),
metrics into ``results/runs/<run>/`` and figures into ``results/figures/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.evaluate import evaluate_fold
from netwm.features.scaler import StateScaler
from netwm.models.world_model import WorldModelConfig
from netwm.train import TrainConfig, prepare_days, train_model
from netwm.utils import FIGURES, TABLES, ensure_dirs, git_sha, run_dir, save_run, set_seed


def plot_forecast(ds, day: str, extras: dict, threshold: float, out: Path) -> None:
    frame = ds.frame(day)
    p = np.asarray(extras["p_cum"])[:, -1]
    lo, hi = np.asarray(extras["p_lo"])[:, -1], np.asarray(extras["p_hi"])[:, -1]

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(12, 5), dpi=140, sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    ax.fill_between(frame["ts"], lo, hi, color="#2f6fdb", alpha=0.18, label="MC 5-95 %")
    ax.plot(frame["ts"], p, lw=1.3, color="#2f6fdb", label="P(compromise within K)")
    ax.axhline(threshold, ls="--", lw=0.9, color="#888", label=f"threshold {threshold:.2f}")
    ax.fill_between(
        frame["ts"], 0, 1, where=frame["y_within_K"] == 1, color="#e2574c", alpha=0.12,
        label="ground truth window",
    )
    for onset in ds.onsets(day):
        ax.axvline(frame["ts"].iloc[onset], color="#e2574c", lw=1.0)
    ax.set_ylim(0, 1)
    ax.set_ylabel("probability")
    ax.set_title(f"World model forecast - {day.capitalize()} (held out)")
    ax.legend(fontsize=7, frameon=False, ncol=4)
    ax.spines[["top", "right"]].set_visible(False)

    ax2.plot(frame["ts"], extras["surprise"], lw=0.9, color="#8e5bd9")
    ax2.set_ylabel("surprise")
    ax2.set_yscale("symlog", linthresh=1)
    ax2.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_rollout(rollout: dict, day: str, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 3.2), dpi=140)
    ax.plot(rollout["k"], rollout["world_model_mse"], "o-", color="#2f6fdb", label="world model")
    ax.plot(rollout["k"], rollout["persistence_mse"], "s--", color="#888", label="persistence")
    ax.set_xlabel("imagined steps ahead (k)")
    ax.set_ylabel("next-state MSE")
    ax.set_title(f"Open-loop rollout fidelity - {day.capitalize()}")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/cicids2017.yaml")
    ap.add_argument("--data", default=None, help="override processed_dir from the config")
    ap.add_argument("--test-days", nargs="*", default=["thursday", "friday"])
    ap.add_argument("--run", default="e4e7-worldmodel")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--samples", type=int, default=16, help="Monte-Carlo rollouts per window")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true", help="2 epochs, first test day only")
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    ds = ProcessedDataset(args.data or cfg["processed_dir"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    test_days = args.test_days[:1] if args.smoke else args.test_days
    train_cfg = TrainConfig(epochs=2 if args.smoke else args.epochs)
    model_cfg = WorldModelConfig(
        n_features=len(ds.feature_names), horizon_k=ds.horizon, n_stages=7
    )
    run_id = f"{args.run}-smoke" if args.smoke else args.run
    model_root = Path("models") / run_id
    model_root.mkdir(parents=True, exist_ok=True)

    rows, per_day, histories = [], {}, {}
    for test_day in test_days:
        train_days = [d for d in ds.splits if d != test_day]
        print(f"\n== fold: test={test_day}  train={train_days}  device={device}")
        scaler = StateScaler().fit(ds.concat(train_days)[ds.feature_names])
        model, history = train_model(ds, train_days, train_cfg, model_cfg, device, scaler)
        histories[test_day] = history

        prepared = prepare_days(ds, ds.splits, scaler)
        fold_rows, extras = evaluate_fold(
            model,
            {d: prepared[d] for d in train_days},
            test_day,
            prepared[test_day],
            ds.horizon,
            ds.stride_s,
            device,
            n_samples=4 if args.smoke else args.samples,
        )
        rows.extend(fold_rows)
        per_day[test_day] = {k: v for k, v in extras.items() if k not in {"p_cum", "p_lo", "p_hi", "attention"}}

        torch.save(
            {
                "model_state": model.state_dict(),
                "model_config": model_cfg.as_dict(),
                "train_config": train_cfg.__dict__,
                "feature_names": ds.feature_names,
                "scaler": scaler,
                "train_days": train_days,
                "test_day": test_day,
                "git_sha": git_sha(),
                "horizon_k": ds.horizon,
                "stride_s": ds.stride_s,
                "threshold": extras["threshold_train"],
            },
            model_root / f"{test_day}.pt",
        )
        plot_forecast(ds, test_day, extras, extras["threshold_train"],
                      FIGURES / f"e6_{test_day}_worldmodel_forecast.png")
        plot_rollout(extras["rollout"], test_day, FIGURES / f"e5_{test_day}_rollout_fidelity.png")

        for row in fold_rows:
            print("   " + json.dumps({k: row[k] for k in
                  ("threshold_mode", "f1", "precision", "recall", "fpr", "pr_auc",
                   "warned_early", "episodes", "mean_lead_windows")}))

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / f"{run_id}_forecast.csv", index=False)
    pd.DataFrame(
        [{"test_day": d, **h} for d, hist in histories.items() for h in hist]
    ).to_csv(TABLES / f"{run_id}_training_curves.csv", index=False)
    save_run(run_id, {"rows": rows, "per_day": per_day}, config={**vars(args), "model": model_cfg.as_dict()})
    print(f"\nwrote {model_root}/*.pt, results/tables/{run_id}_*.csv, results/figures/e5_*, e6_*")


if __name__ == "__main__":
    main()
