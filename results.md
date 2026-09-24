# Results index

All experiment artefacts live in `results/`:
`results/figures/` (PNG), `results/tables/` (CSV), `results/runs/` (per-run JSON metrics + config).

Every row below must be reproducible with the command shown. Nothing here is typed by hand except
the commentary column.

| # | experiment | dataset / split | command | artefacts | headline |
|---|---|---|---|---|---|
| E1 | dataset audit | CIC-IDS2017 corrected, all 5 days | `python scripts/audit_dataset.py` | `results/tables/e1_*.csv`, `results/figures/e1_*_timeline.png`, `results/runs/e1-dataset-audit/` | 2.10 M flows, 4 907 windows; attack share 0-47 % per day; 6 compromise onsets total |

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

---

## E1 - dataset audit (CIC-IDS2017, corrected release)

`python scripts/audit_dataset.py` · run: `results/runs/e1-dataset-audit/` · 2026-09-24

### Scale and balance

| day | flows | attack flows | attempted flows | windows (60 s / 30 s) | compromise onsets |
|---|---:|---:|---:|---:|---:|
| Monday | 371 624 | 0.00 % | 0 | 974 | 0 |
| Tuesday | 322 078 | 2.17 % | 39 | 976 | 0 |
| Wednesday | 496 641 | 35.74 % | 5 876 | 1 017 | 0 |
| Thursday | 362 076 | 20.41 % | 1 997 | 972 | 5 |
| Friday | 547 557 | 47.30 % | 4 067 | 968 | 1 |

Window stage distribution (after excluding `- Attempted`, D-009) - `results/tables/e1_window_stats.csv`:

| day | Benign | Recon | Initial Access | Lateral Movement | C2 | Impact |
|---|---:|---:|---:|---:|---:|---:|
| Monday | 974 | - | - | - | - | - |
| Tuesday | 724 | - | 252 | - | - | - |
| Wednesday | 860 | - | 22 | - | - | 135 |
| Thursday | 736 | - | 126 | 110 | - | - |
| Friday | 759 | 52 | - | - | 116 | 41 |

### Findings

1. **Attempted traffic would have destroyed the Friday timeline.** `Botnet - Attempted` covers
   14:03-20:01 UTC (307 min) vs 59 min of real botnet traffic. Counting it as C2 labelled 727/968
   Friday windows as Command & Control and masked the PortScan (11 windows) and DDoS (5 windows)
   completely. Excluding it gives 116 / 52 / 41 - which matches the published schedule. -> **D-009**
2. **Lateral movement starts ~19 minutes before the documented infiltration.** The corrected labels
   put `Infiltration - Portscan` at 17:00:31 UTC while the official schedule starts the infiltration
   at 17:19. Onsets used for lead time are therefore taken from the data, not the schedule.
   -> **D-011**
3. **The compromise event itself is 36 flows.** `Infiltration` (the Meterpreter session) is 36 flows
   out of 362 076 on Thursday (0.01 %); the loud part is the 71 767-flow internal portscan that
   follows. Any metric averaged over flows will be dominated by the aftermath, not the compromise -
   another reason the headline metric is lead time to onset, not flow-level F1.
4. **This dataset serialises its attacks.** After D-009, no window contains two different stages, so
   the multi-label view (D-010) is currently identical to the dominant-stage view. Concurrency has to
   come from CTU-13 in M2.
5. **Only 6 compromise onsets exist in the whole week** (5 Thursday + 1 Friday). Lead time will have
   a tiny sample size, so it must be reported per episode with the individual values, never as a
   single mean with an implied confidence.

### Artefacts

- `results/tables/e1_label_counts.csv` - flows per label per day, with stage + ATT&CK technique
- `results/tables/e1_attack_timeline.csv` - observed first/last flow per label vs official schedule
- `results/tables/e1_window_stats.csv` - dominant vs present stage counts per window
- `results/figures/e1_{monday..friday}_timeline.png` - attack flows/min (symlog), official schedule shaded
