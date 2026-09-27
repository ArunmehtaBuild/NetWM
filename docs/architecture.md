# NetWM - Architecture

**SIH 2026 · PS 26153 (NTRO) · AI based Network Attack Forecasting from Network Traffic Data**

NetWM learns the *dynamics* of a network - how its state evolves from one time window to the next -
and rolls those dynamics forward to answer what the next five minutes look like. It is a world model
with prediction heads attached, not a flow classifier with a time axis bolted on.

```
 flow CSV ─┐                           ┌─ next-state decoder → surprise (unseen-behaviour signal)
           ├─► windowing ─► S_t ─► RSSM ┼─ stage head        → per-step MITRE distribution
 PCAP ─────┘   60 s / 30 s   70-d  core └─ risk heads (3)    → compromise / attack / escalation
                                     │                         K-step rollout: p_cum, p_lo, p_hi
                                     └──► attention + Integrated Gradients → per-prediction reasons
```

## 1. Network state `S_t`

Traffic is aggregated into **60 s windows at 30 s stride**; `S_t` is a 70-dimensional vector per
window, not a per-flow row, because a world model needs a state that *evolves* and consecutive flow
records are not consecutive states (D-002).

Flow-level (NetFlow / IPFIX): TCP flag ratios (SYN-without-ACK, RST, PSH, URG), protocol and service
mix, bytes/packets per flow, duration, flow IAT statistics, bidirectional ratios, unique IPs and
ports, destination-port entropy, per-host fan-out, ports-per-pair. Packet-level (PCAP): TTL variance,
TCP initial window size, fragment flags, payload-size distribution, retransmissions, scan signatures -
with a `has_pcap` mask so CSV-only input works unchanged. Heavy-tailed columns are `log1p`-compressed,
then standardised by a scaler fitted on **training days only** (D-014).

**Data.** CIC-IDS2017 in its *corrected* re-extraction (Engelen et al.): the original mis-terminates
TCP flows and mislabels attack onsets, and onset time is exactly what we predict (D-001). Our audit
corrected it further - `- Attempted` traffic must not set the stage, or six hours of post-shutdown
botnet retries relabel Friday and hide the port scan and the DDoS (D-009); and `Infiltration -
Portscan` covers two kill-chain stages, an external sweep and the victim's internal one, separable by
source address (D-012).

**Labels.** Each window carries an ordered MITRE stage - Benign < Reconnaissance < Initial Access <
Lateral Movement < C2 < Exfiltration - with Impact (DoS/DDoS) off the progression axis (D-003).

## 2. Dynamics model

An RSSM-style latent world model (~0.6 M parameters, ~5 min per fold on a GTX 1650):

- a temporal Transformer encoder over the last L windows produces `h_t`, whose attention weights are
  reused directly as the temporal half of the explanation;
- a **stochastic** latent `z_t` with posterior `q(z_t | h_t, S_t)` and prior `p(z_{t+1} | z_t, h_t)` -
  the prior *is* the learned transition function, and the KL between them is what forces it to become
  a usable predictor. *E10: removing the stochastic latent has no consistent effect on rollout or detection across three seeds, so the ablation does not support it. It is kept because the submission checkpoint uses it and the Monte-Carlo bands come from it*;
- heads reading any real *or imagined* state: next-state decoder, MITRE stage, and three risk logits -
  `compromise`, `attack`, `escalate_step` (D-016).

Training combines next-state NLL, KL with free bits, a multi-step open-loop rollout loss, stage
cross-entropy and risk BCE. *E10: the multi-step loss earns its place on **detection** (removing it costs 0.17-0.21 Thursday F1 on two of three seeds), not on rollout fidelity (Thursday rollout is better without it on all three seeds).* Three risk heads rather than one because the week holds exactly two
compromise families: a single target gives each fold one positive family and the model memorises it,
while "anything hostile" and "the attacker advanced a stage" have positives on every attack day.

## 3. Forecasting

From `S_t` the model imagines K = 10 steps (5 minutes, D-013) in latent space with N Monte-Carlo
samples. Per window it outputs the cumulative risk curve with 5th/95th percentile bands, the per-step
stage distribution, and next-state prediction error as a *surprise* score for unfamiliar behaviour.
The alarm score itself is read off the deterministic mean path, so a lead-time count cannot move
between runs of the same checkpoint on the same file.

The alarm statistic is `max_k P(compromised at t+k)` rather than the cumulative union, because the
compromise head predicts a state *property* that persists, which the union over-counts (D-019). The
deployable threshold is an **alert budget** - the top 10 % of scores in the capture being analysed,
set without labels - because F1-optimal thresholds from training days are ~100x too high on a
held-out day and fire zero alarms (D-017, D-020).

## 4. Explainability

