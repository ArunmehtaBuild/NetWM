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
| E10 | ablations | 9 retrained runs (`e10-*`), 3 seeds | `run_y4_ablation.bat` -> `rescore_pmax.py --run e10-*` -> `e10_collect.py` | `results/tables/e10_ablation_summary.csv` | neither component passes D-030; the multi-step loss earns detection (2 of 3 seeds), not rollout; headline F1 spans 0.43-0.57 over seeds |
| E17 | calibration | r2 checkpoints | `python scripts/calibration_eval.py` | `results/tables/e17_*`, `results/figures/e17_reliability.png` | temperature scaling improves held-out Thursday and fails held-out Friday (worse than a constant forecast); budget stays |
| E9 | MITRE stage confusion (G-4) | r2, held-out Thu + Fri | `python scripts/stage_confusion.py --run e4e7-worldmodel-r2` (D-035) | `results/tables/e9_*`, `results/figures/e9_*.png`, `results/runs/e9-*` | the stage that matters on each held-out day never occurs in its training days (Thu Lateral Movement, Fri C2): recall 0 on both; web attacks all called benign; merged as T1046 the sweep is found at precision 0.885 |
| E11 | explanation sanity (G-7) | r2, 6 held-out episodes | `python scripts/explain_sanity.py --run e4e7-worldmodel-r2` (D-035) | `results/tables/e11_*`, `results/figures/e11_*.png`, `results/runs/e11-*` | **fails its bar: 1 of 6 episodes** put the known signature in the top 8 (bar >= 4); on both port scans a plain |value| ranking does better than IG |
| F4 | feature build, M1 v2 | same, 93 features/window | `python scripts/build_features.py --config configs/features_m1v2.yaml` | `results/runs/f4-m1v2-build/`, `data/processed/cicids2017_m1v2/` | v1 + 17 CSV packet statistics + 6 host-relative; v1 columns and labels bit-identical to F1 |
| F5 | packet build, real captures | the five CIC-IDS2017 day PCAPs (pcapng, 52.4 GB) | `python scripts/build_packet_features.py --pcap-dir <dir>` | `results/runs/f5-pcap-build-*`, `data/processed/cicids2017_m1v2p/` | 53.7 M IPv4 packets after 2.24 M capture duplicates; 18 `pcap_` features; per-window counts track the CSV flows (corr 0.86-0.92) |
| F6 | CTU-13 build | 13 scenarios, Argus flows | `python scripts/build_ctu13.py` | `results/runs/f6-ctu13-build/`, `data/processed/ctu13/` | 20.0 M flows, 16,008 windows, chunked (== single pass) |
| E19-E23 | M1 v2 stack, step by step | 5 folds x 3 seeds | `bash scripts/run_m1v2.sh <exp> <config>` + `scripts/scorecard.py` (D-035) | `results/tables/scorecard_e19..e23.csv` | anticipation above chance before any change (S2\* 0.651); **only the factorised target (E22) passes the bar** (S2\* 0.704); packet block non-inferior; causal representation improves alarm cost only; curriculum collapses; no early warning (S3) on any run |
| E24 | Model A vs Model B | E22 stack, 3 seeds | `run_m1v2.sh e24a ...` + scorecard | `results/tables/scorecard_e24.csv` | B beats A on all seeds (S2\* +0.096, precision +0.20); *qualified by E26: LR ranks pre-onset windows at 0.659, above A and level with round 2* |
| E20r | flow-only vs flow + real packets | 5 folds x 3 seeds | `run_m1v2.sh e20r ... data/processed/cicids2017_m1v2p` | `results/tables/scorecard_e20r.csv` | packets do **not** help anticipation (S2\* 0.642 vs 0.651); they **do** help detection: Thursday PR-AUC 0.56 [0.42-0.71] vs 0.43 |
| E25 | M2, CTU-13 leave-one-family-out | 7 folds, seed 42 | `train.py --data data/processed/ctu13 --group-folds configs/ctu13_folds.yaml` | `results/tables/scorecard_e25.csv` | anticipation does **not** transfer across botnet families (S2\* 0.551); detection transfers to Neris/NSIS/Virut (ROC-AUC 0.85-0.99) and inverts on Murlo/Sogou |
| E26 | E22 + real packets, one model for CSV and PCAP (D-037) | 5 folds x 3 seeds, two input modes | `run_m1v2.sh e26 ...` + `scripts/ablation_matrix.py` | `results/tables/e26_ablation_*.csv`, `results/runs/e26-ship-decision/` | **does not compose**: detection +0.054 PR-AUC, anticipation -0.041 (bar -0.03) -> outcome 3, r2 stays shipped; LR ranks pre-onset windows at 0.659, level with round 2; inference state == training state on real Thursday (0 of 103k cells differ) |
| E18 | causal alert budget (G-8) | r2 + E10 seeds, published scores | `python scripts/threshold_eval.py` (D-034) | `results/tables/e18_*`, `results/figures/e18_*` | the causal expanding q90 keeps the signal (Thursday F1 0.608, 0.52-0.61 over seeds) but alarms 16.8 % of windows at FPR 0.078; the non-causal 0.576 is an upper bound only; the 5 % precision 0.959 does not survive |

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

```
scriptsun_y4_ablation.bat                         # 3 arms x seeds 42/43/44 x Thursday/Friday, 25 epochs
python scripts/rescore_pmax.py --run e10-<arm>-s<seed>   # all nine runs, no --write-thresholds
python scripts/e10_collect.py                       # -> results/tables/e10_ablation_summary.csv
```
runs: `results/runs/e10-*` (checkpoints gitignored) · 2026-09-26 · scored against **D-030 as amended
before any number was read** (`6390d6b`, `93e96f9`).

**The bar (D-030).** A component earns its place on a metric if removing it makes that metric worse
by more than 0.01 on >= 2 of 3 seeds, paired by seed. Rollout: R = mean over k = 2..10 of
(world-model MSE - persistence MSE), on both folds. Detection: `p_max` F1 at the 10 % budget, on
Thursday only. To be *supported*, a component must earn its place on **both** metrics.

### The full model, per seed - the spread every number below sits inside

| seed | Thursday F1 | Thursday PR-AUC | R Thursday | R Friday |
|---:|---:|---:|---:|---:|
| 42 | 0.568 | 0.640 | -0.188 | -0.119 |
| 43 | 0.432 | 0.365 | -0.182 | -0.165 |
| 44 | 0.470 | 0.412 | -0.165 | -0.162 |

Seed 42 reproduces the submission checkpoint (r2: F1 0.576, PR-AUC 0.640). **The headline F1 sits at
the top of a 0.43-0.57 seed range** (mean 0.49), and Thursday PR-AUC spans 0.37-0.64. The 0.01
margin in D-030 is far inside that spread, so a single-seed difference is not evidence on its own.
Only the >= 2-of-3 rule protects it. Friday F1 is 0.000 on every seed, as in E14.

**What holds.** R is negative for every arm, every seed and both folds. Averaged over steps 2-10,
every variant's open-loop rollout beats persistence on both held-out days. This is the evidence for
the world-model rollout claim, in its averaged form. It is *not* true step by step: r2 loses to
persistence at k = 2 on Friday (E5).

### 1. Stochastic latent (`model_no_stochastic.yaml`)

Differences are "removing it made this worse by ...", so a negative number means it got better.

| seed | R Thu | R Fri | Thursday F1 |
|---:|---:|---:|---:|
| 42 | -0.018 | -0.021 | **+0.030** |
| 43 | **+0.016** | +0.007 (within margin) | -0.083 |
| 44 | **+0.014** | **+0.030** | 0.000 |

Rollout: worse on both folds on 1 of 3 seeds (seed 44). Detection: worse on 1 of 3 (seed 42).
**Verdict: unsupported. No consistent effect in either direction.** Removing the latent hurts some
seeds and helps others. That neither supports it nor shows a deterministic model is better.

### 2. Multi-step rollout loss (`model_no_multistep.yaml`)

| seed | R Thu | R Fri | Thursday F1 |
|---:|---:|---:|---:|
| 42 | -0.070 | **+0.024** | -0.045 |
| 43 | -0.122 | -0.008 (within margin) | **+0.205** |
| 44 | -0.058 | -0.006 (within margin) | **+0.174** |

Rollout: worse on both folds on 0 of 3 seeds. Thursday rollout is *better* without the loss on all
three seeds. Detection: worse on 2 of 3 seeds, by 0.205 and 0.174 F1.
**Verdict: unsupported under D-030's both-metrics rule, but it earns its place on detection.** The
loss imagines the compromise and stage heads forward (`imagine_compromise`, `imagine_stage`). What it
buys is detection, not rollout fidelity. Removing it would cost about 0.2 F1 on two of three seeds.
It stays in the model, described for what it does.

### What E10 settles

- Neither component is supported under the pre-registered bar. `docs/architecture.md` claims neither
  as the reason the rollout works.
- The multi-step loss is a detection component, not a rollout component, and it is kept.
- The stochastic latent has no demonstrated effect. It is kept because the submission checkpoint has
  it and the Monte-Carlo bands come from it, and the doc says it is unsupported.
- The headline F1 (0.576, seed 42) should never be quoted without this 0.43-0.57 seed range. How
  the slides, demo script and model card quote it is an open decision on the board.

Artefacts: `results/tables/e10_ablation_summary.csv`, `results/tables/e14_pmax_rescore_e10-*.csv`,
`results/runs/e10-*`, `results/runs/e14-pmax-rescore-e10-*`.

---

## E18 - A causal alert budget (G-8): the signal survives, the 10 % budget does not

```
python scripts/threshold_eval.py      # pre-registered in D-034 (e87a8aa) before this was run
```
Scores: the held-out `p_max` scores E14 published for r2 and the three E10 full seeds. No
re-inference, so the whole-capture row reproduces E14 exactly (F1 0.5758). r2's training-day scores
were recomputed with E14's exact procedure; the held-out scores recomputed alongside matched the
published ones, so these are E14's own training-day scores. Label: `y_within_K`; lead time as in E14.

**Why this was run.** E14's deployable threshold, the one behind 0.576, is the 90th percentile of the
*whole* held-out day, windows after the one being judged included. So is the dashboard's
(`engine/predict.py`). A live sensor has only the past.

### Held-out Thursday, r2 checkpoint (seed range from the E10 full seeds in brackets)

| policy | causal | alarm rate | precision | recall | F1 | FPR | warned early |
|---|:---:|---:|---:|---:|---:|---:|---:|
| whole-capture q90 (E14) | **no** | 0.101 | 0.776 | 0.458 | 0.576 [0.43-0.57] | 0.027 | 0/4 |
| **expanding q90 - primary** | yes | **0.168** [0.13-0.17] | **0.614** [0.54-0.64] | **0.602** [0.50-0.60] | **0.608** [0.52-0.61] | **0.078** [0.06-0.09] | 2/4, p = 0.33 |
| trailing-120 q90 | yes | 0.135 | 0.397 | 0.313 | 0.350 [0.31-0.35] | 0.098 | 0/4 |
| trailing-60 q90 | yes | 0.161 | 0.308 | 0.289 | 0.298 [0.18-0.30] | 0.134 | 0/4 |
| expanding q95 | yes | 0.131 | 0.661 | 0.506 | 0.573 [0.23-0.57] | 0.053 | 1/4 |
| training-day q95 | yes | 0.000 | 0 | 0 | 0.000 | 0.000 | 0/4 |

Friday: every policy is near zero, as in E14. The expanding q90 gives F1 0.061. The trailing-60 gives
0.251 and warns 1 of 1 (p = 0.29), but it scores 0.30 on Thursday, and per D-034 a secondary policy
cannot be adopted on one fold's result.

### What E18 shows

1. **The detection signal survives a real-time threshold.** On the pre-registered primary policy,
   Thursday F1 is 0.608 on the shipped checkpoint (0.52-0.61 over three seeds), against the
   non-causal 0.576 (0.43-0.57). The Thursday plot (`e18_thursday_thresholds.png`) shows why.
   The expanding threshold is built from a quiet day, so it sits near 0.005 when the attack starts
   and lets the attack's lower-scoring windows through. The whole-capture threshold (0.0455) is
   partly set *by* the attack: a tenth of the "whole day" is the attack's own high scores. So the
   causal version buys recall (0.46 -> 0.60) with precision (0.78 -> 0.61).
2. **What it no longer is: a 10 % budget.** It fires on 16.8 % of windows, and the FPR roughly
   triples (0.027 -> 0.078). A percentile of a day's *past* is not a cap on its future alert volume.
   Wherever "at a 10 % alert budget" and "2.7 % FPR" were quoted, the deployable figures are now
   16.8 % of windows alarmed at 7.8 % FPR.
3. **The 5 % figure does not survive.** D-021's precision 0.959 at a 5 % budget becomes 0.661 under
   the causal q95, and its F1 is unstable across seeds (0.23-0.57).
4. **No early warning.** The primary's 2 of 4 warned early is chance: a circular-shift null of the
   same alarm sequence averages 0.97 and reaches 3 at its 95th percentile, p = 0.33. It meets no
   clause of D-023.
5. **Why a training-day threshold fires nothing** (`e18_score_distributions.png`,
   `e18_score_distributions.csv`). The in-sample training-day scores reach 0.99 (q95 0.517), while
   held-out Thursday tops out at 0.47 (q95 0.182). Held-out Friday is the opposite: its top 10 % sits
   at 0.94-0.99 on windows that are not compromise, the over-forecast E17 found.
