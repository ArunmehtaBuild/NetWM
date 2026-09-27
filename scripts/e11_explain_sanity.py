"""E11 - Explainability sanity check.

Verifies if the top attributions on known attacks point to their known signatures,
e.g., port spread on the 17:00 scan and fan-out on the sweep.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint
from netwm.engine.explain import explain_window, top_features
from netwm.labels.mitre_map import STAGE_LABELS, Stage


def analyze_known_attacks(model, x, true_stages, onsets, names, horizon, device):
    """Pick specific attack windows and check their top features."""
    
    # Identify windows of interest.
    # The 17:00 scan is Reconnaissance (Stage 1). Let's find the first Recon window.
    recon_windows = np.where(true_stages == int(Stage.RECONNAISSANCE))[0]
    if len(recon_windows) > 0:
        target_t = recon_windows[0]
        explain_and_print("17:00 External Scan (Reconnaissance)", model, x, target_t, names, horizon, device)
        
    # The internal sweep is Lateral Movement (Stage 3).
    lm_windows = np.where(true_stages == int(Stage.LATERAL_MOVEMENT))[0]
    if len(lm_windows) > 0:
        target_t = lm_windows[0]
        explain_and_print("Internal Sweep (Lateral Movement)", model, x, target_t, names, horizon, device)

    # Infiltration onset
    if len(onsets) > 0:
        target_t = onsets[0]
        explain_and_print("First Compromise Onset (Infiltration)", model, x, target_t, names, horizon, device)

def explain_and_print(title, model, x, t, names, horizon, device):
    print(f"\n--- {title} at window {t} ---")
    expl = explain_window(model, x, t, horizon, device)
    
    if expl is None or "feature_attribution" not in expl:
        print("No attribution generated.")
        return
        
    top = top_features(expl["feature_attribution"], x[t], names, k=10)
    print(f"Top 10 features by attribution:")
    for feat in top:
        print(f"  {feat['feature']:>25}: {feat['attribution']:>8.4f} (value: {feat['value']:>8.4f})")

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    args = ap.parse_args()

    ds = ProcessedDataset(args.data)
    # We mainly care about Thursday for the infiltration and scans
    day = "thursday"
    
    ckpt_path = Path("models") / args.run / f"{day}.pt"
    if not ckpt_path.exists():
        print(f"Checkpoint not found at {ckpt_path}")
        return

    ckpt = load_checkpoint(ckpt_path)
    model, device, scaler, names = ckpt["model"], ckpt["device"], ckpt["scaler"], ckpt["feature_names"]
    
    x = scaler.transform(ds.states(day))
    true_stages = ds.frame(day)["stage"].to_numpy()
    onsets = ds.onsets(day)

    print(f"Running E11 explainability sanity check for {day.capitalize()}...")
    analyze_known_attacks(model, x, true_stages, onsets, names, ds.horizon, device)


if __name__ == "__main__":
    main()
