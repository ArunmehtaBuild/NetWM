"""E17 (Y-1) - are the forecast probabilities calibrated on a day the model never saw?

The PS asks for a *probability* of infiltration. The model's answer is ``p_cum[:, K-1]``, the
Monte-Carlo mean of P(compromise within K windows), and its label is ``y_within_K``. D-017 quotes
alert budgets instead of probabilities "until calibration closes the gap". This measures whether it
can.

    python scripts/calibration_eval.py --run e4e7-worldmodel-r2

For every fold checkpoint it reports, on the **held-out** day: the base rate, the mean forecast,
the Brier score and the expected calibration error (10 equal-width bins), raw and after temperature
scaling. The temperature is fitted on the checkpoint's own **training** days. That is in-sample by
necessity: only Thursday and Friday carry compromise positives and each fold tests one of them, so
no held-out training day with positives exists (teamtasks Y-1). The question answered is therefore
"does an in-sample temperature transfer to an unseen day", not held-out calibration.

Outputs results/tables/e17_calibration_summary.csv, results/tables/e17_reliability.csv and
results/figures/e17_reliability.png. Runs on CPU by default so it can share a machine with training.
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
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint
from netwm.utils import FIGURES, TABLES, ensure_dirs, set_seed

EPS = 1e-6
BINS = np.linspace(0.0, 1.0, 11)


def forecast_prob(ckpt: dict, ds: ProcessedDataset, day: str, samples: int) -> np.ndarray:
    """P(compromise within K) for every window of one day, as the payload reports it."""
    x = ckpt["scaler"].transform(ds.states(day))
    with torch.no_grad():
        out = ckpt["model"].forecast(
            torch.from_numpy(x).unsqueeze(0).to(ckpt["device"]), horizon=ds.horizon, n_samples=samples
        )
    return np.asarray(out["p_cum"])[:, -1].astype(float)


def reliability(p: np.ndarray, y: np.ndarray) -> pd.DataFrame:
    idx = np.clip(np.digitize(p, BINS[1:-1]), 0, len(BINS) - 2)
    rows = []
    for b in range(len(BINS) - 1):
        m = idx == b
        rows.append({
            "bin_lo": BINS[b], "bin_hi": BINS[b + 1], "n": int(m.sum()),
            "mean_p": float(p[m].mean()) if m.any() else np.nan,
            "observed": float(y[m].mean()) if m.any() else np.nan,
        })
    return pd.DataFrame(rows)


def ece(p: np.ndarray, y: np.ndarray) -> float:
    r = reliability(p, y)
    r = r[r["n"] > 0]
    return float((r["n"] * (r["mean_p"] - r["observed"]).abs()).sum() / len(p))


def fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    z = logit(np.clip(p, EPS, 1 - EPS))

    def nll(log_t: float) -> float:
        q = np.clip(expit(z / np.exp(log_t)), EPS, 1 - EPS)
        return float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())

    return float(np.exp(minimize_scalar(nll, bounds=(-5.0, 5.0), method="bounded").x))


def scaled(p: np.ndarray, t: float) -> np.ndarray:
    return expit(logit(np.clip(p, EPS, 1 - EPS)) / t)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    ensure_dirs()
    set_seed(args.seed)
    ds = ProcessedDataset(args.data)

    summary, rel_rows = [], []
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for ax, path in zip(axes, sorted(Path("models", args.run).glob("*.pt"))):
        ckpt = load_checkpoint(path, device=torch.device(args.device))
        day, train_days = ckpt["test_day"], list(ckpt["train_days"])
        p_train = np.concatenate([forecast_prob(ckpt, ds, d, args.samples) for d in train_days])
        y_train = np.concatenate([ds.target(d) for d in train_days]).astype(float)
        p_test = forecast_prob(ckpt, ds, day, args.samples)
        y_test = ds.target(day).astype(float)
        t = fit_temperature(p_train, y_train)

        for name, p, y in (
            ("train days (in-sample), raw", p_train, y_train),
            ("train days (in-sample), temperature", scaled(p_train, t), y_train),
            ("held-out day, raw", p_test, y_test),
            ("held-out day, temperature", scaled(p_test, t), y_test),
        ):
            summary.append({
                "run": args.run, "test_day": day, "scores": name, "temperature": round(t, 4),
                "n": len(y), "base_rate": round(float(y.mean()), 4), "mean_forecast": round(float(p.mean()), 4),
                "brier": round(float(((p - y) ** 2).mean()), 4),
                "brier_base_rate": round(float(((y.mean() - y) ** 2).mean()), 4),
                "ece": round(ece(p, y), 4),
            })
            r = reliability(p, y).assign(test_day=day, scores=name)
            rel_rows.append(r)
            if name.startswith("held-out"):
                shown = r[r["n"] > 0]
                ax.plot(shown["mean_p"], shown["observed"], "o-", label=f"{name.split(', ')[1]} (ECE {ece(p, y):.3f})")
        ax.plot([0, 1], [0, 1], "k--", lw=0.8, label="perfect calibration")
        ax.set_title(f"held-out {day}  (T fitted in-sample = {t:.2f})")
        ax.set_xlabel("forecast P(compromise within K)")
        ax.set_ylabel("observed frequency")
        ax.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(FIGURES / "e17_reliability.png", dpi=130)
    out = pd.DataFrame(summary)
    out.to_csv(TABLES / "e17_calibration_summary.csv", index=False)
    pd.concat(rel_rows).round(4).to_csv(TABLES / "e17_reliability.csv", index=False)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    print(f"\nwrote {TABLES / 'e17_calibration_summary.csv'}, {TABLES / 'e17_reliability.csv'}, {FIGURES / 'e17_reliability.png'}")


if __name__ == "__main__":
    main()
