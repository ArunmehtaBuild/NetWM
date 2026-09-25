# Results index

> **Claims policy:** what may and may not be said about these numbers in the video, slides and
> architecture document is fixed in [decisions.md D-021](decisions.md). Every number quoted outside
> this file must carry its experiment id and threshold policy.

All experiment artefacts live in `results/`:
`results/figures/` (PNG), `results/tables/` (CSV), `results/runs/` (per-run JSON metrics + config).

Every row below must be reproducible with the command shown. Nothing here is typed by hand except
the commentary column.

| # | experiment | dataset / split | command | artefacts | headline |
|---|---|---|---|---|---|
| E1 | dataset audit | CIC-IDS2017 corrected, all 5 days | `python scripts/audit_dataset.py` | `results/tables/e1_*.csv`, `results/figures/e1_*_timeline.png`, `results/runs/e1-dataset-audit/` | 2.10 M flows, 4 907 windows; attack share 0-47 % per day; only 5 compromise onsets all week |
| F1 | feature build | same, 70 features/window | `python scripts/build_features.py --config configs/cicids2017.yaml` | `data/processed/cicids2017/*.parquet` (not committed), `meta.json` | S_t = 70 features; positives 17.1 % (Thu), 13.1 % (Fri), 0 elsewhere |
| E2 | persistence floor | leave-one-day-out | `python scripts/benchmark_baselines.py` | `results/tables/e2e3_baselines_lags0.csv` | median next-state NLL 0.85-0.94; Thursday mean 152 010 (distribution shift) |
| E3 | logistic regression | leave-one-day-out | `python scripts/benchmark_baselines.py` | same + `results/figures/e3_*_logreg_forecast.png`, `results/tables/e3_lead_times_lags0.csv` | **0 of 5 episodes warned early**; F1 0.011 (Thu) / 0.000 (Fri) at a deployable threshold |
| E4-E7 r1 | world model, round 1 | leave-one-day-out | `python scripts/train.py --epochs 25` | `results/tables/e4e7-worldmodel_*.csv`, `results/figures/e5_*`, `e6_*` | Thursday PR-AUC 0.139 -> **0.473**, ROC-AUC 0.379 -> **0.753**; still 0 / 5 warned early; Friday worse than chance |
| E12 | precursor analysis | within-day probe | `python scripts/precursor_analysis.py` | `results/tables/e12_precursor_effect_sizes.csv`, `results/figures/e12_precursors.png` | pre-onset windows separable at ROC-AUC **0.88 / 0.96** - the early signal exists |
| E4-E7 r2 | world model, round 2 | leave-one-day-out | `python scripts/train.py --run e4e7-worldmodel-r2` | `results/tables/e4e7-worldmodel-r2_*.csv` | Thursday PR-AUC **0.675**, ROC-AUC **0.814**, F1 0.592 at 4.2 % FPR; lead time still 0 |
| E13 | rollout scoring rules | r2 checkpoints | `python scripts/scoring_rules.py --run e4e7-worldmodel-r2` | `results/tables/e13_scoring_rules_*.csv` | ranking insensitive to the rule; only max-over-horizon warns early (2/4, oracle) |
| E14 | p_max + threshold policies | r2 checkpoints | `python scripts/rescore_pmax.py --run e4e7-worldmodel-r2` | `results/tables/e14_pmax_rescore_*.csv`, `results/figures/e14_*.png` | **deployable point: F1 0.576 @ 2.7 % FPR** (self-budget); lead time still 0 - thresholding ruled out |

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
| Thursday | 362 076 | 20.41 % | 1 997 | 972 | 4 |
| Friday | 547 557 | 47.30 % | 4 067 | 968 | 1 |

Window stage distribution (after excluding `- Attempted`, D-009) - `results/tables/e1_window_stats.csv`:

| day | Benign | Recon | Initial Access | Lateral Movement | C2 | Impact |
|---|---:|---:|---:|---:|---:|---:|
| Monday | 974 | - | - | - | - | - |
| Tuesday | 724 | - | 252 | - | - | - |
| Wednesday | 860 | - | 22 | - | - | 135 |
| Thursday | 736 | 2 | 126 | 108 | - | - |
| Friday | 759 | 52 | - | - | 116 | 41 |

### Findings