6. **Trailing windows are worse on Thursday** (0.30-0.35). A sustained attack fills the trailing hour
   and raises its own threshold, the saturation E16 saw with trailing rank.

**Commitment (D-034).** Everywhere D-032 applies, the deployable Thursday number becomes **F1 0.608
(0.52-0.61 over three seeds) at 16.8 % of windows alarmed, precision 0.614, FPR 0.078**, with the
causal expanding budget. 0.576 may be quoted only as a non-causal upper bound. *(G-9, `f2bb6de`:
the dashboard, model card and fixtures now run the primary policy through the same function.)*

Artefacts:
- `results/tables/e18_window_scores_e4e7-worldmodel-r2_{thursday,friday}.csv`: per window, the
  score, label, stage, every policy's threshold and alarm.
- `results/tables/e18_score_distributions.csv`, `results/tables/e18_policy_summary.csv` (all runs x
  days x policies).
- `results/figures/e18_{thursday,friday}_thresholds.png`, `results/figures/e18_score_distributions.png`.

---

## E9 - MITRE stage confusion on held-out days (G-4)

```
python scripts/stage_confusion.py --run e4e7-worldmodel-r2      # design: D-035 (529289d)
```
Rows are the window's ground-truth stage; columns are `argmax stage_now`, read off the filtered state
on the deterministic mean path. Scored on each fold's held-out day only.

