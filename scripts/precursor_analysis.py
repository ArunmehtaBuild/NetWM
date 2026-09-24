"""E12 - is there any signal *before* a compromise, or are we asking for the impossible?

Before blaming the model for zero lead time we should check whether the pre-onset windows differ
from ordinary benign traffic at all. For each compromise onset we take the K windows before it
(excluding any window that is already an attack window) and compare them against benign windows far
from any attack, feature by feature (Cohen's d), plus a within-day logistic probe that answers
"could *anything* separate these two sets?".

    python scripts/precursor_analysis.py

Outputs results/tables/e12_precursor_effect_sizes.csv and results/figures/e12_precursors.png.
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
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.features.scaler import StateScaler
from netwm.utils import FIGURES, TABLES, ensure_dirs, save_run, set_seed


def cohens_d(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    na, nb = len(a), len(b)
    pooled = np.sqrt(((na - 1) * a.var(0, ddof=1) + (nb - 1) * b.var(0, ddof=1)) / (na + nb - 2))
    return (a.mean(0) - b.mean(0)) / np.where(pooled < 1e-9, np.nan, pooled)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--quiet-gap", type=int, default=30, help="windows of separation for background")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)
    rows, metrics = [], {}

    for day in ds.splits:
        onsets = ds.onsets(day)
        if not onsets:
            continue
        frame = ds.frame(day)
        scaler = StateScaler().fit(frame[ds.feature_names])       # within-day: we ask about signal,
        x = scaler.transform(frame[ds.feature_names])             # not about generalisation
        attack = frame["attack_now"].to_numpy() > 0

        pre_idx: list[int] = []
        for onset in onsets:
            for t in range(max(0, onset - ds.horizon), onset):
                if not attack[t]:
                    pre_idx.append(t)
        pre_idx = sorted(set(pre_idx))

        far_from_attack = np.ones(len(frame), dtype=bool)
        for t in np.flatnonzero(attack):
            far_from_attack[max(0, t - args.quiet_gap) : t + args.quiet_gap] = False
        bg_idx = np.flatnonzero(far_from_attack)

        if len(pre_idx) < 5 or len(bg_idx) < 20:
            print(f"{day}: not enough windows (pre={len(pre_idx)}, background={len(bg_idx)})")
            continue

        d = cohens_d(x[pre_idx], x[bg_idx])
        for name, value in zip(ds.feature_names, d):
            rows.append({"day": day, "feature": name, "cohens_d": round(float(value), 4)})

        xs = np.vstack([x[pre_idx], x[bg_idx]])
        ys = np.r_[np.ones(len(pre_idx)), np.zeros(len(bg_idx))]
        auc = cross_val_score(
            LogisticRegression(max_iter=2000, class_weight="balanced"),
            xs, ys, cv=StratifiedKFold(5, shuffle=True, random_state=args.seed), scoring="roc_auc",
        )
        metrics[day] = {
            "pre_onset_windows": len(pre_idx),
            "background_windows": int(len(bg_idx)),
            "probe_roc_auc_mean": round(float(auc.mean()), 4),
            "probe_roc_auc_std": round(float(auc.std()), 4),
            "top_features": sorted(
                [{"feature": n, "cohens_d": round(float(v), 3)} for n, v in zip(ds.feature_names, d)
                 if np.isfinite(v)],
                key=lambda r: abs(r["cohens_d"]), reverse=True,
            )[:10],
        }
        print(f"{day}: pre-onset={len(pre_idx)} background={len(bg_idx)} "
              f"probe ROC-AUC={auc.mean():.3f}+-{auc.std():.3f}")
        for row in metrics[day]["top_features"][:5]:
            print(f"    {row['feature']:28s} d={row['cohens_d']:+.2f}")

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "e12_precursor_effect_sizes.csv", index=False)

    if not table.empty:
        fig, axes = plt.subplots(1, len(metrics), figsize=(6 * len(metrics), 4.2), dpi=140, squeeze=False)
        for ax, (day, m) in zip(axes[0], metrics.items()):
            top = m["top_features"][::-1]
            ax.barh([r["feature"] for r in top], [r["cohens_d"] for r in top],
                    color=["#e2574c" if r["cohens_d"] > 0 else "#2f6fdb" for r in top])
            ax.axvline(0, color="#444", lw=0.8)
            ax.set_title(f"{day.capitalize()}: pre-onset vs background\nprobe ROC-AUC {m['probe_roc_auc_mean']:.2f}")
            ax.set_xlabel("Cohen's d")
            ax.tick_params(labelsize=7)
            ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(FIGURES / "e12_precursors.png")
        plt.close(fig)

    save_run("e12-precursor-analysis", metrics, config=vars(args))
    print("\nwrote results/tables/e12_precursor_effect_sizes.csv, results/figures/e12_precursors.png")


if __name__ == "__main__":
    main()