1. **Attempted traffic would have destroyed the Friday timeline.** `Botnet - Attempted` covers
   14:03-20:01 UTC (307 min) vs 59 min of real botnet traffic. Counting it as C2 labelled 727/968
   Friday windows as Command & Control and masked the PortScan (11 windows) and DDoS (5 windows)
   completely. Excluding it gives 116 / 52 / 41 - which matches the published schedule. -> **D-009**
2. **One label, two kill-chain stages.** `Infiltration - Portscan` starts at 17:00:31 UTC, ~19 min
   before the documented infiltration - but those 955 early flows come from **172.16.0.1**
   (the external attacker NAT) hitting 954 ports on a single host, while the remaining 70 812 come
   from **192.168.10.8**, the compromised victim. External scan = Reconnaissance, victim scan =
   post-compromise discovery. Splitting them by source moved Thursday's first compromise onset from
   17:00:00 to **17:18:30**, matching the documented 17:19 infiltration, and removed one spurious
   episode (5 onsets -> 4). -> **D-012**
3. **The compromise event itself is 36 flows.** `Infiltration` (the Meterpreter session) is 36 flows
   out of 362 076 on Thursday (0.01 %); the loud part is the 71 767-flow internal portscan that
   follows. Any metric averaged over flows will be dominated by the aftermath, not the compromise -
   another reason the headline metric is lead time to onset, not flow-level F1.
4. **This dataset serialises its attacks.** After D-009, no window contains two different stages, so
   the multi-label view (D-010) is currently identical to the dominant-stage view. Concurrency has to
   come from CTU-13 in M2.
5. **Only 5 compromise onsets exist in the whole week** (4 Thursday + 1 Friday). Lead time will have
   a tiny sample size, so it must be reported per episode with the individual values, never as a
   single mean with an implied confidence.

### Artefacts

- `results/tables/e1_label_counts.csv` - flows per label per day, with stage + ATT&CK technique
- `results/tables/e1_attack_timeline.csv` - observed first/last flow per label vs official schedule
- `results/tables/e1_window_stats.csv` - dominant vs present stage counts per window
- `results/figures/e1_{monday..friday}_timeline.png` - attack flows/min (symlog), official schedule shaded

---

## F1 - feature build

`python scripts/build_features.py --config configs/cicids2017.yaml` · 2026-09-24

**70 features per window**, grouped as: volume/rate (6), flag behaviour (`syn_no_ack_rate`,
`has_rst_rate`, `has_fin_rate`, flag sums), port/host spread (`uniq_dst_port`, `dst_port_entropy`,
`fanout_max`, `port_fanout_max`, `top_talker_share`), service mix (9 well-known port ratios),
protocol mix, timing (`flow_iat_*`, `active_mean`, `idle_mean`, `beacon_score`), direction
(`is_outbound_rate`, `byte_asymmetry`, `outbound_bytes`), TCP shape (`fwd_init_win_mean/std`,
`fwd_seg_size_min_mean`) and scan signatures (`seq_port_ratio`, `ports_per_pair_max`).

| day | windows | positives (`y_within_K`) | onsets |
|---|---:|---:|---:|
| Monday | 974 | 0.000 % | 0 |
| Tuesday | 976 | 0.000 % | 0 |
| Wednesday | 1 017 | 0.000 % | 0 |
| Thursday | 972 | 17.078 % | 4 |
| Friday | 968 | 13.120 % | 1 |

Only Thursday and Friday can serve as test days for the forecasting target - Tuesday (brute force)
and Wednesday (DoS) never reach Lateral Movement. Feature extraction runs in ~0.6 s per day after
vectorising the entropy and beaconing computations (a groupby-apply version took 16 s per 60 k flows).

---

## E2 + E3 - the baselines (leave-one-day-out)

`python scripts/benchmark_baselines.py` · run: `results/runs/e2e3-baselines-lags0/`

### E2 - persistence (`S_hat_{t+1} = S_t`)

| test day | NLL mean | NLL median | NLL p95 |
|---|---:|---:|---:|
| Monday | 1.01 | 0.85 | 1.55 |
| Tuesday | 1.09 | 0.89 | 1.96 |
| Wednesday | 1.15 | 0.91 | 2.18 |
| Thursday | **152 010** | 0.85 | 18.84 |
| Friday | 1.41 | 0.94 | 2.75 |

The Thursday mean is not a typo: a handful of internal-portscan windows sit so far outside the
training distribution (the scaler is fitted without Thursday) that they dominate the average. The
median is unremarkable. This is the first quantitative sign of what the world model has to handle -
**distribution shift, not just class imbalance** - and it is why we report median and p95 alongside.

