import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import torch.optim as optim
from scipy.special import logit, expit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint
from netwm.metrics import best_threshold, forecast_metrics

def scores_for(model, scaler, ds, day, device, samples=16):
    x = scaler.transform(ds.states(day))
    out = model.forecast(
        torch.from_numpy(x).unsqueeze(0).to(device), horizon=ds.horizon, n_samples=samples
    )
    return out["p_max"].numpy()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--samples", type=int, default=16)
    args = ap.parse_args()

    ds = ProcessedDataset(args.data)
    rows = []

    for ckpt_path in sorted(Path("models", args.run).glob("*.pt")):
        day = ckpt_path.stem
        ckpt = load_checkpoint(ckpt_path)
        model, device, scaler = ckpt["model"], ckpt["device"], ckpt["scaler"]
        
        train_days = [d for d in ds.splits if d != day]
        val_day = train_days[-1]
        fit_days = train_days[:-1]

        print(f"[{day}] scoring fit days...")
        fit_score = np.concatenate([scores_for(model, scaler, ds, d, device, max(4, args.samples//4)) for d in fit_days])
        fit_y = np.concatenate([ds.target(d) for d in fit_days])
        
        print(f"[{day}] scoring val day ({val_day})...")
        val_score = scores_for(model, scaler, ds, val_day, device, max(4, args.samples//4))
        val_y = ds.target(val_day)

        print(f"[{day}] scoring test day ({day})...")
        test_score = scores_for(model, scaler, ds, day, device, args.samples)
        test_y = ds.target(day)

        eps = 1e-7
        val_logits = torch.tensor(logit(np.clip(val_score, eps, 1 - eps)), dtype=torch.float32)
        val_labels = torch.tensor(val_y, dtype=torch.float32)

        T = torch.nn.Parameter(torch.ones(1))
        optimizer = optim.LBFGS([T], lr=0.01, max_iter=100)
        
        def closure():
            optimizer.zero_grad()
            loss = F.binary_cross_entropy_with_logits(val_logits / T, val_labels)
            loss.backward()
            return loss
            
        optimizer.step(closure)
        temp = T.item()
        print(f"[{day}] Learned temperature: {temp:.3f}")

        fit_score_cal = expit(logit(np.clip(fit_score, eps, 1 - eps)) / temp)
        test_score_cal = expit(logit(np.clip(test_score, eps, 1 - eps)) / temp)

        thr_train = best_threshold(fit_y, fit_score)
        thr_oracle = best_threshold(test_y, test_score)
        
        thr_train_cal = best_threshold(fit_y, fit_score_cal)
        thr_oracle_cal = best_threshold(test_y, test_score_cal)
        
        gap_uncal = thr_train / thr_oracle if thr_oracle > 0 else float('inf')
        gap_cal = thr_train_cal / thr_oracle_cal if thr_oracle_cal > 0 else float('inf')
        
        print(f"[{day}] Uncalibrated Gap: {thr_train:.3f} / {thr_oracle:.3f} = {gap_uncal:.2f}x")
        print(f"[{day}] Calibrated Gap:   {thr_train_cal:.3f} / {thr_oracle_cal:.3f} = {gap_cal:.2f}x")
        
        rows.append({
            "test_day": day,
            "temp": temp,
            "thr_train_uncal": thr_train,
            "thr_oracle_uncal": thr_oracle,
            "gap_uncal": gap_uncal,
            "thr_train_cal": thr_train_cal,
            "thr_oracle_cal": thr_oracle_cal,
            "gap_cal": gap_cal,
        })
        
    df = pd.DataFrame(rows)
    df.to_csv("results/tables/y1_calibration.csv", index=False)
    print("Done. Wrote results/tables/y1_calibration.csv")

if __name__ == "__main__":
    main()
