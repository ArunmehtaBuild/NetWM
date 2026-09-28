# NetWM - Architecture

**SIH 2026 · PS 26153 (NTRO) · AI based Network Attack Forecasting from Network Traffic Data**

This document describes **what ships now**, following D-041. The experiments that led here, including
the models the current ones replaced, are in `results.md`, and every modelling choice is in
`decisions.md`. Every number below comes from an artefact under `results/`.

NetWM learns the *dynamics* of a network: how its state evolves from one time window to the next. It
rolls those dynamics forward to score the next five minutes. It is a world model with prediction heads
attached, not a flow classifier with a time axis bolted on.

```
                     ┌─ CSV route:  70 flow features ───────────────► r2w (1 checkpoint per fold)
 flow CSV ──► windowing
 PCAP ──────► 60 s / 30 s ┤
                     └─ PCAP route: 70 flow + 17 CSV-packet + 18 pcap_ ─► E20rw seeds 42/43/44, mean per window

 each model:  S_t ─► encoder ─► attention over the last 16 windows ─► RSSM latent ─┬─ next-state decoder → surprise
                     (window positions, state carried across chunks - D-041)        ├─ stage head        → MITRE stage
                                                                                   └─ risk heads (3)    → K = 10 rollout
 alarm: p_max (mean path) ≥ causal expanding 90th percentile (D-034) · reasons: attention + Integrated Gradients
```

## 1. What ships, and what does not

| input | model served | what it is | why it is served |
|---|---|---|---|
| **flow CSV** | **r2w seed 42** (`models/n8-r2w-s42/`, 584,470 parameters) | r2's setup with window positions: 70 flow features, Thursday fold by default and Friday on request | passed D-041's gate G3 |
| **PCAP** | **E20rw, seeds 42/43/44**, the arithmetic mean per window (`models/m1v2-n8-e20rw-s4{2,3,4}/`, 593,500 parameters each) | E20r with window positions: 105 inputs. Each seed's fold for a held-out demo day, else Thursday | D-038's aggregation; passed D-041's gate G2 |
| **CTU-13** | **none: benchmark only** | E25's stack (factorised target, 56 Argus flow features), trained per botnet family to measure cross-family transfer (M2) | never served; it answers a research question |

- **Separate routes.** A PCAP upload never falls back to the CSV model, and a flow CSV is never fed to
  the packet model. That model would see zeros for packet features it never trained without.
- **One served model.** Both routes' checkpoints are identified by SHA-256 in
  `results/runs/<run>/checkpoints_manifest.json`.
- **Frozen evidence.** The M1/M2 evidence behind this document is frozen by
  `scripts/evidence_freeze.py` (tag `m1-m2-evidence-freeze`).

## 2. Network state `S_t`

Traffic is aggregated into **60 s windows at a 30 s stride**. `S_t` is one feature vector per window,
not a per-flow row: a world model needs a state that *evolves*, and consecutive flow records are not
consecutive states (D-002).

**Flow features: 70, read by both routes (S_t v1).**
- TCP flag ratios (SYN without ACK, RST, PSH, URG), and the protocol and service mix;
- bytes and packets per flow, duration, flow inter-arrival statistics, and bidirectional ratios;
- unique IPs and ports, destination-port entropy, per-host fan-out, and ports per pair.

**Packet features: read by the PCAP route only (35 of its 105 inputs).**
- **17 per-packet statistics that a flow meter records.** These are the TCP initial-window
  distribution, a packet-weighted payload histogram, per-direction payload and timing spread, the
  inter-arrival coefficient of variation, directional RST, SYN-only probes, and header bytes per packet.
  In training they come from the corrected CSVs; for an upload, from the PCAP converter (`pcap_to_flows`).
- **18 features measured directly from packets (`pcap_`, via `read_packets`).** These are TTL
  statistics, fragment rate, TCP retransmissions, zero windows, the true per-packet payload histogram,
  inter-packet timing, and SYN-only and RST shares. Capture duplicates are removed first.
- **The CSV route consumes no packet features.** A flow CSV carries none, so its model reads the 70
  flow features only.

**Scaling.** Heavy-tailed columns are `log1p`-compressed, then standardised by a scaler fitted on
**training days only** (D-014) and stored inside each checkpoint.

**Data.**
- CIC-IDS2017 in its corrected re-extraction (D-001), with two corrections of our own:
  - `- Attempted` traffic does not set the stage (D-009);
  - the infiltration sweep is split by source address (D-012).
