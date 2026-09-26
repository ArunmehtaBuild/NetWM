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
| F2 | feature build, S_t v2 (trend) | same, 94 features/window | `python scripts/build_features.py --config configs/features_trend.yaml` | `results/runs/f2-trend-build/`, `results/runs/f1-v1-recheck/`, `results/tables/f2*.csv` | S_t v2 = 94 features; v1 columns + labels bit-identical to the v1 rebuild, which reproduces F1; no measurable build cost |
| F3 | feature build, per-host channel | same, 82 features/window | `python scripts/build_features.py --config configs/features_hosts.yaml` | `results/runs/f3-hosts-build/`, `results/tables/f2f3_feature_builds.csv`, `results/tables/f3_host_channel_stats.csv` | 3 host slots x 4; v1 columns + labels bit-identical; slot 1 filled on every Thu/Fri window |
| E2 | persistence floor | leave-one-day-out | `python scripts/benchmark_baselines.py` | `results/tables/e2e3_baselines_lags0.csv` | median next-state NLL 0.85-0.94; Thursday mean 152 010 (distribution shift) |
| E3 | logistic regression | leave-one-day-out | `python scripts/benchmark_baselines.py` | same + `results/figures/e3_*_logreg_forecast.png`, `results/tables/e3_lead_times_lags0.csv` | **0 of 5 episodes warned early**; F1 0.011 (Thu) / 0.000 (Fri) at a deployable threshold |
| E4-E7 r1 | world model, round 1 | leave-one-day-out | `python scripts/train.py --epochs 25` | `results/tables/e4e7-worldmodel_*.csv`, `results/figures/e5_*`, `e6_*` | Thursday PR-AUC 0.139 -> **0.473**, ROC-AUC 0.379 -> **0.753**; still 0 / 5 warned early; Friday worse than chance |
| E12 | precursor analysis | within-day probe | `python scripts/precursor_analysis.py` | `results/tables/e12_precursor_effect_sizes.csv`, `results/figures/e12_precursors.png` | pre-onset windows separable at ROC-AUC **0.88 / 0.96** - the early signal exists |
| E4-E7 r2 | world model, round 2 | leave-one-day-out | `python scripts/train.py --run e4e7-worldmodel-r2` | `results/tables/e4e7-worldmodel-r2_*.csv` | Thursday PR-AUC **0.675**, ROC-AUC **0.814**, F1 0.592 at 4.2 % FPR; lead time still 0 |
| E13 | rollout scoring rules | r2 checkpoints | `python scripts/scoring_rules.py --run e4e7-worldmodel-r2` | `results/tables/e13_scoring_rules_*.csv` | ranking insensitive to the rule; only max-over-horizon warns early (2/4, oracle) |
| E14 | p_max + threshold policies | r2 checkpoints | `python scripts/rescore_pmax.py --run e4e7-worldmodel-r2` | `results/tables/e14_pmax_rescore_*.csv`, `results/figures/e14_*.png` | **deployable point: F1 0.576 @ 2.7 % FPR** (self-budget); lead time still 0 - thresholding ruled out |
| E3b | lagged logistic regression | leave-one-day-out | `python scripts/benchmark_baselines.py --lags 4` | `results/tables/e2e3_baselines_lags4.csv` | history does not help the baseline: 0 early warnings, ranking worse than lags=0 |
| E10 | ablations | r2 checkpoints | `python scripts/e10_collect.py` | `results/tables/e10_ablation_summary.csv` | stochastic latent and multi-step rollout fail to pass the D-030 bar |
| E17 | calibration | r2 checkpoints | `python scripts/calibration_eval.py` | `results/tables/e17_*`, `results/figures/e17_reliability.png` | temperature scaling improves in-sample but fails on held-out Friday (worse than constant); budget stays |

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

## F2 - trend feature build (S_t v2)

```
python scripts/build_features.py --config configs/cicids2017.yaml \
    > results/runs/f1-v1-recheck/build.log 2>&1; echo "exit=$?"       # v1, rebuilt as the control
python scripts/build_features.py --config configs/features_trend.yaml \
    > results/runs/f2-trend-build/build.log 2>&1; echo "exit=$?"
```
runs: `results/runs/f1-v1-recheck/`, `results/runs/f2-trend-build/` (`build.log` + `meta.json`, seed 42,
git `c810f7c`) · 2026-09-26 · both exit 0

S_t v2 = the 70 v1 features + the D-026 trend block (delta, least-squares slopes over 5 and 10
windows, trailing 60-min z-score) for the six E12 features: **94 features per window**
(`meta.json` `n_features`). Built into `data/processed/cicids2017_trend/`; the v1 matrix in
`data/processed/cicids2017/` is untouched.