### E3 - logistic regression on the same features

| test day | target | threshold | F1 | precision | recall | FPR | PR-AUC | base rate | ROC-AUC | episodes warned early |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Thursday | detect | train-tuned | 0.101 | 0.545 | 0.056 | 0.006 | 0.158 | 0.111 | 0.437 | 0 / 4 |
| Thursday | detect | oracle | 0.203 | 0.155 | 0.296 | 0.203 | 0.158 | 0.111 | 0.437 | 1 / 4 |
| Thursday | forecast | train-tuned | **0.011** | 0.071 | 0.006 | 0.016 | 0.139 | 0.171 | 0.379 | **0 / 4** |
| Thursday | forecast | oracle | 0.193 | 0.125 | 0.422 | 0.608 | 0.139 | 0.171 | 0.379 | 4 / 4 |
| Friday | detect | train-tuned | 0.000 | 0.000 | 0.000 | 0.011 | 0.210 | 0.120 | 0.730 | 0 / 1 |
| Friday | detect | oracle | 0.344 | 0.239 | 0.612 | 0.265 | 0.210 | 0.120 | 0.730 | 1 / 1 |
| Friday | forecast | train-tuned | **0.000** | 0.000 | 0.000 | 0.044 | 0.156 | 0.131 | 0.615 | **0 / 1** |
| Friday | forecast | oracle | 0.286 | 0.187 | 0.606 | 0.397 | 0.156 | 0.131 | 0.615 | 1 / 1 |

### Findings

1. **A static classifier gives no early warning here.** At a threshold chosen the only way a deployed
   system could choose it - on training data - logistic regression warned early on **0 of the 5
   compromise episodes** in the week. Per-episode detail: `results/tables/e3_lead_times_lags0.csv`.
2. **Its ranking is near chance, and on Thursday it is worse than chance.** Thursday forecast
   PR-AUC 0.139 against a base rate of 0.171, ROC-AUC 0.379. Trained on the other days - whose
   attacks are brute force, DoS, botnet C2 and external scanning - the weights it learns are
   *anti-correlated* with what an infiltration looks like. Friday is better (ROC-AUC 0.615) because
   Thursday's internal-scan traffic is in its training set.
3. **The oracle threshold flatters it enormously** (F1 0.011 -> 0.193 on Thursday), which is exactly
   why both numbers are reported (D-015). Even then, the FPR is 0.61: to catch the infiltration it
   has to flag two thirds of the benign day.
4. **The top weights are plausible but unstable across folds** - Thursday leans on `one_way_rate`
   (-4.8), `is_outbound_rate` (+3.9), `dst_port_entropy` (+3.8); Friday on `is_inbound_rate` (-4.5),
   `svc_dns_rate` (+3.7), `ephemeral_dst_rate` (+3.6). Different folds, different story: no stable
   mechanism is being learned.
5. `results/figures/e3_thursday_logreg_forecast.png` is the picture worth putting in the deck: the
   baseline's probability oscillates between 0 and 1 all day long, with no structure around the
   actual compromise onsets.

**Bar for the world model:** beat median NLL 0.85-0.94 (E2), and warn early on more than 0 of 5
episodes at a train-tuned threshold (E3).

---

## E4-E7 (round 1) - world model, leave-one-day-out

`python scripts/train.py --epochs 25 --samples 16` · run: `results/runs/e4e7-worldmodel/`
0.58 M params, ~5 min/fold on a GTX 1650.

| fold | threshold | base rate | F1 | precision | recall | FPR | PR-AUC | ROC-AUC | warned early |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Thursday | train-tuned (0.843) | 0.171 | 0.000 | 0.000 | 0.000 | 0.000 | **0.473** | **0.753** | 0 / 4 |
| Thursday | oracle (0.059) | 0.171 | **0.509** | 0.657 | 0.416 | 0.045 | 0.473 | 0.753 | 0 / 4 |
| Thursday | 90th pct of own scores (0.062) | 0.171 | 0.508 | 0.684 | 0.404 | 0.038 | 0.473 | 0.753 | 0 / 4 |
| Friday | train-tuned (0.990) | 0.131 | 0.000 | 0.000 | 0.000 | 0.180 | 0.082 | 0.245 | 0 / 1 |
| Friday | oracle (0.010) | 0.131 | 0.055 | 0.037 | 0.102 | 0.401 | 0.082 | 0.245 | 0 / 1 |

