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

Flow-level (NetFlow / IPFIX): TCP flag counts and ratios (SYN-without-ACK, RST, PSH, URG), protocol
and service mix, bytes and packets per flow, duration, flow IAT mean/std/max, bidirectional ratios,
unique source and destination IPs and ports, destination-port entropy, per-host fan-out and
ports-per-pair. Packet-level (PCAP): TTL variance, TCP initial window size, fragment flags,
payload-size distribution, retransmissions and scan signatures, with a `has_pcap` mask so CSV-only
input works unchanged. Heavy-tailed columns are `log1p`-compressed then standardised with a scaler
fitted on **training days only** (D-014).

**Data.** CIC-IDS2017 in its *corrected* re-extraction (Engelen et al.), not the original CSVs: the
original mis-terminates TCP flows and mislabels attack onsets, and onset time is precisely the
quantity we predict (D-001). Our own audit corrected the labels further - `- Attempted` traffic must
not set the stage, or six hours of post-shutdown botnet retries relabel Friday and hide both the port
scan and the DDoS (D-009); and `Infiltration - Portscan` covers two different kill-chain stages, an
external sweep and the victim's internal sweep, separable by source address (D-012).

**Labels.** Each window carries an ordered MITRE stage - Benign < Reconnaissance < Initial Access <
Lateral Movement < Command & Control < Exfiltration - with Impact (DoS/DDoS) deliberately off the
progression axis (D-003).

## 2. Dynamics model

An RSSM-style latent world model (~0.6 M parameters, ~5 min per fold on a GTX 1650):

- a temporal Transformer encoder over the last L windows produces `h_t`, whose attention weights are
  reused directly as the temporal half of the explanation;
- a **stochastic** latent `z_t` with posterior `q(z_t | h_t, S_t)` and prior `p(z_{t+1} | z_t, h_t)` -
  the prior *is* the learned transition function, and the KL between them is what forces it to become
  a usable predictor;
- heads reading any real *or imagined* state: next-state decoder, MITRE stage, and three risk logits -
  `compromise`, `attack`, `escalate_step` (D-016).

Training combines next-state NLL, KL with free bits, a multi-step open-loop rollout loss, stage
cross-entropy and risk BCE. Three risk heads rather than one because the week contains exactly two
compromise families: a single target gives each fold one positive family and the model memorises it,
whereas "anything hostile" and "the attacker advanced a stage" have positives on every attack day.

## 3. Forecasting

From `S_t` the model imagines K = 10 steps (5 minutes, D-013) in latent space with N Monte-Carlo
samples, decoding nothing until the heads are read. Per window it outputs the cumulative risk curve
with 5th/95th percentile bands, the per-step stage distribution, and next-state prediction error as a
*surprise* score for behaviour unlike anything in training.

The alarm statistic is `max_k P(compromised at t+k)` rather than the cumulative union, because the
compromise head predicts a state *property* that persists, which the union over-counts (D-019). The
deployable threshold is an **alert budget** - the top 10 % of scores in the capture being analysed,
set without labels - because F1-optimal thresholds from training days are ~100x too high on a
held-out day and fire zero alarms (D-017, D-020).

## 4. Explainability

Every prediction carries encoder attention over the preceding windows ("which earlier moment made the
model worried") and Integrated Gradients attributions over the input features ("which flags, ports and
flow statistics drove it"). IG runs on alarm windows plus a regular sample rather than all ~970
windows of a day, which keeps an interactive request interactive (D-018). The logistic-regression
baseline is explained with exact linear SHAP so the two are directly comparable.

## 5. Evaluation methodology

This is where most published CIC-IDS2017 results go wrong, so it is a design element, not an
afterthought.

- **Leave-one-day-out, never random splits.** Random splits put near-duplicate flows from a single
  attack burst in both train and test, which is how the literature reaches ~0.99 F1 (D-006).
- **Leave-one-attack-family-out** for the PS's "generalise to unseen attack patterns" requirement.
- **Two thresholds, always**: train-tuned (what a deployment could pick) and oracle (an upper bound it
  could not), because the baseline's F1 swings 0.011 -> 0.193 between them (D-015).
- **A persistence floor** (`S_hat_{t+1} = S_t`): traffic is autocorrelated, so "nothing changes" is a
  strong predictor and any dynamics claim must beat it.
- **Lead time is reported with its false-positive rate on the same line.** A score that fires almost
  everywhere "warns early" by accident: one configuration reports 2 of 4 episodes warned with 6.5
  windows of lead while scoring F1 0.021 (E3b).

## 6. Results (held-out infiltration day; tables and commands in `results.md`)

| Thursday fold | LR baseline (E3) | NetWM r1 | **NetWM r2** |
|---|---:|---:|---:|
| PR-AUC (base rate 0.171) | 0.139 | 0.473 | **0.675** |
| ROC-AUC | 0.379 | 0.753 | **0.814** |
| F1 at a deployable threshold | 0.011 | - | **0.576** (self-budget 10 %) |
| FPR at that threshold | 0.608 (oracle) | - | **0.027** |
| episodes warned early | 0 / 4 | 0 / 4 | 0 / 4 |

Open-loop rollout beats the persistence floor from k = 2 onward (NLL 2.05 vs 2.72 at k = 8) and loses
at k = 1 - one step ahead, "nothing changes" is still the better guess (E5). Adding 2 minutes of
history to the baseline does not help it: PR-AUC falls to 0.114 (E3b).

> **Pending:** the round-3 experiment (first-occurrence hazard target) reports into this table. Per
> D-021, an early-warning claim enters this document only if it survives a deployable threshold over
> multiple seeds, quoted with its false-positive rate.

## 7. What does not work yet, and what it would take

**No early warning.** Lead time is 0 at every deployable threshold. The cause is localised: the
precursor signal exists (pre-onset windows separate from background at ROC-AUC 0.88-0.96 within a
day, E12), the rollout statistic is not the blocker (E13), the threshold is not the blocker across
five policies (E14), and giving the baseline history makes it worse, not better (E3b). What remains
is the supervision target - the compromise head learns "is this state compromised", which is only
true after the fact - and a first-occurrence hazard target is the run that tests it.

**Unseen families sit at chance.** Friday's botnet C2 is the only C2 in the week, so a model trained
on the other four days has never seen an attacker advance that way. That is a dataset limitation,
answered by CTU-13 rather than by tuning.

**Roadmap.** M2 CTU-13 (scenario-held-out, real C2 and exfiltration ground truth), M3 CIC-IDS2018
(enterprise scale), M4 UNSW-NB15 (cross-domain transfer).

## Deployment and reproducibility

The API (FastAPI + uvicorn) and the dashboard (static files, vendored assets) deploy separately and
run **fully offline**; a test that makes `socket.socket` raise exercises upload -> result -> replay as
the evidence for that claim.

```bash
python scripts/build_features.py --config configs/cicids2017.yaml   # S_t matrices
python scripts/benchmark_baselines.py                               # E2, E3 baselines
python scripts/train.py --run e4e7-worldmodel-r2                    # world model, per fold
python scripts/predict.py --model models/e4e7-worldmodel-r2/thursday.pt --input <csv|pcap>
uvicorn backend.server:app --port 5000                              # API; serve frontend/ statically
```

Every number carries an experiment id, threshold policy, seed and git SHA in
`results/runs/<id>/metrics.json`; every modelling choice carries its reason in `decisions.md`
(D-001 … D-021).