| day | flows | windows | v1 build (s) | v2 build (s) |
|---|---:|---:|---:|---:|
| Monday | 371 624 | 974 | 7.22 | 5.45 |
| Tuesday | 322 078 | 976 | 6.54 | 4.83 |
| Wednesday | 496 641 | 1 017 | 10.42 | 7.87 |
| Thursday | 362 076 | 972 | 7.52 | 5.25 |
| Friday | 547 557 | 968 | 9.70 | 9.07 |

### Findings

1. **v1 is reproduced exactly.** The v1 rebuild at `c810f7c` gives F1's window counts and positive
   rates on every day. Inside the v2 build the 70 v1 columns and every label column are
   bit-identical to the v1 build, so S_t v2 changes the state and nothing else - Y-4 can compare
   the two one variable at a time.
2. **The trend block costs nothing measurable.** `build_s` is load + window + features + labels
   for one day, dominated by reading the CSV. v2 came out *faster* than v1 only because v1 ran first
   against a cold disk cache - read these as "no measurable overhead", not as a speed-up. They are
   not comparable with F1's ~0.6 s, which timed feature extraction alone.
3. **The +-10 z-score clip is a tail guard, not a reshaping.** It fires on at most 0.41 % of a day's
   windows for any of the six columns, on at most 0.14 % of benign windows, and on about 0.7 % of
   attack windows (Wednesday / Thursday / Friday). No NaN or inf in any trend column.

Artefacts: `results/tables/f2f3_feature_builds.csv`, `results/tables/f2_zscore_clip_rates.csv`.
Descriptive only - whether the trend block helps the forecast is Y-4's question, under the D-023 bar.

---

## F3 - per-host channel build (S-2)

```
python scripts/build_features.py --config configs/features_hosts.yaml \
    > results/runs/f3-hosts-build/build.log 2>&1; echo "exit=$?"
```
run: `results/runs/f3-hosts-build/` (`build.log` + `meta.json`, seed 42, git `c810f7c`) · 2026-09-26 · exit 0

The 70 v1 features + the D-027 per-host channel for the 3 busiest internal source hosts (fanout,
ports, byte asymmetry, new-peer rate): **82 features per window**, trend block off. Built into
`data/processed/cicids2017_hosts/`.

| day | windows | build (s) |
|---|---:|---:|
| Monday | 974 | 6.65 |
| Tuesday | 976 | 5.67 |
| Wednesday | 1 017 | 10.96 |
| Thursday | 972 | 7.56 |
| Friday | 968 | 10.33 |

### Findings

1. **Same windows, same v1 columns, same labels** as the v1 build - bit-identical, as for F2.
2. **Slot 1 is never empty on the attack days**: `host1_fanout` is at least 1 on every Thursday
   and Friday window (max 212 Thursday, 287 Friday), so there is always an internal host to read.
3. **`new_peer_rate` is exactly 0 in about 44 % of windows** on Thursday and Friday (the busiest
   host is talking only to peers it has contacted before) and spans the full 0-1 range - the
   feature varies instead of saturating.

Artefacts: `results/tables/f2f3_feature_builds.csv`, `results/tables/f3_host_channel_stats.csv`
(min / max / mean / zero share of every host column, per day). Descriptive only; the forecasting
value of the channel is measured in Y-4.

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

> **Statistic note (2026-09-25, T-09).** The forecast rows below were produced inside the training
> run, which scored `p_cum[:, -1]` while the engine and E14 score `p_max` (D-019). The two disagreed
> on the same checkpoints. `evaluate.py` now scores `p_max`, so future in-training rows match; the
> rows in this section are **superseded by E14** for anything threshold-dependent and must not be
> quoted. The PR-AUC / ROC-AUC figures for the *cumulative union* statistic remain valid as such -
> E13 compares the statistics directly.

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

---

## E3b - the lagged logistic-regression check (insurance for D-021)

`python scripts/benchmark_baselines.py --lags 4` · `results/tables/e2e3_baselines_lags4.csv`

D-021 says the framing is wrong if a method simpler than ours gets positive lead time at a deployable
threshold. The cheapest candidate is the mandated baseline given *history*: logistic regression on
the current state plus the previous 4 windows (2 minutes), same folds, same features.

| fold | target | threshold | F1 | PR-AUC | ROC-AUC | warned early | lead |
|---|---|---|---:|---:|---:|---:|---:|
| Thursday | forecast | train-tuned (0.902) | 0.000 | 0.114 | 0.278 | 0 / 4 | 0 |
| Thursday | forecast | oracle (0.010) | 0.057 | 0.114 | 0.278 | 1 / 4 | 3 windows |
| Friday | forecast | train-tuned (0.774) | 0.000 | 0.185 | 0.692 | 0 / 1 | 0 |
| Friday | forecast | oracle (0.010) | 0.185 | 0.185 | 0.692 | 0 / 1 | 0 |

**The check passes.** Adding history to the baseline does not buy lead time at any deployable
threshold, and on Thursday it makes the ranking *worse* than the memoryless baseline
(PR-AUC 0.139 -> 0.114, ROC-AUC 0.379 -> 0.278). The one early warning it produces needs the oracle
threshold and comes from a score that is close to noise (F1 0.057).