Comparison on the same folds (E3 logistic regression): Thursday PR-AUC 0.139 / ROC-AUC 0.379,
Friday PR-AUC 0.156 / ROC-AUC 0.615.

### What this round actually shows

1. **Ranking improved a lot on the infiltration day.** Thursday PR-AUC 0.139 -> **0.473** (2.8x the
   base rate) and ROC-AUC 0.379 -> **0.753** against the logistic-regression baseline. Oracle F1
   0.193 -> 0.509. The dynamics model sees something the per-window classifier does not.
2. **But it is still detecting, not forecasting.** Lead time is 0 on all 5 episodes at every
   threshold we tried, including percentile thresholds on the model's own score distribution. The
   score sits at ~0.02 in the ten windows *before* each onset and only climbs once the attack is
   visible. Raw traces are in `results/runs/e4e7-worldmodel/metrics.json`.
3. **Friday is worse than chance** (ROC-AUC 0.245). Friday's only compromise is the ARES botnet C2 -
   a stage that appears *nowhere else in the week*, so in this fold the model is asked to forecast a
   family it has never seen, from a training set whose only notion of "compromise" is Thursday's
   loud internal port sweep. It confidently predicts the opposite. This is a genuine leave-one-family
   -out result, and it belongs in E8 rather than being averaged away here.
4. **Diagnosis: one compromise family per fold.** Leave-one-day-out gives the compromise head a
   single positive family in training (Thursday's infiltration or Friday's C2). It cannot learn what
   "an attacker advancing" looks like in general from n = 1 family, so it memorises the one it saw.
5. **Probabilities do not transfer across days.** The F1-optimal threshold is 0.843 on the training
   days and 0.059 on Thursday - a 14x gap. Any deployment story that depends on a fixed probability
   threshold is fiction; the fix is either calibration or an alert-budget threshold, and both are
   tracked in D-016.
6. Training itself is healthy: KL sits at 0.50-0.67 nats (no posterior collapse), reconstruction
   0.43, imagination-compromise loss 0.02-0.07. Open-loop rollout
   (`results/figures/e5_thursday_rollout_fidelity.png`) **beats persistence from k = 2 onwards**
   (2.21 vs 2.44 at k = 2, 2.05 vs 2.72 at k = 8) but **loses at k = 1** (2.03 vs 1.05) - one step
   ahead, "nothing changes" is still the better guess, and we should say so rather than quoting an
   average. The curve is also noisy: it is computed from ~119 start points at stride 8.

**Consequence:** round 2 changes the supervision, not the architecture - see decisions **D-016**.

---

## E12 - is there a precursor signal at all?

`python scripts/precursor_analysis.py` · run: `results/runs/e12-precursor-analysis/`

Before blaming the model for zero lead time, we asked whether the windows *before* a compromise are
distinguishable from ordinary benign traffic. For each onset we took the 10 preceding windows that
are not themselves attack windows, and compared them with benign windows at least 30 windows away
from any attack.

| day | pre-onset windows | background windows | within-day probe ROC-AUC |
|---|---:|---:|---:|
| Thursday | 38 | 472 | **0.883 ± 0.044** |
| Friday | 10 | 464 | **0.955 ± 0.051** |