- Labels are ordered MITRE stages, with Impact (DoS/DDoS) off the progression axis (D-003).

## 3. Dynamics model (both served routes)

An RSSM-style latent world model, about 0.6 M parameters:
- an encoder, then attention over the **last 16 windows**. Each key's position is its distance from
  the query (D-041), so a window's score never depends on how much of the capture follows it;
- a stochastic latent with a learned prior, the transition function the rollouts use;
- heads reading any real or imagined state: a next-state decoder (whose error is the *surprise*
  score), a MITRE stage head, and three risk logits: compromise, attack, escalation (D-016).

**Streaming.** `forecast(..., carry=)` carries the latent state and the last 15 embeddings between
calls. A live feed scored in 60-window chunks gives the one-pass scores to within 2.3e-10 on every
served checkpoint and held-out day (D-041, gate G1). Before D-041 the positional vectors were stretched
to the input's length, and chunked scoring was impossible.

**What the latent dynamics earn, and what they do not.**
- Against the same encoder predicting "within K" directly (Model A), the world model ranks pre-onset
  windows better (S2\* 0.70 against 0.61) and detects better (Thursday PR-AUC 0.39 against 0.22) (E24).
- Logistic regression ranks pre-onset windows as well as the round-2 world model (0.66 against 0.65,
  E26). So anticipation *as a ranking* does not need a world model.
- What the world model adds is detection at a usable alarm cost, and rollouts that beat "nothing
  changes" over steps 2-10 (E10). It loses to persistence at k = 1.

**Not in the served models.** The factorised risk target (E22) passed its own bar but was not composed
with real packets (E26, outcome 3). Neither served route uses it; the CTU-13 benchmark does.

## 4. Forecasting and alarms

From each window's filtered state the model imagines K = 10 steps (5 minutes, D-013).
- **Alarm score.** `p_max` is the maximum over the rollout of P(compromised), read off the
  deterministic mean path, so the score does not change between runs (D-019, E14). Monte-Carlo
  rollouts give the uncertainty band only.
- **Threshold.** A causal alert budget: each window's threshold is the 90th percentile of the scores
  *before it* in the capture, with no alarm in the first 20 windows (10 minutes) (D-034). Thresholds
  tuned on training days fire nothing on a held-out day (D-017, D-020). The dashboard calls the same
  function the evaluation measured, and draws the threshold as a curve (G-9).
- **PCAP route.** The alarm score is the per-window mean of the three seeds' scores (D-038).

## 5. Explainability

Every prediction carries two kinds of explanation:
- **When:** attention over the preceding windows;
- **What:** Integrated Gradients over the input features. IG runs on alarm windows plus a sample
  (D-018); the logistic-regression baseline gets exact linear SHAP.

**Weaker than it looks (E11).** The top-8 attributions contain the attack's known signature at
p < 0.05 on only 1 of 6 held-out episodes. The panel is therefore labelled "feature contributions to the
compromise score", not "why this is an attack".

**Stage mapping (E9).** On each held-out day the stage that matters is one the fold never trained on,
so the stage head has 0 recall on it by construction.

## 6. What the served models measure (CIC-IDS2017, held-out days)

These numbers come from `results/tables/n8_fix_eval.csv` and `n8_fix_scorecard.csv`.
- Threshold: the causal expanding 90th percentile of `comp`, label `y_within_K`.
- Leave-one-day-out: a day's numbers come from the fold that never trained on it.
- The baseline is logistic regression at the same causal threshold (`benchmark_final.csv`).

| Thursday (held out) | PR-AUC | F1 | precision | recall | FPR |
|---|---:|---:|---:|---:|---:|
| **CSV route**: r2w seed 42 | **0.677** | 0.591 | 0.574 | 0.608 | 0.093 |
| its seeds 43 / 44 (reported, not served) | 0.340 / 0.408 | 0.498 / 0.577 | | | |
| **PCAP route**: E20rw mean of 3 seeds | **0.514** | 0.583 | 0.581 | 0.584 | 0.087 |
| its seeds 42 / 43 / 44 | 0.409 / 0.542 / 0.726 | | | | |
| logistic regression (PS baseline) | 0.139 | 0.112 | 0.167 | 0.084 | 0.087 |

- **Friday is near floor for every model.** Its only compromise is a C2 family seen on no training day:
  PR-AUC 0.118 (CSV route) and 0.137 (PCAP route).
- **Seed luck is part of the CSV route's number.** Its recipe gives 0.34-0.68 Thursday PR-AUC across
  seeds; the served checkpoint is the favourable one, as r2 was.
