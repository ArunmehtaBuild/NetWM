# Results index

All experiment artefacts live in `results/`:
`results/figures/` (PNG), `results/tables/` (CSV), `results/runs/` (per-run JSON metrics + config).

Every row below must be reproducible with the command shown. Nothing here is typed by hand except
the commentary column.

| # | experiment | dataset / split | command | artefacts | headline |
|---|---|---|---|---|---|
| - | _no experiments run yet_ | | | | |

## Planned experiment set (M1)

| # | experiment | purpose |
|---|---|---|
| E1 | dataset audit: class / stage distribution per day, window statistics | know the imbalance before modelling |
| E2 | persistence baseline (next state = current state), next-state NLL | floor for "did we learn dynamics at all" |
| E3 | logistic regression on S_t -> infiltration within K | the PS-mandated baseline |
| E4 | world model one-step next-state NLL vs E2 | evidence of dynamics learning |
| E5 | world model K-step open-loop rollout fidelity, k = 1..10 | evidence it is a world model, not a classifier |
| E6 | forecast quality: F1 / precision / recall / FPR / PR-AUC vs E3 | the PS-mandated comparison |
| E7 | lead-time distribution (windows before ground-truth onset) | the metric a classifier cannot score |
| E8 | leave-one-attack-family-out (hold out Infiltration; hold out Botnet) | generalisation to unseen attacks |
| E9 | stage classification confusion matrix | ATT&CK stage mapping quality |
| E10 | ablations: no stochastic latent, no multi-step loss, no packet-level features | which parts earn their place |
| E11 | explainability sanity check: IG / attention vs known attack signatures | explanations must match ground truth |