Curiosity worth noting for Y-3: Thursday's `detect` target at an oracle threshold reports 2 of 4
episodes "warned early" with a mean lead of 6.5 windows while scoring F1 0.021 and PR-AUC 0.069. That
is a score firing almost everywhere, not a forecaster - a reminder that lead time must always be read
next to the false-positive rate, and that our own early-warning counts need the same scrutiny.

---

## E15a - what does an unaligned score warn about? (Y-2 / Y-5, calibration for D-021)

`python scripts/precursor_eval.py --scores-from-run e14-pmax-rescore-e4e7-worldmodel-r2`
run: `results/runs/e15a-null-calibration-e14-pmax-rescore-e4e7-worldmodel-r2/`

Before training anything for Y-2, we asked what an early-warning *count* is worth. The harness reads
the **exact score arrays E14 published** rather than re-forecasting, so no Monte-Carlo noise sits
between this calibration and the numbers already in this file. Method in D-022: a 2,000-shift
circular null at the same threshold, an eligibility mask that refuses credit for alarms inside the
previous episode's traffic, and a confirmation that must land before the onset.

**Reproduction gate.** The harness reproduces E14 exactly on the same scores - Thursday self-budget
10 %: F1 **0.5758**, FPR **0.0273**, precision 0.776, 0 of 4 compromise episodes; Friday oracle
1 of 1. Measurement verified before anything was measured with it.

### The two early warnings E14 reports

| fold | policy | alarm rate | FPR | warned early | null mean | null p95 | **p** |
|---|---|---:|---:|---:|---:|---:|---:|
| Thursday | oracle (0.010) | 0.146 | 0.065 | 1 / 4 compromise | 0.78 | 3 | **0.412** |
| Friday | oracle (0.020) | **0.472** | **0.469** | 1 / 1 compromise | 0.55 | 1 | **0.550** |
| Thursday | self-budget 10 % | 0.101 | 0.027 | 0 / 4 compromise | 0.53 | 2 | 1.000 |
| Friday | self-budget 10 % | 0.100 | 0.115 | 0 / 1 compromise | 0.14 | 1 | 1.000 |

### The raw-feature floor, same threshold policy, no model at all

| fold | score | alarm rate | warned early (attack, n=8) | warned early (compromise) | p (compromise) |
|---|---|---:|---:|---:|---:|
| Friday | `uniq_dst_ip` | 0.100 | 1 / 8 | **1 / 1** | 0.236 |
| Friday | `fanout_mean` | 0.100 | 2 / 8 | **1 / 1** | 0.224 |
| Friday | `p_max` (the model) | 0.100 | 2 / 8 | 0 / 1 | 1.000 |
| Thursday | `uniq_dst_ip` | 0.101 | 1 / 8 | 0 / 4 | 1.000 |
| Thursday | `p_max` (the model) | 0.101 | 0 / 8 | 0 / 4 | 1.000 |

### Findings

1. **Neither of E14's early warnings is distinguishable from chance.** Thursday's "1 of 4 at the
   oracle threshold" scores p = 0.412 against an unaligned score of the same shape; Friday's
   "1 of 1" scores p = 0.550 and needs a 47 % alarm rate to occur at all. This does not change
   E14's conclusion - it strengthens it. D-019 withdrew the claim that `p_max` buys lead time on
   the evidence that the warnings only survived at an oracle threshold; the null says they did not
   really survive there either.