- **Anticipation (PCAP route, 19 onsets on four held-out days).**
  - The ensemble ranks pre-onset windows above background at S2\* 0.675, where chance is 0.5.
  - Its alarm precision is 0.350 at an FPR of 0.129 (S1).
  - Early warning against a circular-shift null is **not met**: 5 of 19 onsets warned early, p = 0.53.

## 7. The CTU-13 benchmark (M2, not served)

Seven botnet families, each held out in turn (E25b, 3 seeds, LR alongside), on a 56-feature Argus flow
state. The result is reported **family by family, with 95 % block-bootstrap intervals**. Several
captures have almost no background traffic, so there is no pooled number, and the strong families must
not stand in for the weak ones.
- **Detection transfers firmly to one family: NSIS** (0.98 on every seed, interval above 0.97).
- **Separation is modest on Rbot's largest capture (s03).** The seed mean is 0.70 [0.65, 0.75], while
  LR is at chance.
- **Menti's "transfers" is not established.** It rests on 6 background windows, and the interval runs
  from 0.11 to 0.96.
- **The model is inverted on Murlo** (every seed's interval ends below 0.36) **and on Rbot s11** (below
  0.18, on 20 background windows). It scores the bot *lower* than background.
- **Not established either way:** Neris's inversion (s02's intervals cross 0.5), and Virut (s05 spans
  0.23-1.00; s13 sits below 0.5 on 9 background windows).
- **Diagnosis.**
  - Most inversions are direction flips: features move the opposite way from the training families
    (N-6a).
  - On Murlo the bot host's own traffic separates, but it is drowned in the network-global state
    (N-6b).
  - Adding each host's deviation from its own past does not fix the inversions (D-042).
- **Anticipation on CTU-13** carries to two Neris and two Rbot captures, fails on Murlo and Rbot s03,
  and never beats the null.

## 8. Current limitations

1. **No validated early warning.** No configuration's early alarms beat a shuffled-time baseline on
   CIC-IDS2017 or CTU-13. The claim is limited to "ranks pre-attack windows above background" (D-021).
   The candidate causes (statistic, threshold, target, representation) were each tested and ruled out
   (E13-E16).
2. **No reliable cross-family transfer.** Within a day, pre-onset windows separate at ROC-AUC
   0.88-0.96. Across days and across botnet families the signal falls to chance or inverts (E12, E16,
   E25b). CIC-IDS2017 has only two compromise families, so M3 (CIC-IDS2018) is the next transfer test.
3. **Scores are risk scores, not calibrated probabilities (E17).** Hence the alert budget rather than
   a probability threshold.
4. **The PCAP route's numbers describe the model on the training-matrix state.** On a full real
   capture, 28 of the 67 flow features the upload converter builds still differ from the training
   matrix by more than 5 % on average (E27 check 4, D-040). So no live-PCAP detection number is quoted
   until that parity holds (N-9).
5. **Packet features help detection, not anticipation.**
   - Real packets raised Thursday PR-AUC from 0.43 to 0.56 over flow-only (E20r).
   - They did not raise S2\*.
6. **Explanations and stage labels are weak on unseen attacks** (E9, E11).

## Deployment and reproducibility

The API (FastAPI + uvicorn) and the dashboard (static files, vendored assets) deploy separately and run
**fully offline**: a test that makes `socket.socket` raise exercises upload -> result -> replay.

```bash
python scripts/build_features.py --config configs/cicids2017.yaml       # S_t matrices
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/n8/r2_window.yaml \
    --test-days thursday friday --epochs 25 --samples 16 --run n8-r2w-s42 --seed 42 --no-figures    # CSV route
python scripts/train.py --data data/processed/cicids2017_m1v2p --model-config configs/n8/e20r_pcap_window.yaml \
    --test-days monday tuesday wednesday thursday friday --epochs 25 --seed 42 --run m1v2-n8-e20rw-s42 --no-figures
                                                                          # PCAP route, and seeds 43, 44
python scripts/n8_eval.py                                                 # D-041's gates
uvicorn backend.server:app --port 5000                                    # API; serve frontend/ statically
```

- **Traceability.** Every number carries an experiment id, threshold policy, seed and git SHA in
  `results/runs/<id>/metrics.json`, and every modelling choice its reason in `decisions.md`
  (D-001 … D-042).
- **Weights.** They are not tracked: `models/` stays local. Each run's `checkpoints_manifest.json`
  identifies its weights by SHA-256.