Largest effect sizes (Cohen's d, pre-onset vs background):

| Thursday (before infiltration) | d | Friday (before botnet C2) | d |
|---|---:|---|---:|
| `uniq_dst_port` | +1.26 | `uniq_dst_ip` | +1.51 |
| `ports_per_pair_max` | +1.19 | `fanout_mean` | +1.39 |
| `urg_cnt_sum` | −0.98 | `flows_per_s` | +1.23 |
| `port_fanout_max` | +0.92 | `psh_cnt_sum` | +1.21 |
| `svc_db_rate` | −0.86 | `fanout_max` | +1.18 |

### Findings

1. **The signal exists.** Pre-compromise windows are separable from background with a plain logistic
   probe: ROC-AUC 0.88-0.96. Round 1's zero lead time is therefore a *supervision* failure, not a
   property of the data - which is what D-016 acts on.
2. **It is the shape a defender would expect**: before the infiltration, more distinct destination
   ports and wider per-pair port sweeps (the attacker looking around); before the botnet C2, more
   distinct destination hosts, higher fan-out and more flows per second.
3. **Read with the caveats.** The probe is cross-validated *within the same day*, with a scaler fitted
   on that day, and n = 38 and n = 10 pre-onset windows. It proves separability, not that a model
   trained on other days will find the same boundary - that is exactly what the leave-one-day-out
   benchmark measures, and where round 1 failed.

---

## E4-E7 (round 2) - multi-target supervision (D-016)

`python scripts/train.py --epochs 25 --samples 16 --run e4e7-worldmodel-r2`
run: `results/runs/e4e7-worldmodel-r2/` · same architecture, three risk targets instead of one.

| fold | target | threshold | base rate | F1 | FPR | PR-AUC | ROC-AUC | warned early |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Thursday | forecast | train-tuned (0.990) | 0.171 | 0.000 | 0.000 | **0.675** | **0.814** | 0 / 4 |
| Thursday | forecast | alert budget 5 % (0.977) | 0.171 | 0.000 | 0.000 | 0.675 | 0.814 | 0 / 4 |
| Thursday | forecast | oracle (0.108) | 0.171 | **0.592** | 0.042 | 0.675 | 0.814 | 0 / 4 |
| Thursday | escalation | oracle | 0.204 | 0.369 | 0.561 | 0.332 | 0.624 | - |
| Friday | forecast | oracle (0.039) | 0.131 | 0.237 | 0.893 | 0.114 | 0.465 | 1 / 1 |
| Friday | escalation | oracle | 0.101 | 0.203 | 0.761 | 0.107 | 0.500 | - |

### Progress against round 1 and the baseline

| Thursday fold | logistic regression (E3) | world model r1 | world model r2 |
|---|---:|---:|---:|
| PR-AUC (base rate 0.171) | 0.139 | 0.473 | **0.675** |
| ROC-AUC | 0.379 | 0.753 | **0.814** |
| F1 at oracle threshold | 0.193 | 0.509 | **0.592** |
| FPR at that threshold | 0.608 | 0.045 | **0.042** |
| episodes warned early | 0 / 4 | 0 / 4 | 0 / 4 |

Friday (the unseen-C2-family fold) improved from *worse than chance* to chance: ROC-AUC
0.245 -> 0.465, PR-AUC 0.082 -> 0.114.

### E13 - which rollout statistic should raise the alarm?

`python scripts/scoring_rules.py --run e4e7-worldmodel-r2` · `results/tables/e13_scoring_rules_*.csv`

The compromise head predicts a *state property*, not a first-occurrence hazard, so the usual union
`1 - prod(1 - p)` over-counts a compromise that merely persists. Six candidate rules on the same
checkpoints (oracle thresholds):

| rule | Thursday PR-AUC | Thursday ROC | Thursday early | Friday PR-AUC |
|---|---:|---:|---:|---:|
| cumulative union | 0.670 | 0.812 | 0 / 4 | 0.114 |
| **max over horizon** | 0.641 | **0.827** | **2 / 4** | 0.109 |
| mean over horizon | 0.672 | 0.812 | 0 / 4 | 0.114 |
| step 1 only | 0.674 | 0.819 | 0 / 4 | 0.105 |
| step K only | 0.611 | 0.798 | 0 / 4 | 0.118 |
| escalation union | 0.670 | 0.809 | 0 / 4 | 0.117 |

Ranking is insensitive to the rule (PR-AUC 0.61-0.67); only the *max over the horizon* produces early
warnings, and only at an oracle threshold. So the saturation of the union formula was not the
blocker - the blocker is that the score before an onset is not high enough relative to the rest of
the day.

### Honest state of play

- **Detection:** the world model is clearly better than the mandated baseline on the infiltration
  day - PR-AUC 4.8x the logistic regression, at a tenth of its false-positive rate.
- **Forecasting:** not yet. Lead time is 0 at any threshold a deployment could actually set, even
  though E12 shows the pre-onset windows are separable at ROC-AUC 0.88 within the day.
- **Unseen families:** Friday remains at chance. Four days of training contain exactly one kind of
  compromise; that is the core data limitation and it is what M2 (CTU-13) is for.
- **Thresholds still do not transfer.** Train-tuned 0.990 vs oracle 0.108, and the 5 % alert budget
  lands at 0.977 because the score saturates on training days. Calibration is now the top open item.

---

## E14 - max-over-horizon alarm statistic (T-01)

`python scripts/rescore_pmax.py --run e4e7-worldmodel-r2` · run: `results/runs/e14-pmax-rescore-e4e7-worldmodel-r2/`
Same r2 checkpoints, same rollouts, different statistic: `p_max = max_k P(compromised at t+k)`
instead of the cumulative union (D-019). No retraining.

| fold | threshold policy | threshold | F1 | precision | recall | FPR | warned early | first-onset lead |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Thursday | train-tuned | 0.961 | 0.000 | 0.000 | 0.000 | 0.000 | 0 / 4 | 0 |
| Thursday | alert budget 5 % (train days) | 0.517 | 0.000 | 0.000 | 0.000 | 0.000 | 0 / 4 | 0 |
| Thursday | **self-budget 10 %** | 0.046 | **0.576** | 0.776 | 0.458 | **0.027** | 0 / 4 | 0 |
| Thursday | self-budget 5 % | 0.182 | 0.437 | **0.959** | 0.283 | 0.003 | 0 / 4 | 0 |
| Thursday | self-budget 2 % | 0.225 | 0.194 | 0.900 | 0.108 | 0.003 | 0 / 4 | 0 |
| Thursday | oracle | 0.010 | 0.584 | 0.634 | 0.542 | 0.065 | **1 / 4** | **5 windows (150 s)** |
| Friday | any deployable policy | 0.68-0.99 | 0.000 | 0.000 | 0.000 | 0.02-0.15 | 0 / 1 | 0 |
| Friday | oracle | 0.020 | 0.216 | 0.138 | 0.496 | 0.469 | 1 / 1 | **10 windows (300 s)** |

Threshold-free ranking (unchanged by the statistic, both computed on p_max): Thursday PR-AUC 0.640 /
ROC-AUC 0.827, Friday PR-AUC 0.109 / ROC-AUC 0.438.

### Answer to the question T-01 asked

**No - the central claim does not land today.** Switching to `p_max` does *not* produce positive lead
time at a deployable threshold. It changes nothing about ranking, and the only early warnings still
require the oracle threshold: 5 windows (2.5 min) before Thursday's first onset, 10 windows (5 min)
before Friday's.

### What E14 did establish

1. **A deployable operating point exists for detection.** The *self-budget* policy - alarm on the top
   10 % of scores in the capture being analysed, using no labels, so a sensor can set it from its own
   live stream - gives Thursday **F1 0.576 at 2.7 % FPR** (precision 0.776). At 5 % budget, precision
   is **0.959** for recall 0.283. Compare the mandated baseline on the same fold: F1 0.011 at its own
   deployable threshold, or F1 0.193 at FPR 0.608 with an oracle threshold it could never pick.
2. **Thresholds tuned on training days are ~100x too high.** Train-tuned 0.961 and train-quantile
   0.517 versus an oracle of 0.010; both produce **zero alarms** on the held-out day. This is now a
   measured fact rather than a suspicion, and it is why the engine and the API default to a
   per-capture budget (contract v1.1, `threshold_policy`).
3. **Friday is still broken** - every deployable policy scores 0.000 because the model's scores
   saturate near 1 across that day (self-budget 10 % lands at 0.939). One compromise family in
   training is not enough, as round 2 already showed.
4. **Lead time is not a thresholding problem.** Both the statistic (E13) and the threshold (E14) have
   now been ruled out. What remains is the target itself: the compromise head is trained on
   "is this state compromised", which is only true *after* the fact. The round-3 fix - a
   first-occurrence hazard target, so a window is positive precisely when a compromise *begins*
   within k - is the remaining untested hypothesis, and E12 says the signal is there to be found.

### Caveat found while building the UI fixture

Forecasts are Monte-Carlo rollouts, so the scores are stochastic. Re-running the same checkpoint at
the same oracle threshold (0.010) on Thursday gave **1 of 4** episodes warned early in the E14 run
and **2 of 4** in the fixture run (`fixtures/api/thursday_oracle.json`, leads of 5 and 10 windows). The
ranking metrics are stable, but any early-warning *count* quoted from a single run carries that
sampling noise on top of an n = 4 sample. Round 3 must report these over several seeds, or with the
deterministic (mean-path) rollout, before any lead-time claim goes in the deck.

Figures: `results/figures/e14_thursday_pmax.png`, `results/figures/e14_friday_pmax.png`.
