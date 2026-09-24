"""E13 - which statistic of the K-step rollout should raise the alarm?

The compromise head predicts a property of a state ("this state is compromised"), so the usual
hazard union 1 - prod(1 - p) over-counts a compromise that simply persists across the horizon and
saturates near 1. This compares candidate scoring rules on the trained checkpoints, without
retraining anything.

    python scripts/scoring_rules.py --run e4e7-worldmodel-r2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint
from netwm.metrics import best_threshold, forecast_metrics, lead_times, summarise_lead
from netwm.utils import TABLES, ensure_dirs, save_run, set_seed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)
    rows = []

    for ckpt_path in sorted(Path("models", args.run).glob("*.pt")):
        day = ckpt_path.stem
        ckpt = load_checkpoint(ckpt_path)
        model, device, scaler = ckpt["model"], ckpt["device"], ckpt["scaler"]
        x = scaler.transform(ds.states(day))
        out = model.forecast(
            torch.from_numpy(x).unsqueeze(0).to(device), horizon=ds.horizon, n_samples=args.samples
        )
        raw = out["p_raw"].numpy()[..., 0]                     # (T, K) compromise per imagined step
        y = ds.target(day)
        onsets = ds.onsets(day)

        candidates = {
            "cumulative_union": out["p_cum"].numpy()[:, -1],
            "max_over_horizon": raw.max(axis=1),
            "mean_over_horizon": raw.mean(axis=1),
            "step_1": raw[:, 0],
            "step_K": raw[:, -1],
            "escalation_union": out["p_cum_escalate"].numpy()[:, -1],
        }
        for name, score in candidates.items():
            thr = best_threshold(y, score)
            m = forecast_metrics(y, score, thr)
            lead = summarise_lead(
                lead_times(score, onsets, thr, ds.horizon, persistence=2), ds.stride_s
            )
            rows.append(
                {
                    "experiment": "E13",
                    "test_day": day,
                    "scoring_rule": name,
                    "base_rate": round(float(y.mean()), 4),
                    "f1_oracle": round(m.f1, 4),
                    "pr_auc": round(m.pr_auc, 4),
                    "roc_auc": round(m.roc_auc, 4),
                    "fpr_at_oracle": round(m.fpr, 4),
                    "warned_early": lead["episodes_warned_early"],
                    "episodes": lead["episodes"],
                    "mean_lead_windows": round(lead["mean_lead_windows"], 2),
                    "score_spread": round(float(score.max() - score.min()), 4),
                }
            )
            print(f"{day:9s} {name:18s} PR-AUC={m.pr_auc:.3f} ROC={m.roc_auc:.3f} "
                  f"F1*={m.f1:.3f} early={lead['episodes_warned_early']}/{lead['episodes']}")

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / f"e13_scoring_rules_{args.run}.csv", index=False)
    save_run(f"e13-scoring-rules-{args.run}", {"rows": rows}, config=vars(args))
    print(f"\nwrote results/tables/e13_scoring_rules_{args.run}.csv")


if __name__ == "__main__":
    main()
