"""E9 (G-4) - MITRE stage confusion on held-out days (design pre-registered in D-035).

    python scripts/stage_confusion.py --run e4e7-worldmodel-r2
    python scripts/stage_confusion.py --run m1v2-base-s42 --data data/processed/cicids2017_m1v2

Rows are the window's ground-truth stage (D-003), columns ``argmax stage_now`` read off the filtered
state on the deterministic mean path, so the matrix carries no Monte-Carlo noise. Every checkpoint in
``models/<run>/`` is scored on its own held-out day only.

Beside each stage's precision and recall sits ``in_training``: whether that stage occurs on any of the
fold's training days at all. A stage the head never saw cannot be predicted, so an error there is
structural, not a failure to learn. A technique-level view merges Reconnaissance and Lateral Movement,
which are the same technique here (network service discovery, T1046) split by source address (D-012).

Outputs: results/tables/e9_<run>_confusion.csv (long form), e9_<run>_per_stage.csv,
results/figures/e9_<run>.png, results/runs/e9-<run>/metrics.json
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
from netwm.labels.mitre_map import Stage
from netwm.utils import FIGURES, TABLES, ensure_dirs, save_run, set_seed

STAGES = [s.name for s in Stage]
#: technique view: Recon and Lateral Movement are both T1046 in this capture (D-012 splits them by source)
TECHNIQUE = {s.name: s.name for s in Stage} | {"RECONNAISSANCE": "DISCOVERY_T1046", "LATERAL_MOVEMENT": "DISCOVERY_T1046"}


def predict_stages(ckpt: dict, ds: ProcessedDataset, day: str) -> np.ndarray:
    x = ckpt["scaler"].transform(ds.frame(day)[ckpt["feature_names"]])
    tensor = torch.from_numpy(np.asarray(x, dtype=np.float32)).unsqueeze(0).to(ckpt["device"])
    out = ckpt["model"].forecast(tensor, horizon=ds.horizon, n_samples=1, sample=False)
    return out["stage_now"].numpy().argmax(axis=1)


def per_stage(truth: np.ndarray, pred: np.ndarray, labels: list[str], seen: set[str]) -> list[dict]:
    rows = []
    for s in labels:
        t, p = truth == s, pred == s
        tp = int((t & p).sum())
        rows.append({
            "stage": s, "support": int(t.sum()), "predicted": int(p.sum()),
            "precision": round(tp / p.sum(), 4) if p.sum() else None,
            "recall": round(tp / t.sum(), 4) if t.sum() else None,
            "in_training": s in seen,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)
    long_rows, stage_rows, summary = [], [], {}
    mats = {}
    for ckpt_path in sorted(Path("models", args.run).glob("*.pt")):
        day = ckpt_path.stem
        ckpt = load_checkpoint(ckpt_path)
        truth = np.array([STAGES[i] for i in ds.frame(day)["stage"].to_numpy()])
        pred = np.array([STAGES[i] for i in predict_stages(ckpt, ds, day)])
        seen = {STAGES[i] for d in ckpt["train_days"] for i in np.unique(ds.frame(d)["stage"])}

        mat = pd.crosstab(pd.Categorical(truth, STAGES), pd.Categorical(pred, STAGES), dropna=False)
        mats[day] = mat
        for t_stage in STAGES:
            for p_stage in STAGES:
                long_rows.append({"run": args.run, "test_day": day, "view": "stage",
                                  "true": t_stage, "pred": p_stage, "windows": int(mat.loc[t_stage, p_stage])})
        for row in per_stage(truth, pred, STAGES, seen):
            stage_rows.append({"run": args.run, "test_day": day, "view": "stage", **row})

        tech_truth = np.array([TECHNIQUE[s] for s in truth])
        tech_pred = np.array([TECHNIQUE[s] for s in pred])
        tech_labels = sorted(set(TECHNIQUE.values()), key=list(TECHNIQUE.values()).index)
        tech_seen = {TECHNIQUE[s] for s in seen}
        for row in per_stage(tech_truth, tech_pred, tech_labels, tech_seen):
            stage_rows.append({"run": args.run, "test_day": day, "view": "technique", **row})

        hostile = truth != "BENIGN"
        summary[day] = {
            "accuracy": round(float((truth == pred).mean()), 4),
            "hostile_windows": int(hostile.sum()),
            # of the windows where something hostile happens, how often the head names the right stage
            "hostile_stage_accuracy": round(float((truth[hostile] == pred[hostile]).mean()), 4) if hostile.any() else None,
            # ... and how often it at least says "not benign"
            "hostile_detected": round(float((pred[hostile] != "BENIGN").mean()), 4) if hostile.any() else None,
            "benign_false_stage": round(float((pred[~hostile] != "BENIGN").mean()), 4),
            "stages_present_not_in_training": sorted(set(truth) - seen),
        }
        print(f"\n== {args.run} / {day} (held out; trained on {ckpt['train_days']})")
        print(mat.to_string())
        print(summary[day])

    pd.DataFrame(long_rows).to_csv(TABLES / f"e9_{args.run}_confusion.csv", index=False)
    per = pd.DataFrame(stage_rows)
    per.to_csv(TABLES / f"e9_{args.run}_per_stage.csv", index=False)
    print("\n" + per[per["support"] > 0].to_string(index=False))
    save_run(f"e9-{args.run}", {"summary": summary, "per_stage": stage_rows, "confusion": long_rows},
             config=vars(args))
    plot(mats, args.run)


def plot(mats: dict, run: str) -> None:
    fig, axes = plt.subplots(1, len(mats), figsize=(6.2 * len(mats), 5.4), dpi=130, squeeze=False)
    short = ["BEN", "RECON", "INIT", "LAT", "C2", "EXFIL", "IMPACT"]
    for ax, (day, mat) in zip(axes[0], mats.items()):
        m = mat.to_numpy().astype(float)
        norm = m / np.maximum(m.sum(axis=1, keepdims=True), 1)
        ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                if m[i, j]:
                    ax.text(j, i, int(m[i, j]), ha="center", va="center", fontsize=7,
                            color="white" if norm[i, j] > 0.5 else "black")
        ax.set_xticks(range(len(short)), short, fontsize=7)
        ax.set_yticks(range(len(short)), short, fontsize=7)
        ax.set_xlabel("predicted (argmax stage_now)")
        ax.set_ylabel("ground truth (window stage)")
        ax.set_title(f"E9 - {day} held out ({run})", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIGURES / f"e9_{run}.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
