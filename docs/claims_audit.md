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

## Review (Atharv, T-19 / T-13)

| Claim | Source File(s) | Verdict / Action |
|-------|----------------|------------------|
| "0.576" without its range | `docs/demo_script.md` spoken line at 3:15 | **Fixed**: D-032 now exists (it was cited before it was written); the spoken line gives the checkpoint's 0.576 and the 0.43-0.57 seed range |
| PR-AUC 0.675 / ROC-AUC 0.814 beside a `p_max` F1 | `docs/architecture.md` results table | **Fixed**: those were r2's `p_cum` training-run numbers. The table now uses `p_max` throughout (PR-AUC 0.640, ROC-AUC 0.827, E14), with seed ranges from E10 (D-024: one statistic per card) |
| "beats persistence ... on both held-out days" | `docs/architecture.md` | **Fixed**: the edit had dropped "loses at k = 1", leaving a broken sentence that rendered as a list item |
| "the next experiment is the state representation" | `docs/architecture.md` section 7 | **Fixed**: E16 ran it. Five causes eliminated; the signal dies in cross-day transfer |
| E17 method: "fitted on a day with no positives, or in-sample on the day being tested" | `research.md`, `research/early-warning-nulls.md` | **Fixed**: E17 fitted on each checkpoint's own training days (in-sample), then applied to the held-out day |
| "pre-registration drifted from cross-entropy to NLL ... lowering the bar" | `research.md`, `research/early-warning-nulls.md` | **Fixed**: no cross-entropy stage existed. The bar named NLL, which E5 never recorded (the wording came from the orchestrator's card); an either/or gate; a Friday clause nothing could pass. All three were fixed before any E10 number was read |
| "probability" in the dashboard and the deck | `frontend/`, `docs/presentation.md` | **Open**: H-16 (branch `h16`) and S-6b |
| "F1 0.576 at 2.7 % FPR", "precision 0.959 at a 5 % budget" as deployable | `docs/architecture.md`, `docs/demo_script.md`, D-020, D-021 | **Fixed (E18)**: both used a threshold over the whole day, future windows included. Causal: F1 0.608 (0.52-0.61) at 7.8 % FPR and 16.8 % of windows alarmed; the 5 % precision becomes 0.661. 0.576 is quoted only as a non-causal upper bound |
| The dashboard threshold and the model card | `engine/predict.py`, `backend/inference.py` | **Fixed (G-9, `f2bb6de`)**: the dashboard alarms on E18's causal rule through the same function; the model card reads E18's primary row (0.608, FPR 0.078) |
| "EARLY WARNING VERIFIED" on any count above zero | `frontend/js/panels/alarms.js` | **Fixed (G-9)**: the payload carries D-022's null on its own alarm series. Thursday's 2 of 4 (p = 0.331) now reads "not distinguishable from chance" |
| The why panel as "why this is an attack" | `frontend/js/panels/why.js`, the deck | **Qualified (E11)**: the known signature is in the top 8 on only 1 of 6 episodes. Say "features pushing the compromise score" |
| "Stage mapping validated" | checklist, deck | **Not claimable (E9)**: the held-out stage is never in training (Thursday LM, Friday C2), so recall is 0. Claim the T1046 technique view (precision 0.885 on the sweep) and point to M2 |
