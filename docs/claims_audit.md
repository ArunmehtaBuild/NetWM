# Claims Audit (Y-10)

This document audits claims across the repository to ensure they match our latest experimental findings, specifically E10 (ablation) and E17 (calibration).

| Claim | Source File(s) | Verdict / Action |
|-------|----------------|------------------|
| "probability of infiltration" | `README.md`, `docs/demo_script.md` | **Fixed**: Changed to "risk score" per E17 (probabilities do not transfer/calibrate). |
| "beats persistence from k = 2 onward" | `docs/architecture.md`, `docs/demo_script.md` | **Fixed**: Changed to "averaged over steps 2-10, on both held-out days" per E10. |
| "F1 0.576" | `docs/architecture.md`, `docs/demo_script.md` | **Fixed**: Updated to "0.576 (0.43-0.57 over 3 seeds)" per D-032. |
| "before compromise / early warning" | `docs/architecture.md`, `docs/demo_script.md` | **Clean**: The architecture doc correctly states "no early-warning claim enters this document", and the demo script explicitly forbids saying "warns before". |
| "Stochastic latent and multi-step loss" | `docs/architecture.md` | **Clean**: These were already marked as unsupported based on E10 results in Y-4b. |
| Model card metrics | `backend/inference.py` | **Clean**: Metrics are dynamically loaded from the run folders, ensuring they reflect actual evaluated numbers without hardcoded claims. |
