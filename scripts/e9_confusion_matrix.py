"""E9 - MITRE stage confusion matrix on held-out days.

Validates the ATT&CK stage mapping quality (per-stage precision and recall)
on Thursday and Friday using the r2 checkpoints.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import classification_report, confusion_matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint
from netwm.labels.mitre_map import STAGE_LABELS, Stage


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    args = ap.parse_args()

    ds = ProcessedDataset(args.data)
    test_days = ["thursday", "friday"]

    for day in test_days:
        ckpt_path = Path("models") / args.run / f"{day}.pt"
        if not ckpt_path.exists():
            print(f"Skipping {day}: checkpoint not found at {ckpt_path}")
            continue

        ckpt = load_checkpoint(ckpt_path)
        model, device, scaler = ckpt["model"], ckpt["device"], ckpt["scaler"]
        
        # Load test day data
        x = scaler.transform(ds.states(day))
        tensor = torch.from_numpy(x).unsqueeze(0).to(device)
        
        # Forecast to get stage_now logits
        with torch.no_grad():
            out = model.forecast(tensor, horizon=ds.horizon, n_samples=1, sample=False)
        
        stage_now = out["stage_now"].numpy()
        pred_stage = np.argmax(stage_now, axis=-1)
        
        # True stages
        true_stage = ds.frame(day)["stage"].to_numpy()
        
        print(f"\n{'='*50}\nE9 Confusion Matrix & Report for {day.capitalize()}\n{'='*50}")
        
        labels = sorted(list(set(true_stage) | set(pred_stage)))
        target_names = [STAGE_LABELS[Stage(l)] for l in labels]
        
        print("Classification Report:")
        print(classification_report(true_stage, pred_stage, labels=labels, target_names=target_names, zero_division=0))
        
        print("Confusion Matrix:")
        cm = confusion_matrix(true_stage, pred_stage, labels=labels)
        
        # Print a formatted confusion matrix
        header = f"{'True \ Pred':>20} " + " ".join([f"{name[:8]:>8}" for name in target_names])
        print(header)
        for i, name in enumerate(target_names):
            row_str = " ".join([f"{cm[i, j]:>8}" for j in range(len(target_names))])
            print(f"{name:>20} {row_str}")
        print("\n")


if __name__ == "__main__":
    main()