Every prediction carries encoder attention over the preceding windows ("which earlier moment made the
model worried") and Integrated Gradients over the input features ("which flags, ports and flow
statistics drove it"). IG runs on alarm windows plus a regular sample rather than all ~970 windows of
a day, keeping an interactive request interactive (D-018); the logistic-regression baseline is
explained with exact linear SHAP, so the two are comparable.

## 5. Evaluation methodology

This is where most published CIC-IDS2017 results go wrong, so it is a design element, not an
afterthought.

- **Leave-one-day-out, never random splits** (random splits put near-duplicate flows from one attack
  burst in both halves - how the literature reaches ~0.99 F1, D-006), plus leave-one-attack-family-out
  for the PS's "unseen attack patterns" requirement.
- **Two thresholds, always**: train-tuned (what a deployment could pick) and oracle (an upper bound it
  could not) - the baseline's F1 swings 0.011 -> 0.193 between them (D-015).
- **A persistence floor** (`S_hat_{t+1} = S_t`): traffic is autocorrelated, so any dynamics claim must
  beat "nothing changes".
- **Lead time is reported with its false-positive rate on the same line.** A score that fires almost
  everywhere "warns early" by accident: one configuration reports 2 of 4 episodes warned with 6.5
  windows of lead while scoring F1 0.021 (E3b).
- **Every early-warning count is tested against a null** (D-022): 2,000 circular shifts of the same
  score at the same threshold, an eligibility mask that refuses credit for alarms sitting inside the
  previous episode's traffic, and a confirmation that must land before the onset. The harness first
  reproduces the published numbers on the published score arrays, so the measurement is verified
  before anything is measured with it. This is what turns "1 of 4 episodes warned early" from a
  headline into a p-value - in our case p = 0.41 (E15a).

## 6. Results (held-out infiltration day; tables and commands in `results.md`)

Every NetWM number is the `p_max` alarm statistic (D-019). The threshold is the **causal** alert budget:
the 90th percentile of the scores seen so far that day, never of windows still to come (D-034, E18).
The shipped checkpoint is quoted with the range its method gives over three training seeds (D-032).

| Thursday fold (base rate 0.171) | LR baseline (E3) | **NetWM r2, shipped** (E14) | same method, 3 seeds (E10) |
|---|---:|---:|---:|
| PR-AUC | 0.139 | **0.640** | 0.37-0.64 |
| ROC-AUC | 0.379 | **0.827** | 0.73-0.83 |
| F1 at a deployable threshold | 0.011 (own threshold) | **0.608** | 0.52-0.61 |
| precision / recall | - | **0.614 / 0.602** | 0.54-0.64 / 0.50-0.60 |
| FPR, windows alarmed | 0.608 (oracle) | **0.078, 16.8 %** | 0.06-0.09, 13-17 % |
| episodes warned early | 0 / 4 | 0 / 4 | - |

Even the weakest seed (F1 0.52) is about 50x the baseline. E14's 0.576 at 2.7 % FPR used a threshold
taken over the whole day, future windows included; it is an upper bound, not a deployable number.
The causal threshold keeps the signal but not the budget: it alarms on 16.8 % of windows, not 10 %
(E18). Friday, whose only compromise is a C2 family seen on no training day, is near zero under
every threshold.

Open-loop rollout beats the persistence floor averaged over steps 2-10, on both held-out days and
every training seed (E10). It loses at k = 1: one step ahead, "nothing changes" is still the better
guess (E5). Adding 2 minutes of history to the baseline does not help it: PR-AUC falls to 0.114 (E3b).

Round 3 (first-occurrence hazard + precursor heads) was a regression: PR-AUC 0.35-0.45 against
round 2's 0.640, with no gain in early warning (E15). Round 4 (per-capture rank normalisation) failed
its bar and was unstable across seeds (E16). The shipped checkpoints are therefore round 2. Per D-021,
no early-warning claim enters this document, because none has survived a deployable threshold and a
null.

## 7. What does not work yet, and what it would take

**No early warning, and the gap is bounded by experiments rather than argument.** Five candidate
causes, each tested and eliminated:

| candidate cause | verdict | evidence |
|---|---|---|
| the rollout statistic | ruled out - six statistics, ranking insensitive | E13 |
| the alarm threshold | ruled out - five policies, zero early warnings at every deployable one | E14 |
| the two warnings that survived an oracle threshold | **were chance** - p = 0.41 and p = 0.55 against a circular-shift null | E15a |
| the supervision target | ruled out - first-occurrence hazard + precursor heads fail every clause of a pre-registered bar, on 3 seeds | E15 |
| the state representation | ruled out - per-capture rank normalisation fails every clause of its bar and is seed-unstable; slope features carry no precursor signal | E16 |

**Where the signal dies: transfer across days.** Pre-onset windows separate from background at
ROC-AUC 0.88-0.96 *within* a day (E12). Leave-one-day-out on Thursday, logistic regression over all 70
features scores 0.604, and `uniq_dst_port` alone scores 0.607 (E16). What a model learns about one
day's attack families does not carry to another's. The one Thursday onset with a clean quiet run-up
(602) turns out to be bystander traffic, not the attack (S-8). Testing transfer properly needs more
compromise families than CIC-IDS2017 has: two, each confined to one day, so leave-one-day-out already
*is* leave-one-family-out (D-006 amendment).

**Outputs are risk scores, not calibrated probabilities (E17).** A temperature fitted on the training
days improves held-out Thursday but makes held-out Friday worse than a constant forecast. The
deployable threshold stays an alert budget (D-017).

**Roadmap.** M2 CTU-13: seven botnet families across 13 scenarios, the experiment that can test
transfer. Its public PCAPs are botnet-only, so M2 is a new model on a reduced flow state, not a
transfer test of this checkpoint (`research/ctu13.md`). M3 CIC-IDS2018 (scale), M4 UNSW-NB15
(cross-domain).

## Deployment and reproducibility

The API (FastAPI + uvicorn) and the dashboard (static files, vendored assets) deploy separately and
run **fully offline** - a test that makes `socket.socket` raise exercises upload -> result -> replay.

```bash
python scripts/build_features.py --config configs/cicids2017.yaml   # S_t matrices
python scripts/benchmark_baselines.py                               # E2, E3 baselines
python scripts/train.py --run e4e7-worldmodel-r2                    # world model, per fold
python scripts/predict.py --model models/e4e7-worldmodel-r2/thursday.pt --input <csv|pcap>
uvicorn backend.server:app --port 5000                              # API; serve frontend/ statically
```

Every number carries an experiment id, threshold policy, seed and git SHA in
`results/runs/<id>/metrics.json`; every modelling choice carries its reason in `decisions.md`
(D-001 … D-023).