*Design credit: Yash designed E9 independently (PR #13). His script, with a one-character fix for
Python 3.10, reproduces the matrices below exactly. The script on main adds the `in_training` column
and the technique view, and writes the artefacts.*

| held-out day | stage | windows | predicted | precision | recall | stage on a training day? |
|---|---|---:|---:|---:|---:|:---:|
| Thursday | Benign | 736 | 888 | 0.821 | 0.991 | yes |
| | Reconnaissance (17:00 scan) | 2 | 78 | 0.013 | 0.500 | yes |
| | Initial Access (web attacks) | 126 | 0 | - | **0.000** | yes |
| | Lateral Movement | 108 | 0 | - | **0.000** | **no** |
| Friday | Benign | 759 | 556 | 0.845 | 0.619 | yes |
| | Reconnaissance (port scan) | 52 | 37 | 0.405 | 0.288 | yes |
| | Command and Control (Ares) | 116 | 0 | - | **0.000** | **no** |
| | Impact (DDoS) | 41 | 54 | 0.759 | **1.000** | yes |

Where the Thursday windows go: Lateral Movement goes to Reconnaissance on 68 windows, to Benign on 35
and to Impact on 5. The web attacks go to Benign (123) and Reconnaissance (3). On Friday, C2 goes to
Benign (82) and Initial Access (34). And 38 % of Friday's benign windows get a hostile stage: Initial
Access 185, Lateral Movement 69, Reconnaissance 22, Impact 13.

**Technique view** (Reconnaissance and Lateral Movement merged as T1046, network service discovery,
which D-012 splits only by source address). Thursday's T1046 windows: precision **0.885**, recall
**0.627**. Friday's: precision 0.248, recall 0.577.

### What E9 shows

1. **The stage that matters on each held-out day is a class its training days never contain.**
   Leave-one-day-out on CIC-IDS2017 is leave-one-family-out (D-006). Thursday is the only day with
   Lateral Movement and Friday the only day with C2, so the stage head scores 0 recall on both by
   construction. That is a property of the split, not a model failure, but it means **stage mapping
   of compromise cannot be validated on this dataset with a held-out day.** M2 (CTU-13, seven
   families) is where it can be.
2. **The sweep is found as a technique, not as a stage.** Merged, 68 of the 108 sweep windows are
   called discovery, at precision 0.885. The model recognises the behaviour; it has no way of telling
   an internal source from an external one, because it never saw an internal scan.
3. **Initial Access is missed entirely on Thursday** (0 of 126), although brute force was in
   training on Tuesday. Web brute force and XSS against port 80 do not look like FTP/SSH-Patator in
   flow aggregates, and the stage head does not generalise across that gap.
4. **Impact transfers** (Friday DDoS recall 1.0, trained on Wednesday's DoS). This is the one family
   with a close relative in training, which fits D-029's diagnosis: transfer works within a family
   and fails across families.

Artefacts: `results/tables/e9_e4e7-worldmodel-r2_{confusion,per_stage}.csv`,
`results/figures/e9_e4e7-worldmodel-r2.png`, `results/runs/e9-e4e7-worldmodel-r2/metrics.json`.

---

## E11 - Do the dashboard's explanations point at the attack? (G-7)

```
python scripts/explain_sanity.py --run e4e7-worldmodel-r2       # signature sets and bar: D-035 (529289d)
```
This runs the dashboard's own Integrated-Gradients attribution (`engine/explain.explain_window`,
unchanged) on the r2 checkpoint, over up to 24 evenly spaced attack windows per held-out episode. For
each episode it ranks the 70 features by mean |attribution| and counts the pre-registered signature
features in the top 8. The p-value is hypergeometric (the chance of that many hits from a random 8).
**The bar: an episode passes at p < 0.05, and E11 passes if at least 4 of 6 do.**

| episode | windows | IG hits / 8 | p | chance | control: \|value\| hits | Spearman IG vs \|value\| |
|---|---:|---:|---:|---:|---:|---:|
| Thu 17:00 external port scan | 2 | 3 | 0.105 | 1.26 | **5** (p 0.002) | 0.81 |
| Thu internal sweep | 24 | 4 | 0.059 | 1.71 | 4 (p 0.059) | 0.79 |
| Thu web attacks | 24 | 1 | 0.688 | 1.03 | 2 | 0.46 |
| Fri botnet C2 (Ares) | 24 | 3 | **0.043** | 0.91 | 1 | 0.45 |
| Fri port scan | 24 | 1 | 0.765 | 1.26 | **4** (p 0.018) | 0.77 |
| Fri DDoS LOIC | 24 | 3 | 0.060 | 1.03 | 2 | 0.80 |

**E11 fails: 1 of 6 episodes passes** (bar: 4).

*Design credit: Yash's E11 draft (PR #13) printed the top attributions for one window per attack,
without a criterion, and crashed on a key name. The version run here fixes the signature sets and the
bar before looking.*

### What E11 shows

1. **The attributions are above chance but do not reliably point at the attack.** Every episode except
   the two weakest scores more hits than chance, and the internal sweep (4 hits, p 0.059) and DDoS (3,
   p 0.060) come close. But only Friday C2 clears p < 0.05. The dashboard's why panel cannot be
   presented as "the model looks at the right features".
2. **On port scans, "which features are unusual" beats IG.** Ranking by |scaled value| puts 5 scan
   signatures in the top 8 on Thursday and 4 on Friday; IG puts 3 and 1. IG attributes the
   *compromise forecast*, and a scan from outside is not a compromise, so it spreads its attribution
   over features like `svc_rdp_rate` and `proto_udp_rate`. That is a mismatch between the target
   explained and the question asked, and it matches E9's finding that the stage and risk heads read
   scans as something else.
3. **IG largely restates the input's magnitude.** On four of the six episodes it correlates 0.77-0.81
   with the |value| ranking. The one episode that passes is also the one where it departs most from it
   (rho 0.45).

**Consequence for the product.** The why panel should label its bars as "features pushing the
compromise score", not "why this is an attack". The claims audit carries this.

Artefacts: `results/tables/e11_e4e7-worldmodel-r2_{episodes,rankings}.csv`,
`results/figures/e11_e4e7-worldmodel-r2.png`, `results/runs/e11-e4e7-worldmodel-r2/metrics.json`.

---

## E19-E23 - the M1 v2 programme, scored on the D-035 scorecard (not on Thursday F1)

```
python scripts/build_features.py --config configs/features_m1v2.yaml          # F4: v1 + pkt_ + hostrel_
bash scripts/run_m1v2.sh <exp> configs/m1v2/<exp>.yaml                          # 5 folds x seeds 42/43/44
python scripts/scorecard.py --variant BASE=... --variant CAND=... --compare CAND:BASE --tag <exp>
```
Everything below was pre-registered in D-035 (`529289d`) before any of it was trained. Each step
was run once, in order, and compared with the stack as it stood.

**The scorecard.**
- **S1** is alarm cost: `comp` at the causal expanding q90 (D-034), pooled over Thursday and Friday.
- **S2** is anticipation: the `threat` score's percentile, among the same day's quiet reference
  windows, of the eligible windows 0-2, 2-4, 4-6 and 6-10 minutes before each of the 19 non-Impact
  attack onsets. 0.5 is chance. **S2\*** is the mean of the three bins from 2 to 10 minutes.
- **S3** is early-warning significance against the circular null.
- **S4** is the worst held-out day.

The bar has three clauses:
1. S2\* rises by at least 0.03 and rises on at least 2 of 3 seeds.
2. S1 precision falls by less than 0.05 and S1 FPR rises by less than 0.02.
3. No seed has Thursday PR-AUC below 0.20.

### The stack, step by step (mean over seeds 42/43/44; range in brackets)

| exp | step | S1 precision | S1 FPR | S2 bins 0-2 / 2-4 / 4-6 / 6-10 min | **S2\*** | isolated onsets (diag.) | worst day | Thu PR-AUC | Thu F1, causal | verdict |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| **E19** | round 2, S_t v1 | 0.325 [0.31-0.35] | 0.120 | 0.69 / 0.69 / 0.66 / 0.60 | **0.651** [0.63-0.68] | 0.631 | 0.566 | 0.434 [0.41-0.47] | 0.514 | baseline |
| **E20** | + CSV packet block | 0.350 [0.30-0.44] | 0.137 | 0.68 / 0.71 / 0.68 / 0.59 | **0.658** [0.59-0.70] | 0.631 | 0.599 | 0.414 | 0.541 | clause 1 fails (+0.008); **carried forward** as non-inferior (PS requirement) |
| **E21** | + causal representation + host-relative | 0.416 [0.40-0.45] | 0.110 | 0.66 / 0.69 / 0.70 / 0.61 | **0.667** [0.62-0.71] | 0.636 | 0.635 | 0.465 | 0.561 | clause 1 fails (+0.008) - **not adopted** |
| **E22** | + factorised target | 0.322 [0.31-0.33] | 0.115 | 0.76 / 0.75 / 0.70 / 0.65 | **0.704** [0.66-0.75] | 0.670 | 0.644 | 0.389 | 0.499 | **adopted**: +0.045 (+0.019 / +0.162 / -0.046), precision -0.028, FPR -0.023 |
| **E23** | + precursor curriculum | 0.137 [0.02-0.25] | 0.128 | 0.64 / 0.69 / 0.64 / 0.58 | **0.634** [0.61-0.66] | 0.622 | 0.568 | 0.223 [0.19-0.29] | 0.152 | **fails every clause**: -0.070, precision -0.185, two seeds collapse |

**Early warning (S3) was significant on no run.** The best Fisher p was 0.011 (E23 seed 42). It rests
on one fold, Tuesday 3 of 3, from a seed whose alarms have precision 0.02. S3 needs at least 2 of 4
folds above the null's p95, so it is not met. Per fold, the warned-early counts at the causal
threshold stay near their nulls: Tuesday 1-3 of 3, Wednesday 0 of 1, Thursday 0-1 of 8, Friday 1-4 of 7.

### What the programme shows

1. **The world model ranks pre-onset windows above quiet ones, across days, before any change.**
   E19's S2\* is 0.651, and 0.631 on the 13 onsets with a quiet run-up of at least 10 minutes, so it
   is not only the tail of the previous episode. This is the first cross-day anticipation measurement
   in the project that is day-normalised and threshold-free. Thursday F1 could not show it.
2. **It is not an alarm yet.** At a causal 10 % budget, the ranking does not turn into warnings that
   beat a shuffled-time baseline on any run (S3). The gap between "ranked above background" and
   "worth waking an analyst" is the one D-021 describes, and it is still open.
3. **Only the factorised target moved anticipation** (E22, +0.045). It learns "is something hostile
   happening" from every attack family of every training day, instead of learning compromise from
   one family per fold. That is exactly the cross-family transfer failure D-029 diagnosed. It pays
   with a little Thursday detection (PR-AUC 0.41 -> 0.39), which the scorecard is built to trade.
   Its gain rests mostly on one seed (+0.162), so it is adopted on the pre-registered rule, not
   presented as robust.
4. **Packet statistics from the flow CSVs are neutral for anticipation** (E20). They are kept
   because the PS requires packet-level features and they cost nothing (clause 2).
5. **The causal representation improved alarm cost, not anticipation** (E21: precision 0.35 -> 0.42,
   FPR 0.137 -> 0.110, worst day 0.60 -> 0.64). The pre-registered bar gates on anticipation, so it
   is not carried forward. It is the strongest candidate for a future run whose question is alarm
   quality rather than lead time.
6. **Training on pre-onset histories hurt** (E23). The imagined 20-step futures from 10 minutes out
   are mostly quiet, and the extra loss pulls the risk heads towards quiet. Two of three seeds lose
   detection almost entirely.

**Procedure notes.** E23 seed 42 crashed silently in its first fold while three E9 GPU jobs shared
the 7 GB machine. Its log is kept as `m1v2-e23-s42.crashed.log`, and it was re-run alone and
unchanged, as D-035 requires. E19's Thursday PR-AUC (0.41-0.47) sits inside E10's seed range, so the
new harness reproduces round 2.

Artefacts:
- `results/tables/scorecard_e19.csv` ... `scorecard_e23.csv`, one row per run with every S-column,
  the per-day S3 and S4, and the compromise-onset table.
- `results/runs/scorecard-*/metrics.json` (with the bar verdicts), `results/runs/m1v2-e*-s*/`,
  `results/runs/m1v2-sweep-logs/`.

---

## E24 - do the latent dynamics earn lead time? Model A vs Model B (D-035)

```
bash scripts/run_m1v2.sh e24a configs/m1v2/e24_modelA_nocurr.yaml       # Model A; Model B = the E22 runs
python scripts/scorecard.py --variant A=m1v2-e24a-s42,... --variant B=m1v2-e22-s42,... --compare B:A --tag e24
```
Model A keeps Model B's observation encoder and causal attention, then predicts each risk channel
"within the next K windows" straight from the attention context. It has no GRU, no stochastic latent,
no decoder and no imagination. Model B is the final stack as built (E20 packet block + E22 factorised
target). Both use the factorised target and the same features, seeds, folds and epoch count.

| | S1 precision | S1 FPR | S2 bins 0-2 / 2-4 / 4-6 / 6-10 min | **S2\*** | isolated | worst day | Thu PR-AUC |
|---|---:|---:|---|---:|---:|---:|---:|
| **A**, no latent dynamics | 0.119 [0.03-0.22] | 0.125 | 0.65 / 0.64 / 0.64 / 0.55 | **0.608** [0.58-0.65] | 0.574 | 0.509 | 0.222 [0.18-0.27] |
| **B**, RSSM (E22) | 0.322 [0.31-0.33] | 0.115 | 0.76 / 0.75 / 0.70 / 0.65 | **0.704** [0.66-0.75] | 0.670 | 0.644 | 0.389 [0.38-0.39] |

**B beats A on every clause:**
- S2\* is +0.096 higher, on all three seeds (+0.116, +0.159, +0.012).
- Precision is +0.20 higher and FPR 0.010 lower.
- A collapses on one seed (Thursday PR-AUC 0.18).

**The latent transition earns anticipation, not only reconstruction.** Given the same inputs, the
model that learns how the network state moves and imagines it forward ranks pre-onset windows higher
at every lead bin, most clearly at 6-10 minutes (0.65 against 0.55, where A is barely above chance).
It also detects better. This is the evidence for calling NetWM a world model rather than a sequence
classifier. It holds on this dataset, with the caveat already on record: S3 is not met, so this is
ranking, not alarm-grade early warning.

---

## E20r - FLOW-ONLY vs FLOW+PACKET, with packets from the real captures (D-035)

```
python scripts/build_packet_features.py --pcap-dir D:/CIC-2017-PCAP            # F5: all five days
bash scripts/run_m1v2.sh e20r configs/m1v2/e20r_pcap.yaml data/processed/cicids2017_m1v2p
python scripts/scorecard.py --data data/processed/cicids2017_m1v2p --variant E19=... --variant E20=... \
    --variant E20r=... --compare E20r:E20 --compare E20r:E19 --tag e20r
```

**F5, the packet build.** The five UNB day captures (52.4 GB) each match UNB's md5. They are pcapng
written by `mergecap`, despite the `.pcap` name, and they record most packets twice (a mirror port
seeing both copies about 2 us apart). An IP packet byte-identical to one of the previous 64 frames is
dropped as a capture duplicate: 2.24 M frames over the week. A real TCP retransmission carries a new IP
ID and is kept. What remains is 53.7 M IPv4 packets. Per-window packet counts track the corrected flow
CSVs on the same grid on every day (log correlation 0.86-0.92, packet ratio 0.94-0.97), so the clocks
and window grid agree.

The 18 `pcap_` features measure what no flow CSV has:
- TTL: mean, std, distinct values, and the share below 60;
- the IP fragment rate;
- the TCP retransmission rate;
- the zero-window rate and the spread of advertised windows;
- the true per-packet payload histogram;
- the spread and coefficient of variation of inter-packet gaps;
- the SYN-only and RST shares.

**Descriptive check on Friday (within-day ROC-AUC, not a test).** The features react strongly to the
loud attacks:
- DDoS: SYN-only share 0.97, RST 0.98, zero-payload 0.98, timing CV 0.96.
- Port scan: distinct TTLs 0.83, RST 0.80.

They barely react to the botnet's C2, where nothing exceeds 0.68. Fragmentation is essentially absent
all week (at most 0.8 % of packets in any window).

| run (mean of 3 seeds) | inputs | S1 precision | S1 FPR | **S2\*** | worst day | **Thu PR-AUC** | **Thu F1, causal** |
|---|---:|---:|---:|---:|---:|---:|---:|
| E19, flow only | 70 | 0.325 | 0.120 | 0.651 [0.63-0.68] | 0.566 | 0.434 [0.41-0.47] | 0.514 [0.48-0.57] |
| E20, + CSV packet statistics | 87 | 0.350 | 0.137 | 0.658 [0.59-0.70] | 0.599 | 0.414 [0.39-0.43] | 0.541 [0.50-0.56] |
| **E20r, + real packets** | 105 | **0.376** | 0.122 | 0.642 [0.60-0.68] | **0.601** | **0.564 [0.42-0.71]** | **0.618 [0.53-0.70]** |

**The PS asked whether packet-level information helps early forecasting. On CIC-IDS2017 it does not.**
- S2\* changes by -0.016 against E20 and -0.009 against flow-only, inside seed noise. Clause 1 fails
  both comparisons.
- **It helps detection.** Thursday PR-AUC rises from 0.43 to 0.56 and causal F1 from 0.51 to 0.62.
  Seed 44 reaches PR-AUC 0.71, the best Thursday ranking the project has produced; the shipped r2 has
  0.640.
- It is non-inferior on alarm cost: precision +0.05 against flow-only at the same FPR.

The detection gain fits the Friday check. TTL, RST and SYN-only shares are exactly what distinguishes
Thursday's internal sweep, and they say nothing about a quiet run-up.

**What this means for the product.** A model that reads `pcap_` features needs a PCAP. A flow-CSV
upload has none, so such a checkpoint would need a `has_pcap` mask (planned in the original design)
before it can serve both inputs. E20r was compared with E20 as pre-registered. The final stack (E22)
was built before all five captures arrived, so E22 + real packets is the untrained combination this
result points to.

---

## E25 - M2: the final stack on CTU-13, leave-one-botnet-family-out (D-035, D-036)

*Completed on three seeds in **E25b** below. Points 1, 2 and 4 of "What E25 shows" are seed-42 readings; E25b revises them.*

```
python scripts/build_ctu13.py --config configs/ctu13.yaml                          # F6: 13 scenarios
python scripts/train.py --data data/processed/ctu13 --model-config configs/m1v2/e25_ctu13.yaml \
    --group-folds configs/ctu13_folds.yaml --run e25-ctu13-s42 --seed 42 --no-figures [--resume]
python scripts/scorecard.py --data data/processed/ctu13 --variant E25=e25-ctu13-s42 --tag e25
```

**Setup.** The stack is the final M1 stack (RSSM + factorised target), fixed in
`configs/m1v2/e25_ctu13.yaml` before any CTU-13 run. It reads 56 features: S_t v1 without the 14 that
Argus cannot supply. The data is 13 scenarios, 20.0 M flows and 16,008 windows (F6). There are seven
folds, each holding out a whole botnet family, and each trains for a CIC fold's 250 steps.

*Procedure note:* a machine restart stopped the run after 5 of 7 folds. It was resumed with `--resume`,
which evaluated the five saved checkpoints unchanged and trained only Murlo and NSIS. The interrupted
log is kept.

| held-out scenario | family | windows | base rate | **ROC-AUC** (comp) | PR-AUC | causal F1 | pre-onset cells in S2 |
|---|---|---:|---:|---:|---:|---:|---:|
| s01 | Neris | 737 | 0.79 | **0.942** | 0.982 | 0.298 | 16 |
| s02 | Neris | 505 | 0.85 | 0.597 | 0.905 | 0.382 | 30 |
| s09 | Neris | 677 | 0.56 | 0.608 | 0.703 | 0.372 | 62 |
| s03 | Rbot | 8,019 | 0.19 | 0.714 | 0.402 | 0.408 | 892 |
| s04 | Rbot | 539 | 0.47 | 0.595 | 0.644 | 0.226 | 197 |
| s10 | Rbot | 618 | 0.25 | 0.671 | 0.421 | 0.487 | 216 |
| s11 | Rbot | 34 | 0.41 | **0.082** | 0.268 | 0.000 | 0 |
| s05 | Virut | 61 | 0.84 | 0.847 | 0.967 | 0.500 | 14 |
| s13 | Virut | 1,967 | 0.995 | 0.439 | 0.996 | 0.171 | 2 |
| s06 | Menti | 260 | 0.98 | 0.770 | 0.992 | 0.656 | 10 |
| s07 | Sogou | 44 | 0.41 | **0.015** | 0.252 | 0.000 | 3 |
| s08 | Murlo | 2,339 | 0.96 | **0.204** | 0.932 | 0.170 | 54 |
| s12 | NSIS.ay | 208 | 0.65 | **0.985** | 0.991 | 0.514 | 16 |

Pooled scorecard, seed 42:
- **S1:** precision 0.522, FPR 0.199.
- **S2** by bin (0-2 / 2-4 / 4-6 / 6-10 min): 0.57 / 0.57 / 0.54 / 0.55, so **S2\* = 0.551**; 0.521 on
  the 72 isolated onsets.
- **S3:** 24 of 112 warned early, Fisher p 0.98, not met.

### What E25 shows

1. **Anticipation does not transfer across botnet families.** S2\* is 0.551, near chance, and 0.521
   on isolated onsets, against 0.704 for the same stack across CIC-IDS2017 days. What the model learns
   about the run-up to an attack in one family does not carry to another family's. This is D-029's
   diagnosis confirmed on a dataset with seven families instead of two.
2. **Detection transfers to some families and fails badly on others.**
   - Held-out Neris s01 (0.94), NSIS (0.985) and Virut s05 (0.85) are detected well.
   - Rbot and the other Neris scenarios sit at 0.60-0.71.
   - Murlo (0.20), Sogou (0.015) and Rbot s11 (0.08) are *inverted*: the model scores the bot's
     traffic lower than the background. Their C2 looks more like the other families' benign traffic
     than their attacks.
   - PR-AUC flatters every capture that is mostly botnet (base rates of 0.8-0.995), so ROC-AUC is the
     honest detection number here.
3. **Most CTU-13 scenarios cannot test forecasting.** Several onsets fall in a capture's first minutes
   (s06, s08, s13), and four scenarios contribute fewer than 15 pre-onset windows. The pooled S2 rests
   mostly on Rbot s03 (892 of 1,512 cells). Per-scenario S4 values of 0 come from scenarios with a
   single reference window and carry no information.
4. **One seed.** D-035 ran seed 42 first. The seed spread CIC-IDS2017 showed (S2\* +/- 0.05) is
   larger than nothing here, but not large enough to lift 0.551 into the range CIC-IDS2017 reached.

Artefacts:
- `results/tables/scorecard_e25.csv` and `results/runs/scorecard-e25/`;
- `results/runs/e25-ctu13-s42/`, `models/e25-ctu13-s42/<family>.pt`;
- `results/runs/m1v2-sweep-logs/e25-ctu13-s42{,.interrupted}.log`, `results/runs/f6-ctu13-build/build.log`.

---

## E26 - do E22 and real packets compose? One model for CSV and PCAP inputs (D-037)

```
bash scripts/run_m1v2.sh e26 configs/m1v2/e26_combined.yaml data/processed/cicids2017_m1v2p   # + <run>-csvmode
python scripts/lr_baseline.py --data data/processed/cicids2017_m1v2 --model-config configs/m1v2/e19_base.yaml \
    --test-days monday tuesday wednesday thursday friday --run lr-flow-s42
python scripts/parity_check.py --day thursday --pcap D:/CIC-2017-PCAP/Thursday-WorkingHours.pcap
python scripts/ablation_matrix.py                                                              # matrix + bar
```

**E26 is E22 (RSSM + factorised target) plus the 18 real-capture `pcap_` features and `has_pcap`,**
106 inputs in all. It is trained with packet dropout 0.3, so one model serves both inputs. Every
held-out day is scored twice: with packets, and in CSV form (packets absent). The reference point is
frozen in `results/runs/reference-m1-2026-09-28/manifest.json` (tag `ref-m1-2026-09-28`).

**Parity, checked on real data before the result was read.** For a whole real day, Thursday, the state
the API builds matches the training matrix in both modes: 972 windows x 106 inputs, **0 mismatched
cells**. The CSV path goes through `read_flow_csv`. The PCAP path puts the 8.3 GB capture through the
engine's packet code (`results/runs/parity-thursday/`). The flow converter now emits the 8 per-flow
columns behind the CSV packet block, so a PCAP upload builds the same 17 `pkt_` features as training.

### The ablation matrix (mean of seeds 42/43/44; LR is deterministic)

| row | S1 precision | S1 FPR | S2 0-2 / 2-4 / 4-6 / 6-10 min | **S2\*** | isolated | Thu PR-AUC | Thu F1 causal | Fri PR-AUC | rollout gain Thu / Fri | S3 |
|---|---:|---:|---|---:|---:|---:|---:|---:|---|---|
| LR flow-only | 0.122 | 0.104 | 0.69 / 0.64 / 0.72 / 0.61 | **0.659** | 0.663 | 0.139 | 0.112 | 0.156 | - | not met |
| E19 flow-only (r2 method) | 0.325 | 0.120 | 0.69 / 0.69 / 0.66 / 0.60 | **0.651** [0.63-0.68] | 0.631 | 0.434 | 0.514 | 0.120 | +0.162 / +0.144 | not met |
| E22 flow + CSV-pkt, factorised | 0.322 | 0.115 | 0.76 / 0.75 / 0.70 / 0.65 | **0.704** [0.66-0.75] | 0.670 | 0.389 | 0.499 | 0.156 | +0.166 / +0.207 | not met |
| E20r flow + real packets | 0.376 | 0.122 | 0.68 / 0.68 / 0.65 / 0.60 | **0.642** [0.60-0.68] | 0.632 | **0.564** | **0.618** | 0.131 | +0.165 / +0.247 | not met |
| E24a no latent dynamics | 0.119 | 0.125 | 0.65 / 0.64 / 0.64 / 0.55 | **0.608** [0.58-0.65] | 0.574 | 0.222 | 0.146 | 0.105 | - | not met |
| **E26 PCAP mode** | **0.375** | 0.114 | 0.67 / 0.68 / 0.69 / 0.62 | **0.663** [0.62-0.69] | 0.618 | 0.444 [0.42-0.46] | 0.546 | **0.234** | +0.055 / +0.104 | not met |
| **E26 CSV mode** | 0.192 | 0.134 | 0.72 / 0.73 / 0.74 / 0.71 | **0.727** [0.69-0.75] | 0.685 | 0.358 [0.27-0.46] | 0.319 | 0.146 | -0.337 / -0.239 | not met |

*Rollout gain is the mean over k = 2..10 of (persistence MSE - world-model MSE); positive means the
open-loop rollout beats "nothing changes".*

### The composition bar and the ship decision (pre-registered in D-037)

| clause, E26 PCAP mode vs E22 | result | bar | |
|---|---|---|---|
| (a) anticipation preserved | S2\* **-0.041** (-0.013 / -0.068 / -0.041) | >= -0.03 | **fails** |
| (b) detection added | Thursday PR-AUC **+0.054** (+0.071 / +0.042 / +0.051) | >= +0.05, >= 2 of 3 seeds | passes |
| (c) alarm cost | precision +0.053, FPR -0.000 | | passes |
| (d) stability | min Thursday PR-AUC 0.42 in PCAP mode, 0.27 in CSV mode | >= 0.20 | passes |
| (e) still a world model | rollout beats persistence on 3 of 3 seeds | >= 2 of 3 | passes |

**Outcome 3: the two gains do not compose on anticipation. r2 stays shipped; E22 (anticipation) and
E20r (detection) remain separate references.** The miss is 0.011 below the bar. D-037 forbids
reading it any other way after the fact, and forbids a tuning sweep.

### Diagnosis (descriptive; nothing tuned)

1. **The packet block acts as current-state evidence.**
   - E26 with packets loses its anticipation on the two compromise days: S4 on Thursday falls from
     0.707 to 0.637, and on Friday from 0.684 to 0.628. It gains on Tuesday and Wednesday.
   - The *same weights* in CSV mode rank the run-up at 0.727, and Thursday's at **0.811**, the highest
     of any row.
   - With packets, E26 has the best Friday detection of any model on the three-seed mean: PR-AUC
     0.234 and causal F1 0.188,
     where every other row stays at or below 0.156 and 0.154 (E20r's best single seed reaches F1 0.285).
   - This is E20r's finding again, inside one model. What packets add is evidence about *now*, and on
     the infiltration and botnet days that evidence outweighs the quieter run-up.
2. **The world-model property holds, but weaker.** The rollout still beats persistence on every seed
   in PCAP mode, by about a third of E22's margin (+0.06 / +0.10 against +0.17 / +0.21). In CSV mode
   the rollout is *worse* than persistence (-0.34 / -0.24). The dynamics were learned on packet-bearing
   states, and predicting the packet block from a masked state is what fails. **The CSV-mode forecasts
   are therefore not world-model rollouts to lean on, whatever their ranking score.**
3. **The logistic-regression baseline ranks pre-onset windows as well as the round-2 world model**
   (S2\* 0.659 against 0.651). Its detection is poor: Thursday PR-AUC 0.139 and alarm precision 0.12.
   - This qualifies E24. The latent dynamics beat a same-encoder model without them (0.608), but that
     model is itself below LR.
   - The world model's anticipation edge over LR comes from the factorised target: E22 reaches 0.704,
     +0.045 over LR. What sets it apart from LR is detection at a usable alarm cost: precision 0.32
     against 0.12, and Thursday PR-AUC 0.39-0.56 against 0.14.
4. **Early warning (S3) is met by no row**, including LR. The claim stays "ranks pre-attack windows
   above background", per D-021.

Artefacts:
- `results/tables/e26_ablation_matrix.csv` (per run) and `e26_ablation_summary.csv`;
- `results/runs/e26-ship-decision/metrics.json` (the bar's verdict);
- `results/runs/m1v2-e26-s4*{,-csvmode}/`, `results/runs/lr-flow-s42/`, `results/runs/parity-thursday/`.

---

## E25b - M2 completed: CTU-13 on three seeds, family by family, world model vs logistic regression (D-037)

```
python scripts/train.py --data data/processed/ctu13 --model-config configs/m1v2/e25_ctu13.yaml \
    --group-folds configs/ctu13_folds.yaml --run e25-ctu13-s43 --seed 43 --no-figures --resume \
    --note "completion of E25"                                                        # and s44 / --seed 44
python scripts/lr_baseline.py --data data/processed/ctu13 --model-config configs/m1v2/e25_ctu13.yaml \
    --group-folds configs/ctu13_folds.yaml --run lr-ctu13-s42
CUDA_VISIBLE_DEVICES="" python scripts/ctu_family_matrix.py
```

**Setup.** Seeds 43 and 44 use seed 42's definition exactly: the same config, folds, 56 Argus
features and 250-step budget (D-037). The LR baseline uses the same features, folds, targets, scaler
and scorer, and is deterministic, so it has one row. The verdict rule was fixed in D-037 before these
runs:
- **transfers:** world-model ROC-AUC >= 0.70 on >= 2 of 3 seeds, for every scenario of the family;
- **inverted:** ROC-AUC < 0.50 on >= 2 of 3 seeds, for any scenario of the family;
- **partial:** everything else.

*Procedure notes:*
1. Seeds 43/44 were trained on an RTX 4060 (torch 2.5.1+cu121, Python 3.10.21); seed 42 was trained on
   the GTX 1650. Each run folder's `env` block records this.
2. A first attempt on the other machine died after fold 1. All seven folds of both seeds were
   retrained here, so each seed was trained on one machine.
3. The code that ran is `git_sha_at_start` = `7399495`. The folders' save-time `git_sha` (`a0dfb52`)
   differs from it only by results commits.
4. The logs carry no `exit=` line. The launcher's `echo exit=%ERRORLEVEL%>>` was parsed by cmd as a
   handle redirect. Completion is shown by `complete: true`, all 13 scenarios with threat scores, the
   final `wrote models/...` line, and no traceback in either log.

**Detection and anticipation, per held-out scenario.** ROC-AUC, PR-AUC and causal F1 are for `comp`
on `y_within_K` at the causal expanding q90. "Background" is the number of windows with
`y_within_K` = 0, the negatives every ROC-AUC below rests on. S2\* is the percentile of pre-onset
windows, reported only where a scenario has >= 20 pre-onset cells. World-model columns show seeds
42 / 43 / 44, or their mean.

| family | scenario | windows | background | **WM ROC-AUC** 42 / 43 / 44 | **LR ROC-AUC** | WM / LR PR-AUC | WM / LR causal F1 | **WM S2\*** 42 / 43 / 44 | **LR S2\*** | S2 cells |
|---|---|---:|---:|---|---:|---|---|---|---:|---:|
| Menti | s06 | 260 | 6 | 0.770 / 0.698 / 0.777 | 0.985 | 0.990 / 1.000 | 0.573 / 0.412 | - | - | 10 |
| Murlo | s08 | 2,339 | 89 | **0.204 / 0.137 / 0.156** | 0.590 | 0.919 / 0.974 | 0.169 / 0.278 | 0.472 / 0.541 / 0.460 | 0.632 | 54 |
| NSIS.ay | s12 | 208 | 72 | 0.985 / 0.979 / 0.985 | 0.957 | 0.990 / 0.952 | 0.651 / 0.378 | - | - | 16 |
| Neris | s01 | 737 | 157 | 0.942 / 0.664 / 0.761 | 0.614 | 0.898 / 0.785 | 0.212 / 0.132 | - | - | 16 |
| Neris | s02 | 505 | 78 | 0.597 / **0.425 / 0.413** | 0.571 | 0.826 / 0.853 | 0.190 / 0.213 | 0.748 / 0.525 / 0.542 | 0.242 | 30 |
| Neris | s09 | 677 | 295 | 0.608 / 0.858 / 0.931 | 0.924 | 0.840 / 0.954 | 0.431 / 0.641 | 0.751 / 0.819 / 0.758 | 0.560 | 62 |
| Rbot | s03 | 8,019 | 6,479 | 0.714 / 0.695 / 0.632 | 0.520 | 0.371 / 0.191 | 0.398 / 0.115 | 0.460 / 0.439 / 0.466 | 0.491 | 892 |
| Rbot | s04 | 539 | 285 | 0.595 / 0.712 / 0.542 | 0.672 | 0.623 / 0.680 | 0.282 / 0.395 | 0.816 / 0.821 / 0.773 | 0.546 | 197 |
| Rbot | s10 | 618 | 466 | 0.671 / 0.667 / 0.652 | 0.531 | 0.400 / 0.243 | 0.364 / 0.129 | 0.666 / 0.571 / 0.612 | 0.521 | 216 |
| Rbot | s11 | 34 | 20 | **0.082 / 0.054 / 0.054** | 0.518 | 0.264 / 0.421 | 0.000 / 0.000 | - | - | 0 |
| Sogou | s07 | 44 | 26 | **0.015 / 0.156 / 0.177** | 0.737 | 0.313 / 0.566 | 0.000 / 0.000 | - | - | 3 |
| Virut | s05 | 61 | 10 | 0.847 / 0.857 / 0.886 | 0.512 | 0.962 / 0.853 | 0.657 / 0.000 | - | - | 14 |
| Virut | s13 | 1,967 | 10 | **0.439 / 0.302 / 0.313** | 0.991 | 0.995 / 1.000 | 0.169 / 0.106 | - | - | 2 |

**S3 (early alarms against the circular-shift null)** is met nowhere: in no scenario, on no seed, and
not by LR. The smallest p is 0.059 (s10, seed 42, 8 of 17 onsets warned early).

### The verdicts (D-037's rule, applied as written)

| family | verdict | the scenario that decides it | WM ROC-AUC, family mean | LR ROC-AUC, family mean |
|---|---|---|---:|---:|
| NSIS.ay | **transfers** | s12: 0.98 on all seeds, 72 background windows | 0.983 | 0.957 |
| Menti | **transfers** | s06: >= 0.70 on 2 of 3 seeds, but only **6** background windows | 0.748 | 0.985 |
| Murlo | **inverted** | s08: 0.14-0.20 on all seeds, 89 background windows | 0.166 | 0.590 |
| Neris | **inverted** | s02: 0.425 and 0.413 on seeds 43/44 (78 background); s01 0.66-0.94, s09 0.61-0.93 | 0.689 | 0.703 |
| Rbot | **inverted** | s11: 0.05-0.08 on all seeds (34 windows, 20 background); s03/s04/s10 0.54-0.71 | 0.506 | 0.560 |
| Sogou | **inverted** | s07: 0.02-0.18 on all seeds (44 windows, 26 background) | 0.116 | 0.737 |
| Virut | **inverted** | s13: 0.30-0.44 on all seeds, but only **10** background windows in 1,967; s05 0.85-0.89 | 0.607 | 0.751 |

**2 families transfer, 5 are inverted, 0 are partial.** The family means are shown only beside the
per-scenario rows above. They are not the result.

### What E25b shows

1. **Three seeds overturn most of E25's detection picture.**
   - Seed 42 alone showed detection transferring to Neris, NSIS and Virut.
   - Across three seeds, only NSIS transfers on well-measured data.
   - Seed 42 was the most favourable seed on both Neris scenarios that decided the verdict: s01 0.942
     against 0.664 / 0.761, and s02 0.597 against 0.425 / 0.413. That is exactly what D-035 and
     D-037 required three seeds for.
2. **The rule weighs a 34-window capture the same as an 8,019-window one.** This point is descriptive
   and does not re-read the rule.
   - Two inversions are well measured: Murlo (89 background windows, 2,339 in all, 0.14-0.20 on every
     seed) and Neris s02 (78 background windows).
   - Rbot's verdict rests on s11 (20 background windows), Sogou's on 26, and Virut's on s13's 10.
   - Menti's "transfers" rests on 6.
   - Several CTU-13 captures are almost entirely botnet (D-036's stated weakness), so their ROC-AUC
     has a handful of negatives behind it.
3. **On CTU-13 detection, the world model is not better than LR.**
   - ROC-AUC: the world model is higher on 5 of 13 scenarios (s01, s03, s05, s10, s12), LR on 8.
   - At the causal threshold the picture reverses: the world model's F1 is higher on 7, LR's on 4,
     with 2 ties at zero.
   - LR on the same 56 network-global features is not inverted on Sogou (0.737) or Virut s13 (0.991),
     although those rest on 26 and 10 background windows. There, the global state carries what is
     needed to rank the bot's windows correctly, and what inverts is the world model's learned
     weighting.
   - LR is weak where the world model fails worst: Murlo 0.590 and Rbot s11 0.518.
4. **Anticipation transfers to some scenarios and fails on others; a pooled number hides which.** It
   is measurable on six scenarios.
   - **World model above LR on all three seeds, on four scenarios:**

     | scenario | world model, 3 seeds | LR |
     |---|---|---:|
     | Neris s02 | 0.53-0.75 | 0.24 |
     | Neris s09 | 0.75-0.82 | 0.56 |
     | Rbot s04 | 0.77-0.82 | 0.55 |
     | Rbot s10 | 0.57-0.67 | 0.52 |

   - **LR above the world model on two scenarios:** Murlo (0.63 against 0.46-0.54) and Rbot s03.
   - On s03 **both are below chance** (0.44-0.47 and 0.49). That scenario holds 892 of the 1,451
     cells, so any pooled S2\* is mostly s03.
   - E25's "anticipation does not transfer across botnet families" therefore needs its scope stated:
     it fails on Murlo and on Rbot's largest capture, and the world model's run-up ranking does carry
     to two Neris and two Rbot scenarios.
5. **Early warning is not established on M2 either.** S3 is met nowhere, so the claim stays "ranks
   pre-attack windows above background", per D-021. On CTU-13 that holds only for the scenarios in
   point 4.
6. **Scope.** M2 covers cross-family behaviour on Argus flow state: 56 features, no packet
   features. CTU-13 has no mixed-traffic PCAPs (D-036), so M2 says nothing about the packet block.

Artefacts:
- `results/tables/e25b_ctu13_scenarios.csv` (one row per run and scenario), `e25b_ctu13_scenario_matrix.csv` and `e25b_ctu13_families.csv`;
- `results/runs/e25b-ctu13-matrix/` (`metrics.json` and `matrix.log`);
- `results/runs/e25-ctu13-s{42,43,44}/` and `results/runs/lr-ctu13-s42/`;
- `results/tables/e25-ctu13-s4{3,4}_{forecast,training_curves}.csv`;
- `results/runs/m1v2-sweep-logs/e25-ctu13-s4{3,4}.log`;
- `models/e25-ctu13-s4{3,4}/<family>.pt` (untracked; kept on the training machine).

---

## E27 - the PCAP route: the mean of the three E20r seeds serves PCAP uploads, r2 serves CSV (D-038)

```
.venv/Scripts/python.exe -m pytest -q tests backend/tests                       # routing tests: backend/tests/test_pcap_route.py
CUDA_VISIBLE_DEVICES="" python scripts/pcap_route_parity.py                    # Step 5, checks 1-3
python scripts/pcap_route_eval.py                                               # Steps 6-7 + D-038's acceptance bar
python scripts/slice_pcap.py --pcap D:/CIC-2017-PCAP/Tuesday-WorkingHours.pcap --start 1499173200 --stop 1499176800 --out data/cic-2017-pcap/tuesday_1300_1400.pcap
python scripts/slice_pcap.py --pcap D:/CIC-2017-PCAP/Thursday-WorkingHours.pcap --start 1499359200 --stop 1499367000 --out data/cic-2017-pcap/thursday_1640_1850.pcap
CUDA_VISIBLE_DEVICES="" python scripts/pcap_route_parity.py --pcap D:/CIC-2017-PCAP/Tuesday-WorkingHours.pcap --day tuesday   # check 4 (after D-040)
CUDA_VISIBLE_DEVICES="" python scripts/check4_dedupe_ab.py --pcap data/cic-2017-pcap/tuesday_1300_1400.pcap --day tuesday   # check 4 diagnostic
python scripts/pcap_route_same_traffic.py --pcap data/cic-2017-pcap/thursday_1640_1850.pcap                                   # Step 8
```

**What E27 is.** The shipped r2 reads 70 flow features, so a PCAP upload used to be turned into flows
and every packet measurement ignored. D-038, committed (`86dbaa3`) before any ensemble number was
computed, routes by input:
- `.csv` → r2, unchanged;
- `.pcap` / `.pcapng` → all three E20r seeds (`models/m1v2-e20r-s{42,43,44}/`). Each reads the same
  105-input state: 70 S_t v1 flow features, the 17 CSV packet statistics, and the 18 `pcap_` features
  measured from the capture (TTL, fragments, retransmissions, TCP window, payload sizes, packet timing,
  SYN-only and RST shares).

The per-window scores are averaged, and the causal q90 (D-034) is applied once, to the mean. No seed
is chosen, and a PCAP upload never falls back to r2. Nothing was trained; the scores below are the
three runs' stored per-window outputs, averaged (run folder `e27-e20r-mean`).

**The checkpoints (Step 2).** On all five folds, the three seeds are one method:
- the same model config (593,500 parameters);
- the same 105 inputs in the same order, with no `has_pcap`, so this is a PCAP-only model;
- scalers that transform the held-out matrix identically, and the same training days.

A flow CSV handed to E20r now raises an error rather than feeding it zeros it never saw.

**Engineering (D-038 criterion 1): passed.**
- **Tests.** `backend/tests/test_pcap_route.py` has 11 passing tests and 1 expected failure (finding 5
  below); the full suite has no other failures (158 passed before the split). The tests cover:
  - CSV → r2 only, with no packet inputs built;
  - PCAP → all three members, with the packet block built once and shared;
  - one window grid, and an ensemble score equal to the members' mean;
  - the causal threshold applied once, to the mean;
  - a deterministic alarm score;
  - no fallback to r2 or a fixture;
  - mixed folds refused;
  - payloads valid under the v1.1 contract.
- **Parity (`results/runs/e27-parity/`, `results/tables/e27_parity.csv`).** Each seed, fed its
  processed held-out matrix, reproduces its stored scores: correlation 0.997-0.9996 on every day, and
  Thursday PR-AUC stored against live 0.418 / 0.419, 0.562 / 0.568, 0.710 / 0.698. The scaler and the
  causal threshold are prefix-invariant on Thursday and Friday.

**Results (causal expanding q90; mean [min-max] over seeds where three runs exist).**

| model | input | Thu PR-AUC | Thu F1 | Thu precision | Thu recall | Thu FPR | Fri PR-AUC | Fri F1 | S1 precision | S1 FPR | S2\* | S3 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| r2 shipped, flow-only | CSV (flow) | 0.640 | 0.608 | 0.613 | 0.602 | 0.078 | 0.109 | 0.061 | - | - | - | - |
| E19, the r2 method | CSV (flow) | 0.434 [0.41-0.46] | 0.514 [0.48-0.57] | 0.549 | 0.484 | 0.082 | 0.120 | 0.106 | 0.325 | 0.120 | 0.651 [0.63-0.68] | not met |
| E20r seed 42 | PCAP (flow + packet) | 0.418 | 0.533 | 0.537 | 0.530 | 0.094 | 0.166 | 0.285 | 0.377 | 0.134 | 0.645 | 4/19, p 0.91 |
| E20r seed 43 | PCAP (flow + packet) | 0.562 | 0.623 | 0.676 | 0.578 | 0.057 | 0.104 | 0.021 | 0.332 | 0.121 | 0.597 | 5/19, p 0.74 |
| E20r seed 44 | PCAP (flow + packet) | 0.710 | 0.697 | 0.750 | 0.651 | 0.045 | 0.123 | 0.155 | 0.418 | 0.111 | 0.685 | 4/19, p 0.82 |
| **E20r mean (PCAP route)** | PCAP (flow + packet) | **0.543** | **0.609** | 0.623 | 0.596 | 0.074 | 0.143 | 0.116 | 0.356 | 0.128 | **0.669** | 4/19, p 0.92 |

**D-038's acceptance bar: accepted.**

| criterion | result | bar |
|---|---|---|
| 1. engineering: tests + parity | passed | - |
| 2. stability: Thursday PR-AUC | 0.543 | >= 0.20 |
| 3. anticipation against flow-only E19 | S2\* 0.669 | >= 0.651 - 0.03 = 0.621 |

**What E27 shows**
1. **The system now has a genuine packet-consuming path.** A PCAP upload is scored by a model that
   reads TTL, fragments, retransmissions, TCP window, payload sizes and packet timing measured from the
   capture. r2 remains the flow-only path for CSV. The payload and the dashboard say which route
   served a file (`inference` block; "Flow + packet telemetry" or "Flow telemetry" pill), and the model
   card lists both routes.
2. **Detection on the PCAP route.** Thursday PR-AUC is 0.543, with causal F1 0.609 at 7.4 % FPR.
   - Against its own seeds: the mean sits inside their range (0.42-0.71), close to the seed average
     (0.564). It removes the choice of seed; it does not beat the best seed.
   - Against the flow-only method on the same seeds (E19): 0.543 against 0.434 PR-AUC, and F1 0.609
     against 0.514.
   - Against the shipped r2 (one seed, CSV input): PR-AUC 0.543 against 0.640, F1 0.609 against 0.608.
     r2's seed is the top of its method's range, so E19 is the like-for-like comparison.
   - Friday's botnet C2, a family no training day contains, stays near the floor for every row (PR-AUC
     0.10-0.17).
3. **Anticipation is non-inferior, not improved.** S2\* 0.669 is above E19's mean (0.651) but inside
   E19's seed range and E20r's. Packets are not claimed to improve anticipation.
4. **No early warning.** S3 is 4/19 with Fisher p 0.92, so the wording stays "ranks pre-attack windows
   above background". The output is a risk score, not a probability (E17); the stage is the model's
   estimate (E9); the why panel shows feature contributions (E11).
5. **Finding: the forecast is not prefix-invariant.** `CausalContext` linearly interpolates its
   `context_len` learned positional embeddings to the input's length whenever the input is longer
   (`src/netwm/models/world_model.py`, `F.interpolate`).
   - Training sequences are 96 windows (a 6x stretch). Evaluation and the dashboard pass a whole
     capture, about 970 windows (about 60x).
   - A window's score therefore depends on how many windows follow it. No future *content* enters,
     since the attention mask is causal, but the capture's *length* does.
   - Measured on the real ensemble, scoring the first half of a day on its own against the whole day:

     | | Thursday | Friday |
     |---|---:|---:|
     | score correlation | 0.995 | 0.948 |
     | largest score change | 0.139 | 0.199 |
     | alarm windows that change | 0 of 38 | 16 of 36 |

   This is pre-existing and shared by every model, r2 included. Every stored number is internally
   consistent, because all were computed on whole days. But a live stream would score differently
   from the offline analysis, and inference runs at positional stretches training never saw.

   A fix changes the model and needs retraining, so it is a separate pre-registered experiment and is
   not done here. `test_forecast_is_prefix_invariant` is marked `xfail(strict=True)` until then. See
   `research/positional-length.md`.
6. **Check 4 and Step 8, on real captures.** Captures from `D:/CIC-2017-PCAP/` match their published
   md5s. Slices were cut with `scripts/slice_pcap.py` (editcap's `-A`/`-B`; Wireshark is not
   installed on every machine).
   - *Check 4, first run (ae3ea25, kept for the record): the packet block matches the training matrix,
     the flow block does not.*
     - All 18 `pcap_` features are exact.
     - The flow features the upload path builds with `pcap_to_flows` are not: 3 of the 87 flow and CSV
       packet features match. The median feature's worst-window relative error is 0.99.
     - Packet, byte and flag counts are inflated, up to about 2x (mean relative error 0.45-0.48,
       correlation above 0.99). The flow count and distinct-destination features differ as well
       (mean relative error 0.39 and 0.44).
     - The cause given with it, capture duplicates, is wrong. The log
       (`results/runs/e27-parity/parity-live-tuesday.log`) says `session cap 100000 reached,
       2869997 packets dropped`. Quiet flows were never closed, so they filled the converter's
       session cap, and every later flow was dropped. The counts fell towards zero; they were not
       inflated: `pkts_total`'s worst window was off by 0.995.
     - Duplicates are not the cause (`scripts/check4_dedupe_ab.py`, Tuesday 13:00-14:00, below the
       cap). The flow counts as served already match the training matrix: median ratio 0.999 for
       `pkts_total`, and 1.000 for the SYN, ACK and PSH sums. Dropping duplicates first moves them to
       0.939, 0.966, 0.983 and 0.955. The corrected CSVs count the mirrored copies.
   - *The fix (D-040, 0c5f976):* flows are finished once they are more than 120 + 60 s old. On the
     slice the flow table is identical before and after.
   - *Check 4, re-run on the full Tuesday capture (968 windows, no session-cap drops).* Per-feature
     differences by block; check 4 is reported, not gated:

     | block | features | exact | median mean rel. error, before -> after | within 5 % on average, before -> after | correlation > 0.9, before -> after |
     |---|---:|---:|---|---|---|
     | `pcap_` (from `read_packets`) | 18 | 18 | 0 -> 0 | 18 -> 18 | 18 -> 18 |
     | flow (from `pcap_to_flows`) | 67 | 4 | 0.312 -> 0.039 | 14 -> 39 | 10 -> 43 |
     | CSV packet statistics (from `pcap_to_flows`) | 20 | 0 | 0.200 -> 0.068 | 4 -> 9 | 0 -> 14 |

     - Totals now track the training matrix: `pkts_total` 0.012 mean relative error, `bytes_total`
       0.010, the SYN, ACK, PSH and FIN sums 0.006 or less, all with correlation 1.000.
     - Still far off, and apparently definition differences rather than lost packets:
       `active_mean_mean` and `bwd_init_win_mean`; the distinct-port and distinct-host counts
       (`ports_per_pair_max`, `uniq_dst_port`, `port_fanout_max`, `uniq_src_ip`);
       `flow_iat_min_min` and `pkt_len_max_max`.
     - **E27's numbers still describe the model on the training-matrix state.** A live upload now
       gets totals close to training, but 28 of 67 flow features still differ by more than 5 % on
       average. So no live-PCAP detection number is quoted. Table
       `results/tables/e27_parity_live_pcap.csv`; log `results/runs/e27-parity/parity-live-tuesday-d040.log`.
       The run's `git_sha` reads 65035a3: it ran with 0c5f976's converter change in the working
       tree, before that commit.
   - *Step 8: the same traffic through both routes* (`results/runs/e27-same-traffic/`). The traffic
     is Thursday 16:40-18:50 UTC: the real capture slice (2,409,533 packets) and the
     `thursday_infiltration` CSV.
     - Both routes are served as D-038 names them, in the one payload format (schema-validated):
       - CSV → r2: 70 features, flow telemetry.
       - PCAP → the mean of the three E20r Thursday folds: 105 features, packet features measured
         from the capture.
       - Both use the same 260-window grid from 16:40:00Z and the causal `expanding-10pct` policy.
     - r2 alarms on 80 windows, the PCAP route on 42. Their per-window risk scores correlate at
       **0.035**.
     - *Why so low (`scripts/step8_decompose.py`, descriptive).* The same 260 windows, scored six
       ways, on the mean-path `p_max`:

       | comparison | score correlation |
       |---|---:|
       | r2 vs E20r mean, as served (Step 8) | 0.035 |
       | r2 vs E20r mean, each on its training matrix's rows, same 260 windows | 0.819 |
       | r2 vs E20r mean, each on its whole training day | 0.834 |
       | **E20r mean: live PCAP state vs its training state** | **0.111** |
       | r2: live CSV state vs its training state | 0.9998 |
       | E20r mean / r2: 260 windows vs the whole day (length effect) | 0.999 / 0.999 |

       - On the state they were trained on, the two models agree (0.82-0.83).
       - The CSV route reproduces its training state, and the capture's length barely matters here.
       - The whole Step 8 disagreement is the live PCAP state. On the real capture the ensemble's
         mean score is 0.377, against 0.135 on the training rows for the same windows, and its
         ranking of windows is nearly unrelated (0.111).
       - Its causal alarms, 42 of 260, are not the 105 it raises on the training state.
     - **So the PCAP route, served a real capture, does not yet behave like the model E27 evaluated.**
       The routing is correct; the state is not. No live-PCAP number is quoted, and the demo should
       not present PCAP-route scores as E27's model until the live state passes check 4 (N-9).
       Artefacts: `results/runs/e27-step8-decompose/`, `results/tables/e27_step8_decompose.csv`
       (per-window scores).
     - *Check 4 on the same Thursday slice* (`--tag thursday-1640`, 252 windows). It shows the same
       picture as full Tuesday:
       - `pcap_` block: 18 of 18 within 0.002.
       - Totals within 1 %: `pkts_total` 0.009 mean relative error, `bytes_total` 0.002.
       - Flow block: median mean relative error 0.045, 36 of 67 within 5 %.
       - The largest residuals are again `bwd_init_win_mean` (11.7), `active_mean_mean` (2.6) and the
         distinct port and host counts (`ports_per_pair_max` 1.13, `uniq_dst_port` 1.05,
         `uniq_src_ip` 0.87).
       - `n_flows` is 15 % off, so flow boundaries still differ somewhere.
       - These residuals, once scaled, are what move the ensemble. Tracing them to the corrected
         extraction's definitions is the next N-9 step.
       - Artefacts: `results/runs/e27-parity-thursday-1640/`,
         `results/tables/e27_parity_live_pcap_thursday-1640.csv`.
     - The demo PCAP (`data/demo/thursday_demo.pcap`) is synthesised from flow rows (D-031). It does
       not qualify for this check, and its packets share one IP ID, so `read_packets` drops 19,379
       of its 80,527 packets as duplicates on upload.
7. **Deployment.** The E20r weights are not tracked (`models/`). On a fresh clone the PCAP route
   returns `no_model`, by design with no fallback. Tracking the six fold files the demo needs
   (Thursday and Friday for each seed, about 14 MB), or publishing them, is a team decision.

Artefacts:
- `results/runs/e27-e20r-mean/`, `results/runs/e27-pcap-route/` (rows + verdict; `eval.log`);
- `results/runs/e27-parity/` (`parity.log`; check 4 on full Tuesday: `parity-live-tuesday.log` before
  D-040, `parity-live-tuesday-d040.log` after), `results/runs/e27-parity-thursday-1640/`;
- `results/runs/e27-check4-dedupe-ab/`, `results/runs/e27-same-traffic/`, `results/runs/e27-step8-decompose/`;
- `results/tables/e27_parity_live_pcap.csv`, `e27_parity_live_pcap_thursday-1640.csv`,
  `e27_check4_dedupe_ab.csv`, `e27_step8_decompose.csv`;
- `results/tables/e27_pcap_route.{csv,md}`, `e27_pcap_route_scorecard.csv`, `e27_parity.csv`;
- code: `src/netwm/engine/predict.py` (`load_ensemble`, the averaged forecast), `backend/inference.py`
  (routing, model-card routes), `backend/tests/test_pcap_route.py`, `scripts/pcap_route_{parity,eval,same_traffic}.py`;
  `src/netwm/features/flow_aggregator.py` (D-040 sweep), `src/netwm/features/pcap_slice.py`,
  `scripts/{slice_pcap,check4_dedupe_ab,step8_decompose}.py`.

---

## N-6a - Why the world model inverts on some CTU-13 families: direction flips and single-feature reliance (D-039, descriptive)

```
python scripts/ctu_inversion_diagnostic.py      # GPU if present; seeds 43/44 fold checkpoints + refit LR
```

**Not a bar, and nothing is tuned.** This is D-039's diagnostic, answering the first half of board
card N-6. The method is fixed in the script's docstring:
- **Scenarios:** the three the card names (Murlo s08, Sogou s07, Rbot s11), the two other scenarios
  that decide an "inverted" verdict (Neris s02, Virut s13), and NSIS s12 as a control that transfers.
- **Models:** the world model's fold checkpoints for seeds 43 and 44 (seed 42's weights are on the
  other machine), on the deterministic mean path; and the fold's LR, refit as `lr_baseline.py`
  fits it.
- **Direction:** per feature, the standardised mean difference `d` (bot windows minus background, on
  `y_within_K`) on the fold's training scenarios and on the held-out one. A feature **flips** when the
  signs differ and both `|d| >= 0.2`.
- **Reliance:** set one feature at a time, and then the whole flipped set, to its training mean across
  the held-out scenario, and record the change in ROC-AUC.

*Checks.*
- The mean-path ROC-AUC reproduces the stored Monte-Carlo one to within 0.011 on every scenario and
  seed. For example, Murlo gives 0.136 / 0.156 against 0.137 / 0.156 stored.
- The refit LR reproduces `lr-ctu13-s42`'s ranking: Spearman >= 0.9997, ROC-AUC within 0.0021. Its
  probabilities differ by up to 0.012, from library versions the stored run did not record, and a
  first run requiring bit-identical probabilities stopped on that. A separate refit gave Spearman
  0.998 on s12, so the fit itself also varies very slightly between runs.
- The script ran from an uncommitted working copy at `8cae357` and was committed unchanged with these
  results.

| scenario | role | background windows | features that flip | **WM ROC-AUC** s43 / s44 | WM, flipped set neutralised | LR ROC-AUC | LR, flipped set neutralised | the single features that push the world model's ranking most the wrong way (ROC-AUC gain when neutralised, s43 / s44) |
|---|---|---:|---:|---|---|---:|---:|---|
| Murlo s08 | inverted | 89 | **25 of 56** | 0.136 / 0.156 | **0.741 / 0.789** | 0.590 | 0.377 | `has_fin_rate` +0.06, `svc_https_rate` +0.12 (s44), `is_outbound_rate` +0.04 / +0.06 |
| Neris s02 | inverted | 78 | 18 | 0.423 / 0.412 | **0.623 / 0.626** | 0.571 | 0.673 | `uniq_src_ip` +0.09 / +0.15 |
| Rbot s11 | inverted | 20 | 19 | 0.050 / 0.050 | **0.811** / 0.486 | 0.518 | 0.679 | `ephemeral_dst_rate` +0.13 (s43), `proto_icmp_rate` **+0.38** (s44) |
| Virut s13 | inverted | 10 | 10 | 0.306 / 0.313 | 0.347 / 0.441 | 0.991 | 0.827 | **`svc_https_rate` +0.61 / +0.53**, `is_inbound_rate` +0.33 / +0.29 |
| Sogou s07 | inverted | 26 | 3 | 0.167 / 0.179 | 0.175 / 0.188 | 0.739 | 0.709 | `duration_s_max` +0.15 / +0.05, `ephemeral_dst_rate` +0.14 / +0.06 |
| NSIS s12 | control | 72 | 11 | 0.980 / 0.984 | 0.979 / 0.991 | 0.958 | 0.985 | none above +0.005 |

### What N-6a shows

1. **Three of the five inversions are mostly direction flips.**
   - On Murlo, Neris s02 and Rbot s11, many network-global features differ between bot and background
     windows in the opposite direction from the training families: 25, 18 and 19 of 56.
   - Neutralising those features lifts the world model from well below chance to 0.62-0.81 on both
     seeds (Rbot s11 on seed 43 only; seed 44 reaches 0.49).
   - The world model has learned which way these features move when a bot is active in the training
     families, and on these captures they move the other way. The E25b inversions are
     therefore a family-specific signature being transferred, as D-039 read them.
2. **The other two are not flips. The world model leans on one or two features.**
   - **Virut s13:** neutralising the HTTPS share alone adds about +0.5 to +0.6 ROC-AUC. That verdict
     rests on 10 background windows in 1,967.
   - **Sogou s07:** the world model leans on the longest flow duration and on the share of ephemeral
     destination ports.
   - LR, on the same 56 inputs, ranks both captures correctly (0.739 and 0.991).
3. **Rbot s11's ICMP.** On seed 44 the ICMP share alone is worth +0.38 ROC-AUC. s11 is the capture
   whose 91 ICMP flows have no `State` field (D-036), a data-format artefact rather than bot
   behaviour.
4. **The control is robust.** On NSIS no single feature moves the world model's ranking by more than
   0.005.
5. **What this does not show.**
   - The flipped set is defined **with the held-out scenario's labels**, so neutralising it is an
     explanation, not a remedy a deployment could apply.
   - Single-feature neutralisation leaves states off the data manifold, and correlated features share
     the blame, so this measures reliance, not cause.
   - The second half of N-6, whether per-host features separate the bot host where network-global
     ones do not, needs the raw CTU-13 flows (`data/raw/ctu13/`), which were not on this machine. It
     is still open, and D-039's per-host question stays unanswered until it runs.

Artefacts:
- `results/tables/n6_ctu13_inversion_features.csv` (one row per model, scenario and feature: `d_train`,
  `d_heldout`, `flips`, `delta_roc_neutralised`) and `n6_ctu13_inversion_summary.csv`;
- `results/runs/n6-ctu13-inversion/` (`metrics.json` with the LR reproduction check; `diagnostic.log`).

---

## N-8 x E25b - Does the capture's length move the CTU-13 detection numbers? Barely; it explains no inversion (descriptive)

```
python scripts/ctu_positional_length.py --seeds 42 43 44   # GPU; seed 42 has all 7 folds here, 43/44 only Neris
```

**Not a bar, nothing is tuned, and E25b's verdicts are not re-read** (D-037 fixed the rule and the
stored scores). The question comes from N-8 (`research/positional-length.md`): `CausalContext`
interpolates its 16 positional vectors to the input length, CTU-13's held-out captures run from 34 to
8,019 windows, and two of E25b's deciding inversions are the two shortest (s11, 34; s07, 44). The
method is fixed in the script's docstring:
- **Models:** the fold checkpoints on this machine: seed 42 for all seven families, seeds 43/44 for
  Neris only (their other folds are on the RTX 4060 machine; the run folder lists what was skipped).
  **Correction (found after this entry was pushed):** the two seed-43/44 `neris.pt` files on this
  machine are *not* E25b's checkpoints. They were saved at 2026-09-27 21:45 UTC by code at `c552088`,
  before E25b's seed-43/44 runs (code `7399495`, RTX 4060, finished 10:22 UTC). They come from an
  earlier run of the same seed and config, and they reproduce E25b's stored Neris ROC-AUC to within
  0.014. Read the seed-43/44 rows below as that earlier run, not as E25b's weights. Without them,
  the largest `prefix_of` move on captures of >= 208 windows is 0.014 (seed 42, Virut s13), not 0.023.
  Deterministic mean path, `p_max`, as in N-6a. ROC-AUC on `y_within_K`.
- **`prefix_of_T'`** - the same single pass, but the positional vectors are interpolated to T' = 96
  (training `seq_len`) or 8,019 (s03, the longest capture) and the first T are used. Attention is
  causal and the state recurrent, so this is exactly the score the capture would get as the start of a
  longer recording. **Only the positional encoding changes: this is the N-8 effect alone.**
- **`slices_L`** - consecutive slices of L = 34 or 96 windows, each scored alone from a fresh latent
  state. Every window sees the same positional stretch, but the recurrent state also restarts every L
  windows, so this mixes N-8 with lost history.

*Check.* The native mean-path ROC-AUC reproduces E25b's stored Monte-Carlo one to within 0.014 on
every row (largest: Neris s09 seed 43, 0.872 against 0.858).

ROC-AUC, change from native in brackets; "-" where the condition does not apply (T > T', or T <= L).

| seed | family | scenario | windows | background | E25b stored | **native** | prefix_of_96 | prefix_of_8019 | slices_34 | slices_96 |
|---|---|---|---:|---:|---:|---:|---|---|---|---|
| 42 | Neris | s01 | 737 | 157 | 0.942 | **0.953** | - | 0.954 (+0.001) | 0.705 (-0.248) | 0.800 (-0.152) |
| 42 | Neris | s02 | 505 | 78 | 0.597 | **0.610** | - | 0.606 (-0.004) | 0.464 (-0.146) | 0.502 (-0.109) |
| 42 | Neris | s09 | 677 | 295 | 0.608 | **0.607** | - | 0.603 (-0.004) | 0.656 (+0.049) | 0.643 (+0.036) |
| 42 | Rbot | s03 | 8,019 | 6,477 | 0.714 | **0.714** | - | 0.714 (+0.000) | 0.706 (-0.008) | 0.713 (-0.000) |
| 42 | Rbot | s04 | 539 | 285 | 0.595 | **0.592** | - | 0.579 (-0.013) | 0.581 (-0.012) | 0.589 (-0.004) |
| 42 | Rbot | s10 | 618 | 466 | 0.671 | **0.669** | - | 0.676 (+0.007) | 0.623 (-0.046) | 0.672 (+0.003) |
| 42 | Rbot | s11 | 34 | 20 | 0.082 | **0.075** | 0.018 (-0.057) | 0.039 (-0.036) | - | - |
| 42 | Virut | s05 | 61 | 10 | 0.847 | **0.857** | 0.925 (+0.069) | 0.965 (+0.108) | 0.867 (+0.010) | - |
| 42 | Virut | s13 | 1,967 | 9 | 0.439 | **0.439** | - | 0.453 (+0.014) | 0.473 (+0.034) | 0.428 (-0.011) |
| 42 | Menti | s06 | 260 | 6 | 0.770 | **0.768** | - | 0.766 (-0.003) | 0.757 (-0.012) | 0.756 (-0.012) |
| 42 | Sogou | s07 | 44 | 26 | 0.015 | **0.015** | 0.024 (+0.009) | 0.049 (+0.034) | 0.015 (+0.000) | - |
| 42 | Murlo | s08 | 2,339 | 89 | 0.204 | **0.205** | - | 0.209 (+0.004) | 0.221 (+0.015) | 0.229 (+0.023) |
| 42 | NSIS.ay | s12 | 208 | 72 | 0.985 | **0.982** | - | 0.989 (+0.007) | 0.978 (-0.005) | 0.984 (+0.002) |
| 43 | Neris | s01 | 737 | 157 | 0.664 | **0.665** | - | 0.649 (-0.016) | 0.584 (-0.081) | 0.610 (-0.055) |
| 43 | Neris | s02 | 505 | 78 | 0.425 | **0.420** | - | 0.414 (-0.007) | 0.355 (-0.065) | 0.394 (-0.026) |
| 43 | Neris | s09 | 677 | 295 | 0.858 | **0.872** | - | 0.849 (-0.023) | 0.814 (-0.058) | 0.840 (-0.032) |
| 44 | Neris | s01 | 737 | 157 | 0.761 | **0.770** | - | 0.756 (-0.014) | 0.719 (-0.051) | 0.741 (-0.029) |
| 44 | Neris | s02 | 505 | 78 | 0.413 | **0.416** | - | 0.418 (+0.002) | 0.397 (-0.018) | 0.408 (-0.008) |
| 44 | Neris | s09 | 677 | 295 | 0.931 | **0.933** | - | 0.933 (-0.000) | 0.936 (+0.003) | 0.922 (-0.011) |

### What this shows

1. **The positional defect alone barely moves E25b's detection numbers.**
   - On every capture of 208 windows or more, the `prefix_of` conditions move ROC-AUC by at most
     0.023 (Neris s09, seed 43), and the scores keep a Spearman correlation of >= 0.98 with native.
   - On the three captures of 61 windows or fewer the move is larger: Virut s05 +0.07 / +0.11, Rbot
     s11 -0.06 / -0.04, Sogou s07 +0.01 / +0.03.
   - No `prefix_of` condition moves any scenario across 0.50 or 0.70, D-037's thresholds.
2. **The two short inversions are not an artefact of being short.** Scored as the start of a
   96-window or an 8,019-window recording, Rbot s11 stays at 0.02-0.04 and Sogou s07 at 0.02-0.05
   (seed 42). s11 moves *further* below chance.
3. **Restarting the latent state matters more than the positional encoding.** Slicing costs Neris
   s01 up to 0.25 on seed 42 (0.953 to 0.705 at L = 34), and seed 42's s02 drops to 0.464 at L = 34,
   the one row in the table that crosses 0.50. The `prefix_of` rows for the same scenarios move by at
   most 0.004, so the loss comes from the history the recurrent state carries, not from N-8. For a
   streaming sensor this means the state should persist across a live feed rather than be rebuilt per
   chunk; it says nothing new about N-8's fix.
4. **N-6a is not touched in substance.** N-6a compares a scenario with itself at one length, so the
   positional stretch is constant across its conditions. Its six scenarios move by at most 0.057 here
   (Rbot s11, seed 42, downwards). N-6a itself used seeds 43/44, whose non-Neris folds are not on this
   machine, so this row set checks it only through seed 42 and the Neris fold.
5. **A small correction to E25b's "background" column.** It was derived from the rounded base rate.
   Counted directly, s03 has 6,477 background windows (not 6,479) and Virut s13 has **9** (not 10;
   N-6a's summary CSV already says 9). Nothing else in E25b depends on that column.
6. **What this does not show.** Seed 42 for six families and three seeds for Neris only. Detection
   ROC-AUC only; S2\* is not recomputed. N-8's fix still needs its own pre-registered retrain.

Artefacts:
- `results/tables/n8_ctu13_positional_length.csv` (one row per seed, scenario and condition, with the
  change from native, the Spearman correlation with native, the largest score change and any 0.50/0.70
  crossing);
- `results/runs/n8-ctu13-positional-length/` (`metrics.json`, which lists the skipped checkpoints, and `run.log`).

---

## N-6b - Does the bot host separate on per-host features where network-global ones fail? Not by a label-free per-host summary (D-039, descriptive)

```
python scripts/ctu_perhost_diagnostic.py        # reads data/raw/ctu13/scenarioNN.binetflow; CPU, about 10 min
```

**Not a bar, nothing is trained.** This is the second half of board card N-6 and the diagnostic D-039
asks for before any per-host-state run. The method and the decision rule are fixed in the script's
docstring, written before any per-host number was computed:
- **Scenarios.** s08, s07 and s11 decide (the three D-039 names). Neris s02, Virut s13 and the NSIS
  s12 control are reported beside them and decide nothing.
- **Windows.** The raw flows go onto the processed matrix's own grid. The script stops unless the
  window count and every window's global flow count match `data/processed/ctu13` exactly; they did on
  all six.
- **Five statistics per window:** flows, distinct destination ports, distinct destination IPs, bytes,
  and unanswered TCP SYNs. The direction is fixed in advance: higher is scored as more bot-like, and
  no ROC-AUC is flipped afterwards. Each is computed four ways:
  - **(i) global:** over all the window's flows, as the network-global state sees them;
  - **(ii) per-host max:** the largest value of any internal source host (`147.32.`), which is
    label-free and so something a per-host state could compute;
  - **(iii) oracle:** the bot host's own value, with the host picked by the labels (source addresses of
    `From-Botnet` flows). This is an upper bound;
  - **(iv) host level:** over every (window, internal host) pair, whether the bot host outranks the
    other internal hosts. This is D-039's literal wording.
- **Rule.** D-039's reopen condition counts as met only if, on **each** of s08, s07 and s11, some
  statistic's per-host max (ii) reaches ROC-AUC >= 0.70 while its global value (i) and the world
  model on all three seeds stay below 0.70.

ROC-AUC on `y_within_K`. The world model (E25b, seeds 42 / 43 / 44) and LR (56 global features) are
the models' own numbers, shown for reference.

| scenario (background windows; WM s42/43/44; LR) | statistic | (i) global | **(ii) per-host max** | (iii) oracle: bot host | (iv) bot vs other hosts |
|---|---|---:|---:|---:|---:|
| **Murlo s08** (89; 0.204 / 0.137 / 0.157; LR 0.590) | flows | 0.338 | **0.343** | 0.926 | 0.284 |
| | dst_ports | 0.341 | **0.508** | 0.947 | 0.368 |
| | dst_ips | 0.315 | **0.480** | 0.930 | 0.397 |
| | bytes | 0.325 | **0.328** | 0.955 | 0.406 |
| | syn_unanswered | 0.550 | **0.575** | 0.553 | 0.539 |
| **Sogou s07** (26; 0.015 / 0.156 / 0.177; LR 0.737) | flows | 0.797 | **0.499** | 0.740 | 0.553 |
| | dst_ports | 0.923 | **0.854** | 0.738 | 0.519 |
| | dst_ips | 0.912 | **0.859** | 0.739 | 0.581 |
| | bytes | 0.806 | **0.762** | 0.740 | 0.590 |
| | syn_unanswered | 0.600 | **0.568** | 0.556 | 0.578 |
| **Rbot s11** (20; 0.082 / 0.054 / 0.054; LR 0.518) | flows | 0.439 | **0.498** | 0.429 | 0.701 |
| | dst_ports | 0.379 | **0.532** | 0.452 | 0.670 |
| | dst_ips | 0.468 | **0.459** | 0.504 | 0.395 |
| | bytes | 0.393 | **0.521** | 0.421 | 0.724 |
| | syn_unanswered | 0.518 | **0.596** | 0.500 | 0.467 |
| Neris s02 (78; 0.597 / 0.425 / 0.413; LR 0.571) | flows | 0.272 | 0.335 | 0.973 | 0.870 |
| | dst_ports | 0.256 | 0.218 | 0.972 | 0.887 |
| | dst_ips | 0.305 | 0.216 | 0.974 | 0.947 |
| | bytes | 0.513 | 0.539 | 0.971 | 0.745 |
| | syn_unanswered | 0.886 | 0.781 | 0.963 | 0.982 |
| Virut s13 (9; 0.439 / 0.302 / 0.313; LR 0.991) | flows | 0.222 | 0.244 | 0.809 | 0.877 |
| | dst_ports | 0.237 | 0.396 | 0.803 | 0.767 |
| | dst_ips | 0.222 | 0.382 | 0.803 | 0.773 |
| | bytes | 0.276 | 0.254 | 0.838 | 0.773 |
| | syn_unanswered | 0.512 | 0.342 | 0.689 | 0.844 |
| NSIS s12, control (72; 0.985 / 0.979 / 0.985; LR 0.957) | flows | 0.875 | 0.927 | 0.922 | 0.537 |
| | dst_ports | 0.866 | 0.872 | 0.921 | 0.710 |
| | dst_ips | 0.871 | 0.884 | 0.922 | 0.676 |
| | bytes | 0.888 | 0.885 | 0.924 | 0.420 |
| | syn_unanswered | 0.909 | 0.897 | 0.526 | 0.477 |

The bot host is the busiest internal source host in **0 %** of the positive windows on s08, s07,
s11 and s13, and in 0.9 % on s02. Each capture has 272-478 active internal hosts.

### What N-6b shows

1. **D-039's reopen condition is not met, as the rule was written.** It fails on all three deciding
   scenarios, for two different reasons.
   - **Sogou s07:** the global statistics already separate (0.80-0.92 on flows, ports, IPs and bytes).
     The information is in the global state, as LR's 0.737 already suggested. The world model's
     inversion there is its learned weighting (N-6a), not drowning.
   - **Murlo s08 and Rbot s11:** the label-free per-host max stays at or below 0.58 and 0.60. It
     never reaches 0.70.
2. **On Murlo, the bot host's signal is real, but drowned in the global state and not recoverable by
   a maximum.**
   - The bot host's own traffic ranks s08's windows at 0.93-0.96. The global statistics sit at
     0.32-0.34 and the per-host max at 0.33-0.51.
   - The bot is never the busiest of s08's 478 internal hosts. At host level it ranks *below* the
     other active hosts (0.28-0.41).
   - Murlo is the one family where LR is weak too (0.590, D-039: "Murlo stays open"). This is the
     "drowned" pattern the evaluators described.
   - Neris s02 and Virut s13 show the same pattern (oracle 0.80-0.97, global 0.22-0.31 on the
     counts). They are reported, but they do not decide.
3. **The oracle is close to the labels by construction, so it is an upper bound and nothing more.**
   `y_within_K` comes from the bot host's own flows, so the bot host's activity nearly defines it
   wherever the bot is silent in background windows. The oracle shows that the information exists
   per host. It does not show that a model could find the host without labels.
4. **Rbot s11 is not a per-host story.** Even the oracle is at chance (0.42-0.50) on its 34 windows,
   and N-6a traced its seed-44 inversion to ICMP flows with no `State` field.
5. **Direction.** Several global and per-host counts sit well below 0.5 on s08, s02 and s13: background
   windows are *busier* than bot windows. The rule fixed "higher = bot" in advance, so these are
   reported as they are, not flipped. They are the same direction flips N-6a found on the models'
   inputs.
6. **What would need the team.** The reopen condition as written is not met, so no per-host-state run
   is licensed. Point 2 is new evidence for the "drowned" half of the evaluators' trigger, on Murlo,
   which D-039 recorded as unsupported. A per-host state that could use it would have to score each
   host against its own past, not take a maximum over hosts. E21's six host-relative features did
   something close and did not help on CIC-IDS2017. Whether that justifies a new pre-registration is
   a team decision, not a result.
7. **Caveats.**
   - s12's `From-Botnet` sources include six external addresses, so its oracle is not a single-host
     number.
   - s07's bot host is active in only 10 of its 44 windows.
   - Five statistics are tried per scenario, so a single hit would have been weak evidence. None
     occurred on s08 or s11.

Artefacts:
- `results/tables/n6b_ctu13_perhost.csv` (one row per scenario and statistic: `roc_global`,
  `roc_perhost_max`, `roc_oracle_bot`, `roc_hostlevel_bot_vs_other_hosts`, the E25b references and
  `meets_rule`);
- `results/tables/n6b_ctu13_perhost_hostlevel.csv` (whether the bot is the busiest internal host);
- `results/runs/n6b-ctu13-perhost/` (`metrics.json` with the grid checks, the bot hosts and the
  internal host counts; `run.log`).

---

## N-6a, seed 42 - the inversion diagnostic on the third seed (D-039, descriptive)

```
python scripts/ctu_inversion_diagnostic.py --seeds 42      # seed 42's CTU-13 fold checkpoints are on the GTX 1650 machine
```

This is N-6a's method, unchanged (the script at `06514ba`), on the seed whose weights were not on the
other machine. The refit LR reproduces `lr-ctu13-s42` exactly on this machine: Spearman 1.0 and
ROC-AUC identical on all six scenarios. The small differences N-6a reported came from the other
machine's library versions.

| scenario | role | features that flip | **WM ROC-AUC** s42 | WM, flipped set neutralised | the single features that push seed 42's ranking most the wrong way (ROC-AUC gain when neutralised) | N-6a, s43 / s44, flipped set neutralised |
|---|---|---:|---:|---:|---|---|
| Murlo s08 | inverted | 25 | 0.205 | **0.719** | `fin_cnt_sum` +0.05, `is_outbound_rate` +0.05, `svc_https_rate` +0.04 | 0.741 / 0.789 |
| Neris s02 | inverted | 18 | 0.610 | 0.678 | `one_way_rate` +0.07, `uniq_dst_ip` +0.05 | 0.623 / 0.626 |
| Rbot s11 | inverted | 19 | 0.075 | **0.700** | `dst_port_entropy` and `dst_ip_entropy` **+0.62** each, `psh_cnt_sum` +0.43, `proto_icmp_rate` +0.39 | 0.811 / 0.486 |
| Virut s13 | inverted | 10 | 0.439 | **0.750** | **`svc_https_rate` +0.48**, `is_internal_rate` +0.16, `is_inbound_rate` +0.15 | 0.347 / 0.441 |
| Sogou s07 | inverted | 3 | 0.015 | 0.017 | none above +0.02 | 0.175 / 0.188 |
| NSIS s12 | control | 11 | 0.982 | 0.991 | none above +0.011 | 0.979 / 0.991 |

**What seed 42 adds to N-6a.**
1. **The direction-flip reading holds on all three seeds for Murlo and Rbot s11.** Neutralising the
   flipped set lifts seed 42 from 0.21 to 0.72 on Murlo and from 0.08 to 0.70 on Rbot s11.
   - On s11, seed 42 leans on destination-port and destination-IP entropy (+0.62 each) and on the
     ICMP share (+0.39).
   - The ICMP share is the `State`-less ICMP artefact N-6a flagged on seed 44.
2. **Neris s02 is not inverted on seed 42 (0.610)**, as E25b already showed. The flipped set still
   costs it about 0.07.
3. **Virut s13 on seed 42 is a flip as well as a single-feature reliance.**
   - The HTTPS share alone is worth +0.48, as on seeds 43/44.
   - Neutralising the whole flipped set lifts seed 42 to 0.750, where seeds 43/44 reached only
     0.35-0.44.
   - N-6a's "not flips" reading of s13 was therefore seed-specific. The verdict rests on 9 background
     windows (see N-8 x E25b, point 5).
4. **Sogou s07 is not explained on seed 42.** No flipped set or single feature moves it by more than
   0.02 (0.015 throughout). The duration and ephemeral-port reliance N-6a found on seeds 43/44 does not
   appear here. N-6b shows the global statistics themselves separate s07 (0.80-0.92), so the seed-42
   inversion is spread across the model's weighting, not concentrated in one input.
5. **The control holds.** On NSIS no single feature moves seed 42 by more than 0.011.

N-6a's caveats apply unchanged. The flipped set is defined with the held-out labels, and neutralising
one feature at a time measures reliance, not cause.

Artefacts:
- `results/tables/n6_ctu13_inversion_s42_features.csv` and `n6_ctu13_inversion_s42_summary.csv`;
- `results/runs/n6-ctu13-inversion-s42/` (`metrics.json` with the LR reproduction check; `diagnostic.log`).

---

## N-8 fix (D-041) - window positions and carried state: gates G1-G3 pass, and both routes now serve length-invariant models

```
bash results/runs/n8-logs/run_chain_d041.sh       # E20rw x 3 seeds, r2w x 3 seeds, the r2i control, then:
python scripts/n8_eval.py                          # D-041's gates G1-G3
.venv/Scripts/python.exe -m pytest -q tests backend/tests
```

**What changed (code `4ba2559`, pre-registered in D-041, `1c78e49`).**
- **Positions.** `pos_mode: window` gives the key at distance d from its query `pos[15 - d]`, so a
  window's score no longer depends on the capture's length. The old `interp` mode stretched the 16
  positional vectors to the whole input.
- **Carried state.** `forecast(..., carry=)` carries the latent state and the last 15 embeddings
  across calls, so a stream scored in chunks equals the same stream scored in one pass.
- **Retrained.** The two served methods were retrained with only that change:
  - E20r becomes E20rw: E20r's exact 105 inputs, 5 folds, seeds 42/43/44;
  - r2's setup becomes r2w: 70 inputs, Thursday and Friday folds, seeds 42/43/44;
  - plus a control, `n8-r2i-s42`: r2's setup with today's code and the old positions.

*Procedure notes.*
1. All runs went one at a time on the GTX 1650 from code `d1b3f22`, which is D-041's amendment
   (`050adaa`) plus tooling. No run needed a retry. Checkpoint sha256 manifests are in each run
   folder's `checkpoints_manifest.json`; the weights stay untracked.
2. Two earlier starts were stopped in their first fold and saved nothing:
   - a parallel one, stopped at the user's request;
   - one that read the rebuilt 106-input matrix, stopped and recorded in D-041's amendment.
   Their logs are in `results/runs/n8-logs/stopped-*`.
3. The runner was replaced once between runs so that the gates could be scored before D-042. The run in
   progress was left running and checked like any other run (`chain.status`).

**D-041's gates, applied as written.**

| gate | bar | result |
|---|---|---|
| **G1** correctness | unit tests pass | 16 / 16 (`tests/test_positional_window.py`, `tests/test_world_model.py`) |
| | on every served checkpoint and held-out day, mean-path `p_max` from 60-window chunks with carried state = one pass, max \|diff\| <= 1e-5 | **2.3e-10** over 17 checkpoint-days |
| | `test_forecast_is_prefix_invariant` no longer a strict xfail and passing on the served checkpoints | passes, plus new tests on the real served checkpoints of both routes; full suite 183 passed, 0 xfailed |
| **G2** PCAP route: mean of E20rw 42/43/44 | Thursday PR-AUC >= 0.20; S2\* >= E19's 0.651 - 0.03 = 0.621 | PR-AUC **0.514**, S2\* **0.675**: passes |
| **G3** CSV route: r2w seed 42 | Thursday PR-AUC >= 0.540; Thursday causal F1 >= 0.508 | PR-AUC **0.677**, F1 **0.591**: passes |

So the PCAP route now serves the E20rw mean, and the CSV route serves r2w seed 42 (`backend/inference.py`,
`models/registry.json`).

**E20r against E20rw, seed by seed.** Causal expanding q90 on `comp`, label `y_within_K`.

| run | Thu PR-AUC | Thu F1 | Fri PR-AUC | S1 precision / FPR | S2\* | S3 | rollout gain Thu / Fri |
|---|---:|---:|---:|---|---:|---|---|
| E20r s42 | 0.418 | 0.533 | 0.166 | 0.377 / 0.134 | 0.645 | 4/19 p=0.91 | 0.161 / 0.244 |
| E20rw s42 | 0.409 | 0.533 | 0.162 | 0.321 / 0.145 | 0.661 | 5/19 p=0.67 | 0.161 / 0.242 |
| E20r s43 | 0.562 | 0.623 | 0.104 | 0.332 / 0.121 | 0.597 | 5/19 p=0.74 | 0.168 / 0.253 |
| E20rw s43 | 0.542 | 0.623 | 0.106 | 0.332 / 0.121 | 0.627 | 4/19 p=0.87 | 0.166 / 0.253 |
| E20r s44 | 0.710 | 0.697 | 0.123 | 0.418 / 0.111 | 0.685 | 4/19 p=0.82 | 0.168 / 0.245 |
| E20rw s44 | 0.726 | 0.688 | 0.129 | 0.432 / 0.104 | 0.692 | 6/19 p=0.22 | 0.166 / 0.250 |
| E20r mean (E27) | 0.543 | 0.609 | 0.143 | 0.356 / 0.128 | 0.669 | 4/19 p=0.92 | - |
| **E20rw mean** | **0.514** | 0.583 | 0.137 | 0.350 / 0.129 | **0.675** | 5/19 p=0.53 | - |

**The CSV route.**

| run | Thu PR-AUC | Thu F1 | Thu FPR | Fri PR-AUC |
|---|---:|---:|---:|---:|
| r2, shipped until now (E14 scores) | 0.640 | 0.608 | 0.078 | 0.109 |
| r2i s42: r2's setup, today's code, `interp` (control) | 0.641 | 0.601 | 0.083 | 0.108 |
| **r2w s42**: the same, `window` (served now) | **0.677** | 0.591 | 0.093 | 0.118 |
| r2w s43 | 0.340 | 0.498 | 0.097 | 0.107 |
| r2w s44 | 0.408 | 0.577 | 0.069 | 0.109 |

### What the N-8 fix shows

1. **The defect is fixed where it matters.**
   - A served model's score for a window no longer depends on how much of the capture follows it.
   - A live feed scored in chunks gives the offline scores to 2e-10.
   - D-034's causal threshold therefore now thresholds a causal score, as "a sensor can run it on a
     live stream" assumed.
2. **The fix costs E20r nothing measurable.**
   - Per seed, Thursday PR-AUC moves by -0.009 / -0.020 / +0.016, and S2\* by +0.016 / +0.030 / +0.007.
   - The rollout gain is unchanged to 0.002.
   - The ensemble's Thursday PR-AUC is 0.514 against 0.543, inside the seeds' own spread
     (0.41-0.73). Its S2\* rises from 0.669 to 0.675.
3. **The control shows no code drift.** r2's setup trained with today's code and the old positions
   reproduces r2 (0.641 against 0.640 Thursday PR-AUC). So r2w's differences are the positional change
   and seed noise, nothing else.
4. **The CSV route rests on one favourable seed, as r2 did.**
   - r2w seed 42 passes G3 (0.677), but seeds 43 and 44 reach 0.340 and 0.408.
   - G3 was written for seed 42, the same seed and setup as r2, and it passes as written.
   - The spread is the honest statement of what this recipe gives: 0.34-0.68 Thursday PR-AUC.
5. **Nothing here changes S3.** Early warning against the circular-shift null is still met nowhere:
   the E20rw mean has 5/19 early, p = 0.53. The claim stays "ranks pre-attack windows above background".
6. **Scope.** E25b (CTU-13) was scored with `interp`; N-8 x E25b bounded that effect at <= 0.023
   ROC-AUC on captures of 208 windows or more. D-042 uses window positions throughout.

Artefacts:
- `results/tables/n8_fix_eval.csv` (detection per run and day), `n8_fix_scorecard.csv` (S1-S4, rollout
  gain), `n8_fix_parity.csv` (G1, per checkpoint and day);
- `results/runs/n8-fix-eval/` (verdict), `results/runs/n8-e20rw-mean/` (the PCAP route's per-window
  scores);
- `results/runs/m1v2-n8-e20rw-s{42,43,44}/`, `n8-r2w-s{42,43,44}/`, `n8-r2i-s42/`, each with
  `checkpoints_manifest.json`, and `results/tables/<run>_{forecast,training_curves}.csv`;
- `results/runs/n8-logs/` (runner scripts, `chain.status`, per-run logs, the stopped starts,
  `n8-full-tests.log`).