2. **The board's Y-2 bar is not measurable on the compromise denominator.** Null p95 is 2 of 4 on
   Thursday and **1 of 1 on Friday** - on a one-episode fold no observed count can ever exceed its
   own null. "Lead > 0 on >= 2 of 5 episodes" can therefore be met by chance, and a run that met it
   would prove nothing. This is the finding that forces the bar to be restated before round 3, not
   after (D-022, and D-021's amendment).
3. **Two raw features beat the model at early warning on Friday.** `uniq_dst_ip` and `fanout_mean`,
   unscaled, at the same 10 % budget, warn before the botnet C2 onset where `p_max` does not - at
   p = 0.24 and 0.22, so not significant either, but they are the floor round 3 has to clear. Both
   are features E12 ranked highest on that day (Cohen's d +1.51 and +1.39), which is consistent:
   the signal is in the state, and the model is not currently reading it.
4. **The eligibility mask matters where we expected.** Wednesday's onsets 219 and 309 have 6 of
   their 10 pre-onset windows inside the previous attack run. They are not in this table (Wednesday
   is a training day for both r2 folds) but they will be in E15, and without the mask a pure
   detector would collect two free warnings there.
5. **Zero-alarm policies behave correctly under the null.** Thursday's train-tuned and
   alert-budget-5 % thresholds fire on 0.0 % of windows, so the null mean is 0.00 and p = 1.000 -
   the harness does not manufacture a comparison where there is nothing to compare.

Full table, all six threshold policies and all three episode denominators:
`results/tables/e15a-null-calibration-e14-pmax-rescore-e4e7-worldmodel-r2.csv`; the per-statistic
Fisher combination across folds is in the `_combined.csv` beside it. That table also carries the leave-one-day-out
logistic-regression floor on the precursor label, added with E15's other floors: ROC-AUC 0.604
Thursday and 0.556 Friday, against E12's *within-day* 0.883 and 0.955. The E12 signal does not
transfer across days for a linear model on the same features.

---

## E15 - precursor supervision (Y-2, round 3): the target was not the cause either

```
python scripts/train.py --config configs/cicids2017.yaml \
    --model-config configs/model_r3_precursor.yaml \
    --test-days tuesday wednesday thursday friday monday \
    --run r3-precursor-s42 --epochs 25 --seed 42        # and s43/44 with --seed 43/44
python scripts/precursor_eval.py --run r3-precursor-s42 r3-precursor-s43 r3-precursor-s44 \
    --deterministic --n-shifts 2000
```
run: `results/runs/e15-precursor-r3-precursor-3seeds/` · 3 training seeds x 5 leave-one-day-out
folds · two new risk channels per D-023: `onset_now` (a first-occurrence hazard, unioned over the
rollout - the forecasting claim) and `precursor` (read off the filtered posterior - a representation
claim). Bar pre-registered in D-023 before the run.

### The bar, and the answer

**Failed on every clause, on every seed.**

| clause of the D-023 bar | required | best observed |
|---|---|---|
| folds exceeding the null's 95th percentile | >= 2 of 4 | **1 of 4**, and only on seed 43 |
| Fisher-combined p across folds | < 0.05 | **0.166** (`p_onset_cum`, seed 43, all attack episodes) |
| holds with Impact excluded | yes | **0 of 4 folds** for `p_onset_cum` on all three seeds |
| stable over >= 3 training seeds | yes | no statistic clears any clause on more than one seed |

Across the whole table, **21 of 1,080 cells with a null p-value fall below 0.05, where chance alone
would give about 54.** The result is not merely non-significant; it is less significant than noise.

### Ranking on the precursor label, leave-one-day-out (ROC-AUC, mean of 3 seeds)

| statistic | Tuesday | Wednesday | Thursday | Friday |
|---|---:|---:|---:|---:|
| `p_onset_cum` - union of the first-occurrence hazard (**the forecast claim**) | 0.590 | 0.629 | **0.440** | 0.624 |
| `p_onset_max` - max over horizon of the same channel | 0.607 | 0.629 | 0.488 | 0.628 |
| `p_precursor` - filtered posterior (**the representation claim**) | 0.596 | **0.369** | 0.477 | 0.610 |
| `p_max` - **the same run's channel 0**, the within-run control | 0.663 | 0.652 | 0.533 | 0.630 |
| logistic regression, LODO, same label (floor) | 0.686 | 0.574 | 0.604 | 0.556 |
| `uniq_dst_port`, unscaled (floor) | 0.745 | 0.542 | 0.607 | 0.558 |
| `uniq_dst_ip`, unscaled (floor) | 0.570 | 0.675 | 0.578 | 0.560 |
| `fanout_mean`, unscaled (floor) | 0.540 | 0.670 | 0.585 | 0.558 |

1. **Both new heads lose to the run's own compromise channel on all four folds.** That is the control
   D-023 pre-registered precisely so that a comparison against the round-2 checkpoint could not be
   mistaken for a result.
2. **On Thursday - the infiltration fold, the PS-relevant one - everything the model produces sits
   at or below chance** (0.440-0.533) while plain logistic regression reaches 0.604 and a single
   unscaled feature reaches 0.607.
3. `p_precursor` on Wednesday is **0.369**, well below chance and consistent across seeds.

### The heads trained. They just did not transfer.

| seed | `precursor` loss, Thursday fold | `imagine_precursor` |
|---|---|---|
| 42 | 1.388 -> 0.450 | 1.372 -> 0.369 |
| 43 | 1.393 -> 0.316 | 1.385 -> 0.230 |
| 44 | 1.371 -> 0.348 | 1.384 -> 0.268 |

The loss falls by two thirds and the leave-one-day-out ranking does not improve. This is the round-1
signature from a different direction: in round 1 the compromise head memorised the one attack family
it saw (D-016); here the precursor heads fit day-specific run-ups and carry nothing to a held-out
day. E12's separability is real and remains within-day.

### The cost: round 3 is measurably worse at detection than round 2

`p_max` on the held-out Thursday, self-budget 10 %, the E14-comparable configuration:

| run | F1 | precision | FPR | PR-AUC | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| round 2 (E14) | **0.576** | **0.776** | **0.027** | **0.640** | **0.827** |
| round 3, seed 42 | 0.523 | 0.704 | 0.036 | 0.439 | 0.750 |
| round 3, seed 43 | 0.439 | 0.592 | 0.050 | 0.353 | 0.697 |
| round 3, seed 44 | 0.492 | 0.663 | 0.041 | 0.445 | 0.754 |

Adding two more targets to the shared trunk **cost about 0.20 PR-AUC on the fold that matters** and
bought nothing. This is not a mean-path artefact: on the same Thursday checkpoint the deterministic
mean path and the 16-sample Monte-Carlo score agree at Spearman rho **0.995** (PR-AUC 0.4387 vs
0.4396), and the same comparison on the round-2 checkpoint returns PR-AUC 0.6436, reproducing E14's
published 0.640. Friday is unchanged and still broken (ROC-AUC 0.47-0.54).

### The cherry the bar stopped us picking

One cell in the table reaches significance: `p_precursor`, Friday, seed 42, the compromise
denominator - 1 of 1 episodes warned early at a 2.1 % alarm rate, FPR 0.013, precision 0.450,
**p = 0.0375**. Quoted alone it reads like the result Y-2 was looking for. It is one fold of four,
one seed of three (seed 43 gives 0 of 1; seed 44 gives 1 of 1 at p = 0.314), on a denominator of a
single episode, out of 1,080 cells. It is exactly what D-023's stability and multi-fold clauses were
written to exclude, and it is recorded here so that nobody rediscovers it later and quotes it.

### What this settles

E13 ruled out the alarm statistic. E14 ruled out the threshold. E15a showed E14's two surviving
early warnings were themselves indistinguishable from chance. **E15 now rules out the supervision
target**, which was the last of the four candidate causes named in D-019, tested on the target
D-019 itself nominated and with more positives per fold than the literal definition allows.

The honest conclusion is the one D-021 already froze: NetWM delivers the PS's required outputs -
learned transition dynamics, K-step rollouts, stage forecasts, explanations - and does not warn
before compromise. What E15 adds is that the gap is now bounded on all four sides by experiments
rather than by argument, and that the round-2 configuration remains the one to ship: **round 3's
heads are not merely unhelpful, they are a regression, and `configs/model_r3_precursor.yaml` should
not be used for the submission checkpoints.**

Remaining untested directions, in order of what E15 makes most plausible - all of them about the
*state*, not the objective: `S_t` is levels-only (S-1's trend and slope features), network-wide
aggregates hide per-host behaviour (S-2), and every result here is a single week of one synthetic
capture with 26 attack episodes and 5 compromise onsets.

Artefacts: `results/tables/e15-precursor-r3-precursor-3seeds.csv` (full table: 4 statistics x 3
floors x 6 threshold policies x 3 episode denominators x 5 folds x 3 seeds),
`..._combined.csv` (Fisher per run), `results/tables/r3-precursor-s4*_training_curves.csv`
(the loss curves Y-2 asks for), `results/figures/e6_r3-precursor-s4*_*.png`. The 15 round-3
checkpoints are **not** committed - 36 MB for a configuration this experiment rejects; regenerate
them with the training command above, which pins the seed, the config and the git SHA.

---

## E8 - leave-one-attack-family-out (generalisation to unseen attacks)

`python scripts/rescore_pmax.py --run e4e7-worldmodel-r2` · **a re-analysis of the E14 checkpoints,
not a new training run**

Read it as framing, not as new evidence: the leave-one-day-out folds *are* family holdouts for these
two families, because infiltration occurs only on Thursday and the ARES botnet only on Friday, so a
model tested on either has never seen that family in training. No model was retrained for this
section and the numbers are E14's. A genuine family holdout that retrains - e.g. dropping Friday's
botnet windows from a Thursday-test fold - is a separate experiment we have not run.

The core limitation of the current training data is that four days of training contain exactly one kind of compromise. This experiment formalises the performance when a specific attack family is held out during training.

| held-out family | test fold | ROC-AUC | PR-AUC | base rate | F1 (oracle) | FPR (oracle) |
|---|---|---:|---:|---:|---:|---:|
| Infiltration | Thursday | **0.827** | **0.640** | 0.171 | 0.584 | 0.065 |
| Botnet C2 | Friday | 0.438 | 0.109 | 0.131 | 0.216 | 0.469 |

### Findings

1. **Unseen families remain at chance.** When the model is tested on Friday (Botnet C2), having only seen Thursday's internal port sweeps in training, it scores worse than chance (ROC-AUC 0.438) and produces no early warnings at a deployable threshold. It fails to generalise "attacker advancing" to an unseen family.
2. **Infiltration is detected.** When Thursday (Infiltration) is held out, the model successfully detects it (ROC-AUC 0.827, PR-AUC 3.7x base rate), though still without reliable lead time.
3. **Conclusion:** Generalisation requires a more diverse training set. This defines the core data limitation for M1, which M2 (CTU-13 dataset with concurrent attacks) is meant to address.

---

## E16 - rank normalisation (Y-6, round 4): representation is not the cause either

```
python scripts/train.py --config configs/cicids2017.yaml \
    --model-config configs/model_r4_rank.yaml \
    --test-days tuesday wednesday thursday friday monday \
    --run r4-rank-s42 --epochs 25 --seed 42          # and s43/44 with --seed 43/44
python scripts/precursor_eval.py --run r4-rank-s42 r4-rank-s43 r4-rank-s44 \
    --deterministic --n-shifts 2000 --experiment E16
```
run: `results/runs/e16-precursor-r4-rank-3seeds/` · 3 training seeds x 5 leave-one-day-out folds ·
**round-2 heads**, causal `rank_window: 120`, so the feature transform is the only variable (D-025) ·
scored against the bar pre-registered in D-023.

### The bar, and the answer

**Failed on every clause, on every seed, on every episode denominator.**

| clause of the D-023 bar | required | best observed |
|---|---|---|
| folds exceeding the null's 95th percentile | >= 2 of 4 | **0 of 4**, all three seeds |
| Fisher-combined p across folds | < 0.05 | **0.715** (`p_max`, seed 43, all attack episodes) |
| holds with Impact excluded | yes | 0 of 4 folds |
| stable over >= 3 training seeds | yes | see the detection collapse below |

### Ranking on the precursor label, leave-one-day-out (ROC-AUC, mean of 3 seeds)

| statistic | Tuesday | Wednesday | Thursday | Friday |
|---|---:|---:|---:|---:|
| `p_max` - **r4's own channel 0**, the within-run control | 0.575 | 0.495 | **0.490** | 0.570 |
| logistic regression, `log_standard` (floor) | 0.686 | 0.574 | 0.604 | 0.556 |
| logistic regression, `rank_window: 120` (matched floor) | 0.556 | **0.802** | 0.497 | 0.568 |
| `uniq_dst_port`, unscaled (floor) | 0.745 | 0.542 | 0.607 | 0.558 |
| `uniq_dst_ip`, unscaled (floor) | 0.570 | 0.675 | 0.578 | 0.560 |
| `fanout_mean`, unscaled (floor) | 0.540 | 0.670 | 0.585 | 0.558 |

r4 is at chance on Thursday (0.490) and Wednesday (0.495), and loses to a **single unscaled column**
on all four folds. For comparison, r3's `p_max` scored 0.533 / 0.652 / 0.663 / 0.630 on the same
label: r4 ranks *worse* than r3, which itself ranked worse than r2.

**The one number that goes up.** Logistic regression on rank features scores **0.802 on Wednesday**,
the highest precursor ROC-AUC anywhere in this project. Read it with the denominator: 6 of
Wednesday's 7 onsets are Impact (DoS), and rank normalisation asks "is this window unusual for this
capture", which is exactly the question a DoS ramp answers loudest. It is not evidence about
infiltration, and it does not transfer - the same floor scores 0.497 on Thursday.

### The cost: detection survives on two seeds and collapses on the third

`p_max` on the held-out Thursday, self-budget 10 %, the E14-comparable configuration:

| run | F1 | precision | FPR | PR-AUC | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| round 2 (E14) | 0.576 | 0.776 | 0.027 | **0.640** | **0.827** |
| round 3 (E15, 3 seeds) | 0.439-0.523 | 0.592-0.704 | 0.036-0.050 | 0.353-0.445 | 0.697-0.754 |
| round 4, seed 42 | **0.591** | **0.796** | **0.025** | 0.607 | 0.827 |
| round 4, seed 43 | 0.553 | 0.745 | 0.031 | 0.629 | 0.810 |
| round 4, **seed 44** | **0.023** | **0.031** | 0.118 | 0.221 | 0.597 |

This is a different failure from round 3. Round 3 was a uniform regression; round 4 **matches round 2
on two seeds out of three and then collapses on the third**. Rank normalisation does not cost
detection on average - it makes it unstable, and a one-in-three catastrophic seed is
disqualifying on its own for a system that has to be demonstrated live. Friday is worse than round 2
on every seed (ROC-AUC 0.299-0.411 against 0.438). Only a three-seed run could see this; a single
seed would have reported r4 as matching r2 (seed 42) or as broken (seed 44), and both would have been
one third of the truth.

### Per-onset diagnostic (added after the run; not part of the bar)

`results/tables/e16-precursor-r4-rank-3seeds_per_onset.csv`. A gap of 7 windows since the previous
attack and a gap of 394 mean opposite things: the first sits inside traffic that has already raised
the whole trailing hour, so crediting it is closer to detecting a campaign under way than to
forecasting a new one. Quiet run-up counts strictly-quiet windows, so they sit one below an
inclusive count.

Thursday, `p_max` at self-budget 10 %, warned/3 seeds:

| onset | family | quiet windows before | warned |
|---|---|---:|---:|
| 39 | Initial Access | 39 | 0 / 3 |
| 153 | Initial Access | 31 | 0 / 3 |
| 201 | Initial Access | 7 | 0 / 3 |
| **602** | **Reconnaissance** | **394** | **0 / 3** |
| 639 | Lateral Movement | 35 | 1 / 3 |
| 658 | Lateral Movement | 17 | 0 / 3 |
| 708 | Lateral Movement | 20 | 0 / 3 |
| 729 | Lateral Movement | 7 | 0 / 3 |

**Onset 602 is never warned, on any seed.** It has the longest quiet run-up in the dataset - first of
the afternoon campaign, 394 windows - which is why it was the obvious place to look for a real
precursor. **S-8 below shows it is not one:** the rise is carried by bystander hosts, so a model that
warned there would have been right for the wrong reason, and r4's silence on it is not the failure
this paragraph originally read it as. Pooling all folds and seeds, r4 warns on 8 of 78 onset-seed
combinations, and they are *not* concentrated in the clean run-ups: 2 of 30 for gaps > 40 windows,
5 of 27 for 11-40, 1 of 21 for <= 10. So the answer to "lost a precursor or lost campaign residue"
is **neither** - r4 finds essentially nothing in either category.

Also settled on the raw capture: the pre-602 elevation is **not** attempted traffic that D-009
zeroes out. All 4356 flows in windows 592-601 are labelled `BENIGN` with `Attempted Category = -1`;
Thursday's 1997 attempted flows all carry `- Attempted` in the label and none fall in that block.
The one clean precursor on Thursday is a genuine rise in `uniq_dst_port` through traffic the
corrected dataset labels benign. D-009's revisit clause is not triggered.

**Who carries the rise (S-8).** `python scripts/onset_audit.py --day thursday --onset 602` ->
`results/tables/s8_thursday_onset602_{windows,hosts}.csv`. The script first checks that
`uniq_dst_port` recomputed from the raw flows equals the matrix column exactly. The rise is real:
14.5 over the run-up against 9.7 over the 120 windows before it. But it is carried by bystanders.
192.168.10.9 opens more ports on 192.168.10.3 (+4.3 distinct ports per window), with smaller
increases from .17, .25 and .19. The hosts the attack touches do not move: the scan's target
192.168.10.51 (+0.1), the host compromised at 17:19, 192.168.10.8 (-0.4), and the scanner 172.16.0.1,
which is absent. .25 is the Cool Disk victim 53 minutes later. In the run-up it sends only NTP,
NetBIOS, SMB, LDAP and mDNS. The level also stays up after the onset: 13.7 over windows 604-638. The
onset itself is a 14-second external scan: 172.16.0.1 -> 192.168.10.51, 954 ports,
17:00:31-17:00:45.

So 602's run-up has the *shape* of a precursor, a long quiet gap followed by a rise, without the
*content* of one. Nothing in it comes from the attack. A model that warned there would have been
right for the wrong reason. The circular-shift null exists to guard against exactly this, and this
is its first concrete instance. The other seven Thursday onsets have not been audited this way.

### Diagnostic arm: whole-capture rank (E16D, excluded from the bar)

`results/tables/e16d-precursor-r4-rank-whole-s42.csv`, one seed. Reported per D-025, which forbids a
lead-time claim resting on it: ranking against the whole capture lets windows *after* an onset set
the scale of the windows before it.

Thursday: 3 of 8 episodes warned, null p95 3, **p = 0.054**. That is the best early-warning p-value
this project has produced, and it is not admissible - it is also the number that would have ended up
on a slide had the arm not been labelled before it was run. Its precursor ROC-AUC is 0.585, still
below `uniq_dst_port` at 0.607.

One identity worth recording: whole-capture rank **must** equal `log_standard` univariately, because
a rank is monotone within the capture and cannot reorder a single column. Any difference it makes is
multivariate only - it makes columns commensurable, nothing more.

### What this settles

Four causes were already eliminated: statistic (E13), threshold (E14), data (E12), target (E15).
**E16 eliminates the representation**, on the transform D-025 nominated, with the floors on the same
table. Every candidate rank variant is now either measured or argued out:

| candidate | status |
|---|---|
| causal `rank_window: 120` | **run: fails the bar, unstable across seeds (this entry)** |
| whole-capture rank | diagnostic only, inadmissible by D-025; univariately identical to level |
| level + rank concatenated | not supported - Thursday LR 0.560 vs 0.604 for level alone, and with ~8 effective episodes a 0.04 gap is inside the noise |
| rank on the v2 trend features | out - `uniq_dst_port_slope_5/_10/_delta` score 0.487 / 0.480 / 0.475 univariately *before* any rank, so there is no rise for a slope to re-express |
| reference CDF fitted on the training days | out by construction - a monotone map preserves within-day ordering, so it cannot be more robust to a day-level shift than `log_standard` |

**Where the signal actually dies: cross-day transfer, not the transform.** On Thursday, logistic
regression over all 70 features scores 0.604 while `uniq_dst_port` alone scores 0.607 - a 70-input
model gains *nothing* from 69 extra features when it is trained on other days' attack families and
scored on web attacks and infiltration. The same comparison under rank is 0.497 against 0.573, i.e.
actively worse. The weights do not carry across families. (Both sets of numbers use all non-precursor
windows as negatives; restricting negatives to non-attack windows raises the univariate figures to
0.678 / 0.633 / 0.629 without changing the comparison, and the two conventions must not be mixed.)

That points the next experiment at generalisation across families rather than at features:
**Y-3's real leave-one-attack-family-out with retraining** - dropping Friday's botnet windows from a
Thursday-test fold - which E8 currently approximates by re-analysing the existing folds. And
**Y-4 on `S_t` v2 levels**, where the floors already favour the trend block under the *existing*
D-014 scaler: LR scores 0.626 on Thursday with v2 levels against 0.604 with v1, the best
level-representation figure measured so far.

Artefacts: `results/tables/e16-precursor-r4-rank-3seeds{,_combined,_per_onset}.csv`,
`results/tables/e16d-precursor-r4-rank-whole-s42{,_combined,_per_onset}.csv`,
`results/tables/r4-rank-s4*_training_curves.csv`, `results/runs/r4-rank-*/train.log`. The 20 round-4
checkpoints are not committed (rejected configuration); the commands above pin seed, config and SHA.

---

## E17 - Calibration of e4e7-worldmodel-r2 on Held-out Days

`python scripts/calibration_eval.py` · run: `ac4ec62` · 2026-09-26

**Write-up (Y-1w / Y-1x):** E17 tests whether calibration transfers to unseen days. 

- **What was scored:** `p_cum[:, K-1]` (P(compromise within K)) against `y_within_K`.
- **The in-sample caveat:** The temperature was fitted on the checkpoint's own training days, because no held-out training day with positives exists. So E17 answers "does an in-sample temperature transfer".
- **Thursday (Held-out):** Brier score 0.097 against 0.142 for a constant base rate. ECE improved from 0.077 to 0.061 with temperature scaling.
- **Friday (Held-out):** Brier score 0.280 against 0.114, which is *worse than a constant baseline*. ECE worsened from 0.245 to 0.270 with temperature scaling. Furthermore, Friday severely over-forecasts: the mean forecast is 0.274 against a 0.131 base rate, and its most confident bins are nearly always wrong.

**Conclusion:** Temperature scaling makes calibration worse on the Friday fold. Calibration does not transfer to unseen days, so probabilities cannot be quoted honestly. We must maintain the alert budget (D-017 stays) and ensure the dashboard labels p-values as "score", not "calibrated probability". 

Artefacts: `results/tables/e17_*`, `results/figures/e17_reliability.png`. `scripts/calibrate.py` is marked superseded.

---

## E10 - Ablation Study (Stochastic Latent & Multi-step Rollout)

`python scripts/e10_collect.py` · 2026-09-26

**Write-up (Y-4b):** E10 tests two core model components against the D-030 bar: to earn its place, a component's removal must worsen both rollout MSE (vs persistence, across both folds) and detection F1 (Thursday, 10% budget) by at least 0.01 on $\ge$ 2 of 3 seeds. 

**1. No Stochastic Latent (`model_no_stochastic.yaml`)**
- **Seed 42:** Rollout improved by 0.018 (Thu) and 0.021 (Fri). Detection F1 worsened by 0.030 (Thu).
- **Seed 43:** Rollout worsened by 0.016 (Thu) and 0.007 (Fri - under margin). Detection F1 improved by 0.083 (Thu).
- **Seed 44:** Rollout worsened by 0.014 (Thu) and 0.030 (Fri). Detection F1 unchanged (0.000 diff).
**Verdict:** The stochastic latent does not earn its place. It fails to consistently improve either rollout or detection across seeds.

**2. No Multi-step Rollout Loss (`model_no_multistep.yaml`)**
- **Seed 42:** Rollout improved by 0.070 (Thu). Detection F1 improved by 0.045 (Thu).
- **Seed 43:** Rollout improved by 0.122 (Thu) and 0.008 (Fri). Detection F1 worsened by 0.205 (Thu).
- **Seed 44:** Rollout improved by 0.058 (Thu) and 0.006 (Fri). Detection F1 worsened by 0.174 (Thu).
**Verdict:** The multi-step rollout loss does not earn its place. Rollout fidelity is generally *better* without it on most seeds and folds.

**Conclusion:** Neither the stochastic latent nor the multi-step rollout loss pass the pre-registered bar. Both add complexity without reliably improving performance and are therefore marked as unsupported in the architecture document.

Artefacts: `results/tables/e10_ablation_summary.csv`.
