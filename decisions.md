# Decisions log

Every non-obvious ML / data decision, with the reason it was taken and what would make us revisit it.
Newest decisions are appended at the bottom. Status: `accepted` / `provisional` / `superseded`.

---

### D-001 — Use the **corrected** CIC-IDS2017 ("improved") flows, not the original CSVs
*Date: 2026-09-24 · Status: accepted*

**Decision.** M1 trains on `CICIDS2017_improved` (Engelen et al., WTMC'21 / Flow-based CNS'22
re-extraction), not the original `MachineLearningCSV` / `GeneratedLabelledFlows` release.

**Why.**
- The original CICFlowMeter mis-terminates TCP flows (a timing flaw), duplicates and miscalculates
  features, and detects the wrong protocol for some flows — so the *input features themselves* are
  wrong, which a dynamics model would happily learn.
- Labelling in the original release is time-window based with no payload validation: setup traffic,
  the dataset authors' own browsing, post-shutdown botnet retries and an entire attack
  (*Cool Disk – MAC*, a Python Meterpreter deployment) are mislabelled or missed. An unlabelled
  NMAP portscan at 17:33 sits outside the official window. For a *forecasting* model these errors
  are worse than for a classifier: they corrupt the onset time of the attack, which is exactly the
  quantity we are trying to predict early.
- The improved release keeps `Timestamp`, `Src IP/Port`, `Dst IP/Port` (the popular
  `MachineLearningCSV` drops them), which we need for windowing and per-host graph features.
- It adds `Attempted` sub-labels, letting us separate "attack traffic that did nothing" from
  "attack traffic that worked" — useful for a hazard target.

**Revisit if.** A reviewer demands comparability with published numbers on the original CSVs — in
that case we run one extra benchmark row on the original labels and report both.

**Refs.** [research/cicids2017.md](research/cicids2017.md)

---

### D-002 — Network state `S_t` = fixed-length time window, not per-flow row
*Date: 2026-09-24 · Status: accepted*

**Decision.** The unit of modelling is a **60 s window with 30 s stride** over the monitored
network; `S_t` is a feature vector aggregating all flows/packets in that window (global stats +
top-talker/host-level aggregates). Per-flow rows are kept alongside for the UI's "flagged flows"
table and for per-flow attribution.

**Why.**
- A world model needs a *state that evolves*; a single flow row is not a state of the network, and
  consecutive flow rows are not consecutive states (they are unordered within a burst).
- Windowing makes `P(S_{t+1}|S_t)` well-defined and gives a natural forecast horizon
  (K windows = K × 30 s of look-ahead).
- 60 s / 30 s chosen because the CIC-IDS2017 attack phases last 2–90 minutes: it gives 4–180
  windows per attack (enough transitions to learn), while a 50 % overlap doubles the number of
  training sequences without leaking future traffic into a window.

**Revisit if.** Lead-time results show the model only fires <1 window ahead (→ try 30 s/10 s), or
training is dominated by near-duplicate overlapping windows (→ drop the overlap).

---

### D-003 — Window label = most advanced MITRE stage present, with an ordered stage scale
*Date: 2026-09-24 · Status: provisional*

**Decision.** Each window gets a stage label from an ordered scale
`Benign < Reconnaissance < Initial Access < Lateral Movement < Command & Control < Exfiltration`,
plus `Impact` (DoS/DDoS) kept off the progression scale. A window's label is the most advanced
stage among its flows.

**Why.** The PS asks for ATT&CK stage prediction, and kill-chain progression is inherently ordered:
"how far along is the attacker" is the decision-support question. Impact is separated because
DoS/DDoS in CIC-IDS2017 is not part of the infiltration chain and would otherwise dominate the
ordinal scale.

**Provisional because.** CIC-IDS2017 has no true exfiltration ground truth; the exfiltration stage
is currently heuristic (sustained outbound byte asymmetry from a host already flagged). CTU-13 (M2)
supplies real C2/exfil sequences and will replace the heuristic.

**Refs.** [research/mitre-mapping.md](research/mitre-mapping.md)

---

### D-004 — Architecture: RSSM-style latent world model (deterministic GRU + stochastic latent) with a Transformer encoder
*Date: 2026-09-24 · Status: provisional*

**Decision.** Encoder (temporal Transformer over the last L windows) → `h_t`; stochastic latent
`z_t`; transition prior `p(z_{t+1} | z_t, h_t)`; heads for (a) next-state reconstruction, (b) stage
logits, (c) infiltration hazard at each rollout step. Rollout = imagine K steps in latent space,
N Monte-Carlo samples.

**Why.**
- *Stochastic* latent, not a point prediction: the honest output for "what happens next" is a
  distribution, and Monte-Carlo rollouts give the uncertainty band the PS's "probability of
  attacker progression" implies.
- Rolling out **in latent space** (Dreamer/PlaNet-style) is what makes K-step forecasting cheap —
  no need to decode observations at every imagined step.
- The Transformer encoder gives per-window attention weights we reuse directly as the temporal part
  of the explanation (the PS explicitly allows attention as the explainability mechanism).
- Small model (~1–3 M params) because training runs on a 4 GB GTX 1650.

**Alternatives rejected for now.** Plain LSTM classifier over windows (no state distribution, no
imagination — would not be a world model); GNN over host graphs (stronger for lateral movement,
but needs the host-graph state first — kept as an M2/M3 extension).

**Revisit if.** The stochastic path collapses (KL → 0) or rollouts are indistinguishable from a
deterministic GRU baseline; then simplify to a deterministic transition model and report it.

---

### D-005 — Two prediction targets: hazard `P(infiltration within k)` and stage forecast
*Date: 2026-09-24 · Status: accepted*

**Decision.** Train a discrete-time hazard head producing `P(compromise at step k | no compromise
before k)` for k = 1..K, converted to a cumulative curve, alongside the per-step stage classifier.

**Why.** A single "is there an attack now" logit cannot express *lead time*, which is the whole
value proposition. A hazard formulation gives a calibrated, monotone cumulative curve that the UI
can plot as a forecast cone and that supports "raise alarm when P(k≤10) > τ".

---

### D-006 — Evaluation: leave-one-day-out **and** leave-one-attack-family-out, reporting lead time
*Date: 2026-09-24 · Status: accepted*

**Decision.** (a) Leave-one-day-out over Tue–Fri (Monday's benign traffic always in train).
(b) A separate leave-one-attack-family-out run (e.g. train without Infiltration or without Botnet).
Metrics: F1, precision, recall, FPR, PR-AUC, per-stage confusion, and **mean lead time** = windows
between first alarm and ground-truth attack onset.

**Why.** Random row-level splits on CIC-IDS2017 leak the same attack burst into train and test and
produce the ~0.99 F1 scores that make published IDS results meaningless. Day-level splits keep
train/test temporally disjoint. The attack-family holdout is the PS's explicit "generalise to
unseen attack patterns" requirement, and lead time is the metric that distinguishes forecasting
from detection — a classifier scores 0 on it by construction.

**AMENDMENT (2026-09-26, Task Y-3c): Closing D-006(b) with evidence.**
On CIC-IDS2017, every compromise family is confined to one day. According to `meta.json`, the compromise positives are:
| Day | Family | Positives |
|---|---|---|
| Mon/Tue/Wed | None | 0 |
| Thursday | Infiltration | 166 |
| Friday | Botnet C2 | 127 |

Because families do not span multiple days, *leave-one-day-out is exactly leave-one-family-out for compromise*. Proposing a run like "drop Friday's botnet from the Thursday fold" would leave the hazard head with zero positives in the training set. Therefore, D-006(b) is satisfied by the leave-one-day-out runs (D-006(a)), and no separate family-holdout runs are possible on this dataset without a multi-family dataset like CTU-13.

---

### D-007 — Explainability: attention + Integrated Gradients, with SHAP for the baseline
*Date: 2026-09-24 · Status: provisional*

**Decision.** Per-prediction explanation = encoder attention over past windows (temporal "when")
+ Integrated Gradients (Captum) attributions over input features (feature "what"). The logistic
regression baseline is explained with exact SHAP (linear explainer) so the two are comparable.

**Why.** Kernel SHAP on a recurrent world model with MC rollouts is prohibitively slow for an
interactive demo (thousands of forward passes per window); IG needs ~32 forward passes and is exact
for the path it integrates. Attention is free and directly answers "which earlier moment made you
worried".

**Revisit if.** IG attributions prove unstable across baselines — then switch to GradientSHAP
(also Captum) and document the change here.

---

### D-008 — Demo UI: Flask + vanilla JS + vendored Chart.js, fully offline
*Date: 2026-09-24 · Status: accepted*

**Decision.** Flask backend, no build step, all JS/CSS assets vendored into `frontend/vendor/`.

**Why.** The PS requires the interface to run offline with no cloud API dependency; a CDN
`<script>` tag would break that on an air-gapped evaluation machine.

---

### D-009 — `- Attempted` traffic does not set the ground-truth stage
*Date: 2026-09-24 · Status: accepted · Evidence: E1*

**Decision.** Flows whose corrected label ends in `- Attempted` keep an `attempted=True` flag but are
treated as stage 0 when building window stage labels, hazard targets and onsets. They remain
available as an auxiliary target.

**Why.** The audit (E1) showed `Botnet - Attempted` spans **14:03 → 20:01 UTC on Friday** (307
minutes of post-shutdown C2 retries) versus 59 minutes for the real `Botnet` traffic. Counting it as
Command & Control labelled **727 of 968 Friday windows** as C2 and, because the window label is the
most advanced stage present, *masked the PortScan and DDoS entirely* (11 and 5 windows). Excluding
attempted traffic gives 116 C2 / 52 Recon / 41 Impact windows, which matches the published schedule.

**Revisit if.** We want a "connection attempt" early-warning signal — attempted traffic is exactly
the weak precursor a forecaster might exploit, so it may return as a *feature* or as an auxiliary
head, never as the stage ground truth.

---

### D-010 — Windows carry a multi-label stage vector alongside the dominant stage
*Date: 2026-09-24 · Status: accepted*

**Decision.** `window_stage_matrix()` produces a binary column per stage per window; the ordinal
"most advanced stage" is derived from it.

**Why.** Attacks overlap in real traffic (C2 beaconing while a scan runs), and collapsing to a single
stage discards the rest. On CIC-IDS2017 *after* D-009 the two views happen to agree — no window
contains two different stages — which is itself a finding: this dataset serialises its attacks. The
multi-label view costs nothing here and is what CTU-13 (M2), where botnet C2 and scanning genuinely
run concurrently, will need.

---

### D-011 — Compromise onset = first window with a non-attempted stage ≥ Lateral Movement
*Date: 2026-09-24 · Status: accepted (open item closed by D-012) · Evidence: E1*

**Decision.** Lead time is measured against episode onsets computed this way, with episodes split by
≥ 4 quiet windows (2 minutes).

**Why.** We need one unambiguous "the attacker got in" instant per episode. The audit puts Thursday's
onsets at **17:00:00, 17:18:30, 17:28:00, 17:53:00, 18:03:30 UTC**, against an official infiltration
schedule starting 17:19 — because the corrected labels mark internal portscan traffic from the
victim host starting **17:00:31**, ~19 minutes before the documented Meterpreter session. We take the
data over the schedule, and treat the official times only as a sanity overlay in plots.

**Resolved.** That 17:00 portscan turned out to be external (see D-012), so it is no longer an
onset; Thursday's first onset is now 17:18:30 UTC, matching the documented infiltration at 17:19.

---

### D-012 — Scan traffic is split by direction before it becomes a stage label
*Date: 2026-09-24 · Status: accepted · Evidence: E1*

**Decision.** A scan-type label whose source address is outside the monitored subnet is
Reconnaissance; the same label from an inside host is post-compromise discovery (Lateral Movement).
Implemented in `refine_scan_direction()` and applied by the CIC-IDS2017 adapter.

**Why.** The corrected release gives both events the single label `Infiltration - Portscan`. The
audit separated them: 955 flows at 17:00:31-17:00:45 UTC from **172.16.0.1** (external attacker NAT)
sweeping 954 ports on one host, then 70 812 flows from **192.168.10.8** — the Meterpreter victim —
sweeping the internal network. Treating the external burst as lateral movement invented a compromise
onset 18 minutes before the attacker actually got in, which would have silently inflated every
lead-time number we report.

**Side note worth keeping.** The infiltration C2 flows show three infected hosts, not one:
`192.168.10.8` (48 flows), `192.168.10.25` (30) and `192.168.10.9` (3), all dialling out to
`205.174.165.73`.

**Revisit if.** A dataset has no reliable notion of "inside" (CTU-13 mixes routed subnets) — then the
rule needs the adapter to declare its monitored prefixes explicitly.

---

### D-013 — Forecast horizon K = 10 windows (5 minutes)
*Date: 2026-09-24 · Status: provisional*

**Decision.** The hazard head and the `y_within_K` target look 10 windows ahead: 10 × 30 s stride =
5 minutes of look-ahead.

**Why.** The gap between the pre-compromise signal and the compromise itself on the infiltration day
is minutes, not hours: the Dropbox download, the reverse shell at 17:19 and the internal sweep at
18:04 are tens of minutes apart, and the individual episodes are 2-10 minutes long. A horizon far
longer than the causal gap just labels benign windows as positive and inflates the base rate; far
shorter and the forecast is a detection.

**Revisit if.** Lead-time results saturate at K (the model wants to warn earlier than we allow), or
the positive rate at K = 10 (17 % on Thursday) proves too permissive.

---

### D-014 — Log-compress heavy-tailed features, then standardise, fitted on training splits only
*Date: 2026-09-24 · Status: accepted*

**Decision.** `StateScaler` applies `log1p` to non-negative columns with skew > 2, then z-scores.
Fitted on the training days of each fold, never on the test day.

**Why.** Byte, packet and flow counts span five orders of magnitude between an idle window and a DDoS
window. Plain standardisation compresses 99 % of windows into a sliver of the range and lets one
attack dominate the gradients; a scaler fitted across all days leaks test-day statistics
(the 71 k-flow portscan changes the mean of half the columns).

---

### D-015 — Every threshold-dependent metric is reported twice: train-tuned and oracle
*Date: 2026-09-24 · Status: accepted*

**Decision.** For each model and fold we report metrics at the threshold that maximises F1 on the
*training* days (the deployable setting) **and** at the threshold that maximises F1 on the *test*
day (an oracle upper bound that no deployed system could pick).

**Why.** The baseline's numbers swing enormously with the threshold — on Thursday, logistic
regression goes from F1 0.011 (train-tuned) to 0.193 (oracle). Publishing only the first invites the
accusation that we handicapped the baseline; publishing only the second is leakage. Both, always,
for our model too.

---

### D-016 — Supervise three questions about a state, not just "is it compromised"
*Date: 2026-09-24 · Status: accepted · Evidence: E4-E7 round 1*

**Decision.** The risk head outputs three logits read off any (real or imagined) state:
`compromise` (at or past Lateral Movement), `attack` (anything non-benign, Impact included), and
`escalate_step` (this window is a step up the progression scale from the previous one). The
cumulative forecast is still `1 - prod(1 - p)` over imagined steps, per output.

**Why.** Round 1 gave the compromise head exactly **one** positive family per fold — Thursday's
infiltration or Friday's botnet C2 — because those are the only two compromises in the week. The
model memorised the family it saw and scored ROC-AUC 0.245 on the other one (worse than chance).
The two extra targets have positives on **every** attack day (attack: 23-34 % of windows;
escalation: 3-20 %), so "an attacker advancing" becomes learnable from four days instead of one.
Escalation is also the PS's own phrasing — *estimate the probability of attacker progression* — read
literally.

**Cost.** Two more heads' worth of parameters (negligible) and a slightly noisier compromise signal
if the shared trunk over-fits the easier targets. Watched via the per-target metrics in the
benchmark table.

---

### D-017 — Alarm threshold is an alert budget, not a probability
*Date: 2026-09-24 · Status: accepted · Evidence: E4-E7 round 1*

**Decision.** The deployable threshold is the 95th percentile of the model's scores on the training
days — "alarm on the noisiest 5 % of windows" — reported alongside the train-tuned and oracle
thresholds (D-015).

**Why.** Round 1: the F1-optimal threshold was 0.843 on training days and 0.059 on the held-out day,
a 14x gap, so a fixed probability threshold produced *zero* alarms on the test day. Absolute
probabilities from a model trained on four days do not transfer to a fifth; a rank-based budget
does, and it is how alert volume is actually managed in a SOC.

**Revisit if.** Calibration (temperature scaling on a held-out training day) closes the gap. *(Amended 2026-09-26: E17 tested this. Held-out Thursday calibration improved, but held-out Friday Brier score is 0.280 against 0.114 for a constant base rate, and ECE worsened from 0.245 to 0.270 with temperature scaling. Calibration does not transfer to an unseen day. The budget stays, and dashboard values must be labeled "score, not a calibrated probability".)*

---

### D-018 — Explanations are computed for alarm windows plus a regular sample, not every window
*Date: 2026-09-24 · Status: accepted*

**Decision.** `engine/predict.py` runs Integrated Gradients on the top-24 alarm windows and every
8th window; other windows carry attention weights only.

**Why.** IG costs ~32 forward passes through a 16-window context per explained window. Explaining
all 972 windows of a day would add minutes to an interactive request for output nobody reads; the
sampled windows keep the global attribution unbiased towards alarms.

---

### D-019 — Alarm score = max over the horizon, and lead time is measured per episode
*Date: 2026-09-24, restated 2026-09-25 · Status: accepted (for the reason below, not the original one) · Evidence: E13, E14*

**Decision.** The alarm statistic is `max_k P(compromised at t+k)` over the K imagined steps rather
than the cumulative union `1 - prod(1 - p_k)`. Implemented in `engine/predict.py` and in the
benchmark scripts.

**Original reasoning, and what happened to it.** The compromise head answers "is this state
compromised", a property that *persists*, so the union formula multiplies the same event K times and
saturates near 1. E13 showed ranking was nearly identical across statistics but that only the max
produced any early warning (2 of 4 Thursday episodes at an oracle threshold), and we took that as a
sign that the statistic might unlock lead time.

**E14 says it does not.** Re-scoring the r2 checkpoints with `p_max` under five threshold policies
gives **zero early warnings at every deployable threshold**, on both folds. Early warnings survive
only at the oracle threshold (Thursday first-onset lead 5 windows, Friday 10), which no deployment
can pick. So the statistic is *kept* - it is better behaved, it gives the score distribution headroom,
and it is what made the per-capture alert budget of D-020 workable (Thursday F1 0.576 at 2.7 % FPR) -
but the claim that it buys lead time is **withdrawn**.

**Also decided.** Thursday's four onsets are 639, 658, 708 and 729 - separated by only 10-20 windows,
with attack traffic in between. Only the **first onset of an episode chain** is a genuine
"before the attacker got in" case; the rest are re-entries. Lead time is therefore reported per
episode (never as a single mean) and the first-onset value is quoted separately.

**What is left for lead time.** E13 ruled out the statistic, E14 ruled out the threshold, E12 says
the pre-onset signal exists (within-day ROC-AUC 0.88). The remaining untested hypothesis is the
*target*: a first-occurrence hazard (`1` only at the **first** compromise window after t, `0`
afterwards), which would also make the union formula correct. That is round 3.

---

### D-020 — The deployable alarm threshold is a per-capture alert budget
*Date: 2026-09-25 · Status: accepted · Evidence: E14*

**Decision.** At inference the threshold is the 90th percentile of the model's scores **on the
capture being analysed** (`threshold_policy: "self-budget-10pct"`, stamped into the checkpoint and
reported in the API payload). Train-tuned and oracle thresholds remain in the benchmark tables for
comparison (D-015), never in the product.

**Why.** E14 measured the gap: a threshold tuned on training days sits at 0.961, the oracle for the
held-out day at 0.010, and both the train-tuned and train-quantile policies fire **zero alarms** on
that day. A budget computed on the capture's own scores uses no labels - a sensor can set it from
its live stream - and it produces the best deployable operating point we have: Thursday F1 0.576 at
2.7 % FPR, or precision 0.959 at a 5 % budget.

**Known limitation.** A budget always fires on *something*: on a capture with no attack at all it
will flag its quietest 10 % of windows as "most suspicious". The UI must therefore show the score
and the threshold, not just a binary alarm, and the Monday-benign demo sample exists to make that
failure mode visible rather than hidden.

**Revisit if.** Calibration (temperature scaling on a held-out training day) brings train and test
score distributions together - then an absolute probability threshold becomes honest again.

**AMENDMENT (2026-09-27, E18): the budget as specified is not causal.** "The quantile of the model's
scores on the capture being analysed" uses windows *after* the one being judged, so "a sensor can
set it from its live stream" was false. D-034 replaces it with the expanding budget (q90 of the
capture so far). Measured in E18: Thursday F1 0.608 at 16.8 % of windows alarmed and FPR 0.078. The
0.576 at 2.7 % FPR above is a non-causal upper bound.

---

### D-021 — How we present the system if Y-2 returns another honest negative
*Date: 2026-09-25 · Status: accepted (framing frozen before the video and slides) · Evidence: E3, E4-E7, E12, E13, E14*

**The decision in one line.** If Y-2 does not produce lead time > 0 on at least 2 of 5 episodes at a
deployable threshold, we present NetWM as **a world model that delivers the PS's required outputs -
learned transition dynamics, K-step rollouts, stage forecasts, explanations - and a measured,
localised account of the one thing it cannot yet do: warn before compromise.** We do not claim early
warning, in any form, anywhere.

**Why this is the stronger position, not the fallback.**
- It is true, and it is checkable. Every number we would quote has an experiment id, a threshold
  policy and a command in `results.md`.
- The gap is *localised*, which is rare. E12 proves the precursor signal exists (within-day ROC-AUC
  0.88 Thursday / 0.96 Friday). E13 rules out the rollout statistic. E14 rules out the threshold, at
  five policies. What is left is the supervision target, and Y-2 is the experiment that tests it.
  "We know exactly which of four candidate causes it is not, and here is the run that tests the
  fourth" is a better answer to a hard question than a confident number a judge can break in one
  follow-up.
- The negative findings are themselves contributions: the corrected-dataset requirement (D-001),
  attempted-traffic mislabelling swamping a day (D-009), one label covering two kill-chain stages
  (D-012), split leakage in the standard literature (D-006), and the ~100x threshold non-transfer
  (D-020). Any team using CIC-IDS2017 after us benefits from those.
- The PS asks for *interpretable decision support*. A system that reports the confidence it has
  earned, including where it has none, is decision support. One that reports early warning it cannot
  substantiate is the opposite.

**What we claim.**
1. A world model, not a classifier: it learns `P(S_{t+1} | S_t)` in a latent state space and rolls it
   forward K steps without observations. Evidence: open-loop rollout beats the persistence floor from
   k = 2 onward (E5), and loses at k = 1 - we say both.
2. On the held-out infiltration day, the learned dynamics give **F1 0.576 at 2.7 % false-positive
   rate** (precision 0.776; precision 0.959 at a 5 % budget) against the PS-mandated logistic
   regression's **0.011** at its own deployable threshold. Evidence: E3, E14, same features, same
   fold, both thresholds reported.
3. Forecast outputs the PS names are produced and rendered: K-step probability curves with
   Monte-Carlo bands, per-step MITRE stage distribution, per-prediction feature attribution and
   attention over the preceding windows.
4. Where it fails and why, with the experiment that tests the remaining cause.

**What we never say.** No exceptions, including in the video voice-over and in answers to judges:
- "predicts attacks before they happen", "early warning", "pre-emptive", or any lead-time number,
  unless Y-2 (or a later run) produced it at a deployable threshold, reported over multiple seeds.
- Any oracle-threshold number as a headline. Oracle numbers appear only beside their train-tuned or
  budget counterpart, labelled as an upper bound no deployment can pick (D-015).
- Any number taken from `fixtures/api/thursday_oracle.json`. It is a UI fixture with a hand-picked
  threshold and is marked `dev_only`.
- A single averaged metric across folds that hides Friday. Friday is reported as its own
  leave-one-family-out result, at chance, every time.
- Accuracy on a random split. We have never used one and will not quote one.

**How the deliverables are bound to this.**
- **Demo video:** the honest alarm panel - "0 of 4 episodes warned early" - must appear on screen at
  least once. If the oracle fixture appears at all, the on-screen label must say it is a UI fixture.
- **Slides (5 max):** one slide is *"What we measured that did not work"* - E13, E14 and the Friday
  fold, with the E12 result next to them as the reason we are still pursuing it. This is the slide
  that earns the rest.
- **Architecture document:** the limitations paragraph names the lead-time gap explicitly and cites
  E12/E13/E14 by id.
- **Any number in any deliverable** carries its experiment id and threshold policy in the speaker
  notes, so a question about provenance has a one-sentence answer.

**What flips the framing** (decided now, so it is not decided at recording time):
| Y-2 outcome | framing |
|---|---|
| lead > 0 on >= 2 of 5 episodes at a deployable threshold, stable across >= 3 seeds | claim early warning, with the lead-time distribution and the seed spread shown, never a single mean |
| lead > 0 but on 1 episode, or only at the oracle threshold, or unstable across seeds | this framing, plus "first indications of a precursor signal" phrased explicitly as a limitation |
| no lead at any deployable threshold | this framing, unchanged |

**What would make us wrong.** If anyone demonstrates positive lead time at a deployable threshold on
this data with a method simpler than ours, the framing is wrong and the honest response is to say so
and cite their result. The cheapest such candidate - logistic regression with 4 lagged windows - has
now been run: **E3b, zero early warnings at every deployable threshold**, and worse ranking than the
memoryless baseline on Thursday (PR-AUC 0.139 -> 0.114). The insurance holds; if a reviewer proposes
another simple method, run it before arguing with them.

**Freeze.** This framing is fixed from now until the submission. Changing it requires a new decision
entry with the result that justifies it - not a conversation at recording time.

---

### D-022 — Lead time is reported against a null, per episode family, or it is not reported
*Date: 2026-09-25 · Status: accepted · Evidence: E15a*

**Decision.** Every early-warning count in this repo carries, on the same line: the alarm rate and
the false-positive rate at that threshold (board card Y-5), the episode denominator it is counted
over, the per-family breakdown, and the p-value of a 2,000-shift circular-shift null computed at the
same threshold. **A count that does not exceed the null's 95th percentile is not a result.**

Three measurement changes make that possible, all in `src/netwm/models/leadtime.py`:

1. **An eligibility mask.** `metrics.lead_times` credits any alarm in `[onset - K, onset)`, including
   windows that are themselves attack windows belonging to the *previous* episode. Wednesday's
   onsets 219 and 309 have 6 of their 10 pre-onset windows inside the run before them, so a pure
   detector collects two free "early warnings". Only non-attack windows can now be credited.
2. **A confirmation that lands before the onset.** With `persistence=2` and `t = onset - 1`, the
   confirming window is the onset itself - a score that only wakes up once the attack starts was
   being credited with a one-window lead.
3. **The null.** Rolling the score circularly preserves its distribution exactly (so the alert
   budget, and therefore the alarm rate, is identical) and its autocorrelation almost exactly, while
   destroying its alignment with the onsets. Shifts smaller than K are excluded. The p-value uses
   the standard +1 correction and so can never be quoted as zero.

**Episode denominators.** Three, always reported together, never collapsed into one number:
all attack episodes (26 across the week), Impact excluded (19), and the five compromise onsets
(D-011). Plus warned/total per attack family, because 7 of the 26 attack onsets are Impact and 6 of
those are Wednesday DoS - a DDoS ramp is visible minutes ahead in flow rate, so an aggregate carried
by Impact would look like success and mean nothing for PS 26153.

**Why now.** E15a ran the null against the **published** E14 score arrays - not a re-run, so no
Monte-Carlo noise sits between the null and the number in `results.md`:

| number as published | null mean | null p95 | p |
|---|---:|---:|---:|
| E14 Thursday, oracle, 1 of 4 compromise episodes | 0.78 | 3 | **0.412** |
| E14 Friday, oracle, 1 of 1 compromise episodes | 0.55 | 1 | **0.550** |
| E14 Thursday, self-budget 10 %, 0 of 4 | 0.53 | 2 | 1.000 |

Neither surviving early warning in E14 is distinguishable from an unaligned score of the same shape.
Friday's is worse than that: it needs an alarm rate of 47 % (FPR 0.469) to happen at all, which is
the E3b pathology reproduced on our own model rather than on the baseline.

**What this costs us.** The two early warnings E14 reports at the oracle threshold can no longer be
described as evidence of anything, and `fixtures/api/thursday_oracle.json` remains what T-07 already
called it: a UI development fixture whose number never reaches a slide.

**Consequence for the Y-2 bar.** On the compromise denominator the null p95 is 2 of 4 on Thursday
and **1 of 1 on Friday** - so on Friday no possible result can exceed it, and the board's
"lead > 0 on >= 2 of 5 episodes" can be met by chance. The bar is restated in D-021's amendment;
this entry only records that the old one is not measurable.

**Known limitation.** The null tests alignment, not calibration: a score that is genuinely
predictive but fires constantly will still fail it, and correctly so, because the alert budget is
what a SOC actually pays. It says nothing about whether the *ranking* is good - PR-AUC and precision
at the budget remain the ranking evidence.

**Revisit if.** A denominator larger than 26 episodes becomes available (more capture days, or
per-host episodes from S-2), at which point the null's resolution improves and the p95 bar tightens.

---

### D-023 — Round 3 supervises when an episode *begins*, keyed on attack episodes
*Date: 2026-09-25 · Status: accepted (recorded before the run, per the board's constraint) · Evidence: E12, E14, E15a; to be tested by E15*

**Decision.** The risk head widens from 3 channels to 5. The two new channels are:

| idx | channel | target | read from |
|---|---|---|---|
| 3 | `onset_now` | this window is the **first** window of an attack episode | imagined states - unioned over the rollout |
| 4 | `precursor` | an onset falls within the next K windows **and** this window is not itself an attack window | the **filtered** posterior only |

They are two different claims and are never merged into one number:

- `onset_now` is a first-occurrence indicator, so `1 - prod(1 - p_k)` over a rollout is a genuine
  `P(an attack episode begins within k)`. **This is the forecasting claim**, and it is the
  hypothesis D-019 left open: *"a first-occurrence hazard ... would also make the union formula
  correct. That is round 3."*
- `precursor` is already a statement about the next K windows, so unioning it over a rollout would
  ask about a horizon of up to 2K. It is read off the filtered state, which means it is a
  **representation** result - `sigmoid(head(RSSM_posterior(S_{t-15..t})))` is a sequence classifier,
  not a rollout. `CLAUDE.md` reserves *rollout* for K-step open-loop imagination, and this is not
  one. It will be reported as "filtered" and never described as forecasting.

**Episodes are keyed on attack, not compromise - and this is a deviation from D-019.** D-019 says
"the first *compromise* window after t". Measured on the frozen dataset:

| keying | onsets per training fold | precursor windows per fold | families |
|---|---:|---:|---|
| compromise (D-019, D-011) | 1 (Thursday fold) | 10 | 1 |
| attack episodes | 18 | 165 | 3 |

Compromise-keyed gives the Thursday fold ten positive windows drawn from a single attack family.
That is exactly the condition D-016 was written to escape - round 1 gave the compromise head one
positive family per fold, it memorised that family, and it scored ROC-AUC 0.245 on the other. There
is no reason to expect a different outcome from a target that is fifteen times sparser. Keying on
any non-benign episode puts positives on four of five days and three attack families in every fold.

**What that costs, and how it is paid.** Training on attack onsets while the product's question is
about compromise is a real gap, so lead time is **evaluated** on three denominators, always
reported together and never collapsed (D-022): all 26 attack episodes, Impact excluded (19), and
the 5 compromise onsets - which are also, by construction, the hard set (4 infiltration + 1 botnet
C2). Per-family counts sit beside them, because 7 of the 26 attack onsets are Impact and 6 of those
are Wednesday DoS: a DDoS ramp is visible minutes ahead in flow rate, so an aggregate carried by
Impact would look like success and mean nothing for PS 26153.

**Pre-registered bar** (fixed before the run; a bar moved after seeing the number is worth nothing):

1. **Significance.** Warned-early must exceed the 95th percentile of a 2,000-shift circular null at
   the same threshold on **>= 2 of the 4 attack folds**, Fisher-combined p < 0.05, **and hold with
   Impact excluded**. An Impact-only result does not pass.
2. **Stability.** Over **>= 3 training seeds** (42/43/44), per-seed counts reported, never only a
   mean. Seed variance here is *training* seed: `onset_now` fires on ~18 windows in a four-day fold
   at a pos_weight of ~199, which is exactly the regime where one seed lands and the next does not.
   Monte-Carlo spread is a separate and weaker number, reported as such.
3. **Floors, on the same table.** The run's **own** channel-0 `p_max` (comparing against the r2
   checkpoint would confound "new target" with "new run"); the single unscaled features
   `uniq_dst_port` / `uniq_dst_ip` / `fanout_mean`, two of which already beat r2 at early warning on
   Friday (E15a); and logistic regression leave-one-day-out on the same precursor label.

This bar supersedes "lead > 0 on >= 2 of 5 episodes" from the Y-2 card, which E15a showed is not
measurable - on Friday's one-episode compromise fold the null's p95 is 1 of 1, so no observed count
can ever exceed it. **Pending ratification in D-021's amendment**; if that amendment sets a
different bar, it governs and this clause is superseded by it.

**Known circularity, stated before the result exists.** `metrics.lead_times` credits alarms in
`[onset - K, onset)`; the `precursor` label is 1 on exactly that set. "Warned early" for channel 4
is therefore per-episode recall with a run-length-2 filter - a legitimate operational readout, not
independent confirmation. Channel 4's headline is leave-one-day-out PR-AUC and precision at the
budget against the floors above. Channel 3's union does not have this problem.

**E12 is not evidence that this label is learnable.** E12's ROC-AUC 0.88-0.96 is a within-day probe
with a within-day scaler, on the *compromise*-keyed window set, at n = 10 on Friday. This target is
attack-keyed and evaluated leave-one-day-out. E12 establishes that a signal exists in the state; it
does not establish that a model trained on other days finds it. That sentence stays out of the deck.

**Implementation notes that are part of the decision.**
- The `WorldModelConfig.n_risk` default stays 3, so every round-2 checkpoint loads unchanged and the
  E14 reproduction path is untouched. Only `configs/model_r3_precursor.yaml` widens the head.
- The risk BCE is split into `compromise` (channels 0-2) and `precursor` (channels 3-4) with
  separate weights. BCE is mean-reduced over every element, so slicing the first three channels
  leaves that term numerically identical to round 2; one term spanning five channels would have
  rescaled the compromise gradient by 3/5 and confounded every comparison with E14.
- `class_weights` caps inverse-frequency weights at 50x. `onset_now` wants ~199, so its cap is
  raised to 250; capping it would flatten the channel carrying the forecasting claim.
- **Corrected latent bug.** `p_cum_attack` and `p_cum_escalate` were computed from Monte-Carlo
  sample 0 while `p_cum` beside them was a 16-sample mean. Unions are now taken per sample and then
  averaged, since `1 - prod(1 - E[p])` is not `E[1 - prod(1 - p)]`. This changes those two curves'
  values (not their shapes) in payloads and in the E6/E13 escalation rows; `p_cum`, `p_max` and the
  alarm path are untouched, so E14 and the demo are unaffected. Fixtures need regenerating.
- A `sample=False` mean path was added to `forecast()`, taking the mean of the posterior, the prior
  and the rollout, so a lead-time count can be produced with no Monte-Carlo variance at all.
  `sigmoid(head(E[z]))` is not `E[sigmoid(head(z))]`, so it under-states saturating probabilities;
  the threshold is a quantile of the same series, so ranking carries over. Reported with Spearman
  rho against the 16-sample score.

**Revisit if.** E15 returns a null result *and* the per-family breakdown shows the head is learning
Impact onsets only - that would say the target is right but the episode definition is too broad, and
the next cut is per-family heads rather than one pooled channel.

---

### D-021 — AMENDMENT (2026-09-25, after E15a and E15)

*Status: the framing in D-021 is now **operative**, not contingent. Its acceptance bar is replaced.*

**1. The original bar was below chance, so it is withdrawn.** D-021 said an early-warning claim
unlocks at "≥2 of 5 episodes at a deployable threshold over ≥3 seeds". E15a shows an *unaligned*
score of the same shape warns early on ~1.7 of 8 episodes by accident at a 10 % alarm budget. A bar
that noise clears is not a bar. Worse, it retro-scores our own published numbers: E14's Thursday
"1 of 4 at an oracle threshold" is **p = 0.412** against the null, and Friday's "1 of 1" is
**p = 0.550** and needs a 47 % alarm rate to happen at all.

**2. The replacement bar** is the one pre-registered in D-023, adopted here as the standing gate for
any early-warning claim in any artefact: warned-early counts must exceed the 95th percentile of a
2 000-shift circular null at the same threshold on **≥2 of 4 attack days**, with Fisher-combined
**p < 0.05**, holding with **Impact excluded**, and reproducing over **≥3 training seeds** - each
count quoted with its alarm rate, FPR and precision on the same line (D-022).

**3. Which branch of the framing applies: the no-early-warning one.** E15 failed every clause
(best 1 of 4 folds, one seed; Fisher p = 0.166; 0 of 4 with Impact excluded; nothing stable across
seeds; 21 of 1 080 cells below p = 0.05 where chance gives ~54). Four candidate causes have now been
eliminated with an experiment each - statistic (E13), threshold (E14), data (E12), target (E15). We
present the system exactly as D-021 describes and **make no early-warning claim of any kind**.

**4. Two claims this adds, both of which are ours to make.**
- We calibrated lead time against a null and **withdrew our own number** when it failed (E14's
  1 of 4 → p = 0.412). Most submissions will not have tested their headline metric against chance.
- The elimination chain is the contribution: four causes ruled out, each with a pre-registered bar,
  and the fifth - representation - named with the evidence that points at it.

**5. Two claims this forbids.**
- Nothing from round 3 ships. It is a **regression**: Thursday PR-AUC 0.353-0.445 against round 2's
  0.640, on the same data, verified not to be a mean-path artefact (Spearman 0.995 between
  deterministic and 16-sample scores; the r2 checkpoint re-scores to 0.6436, reproducing E14).
  `configs/model_r3_precursor.yaml` must not produce submission checkpoints, and the r3 weights are
  gitignored so no `git add -A` sweeps them in.
- **The submission checkpoint is `models/e4e7-worldmodel-r2/`.** Every number in the architecture
  document, the slides and the video comes from it.

**6. What would reopen the early-warning claim.** The remaining hypothesis is **representation, not
supervision**. On the precursor label, leave-one-day-out, a single *unscaled* feature
(`uniq_dst_port`, Thursday ROC-AUC 0.607; Tuesday 0.745) and plain logistic regression (0.604) both
beat every statistic the world model produces (best 0.533). A model that loses to one raw column is
not failing to learn the target - it is losing the signal before the target is reached, and the
prime suspect is the train-day-fitted scaler under the distribution shift E2 already measured
(Thursday persistence NLL mean 152 010, median 0.85). Per-capture rank/percentile normalisation -
the same logic as the alert budget in D-020, applied to features instead of scores - is the next
experiment. It reopens the claim only under the bar in point 2.


---

### D-024 — The demo endpoint runs the model; `/api/model` metrics are read from `results/runs/`
*Date: 2026-09-26 · Status: accepted · Evidence: R-5/R-6/R-7 review, E14, E3*

**Decision.** (1) `POST /api/analyze/demo/{id}` always runs real inference on
`data/demo/<file>.csv` with the day's checkpoint and returns `mock: false`. If the slice or the
checkpoint is missing it fails at request time with `503 no_model` and names the regeneration
command - it never substitutes a fixture. The fixture fallback remains only for uploads with no
checkpoint, where the payload says `mock: true`. (2) The model card's `metrics` are loaded from
`results/runs/e14-pmax-rescore-e4e7-worldmodel-r2` (Thursday, `p_max`, self-budget-10pct: F1 0.576,
FPR 0.027, PR-AUC 0.640) and `results/runs/e2e3-baselines-lags0` (E3 logistic regression,
forecast, train-tuned: F1 0.011), not typed into code.

**Why.** The fixture fallback served the 972-window full-day Thursday payload under the metadata of
a 130-minute, 169 135-flow slice - a demo whose data and description disagree is the first thing a
judge probes, and the PS asks for an interface that runs inference on an accepted file. Metrics read
from the run folders cannot drift from results.md. PR-AUC is 0.640, not the 0.675 of the
e4e7-worldmodel-r2 training run: that figure scores `p_cum` (superseded for this purpose by D-019 /
E14), and the card must quote every number for the same statistic as its F1.

**Revisit if.** A-4 shrinks the demo slices (the run folders stay the source), or a later run
supersedes E14 as the deployable operating point - then change `_E14_RUN` in `backend/inference.py`
in the same commit as the results.md entry.
### D-028 — Trend feature window sizes for Task S-1 (superseded by D-026)

*Date: 2026-09-25 · Status: superseded by D-026 · Evidence: Task S-1 requirements*

The model's original `S_t` state vector contained only absolute level values. As outlined in Task S-1, we augment this with trend (derivative) features specifically for the highest-ranking metrics from E12 (`uniq_dst_port`, `ports_per_pair_max`, `port_fanout_max`, `uniq_dst_ip`, `fanout_mean`, `flows_per_s`).

The selected mathematical operations are:
- **Immediate Delta**: Captures sharp, one-window spikes.
- **Rolling Slopes (2, 5, and 10 windows)**: We use multiple time horizons because attackers operate at different cadences. 2 windows capture immediate escalation, 5 windows capture short-term progression, and 10 windows capture slower, sustained reconnaissance that avoids tripping strict rate-limits.
- **Rolling Z-Score (120-window baseline)**: Because raw values fluctuate by time of day, we compare current values against a rolling 2-hour (120-window) baseline to identify statistical anomalies rather than absolute threshold breaches.

---

### D-025 — Rank normalisation is a scaler option; the causal variant carries any lead-time claim
*Date: 2026-09-26 · Status: accepted (recorded before the r4 run, per the board's constraint) · Evidence: E2, E15, D-021 amendment point 6*

**Decision.** `StateScaler` gains `mode="rank"` (task S-4). Each column is replaced by its Gaussian
rank *within the capture being transformed*: average rank `r` among `n` windows, `p = (r - 0.5) / n`,
value `= Phi^-1(p)`. Nothing is learned from the training days - `fit` only records the column order.
Two variants, one config key:

- `rank_window: null` - rank against the whole capture (the D-020 alert-budget analogue).
- `rank_window: W` - **causal**: rank against the trailing `W` windows only, the first
  `rank_min_periods` windows of a capture sit at 0.

D-014 stays the default (`mode: log_standard`); a model config with no `scaler:` block reproduces
round 2 exactly, and so does every existing checkpoint (the new fields have class-level defaults, so
an old pickle reads them). `configs/model_r4_rank.yaml` selects `mode: rank, rank_window: 120`
(60 min at a 30 s stride) on the r2 heads - the feature transform is r4's only variable.

**Why.**
- *Per capture, because the scaler is the prime suspect.* D-014 fits mean/std on the training days;
  E2 measured what that does to Thursday (persistence NLL mean 152 010, median 0.85), and E15 found
  one unscaled column beating every world-model statistic on the precursor label. A per-capture rank
  is invariant to any monotone drift of a column between days, so that failure cannot recur.
- *Gaussian, not a uniform percentile.* Integrated Gradients uses the all-zero state as its baseline
  (`engine/explain.py`), which under D-014 means "the average window". A Gaussian rank keeps zero at
  the capture's median window; a [0, 1] percentile would silently move it to the *minimum* window and
  change the meaning of every attribution in the UI.
- *Causal for claims.* Whole-capture ranking lets the windows after an onset set the scale of the
  windows before it - a pre-onset window's value depends on the attack that follows. That is harmless
  for detection and fatal for a lead-time claim. Any early-warning count from r4 is therefore made
  with `rank_window` set; the whole-capture variant may be reported, labelled as an upper bound.

**Also decided.** A caller that transforms several days in one frame must pass
`groups=frame["split"]`, or the days are ranked against each other. The trainer (`prepare_days`) and
the inference engine already transform one capture at a time; the leave-one-day-out logistic floor
in `scripts/precursor_eval.py` concatenates days and needs `groups` for a like-for-like E16 row.
`inverse_transform` raises in rank mode - a rank has no fitted scale to undo, and nothing calls it.

**Known limitation.** Rank throws away magnitude by design: a DDoS window and an ordinary busy window
can both sit at the top of their capture. The levels are not lost to the product - flagged flows
and top talkers in the payload are computed from raw flows - but the model can no longer tell
"busiest window today" from "busiest window ever". The causal variant also has a warm-up: the first
`rank_min_periods` windows of every capture carry no information.

**Revisit if.** r4 (Y-6/E16) shows the causal variant losing clearly to the whole-capture one - then
the trailing window length, not the idea, is the next variable; or rank features fail the D-023 bar
as badly as D-014 features did, which would take the representation hypothesis off the table and
leave per-host state (S-2) as the remaining direction.

**Refs.** `research/state-normalisation.md`.

---

### D-026 — S_t v2 trend block, revised: frozen v1, least-squares slopes, a causal z-score
*Date: 2026-09-26 · Status: accepted (supersedes D-028; recorded before any v2 build or run) · Evidence: E12, board sequencing rule 1*

**Decision.** The trend block (task S-1) is kept for the same six E12 features (`uniq_dst_port`,
`ports_per_pair_max`, `port_fanout_max`, `uniq_dst_ip`, `fanout_mean`, `flows_per_s`), with four
columns each - **94 features** in S_t v2 (70 + 24):

- `{f}_delta` - `x_t - x_{t-1}`.
- `{f}_slope_5`, `{f}_slope_10` - the **least-squares slope** over the trailing 5 / 10 windows
  (0 until a full span exists). D-028's `slope_2` is dropped: a least-squares slope over two points
  *is* the delta, so it would be a duplicate column.
- `{f}_zscore` - against the **previous** 120 windows (60 min at the 30 s stride; not 2 h as D-028
  stated), trusted after 10 windows of history (0 before), standard deviation floored and the
  result clipped to +-10.

v1 stays frozen: `configs/cicids2017.yaml` sets `use_trend_features: false` (it had been switched on
by default), and v2 builds from `configs/features_trend.yaml` into its own `processed_dir`
(`data/processed/cicids2017_trend`). The trend parameters are constants in
`src/netwm/features/flow_features.py`, not config values.

**Why.**
- *Frozen v1.* Board sequencing rule 1: Y-2's numbers and every round-2 number were built on the 70
  v1 columns, and v2 is evaluated as an ablation (Y-4), one variable at a time. With the flag on by
  default, the next `build_features.py` run would have overwritten the v1 parquet silently. Verified:
  with the flag off, the current code reproduces the pre-S-1 implementation (f7a0029) byte for byte.
- *Least squares.* A two-point `(x_t - x_{t-w}) / w` is decided by its endpoints alone - one noisy
  window swings it. The fitted slope uses every point in the span; on white noise its spread is
  0.78x the two-point version (pinned in `tests/test_flow_features.py`).
- *Causal, excluded, clipped z-score.* A baseline that includes the current window lets a spike
  dilute its own anomaly. `min_periods=1` gave windows 0-1 of every capture z-scores from one or two
  points. A flat baseline with a 1e-6 floor mints values in the 1e6 range, which is the E2 failure
  mode (Thursday persistence NLL mean 152 010) reintroduced by hand. The baseline is "the last hour",
  not "the last benign hour": a sensor has no labels.
- *Constants, not config.* Checkpoints store `feature_names`, not the data config, and inference
  (`engine/predict.py`) rebuilds the state from those names via `feature_flags_from_names`. A
  config-level window length could differ between the build that trained a model and the engine that
  serves it, and nothing would notice. A name set that matches only part of the trend block (e.g. a
  D-028-era `slope_2`) now fails loudly instead.

**Also decided.** `engine/predict.py` passes the recovered flags to `window_features`, so a v2
checkpoint no longer crashes at inference (it would have raised on missing columns); r2 checkpoints
resolve to the v1 call. `build_features.py` records per-split `build_s`, the seed and the feature
flags in `meta.json`, so results.md F2's build time comes from an artefact.

**Known limitation.** The z-score's baseline absorbs a sustained attack after about an hour, and the
first 10 windows of every capture carry no trend information. Under the D-025 rank scaler the
z-score is partly redundant with the causal rank of the level itself; Y-4 decides whether it earns
its columns.

**Revisit if.** The Y-4 ablation shows no gain from the trend block on the precursor label under the
D-023 bar, or shows one column family (slopes vs z-score) carrying all of it - then drop the rest
rather than keep 24 columns for the sake of it.

---

### D-027 — Per-host channel: the busiest internal hosts as fixed slots in S_t
*Date: 2026-09-26 · Status: accepted (schema only; recorded before any build or run) · Evidence: E12, E15 "remaining untested directions"*

**Decision.** Task S-2 adds an optional per-host sub-vector to `S_t`, `window.host_slots: N`
(0 = off, the v1 default; `configs/features_hosts.yaml` sets 3 and builds into
`data/processed/cicids2017_hosts`, trend features off). In each window the internal source hosts
(`internal_prefixes`) are ranked by flow count, ties by IP, and the top N fill slots `host1..hostN`:

| column | definition | what it exposes |
|---|---|---|
| `host{i}_fanout` | distinct destination IPs of the host in the window | a sweep across hosts - discovery, lateral movement |
| `host{i}_ports` | distinct destination ports | a port scan from one host |
| `host{i}_byte_asym` | `(sent - received) / (sent + received + 1)` over the flows it initiated | pushing data out (exfiltration, staging) vs pulling it in (payload download) |
| `host{i}_new_peer_rate` | share of its destinations it had not contacted earlier **in this capture** | a host suddenly talking to machines it never talked to |

`N = 3` gives 12 columns (82 features with v1). An empty slot is all zeros; a real host always has
`fanout >= 1`, so the two cannot be confused. Inference recovers `host_slots` from the checkpoint's
feature names (D-026's `feature_flags_from_names`), and a partial host schema fails loudly.

**Why.**
- *Per host at all.* Every v1 feature is network-wide: one compromised host sweeping the subnet is
  averaged in with every benign host, and only its max survives (`fanout_max`, `port_fanout_max`).
  E15 names "network-wide aggregates hide per-host behaviour" as one of the two untested state
  directions. A slot keeps one host's behaviour intact across four views.
- *Internal sources only.* Lateral movement and C2 originate inside the monitored network - the
  Thursday infiltration's internal sweep, the Friday bots' beacons. Inbound floods from outside are
  already dominant in the aggregates, and a busy external scanner would otherwise take every slot.
- *Ranked by flows.* It is the ranking the UI's top-talkers panel already uses (`engine/predict.py`
  `_top_talkers`), so the slot a defender sees explained is the slot the model read.
- *New-peer rate, causal and label-free.* "First contact in this capture" depends only on windows
  up to `w`, so it is legal for a lead-time claim and computable on a live stream.

**Known limitation.** *Slot permutation*: slot 1 is whichever host is busiest in *this* window, so
it can be a different machine one window later. The dynamics model sees a jump that is a change of
host, not of behaviour. *Warm-up*: at the start of a capture every peer is new, so
`new_peer_rate` reads 1.0 for everyone until the capture has some history. Demo slices start well
before their attack, which keeps both out of the story being shown.

**Revisit if.** Y-4 shows the host columns adding nothing, or shows slot churn dominating their
signal. The next cut is then *sticky* slots, where a host keeps its slot while it stays in the top
N. If the channel does help, per-host episodes are the natural way to enlarge the 26-episode
denominator D-022 is limited by.


---

### D-029 — Rank normalisation is not adopted; the forecasting gap is cross-day transfer
*Date: 2026-09-26 · Status: accepted · Evidence: E16, E16D, and the floor measurements in this entry*

**Decision.** `mode="rank"` stays in `StateScaler` as an option and keeps its tests, but **no shipped
configuration uses it**. D-014 (`log_standard`) remains the default and the submission scaler.
`configs/model_r4_rank.yaml` and `configs/model_r4_rank_wholecapture.yaml` are kept as the
reproduction path for E16, not as candidates.

**Why.** E16 ran the transform D-025 nominated, on the round-2 heads, 3 training seeds x 5 folds,
against the bar pre-registered in D-023. It failed every clause (0 of 4 folds exceeding the null's
p95, best Fisher p 0.715), it ranks the precursor label at chance on the two folds that matter
(Thursday 0.490, Wednesday 0.495), and it loses to a single unscaled column on all four folds.

**The disqualifying finding is variance, not the mean.** On Thursday detection, r4 matches round 2 on
two seeds (F1 0.591 and 0.553 against 0.576) and collapses on the third (F1 0.023, PR-AUC 0.221).
Round 3 was a uniform regression and could have been traded off; a one-in-three catastrophic training
seed cannot be, for a system that has to be demonstrated live. This is the clause of the D-021
amendment that required *training*-seed stability rather than Monte-Carlo spread, and it is the clause
that caught this - a single-seed run would have reported r4 as matching round 2, or as broken, and
either would have been a third of the truth.

**What the whole-capture variant changes: nothing, and that is worth recording.** It reached
Thursday p = 0.054, the best early-warning p-value this project has produced, and D-025 had already
ruled it inadmissible before it ran because its scale is set partly by windows *after* the onset. It
is reported as E16D under its own experiment id so it cannot be read as a row of the registered
comparison. Also: whole-capture rank is *univariately identical* to `log_standard` by construction,
since a monotone map cannot reorder a single column - any effect it has is multivariate only.

**Where the signal dies.** On Thursday, logistic regression over all 70 features scores 0.604 on the
precursor label while `uniq_dst_port` alone scores 0.607. A 70-input model gains nothing from 69
extra features when trained on other days' attack families and scored on web attacks and
infiltration; under rank the same comparison is 0.497 against 0.573, i.e. actively worse. **The
weights do not transfer across attack families.** That, not the feature transform, is the live
hypothesis for the forecasting gap, and it reframes D-021's "representation" branch.

**Measurement convention, fixed here to stop two incomparable numbers circulating.** A univariate or
LR score on the precursor label is reported with **all non-precursor windows as negatives**.
Restricting negatives to non-attack windows raises the same figures materially (`uniq_dst_port`
0.607 -> 0.678, `uniq_dst_ip` 0.578 -> 0.633, `fanout_mean` 0.585 -> 0.629) and E12's quiet-background
convention raises it further (0.739). All three are defensible; mixing them in one comparison is not,
and the first is the one that matches the LR floors in E15/E16.

**Candidates closed, so they are not re-proposed.**

| candidate | status |
|---|---|
| causal rank, window 120 | run - fails the bar, seed-unstable (E16) |
| whole-capture rank | inadmissible for a lead-time claim (D-025); univariately identical to level |
| level + rank concatenated | not supported - Thursday LR 0.560 vs 0.604; with ~8 effective episodes a 0.04 gap is noise |
| rank on the v2 trend features | out - `uniq_dst_port` slope_5 / slope_10 / delta score 0.487 / 0.480 / 0.475 univariately before any rank; no rise exists for a slope to re-express |
| reference CDF fitted on training days | out by construction - monotone, so it preserves within-day ordering and cannot beat `log_standard` on a day-level shift |

**Also closed, on the raw capture.** The pre-onset-602 elevation is not `- Attempted` traffic that
D-009 removes from the stage label: all 4356 flows in windows 592-601 are `BENIGN` with
`Attempted Category = -1`, and Thursday's 1997 attempted flows all carry `- Attempted` in the label
and fall elsewhere. The rise is real and its traffic is benign-labelled, so D-009's revisit clause is
not triggered and that question should not be reopened.

*Amended the same day, on S-8.* Calling 602 a "clean precursor" was wrong and is withdrawn. S-8
audited who carries the rise: `192.168.10.9` opening more ports on `.3`, with the hosts the attack
touches flat - the scan target `.51` at +0.1, the host compromised at 17:19 at -0.4, and the scanner
`172.16.0.1` absent entirely. The run-up has a precursor's *shape* without its *content*. This does
not change the decision below, and it strengthens it: the one case that looked like a real
early-warning opportunity was not one, and the circular-shift null of D-022 is what stops a model
being credited for finding it.

**Revisit if.** A leave-one-attack-family-out run with actual retraining (Y-3, not E8's re-analysis)
shows the weights *do* transfer when families are held out deliberately - that would move the
diagnosis back towards the features. Or if a capture set with more than one compromise family per
fold becomes available, since every number here rests on 26 attack episodes and 5 compromise onsets
in a single synthetic week.

---

### D-030 — Pre-registration for Y-4 Ablation (E10)
*Date: 2026-09-26 · Status: accepted · renumbered from a second D-029 at merge*

**Decision.** The ablation study (E10) tests two components against the r2 baseline (`configs/cicids2017.yaml`, `--epochs 25 --samples 16`): the stochastic latent space (`model_no_stochastic.yaml`) and the multi-step rollout loss (`model_no_multistep.yaml`).

**What "earns its place" means (Pre-registered Bar).** 
*Amended 2026-09-26 before any E10 numbers were seen: r2's Friday `p_max` F1 at the 10% budget is 0.000 (E14), and nothing can be worse than zero, so "worse on both folds" marks every component unsupported by construction.*

For each ablation (`model_no_stochastic.yaml` and `model_no_multistep.yaml`), its removal must worsen the model's performance on **both** of these metrics:
1. **Rollout**: The mean over `k = 2..K` of `(world_model_mse - persistence_mse)` must be worse (higher) in the ablated model than the full model, on both folds (Thursday and Friday), on ≥2 of 3 seeds. Read from `results/runs/<run>/metrics.json` → `per_day[<fold>].rollout`.
2. **Detection**: E14 `p_max` F1 at the 10 % alert budget (`self-budget-10pct`, from `scripts/rescore_pmax.py --run <run>`, without `--write-thresholds`) must be worse in the ablated model than the full model on **Thursday only**, on ≥2 of 3 seeds. PR-AUC on both folds is reported beside it and does not gate.

If the full model is worse than (or equivalent to) the ablated model on these metrics, we conclude that the component does not justify its added complexity, and it will be marked as unsupported in `docs/architecture.md`. "Equivalent" is defined as a difference of < 0.01 in the metric.

*Clarified 2026-09-26 by Atharv, still before any E10 number was read (the sweep outputs were
unpushed and unopened until this commit). Two points, with Yash's choices otherwise unchanged:*
- *Rollout: E5 records rollout **MSE** against persistence per k (`world_model_mse`,
  `persistence_mse`); it never recorded NLL, so the NLL form could not be scored from the runs.*
- *Detection: the parenthetical "or PR-AUC on both folds" offered two alternative gates, which would
  let the scorer pick one after seeing the numbers. Thursday `p_max` F1 is the gate; PR-AUC is
  reported only.*

**Why.** The stochastic latent has no test of its own. Without a strict seed rule and margin, variance can mask failures (E16 showed one seed in three can collapse). We must test whether each component actually earns its place before we claim it does.

---

### D-031 — PCAP demo source: Scapy synthesis
*Date: 2026-09-26 · Status: accepted; the capture described here is superseded by D-033 (synthesised from the real Thursday flows); withdrawn pending A-5b · renumbered from a third D-029 at merge*

**Decision.** The small PCAP demo (A-5) is synthesized using Scapy rather than extracted from a real
capture.

**Why.** The demo needs to be under 5 MB with one clean, easily explainable story (e.g., a sequential
port scan) that the model can confidently flag. Extracting and anonymizing a clean 5 MB slice from
the 30+ GB CIC-IDS2017 PCAPs while maintaining flow continuity and avoiding unrelated background
noise is complex. Synthesizing it with Scapy guarantees the exact packets, timestamps, and sizes we
need for a crisp demonstration of the `pcap_to_flows` pipeline and the dashboard UI, without
accidental background traffic muddying the narrative.

**Measured at merge (orchestrator).** The generated capture is 6.7 KB and 120 packets spanning 70 s,
which is 3 windows. The index claimed 4.5 MB and 10 minutes. On `e4e7-worldmodel-r2/thursday.pt`, the
single alarm falls on the *benign* window. The scan windows are labelled Impact (stage 6). Surprise
does react to the scan (33 against 0). The addresses (192.168.1.x, 10.0.0.5) sit outside the
training network's `internal_prefixes`. The synthesis choice stands; the capture must be long enough
for the model's context and must use the training network's address plan. Note that the project
downloads CSVs only; no CIC-IDS2017 PCAP is on disk (`scripts/get_data.py`).

---

### D-032 — The headline F1 is the submission checkpoint's, and it travels with its seed range
*Date: 2026-09-26 · Status: accepted · Evidence: E10, E14, D-024 · Board: T-19*

**Decision.** Every artefact quotes Thursday detection as **F1 0.576 for the submission checkpoint
(`e4e7-worldmodel-r2`, seed 42), 0.43-0.57 over three training seeds**. The range always appears next
to the number: slides, demo script, architecture doc, README and anywhere the model card is shown.
Where only one number fits, say "0.576 on the checkpoint we ship". Never write "the model scores
0.576" unqualified. The same applies to PR-AUC: 0.640 for the checkpoint, 0.37-0.64 over seeds.

**Why.** E10 retrained the full model on seeds 42, 43 and 44. Thursday F1 was 0.568 / 0.432 / 0.470,
and seed 42 reproduces the checkpoint (r2: 0.576). So the headline sits at the top of a 0.14 spread
whose mean is about 0.49. Quoting the mean instead would describe models we don't ship. Quoting the
checkpoint alone would present the luckiest seed as the method's result. The checkpoint number is
the true figure for what is demonstrated; the range is what the method delivers. A judge who asks
"is that one seed?" should find the answer already on the slide. This is the same discipline E16
applied to r4, where one seed in three collapsed.

**What does not change.** The comparison with logistic regression (0.011) holds at every seed: the
worst seed, 0.43, is still about 40x the baseline. Friday detection is 0.000 on every seed and is
reported as such (E14, E10).

**Revisit if.** A later run replaces the submission checkpoint. Then quote that checkpoint, with its
own seed range, in the same commit that changes `_E14_RUN` (D-024).

**AMENDMENT (2026-09-27, D-034 / E18).** The 0.576 above used the non-causal whole-day threshold.
The quoted deployable number is now **F1 0.608 for the submission checkpoint, 0.52-0.61 over three
seeds, at 16.8 % of windows alarmed (precision 0.614, FPR 0.078)**, with the causal expanding budget.
0.576 may appear only labelled as a non-causal upper bound.

---

### D-033 — PCAP flows follow the corrected extraction's semantics, measured from its CSVs
*Date: 2026-09-27 · Status: accepted · Evidence: A-3c, `tests/test_pcap_ingest.py` · Supersedes the demo capture in D-031*

**Decision.** `flow_aggregator.pcap_to_flows` reproduces the flows of the corrected CIC-IDS2017 release
(D-001), because the model was trained on them.
- A flow is a bidirectional 5-tuple; forward is the direction of its first packet.
- A flow lasts at most **120 s from its first packet**.
- **RST ends a flow.** A TCP teardown stays in its flow; only a new SYN after both FINs starts another.
- Lengths are payload bytes, and IAT spans both directions.
- `*_init_win` is the window of the first packet in each direction, 0 when unobserved.
- `fwd_seg_size_min` is the smallest forward transport header.
- Active and idle periods use a 5 s threshold.

**Why.** Each rule was read off the CSVs rather than assumed:
- **The timeout runs from the start.** On Thursday 16:50-17:25, repeated 5-tuples restart no sooner
  than 120.7 s after the previous flow's *start*, while about 850 restart less than 120 s after its
  *end*. An idle-based timeout merged those, leaving 849 flows missing; the start-based rule leaves 8
  of 22,486.
- **The encodings.** Unobserved windows are 0 in the CSVs (UDP, one-way TCP). TCP flows without a SYN
  still carry a forward window. Segment-size values are 8 for UDP and 20/24/32 for TCP, which are
  header sizes.
- **The teardown.** Ending a flow at the first FIN, as stock CICFlowMeter does, is the defect the
  corrected release fixed. It turns every close into an extra one- or two-packet flow.

**The demo capture (replaces D-031's).** `scripts/make_demo_pcap.py` synthesises packets from the real
Thursday flow rows (`netwm.features.pcap_synth`) for 16:50-17:25. Every flow is kept and attack flows
keep every packet. Benign flows are trimmed to their handshake and teardown (4 packets), and payloads
to 8 bytes, which comes to 4.56 MB. It reads back as 22,478 flows against 22,486 source TCP/UDP rows,
with all 972 flows from the 17:00 scanner. On `thursday.pt` it runs end to end in 7.5 s, and one
alarm lands on the 17:00:30 scan window. **But the trimming makes traffic look unlike the training
days:** median surprise is 4.6, against 0.15 on the untrimmed CSV slice. So the PCAP demo shows the
ingestion path and nothing about model quality, and its catalogue entry says so.

**Revisit if.** Real packet captures of the training days become available. Then the packet-level
features can become model inputs (G-5), and this parity check becomes a real-capture test.

---

### D-034 — Pre-registration: a causal alert budget replaces the whole-capture one (G-8, E18)
*Date: 2026-09-27 · Status: accepted, written and pushed before any causal threshold was computed · Board: G-8*

**The problem.** D-020's deployable threshold, `self-budget-10pct`, is the 90th percentile of the
scores of the *whole* capture (`scripts/rescore_pmax.py`, and `engine/predict.py` for the
dashboard). A window's alarm therefore depends on scores that come after it. D-020's claim that "a
sensor can set it from its live stream" is false for a live stream. It is D-025's objection to
whole-capture ranking, applied to thresholds. E14's Thursday F1 0.576 (and D-021's precision 0.959
at 5 %) were measured this way.

**Policies, fixed before running** (`scripts/threshold_eval.py`, 90th percentile = 10 % budget):

| policy | threshold at window t | role |
|---|---|---|
| `whole-capture-10pct` | q90 of all windows of the capture | reference, **non-causal** (E14) |
| `expanding-10pct` | q90 of windows 0..t-1; no alarm while t < 20 | **primary** |
| `trailing120-10pct` | q90 of windows t-120..t-1 (at least 20) | secondary |
| `trailing60-10pct` | q90 of windows t-60..t-1 (at least 20) | secondary |
| `expanding-5pct` | q95 of windows 0..t-1 | secondary (the causal version of the 5 % figure) |
| `train-quantile-5pct` | q95 of training-day scores | reference (E14's `alert-budget-5pct`) |

**Why the expanding budget is primary.** It is the causal counterpart of the current policy and
changes exactly one thing: the percentile is taken over the capture *so far* rather than the whole
capture. The trailing variants also change *what* the budget is relative to (the last hour), which
the secondaries measure. The 20-window warm-up (10 minutes) is there so the first quantile is not
taken over a handful of windows.

**Scored on:** the held-out `p_max` scores E14 published for r2 (Thursday, Friday) and for the three
E10 full seeds. Same label (`y_within_K`), same lead-time definition as E14.

**What the result commits us to, whatever it is.** The primary policy's Thursday F1 on the r2
checkpoint, with its E10 seed range, becomes the deployable number everywhere D-032 applies. The
whole-capture 0.576 may only be quoted as a non-causal upper bound. The secondary policies are
sensitivity analysis. **None may replace the primary on the strength of these results:** picking the
best of five policies on one held-out fold would be tuning the threshold on the test set. The
dashboard's threshold moves to the primary policy, which makes the threshold a per-window series in
the API.

**AMENDMENT (2026-09-27, G-9) - the product now runs the primary policy.** `netwm.metrics.causal_threshold`
is the single implementation; `scripts/threshold_eval.py` calls it and reproduces every published E18
table byte for byte, and `engine/predict.py` calls it for every upload and demo. Checkpoints that name
`self-budget-10pct` are served as `expanding-10pct`. The payload carries the threshold per window
(API contract v1.2) and the dashboard draws it as a stepped curve. The model card reads E18's primary
row (F1 0.608, FPR 0.078) from `results/runs/e18-causal-threshold-e4e7-worldmodel-r2/`, with PR-AUC
from E14. Its lead time stays 0: E18's 2 of 4 does not beat the null. The payload's
`lead_time_summary` now carries D-022's circular-shift null on its own alarm series, and the alarm
panel may only say "verified" when `beats_null` is true. On the full Thursday payload it reproduces
E18's null exactly (chance 0.97 of 4, p = 0.331).

---

### D-035 — Pre-registration: the M1 v2 programme, and the scorecard that replaces Thursday F1
*Date: 2026-09-27 · Status: accepted, written and pushed before any v2 model was trained or any E9/E11
number computed · Experiments: E9, E11, E19-E24, E25 (CTU-13)*

**Why.** E18 showed that Thursday F1 moves from 0.576 to 0.608 by changing only the threshold rule. A
number the threshold alone can move is the wrong thing to optimise. PS 26153 asks for anticipation of
attacker progression that survives a change of day. From here on, **no model change is adopted on
Thursday F1.** F1 is still reported, because the PS asks for it.

#### The scorecard (computed by `scripts/scorecard.py`, identical for every run)

Every candidate is trained **leave-one-day-out on all five folds, on seeds 42, 43 and 44**, with the
round-2 training budget (25 epochs, 16 Monte-Carlo samples at evaluation). Two scores are read off
each held-out day:

- `comp`: channel-0 `p_max`, compromise within K. This is the product's alarm statistic (D-019).
- `threat`: channel-1 `p_max`, any hostile activity within K. It does not depend on the attack family.

Four numbers per run:

| id | name | definition |
|---|---|---|
| **S1** | causal alarm cost | `comp` at the causal expanding q90 (D-034) against `y_within_K`, pooled over Thursday and Friday (the only days with compromise): precision and FPR |
| **S2** | anticipation by lead bin | Take every attack episode with Impact excluded: 19 onsets (Tue 3, Wed 1, Thu 8, Fri 7). For each, take the **eligible** (non-attack) windows at 1-4, 5-8, 9-12 and 13-20 windows before the onset, i.e. 0-2, 2-4, 4-6 and 6-10 min. Score each window by the percentile of its `threat` value among the same day's **reference windows**, which are the eligible windows at least 20 windows from every onset. Report the mean percentile per bin; 0.5 is chance. **S2\*** is the mean over the three bins from 2 to 10 min (5-20 windows). The same table for the 5 compromise onsets, scored with `comp`, is reported beside it and does not gate |
| **S3** | early-warning significance | Strict warned-early (the D-022 guards) at the causal expanding q90 on `threat`, over the 19 non-Impact episodes. Tested per fold against a 2,000-shift circular null of the alarm series, then Fisher-combined over the four attack folds |
| **S4** | cross-day robustness | S2\* for each held-out day (Tue, Wed, Thu, Fri); the worst day is reported next to the pooled value |

S2 needs no threshold and is normalised within each day, so a shift in score scale between days
cannot move it. Thursday F1 lacked exactly that property. The 0-2 min bin is reported but does not
gate: a score that rises in the minute before an onset cannot be told apart from detecting the run-up.

#### The adoption bar for every step (fixed now)

Each step is compared with the **current stack** on the same seeds and folds. It is **adopted** only
if all three conditions hold:

1. **Anticipation:** the 3-seed mean of S2\* rises by **at least 0.03**, and it rises on **at least 2 of
   the 3 seeds**.
2. **No extra alarm cost:** the 3-seed mean of S1 precision falls by **less than 0.05**, and S1 FPR rises
   by **less than 0.02**.
3. **Stability:** no seed collapses, meaning no seed has Thursday `comp` PR-AUC below 0.20 (E16's
   failure mode).

A step that fails is reported with all four numbers and is not carried forward.

**Packet features are the exception, because the PS requires them.** They are carried forward if
conditions 2 and 3 hold. Condition 1 then answers the question "does packet information help early
forecasting?", and that answer is reported whichever way it goes.

If S3 ever passes (Fisher p below 0.05, with at least 2 of the 4 folds above the null's p95), that is a
new early-warning claim on its own. It goes through D-021's review before it reaches any slide.

#### The steps, in the order the stack is built

| exp | step | the change, and nothing else |
|---|---|---|
| **E19** | baseline | The round-2 model on S_t v1 (70 features), 5 folds x 3 seeds (`m1v2-base`). Every later step is measured against the stack, starting here |
| **E20** | packet block (CSV) | Adds 17 `pkt_` features. The flow meter recorded these per packet, but S_t never used them: the TCP initial-window distribution (zero and small-window rates, distinct count, entropy); the payload-size histogram (5 bins, weighted by packets); payload variability per direction; per-direction inter-arrival spread and the coefficient of variation of flow IAT (the slow-scan timing signal); RST and SYN-only probes by direction; and header bytes per packet (TCP options). **TTL, fragmentation and retransmissions are not in any flow CSV**, so this block cannot include them |
| **E20r** | packet block (PCAP) | Adds the same families measured from the real packets, once the five CIC-IDS2017 day PCAPs are on disk: TTL mean, std and distinct count; fragment rate; retransmission rate; zero-window rate; the true per-packet payload histogram; and packet inter-arrival spread. Compared with E20 on the same seeds. **This is the FLOW-ONLY vs FLOW+PACKET comparison the PS asks for**; E20 is the half of it the CSVs allow |
| **E21** | causal representation | Each feature becomes four inputs: its level (log-standardised as in D-014), its causal percentile among the previous 120 windows (E16's causal transform), its one-window delta, and its 5-window least-squares slope. Plus 6 **per-host-relative** features, each comparing an internal host with its own past in the capture: the maximum over hosts of the port-count z-score and of the fan-out z-score against the host's trailing 120 windows; the maximum flow-count ratio; the number of hosts that contact a peer they have never contacted before; and the most new ports any single host touched. All causal, all label-free |
| **E22** | factorised target | Drops the dedicated compromise head: `P(compromise) = P(threat) x P(compromise stage \| hostile)`. The first factor, `threat`, is channel 1 and trains on every attack family of every training day. The second is a stage classifier over the six non-benign stages, trained only on hostile windows. The compromise BCE is applied to the product, and the rollout reads the product off imagined states as before |
| **E23** | precursor curriculum | For every attack onset on the training days, adds extra sequences whose history ends 20, 16, 12, 8 or 4 windows (10, 8, 6, 4 or 2 min) before it. Each is imagined **20 steps** ahead and supervised on the true future labels. Inference is unchanged (K = 10), so any gain lives in the representation, not in a longer horizon |
| **E24** | Model A vs Model B | A keeps the same encoder and causal attention but uses heads that predict "within K" directly: no GRU, no stochastic latent, no imagination. B is the stack as built. B keeps the latent dynamics only if it beats A under conditions 1-3 of the bar. Otherwise we report that the latent dynamics earn reconstruction, not lead time |

**Guard against the garden of forking paths.** Each step runs exactly once, in this order, on the
listed seeds. Nothing is tuned between steps, and no step is re-run with changed settings after its
score has been read. If a step's code turns out to be wrong, the fix and the re-run are recorded as such.

#### E9 - MITRE stage confusion (no bar; a measurement the PS requires)

A confusion matrix on each held-out day: rows are the window's ground-truth stage (D-003), columns are
`argmax stage_now`. It is computed for the submission checkpoint r2 (Thursday and Friday folds) and for
every E19 fold, with per-stage precision and recall.

One column records whether the stage **appears in that fold's training days at all**. Thursday's
Lateral Movement occurs only on Thursday, so the Thursday-fold stage head has never seen that class,
and any error there is structural, not a failure to learn. A technique-level view merges
Reconnaissance and Lateral Movement (both T1046 in this capture) and is reported beside the stage view.

#### E11 - do the explanations point at the attack? (bar fixed now)

E11 runs the dashboard's Integrated-Gradients attribution (`engine/explain.py`, unchanged) on the r2
checkpoint. It covers the attack windows of six held-out episodes, up to 24 evenly spaced windows per
episode. Each episode's signature set is written down here:

| episode | windows | signature features |
|---|---|---|
| Thu 17:00 external port scan | stage Recon, 17:00-17:02 | `uniq_dst_port`, `dst_port_entropy`, `port_fanout_max`, `ports_per_pair_max`, `seq_port_ratio`, `syn_no_ack_rate`, `has_rst_rate`, `tiny_flow_rate`, `one_way_rate`, `rst_cnt_sum`, `syn_cnt_sum` |
| Thu internal sweep | stage Lateral Movement, 18:04-18:45 | `uniq_dst_ip`, `fanout_max`, `fanout_mean`, `uniq_dst_port`, `port_fanout_max`, `ports_per_pair_max`, `dst_ip_entropy`, `dst_port_entropy`, `n_flows`, `flows_per_s`, `top_talker_share`, `syn_no_ack_rate`, `has_rst_rate`, `tiny_flow_rate`, `is_internal_rate` |
| Thu web attacks | stage Initial Access, 12:20-13:42 | `svc_http_rate`, `n_flows`, `flows_per_s`, `top_talker_share`, `pkt_len_mean_mean`, `pkt_len_max_max`, `bytes_mean`, `psh_cnt_sum`, `is_inbound_rate` |
| Fri botnet C2 (Ares) | stage C2 | `beacon_score`, `is_outbound_rate`, `outbound_bytes`, `byte_asymmetry`, `svc_http_rate`, `flow_iat_mean_mean`, `flow_iat_std_mean`, `duration_s_mean` |
| Fri port scan | stage Recon | the 17:00 scan's set |
| Fri DDoS LOIC | stage Impact | `flows_per_s`, `n_flows`, `pkts_per_s`, `bytes_per_s`, `svc_http_rate`, `uniq_src_port`, `is_inbound_rate`, `syn_cnt_sum`, `top_talker_share` |

**Per episode:** rank the 70 features by mean |attribution|, count how many signature features are in
the top 8 (`hits`), and compute the hypergeometric p-value of scoring that many hits or more by chance.
**An episode passes at p < 0.05, and E11 passes if at least 4 of the 6 episodes pass.**

Two controls are reported and do not gate. The first is the Spearman correlation between the
attribution ranking and a ranking by |scaled value| alone: if IG only restates which features are
unusual, that correlation will be near 1. The second is the same hit count for the |value| ranking.

#### E25 - CTU-13 (M2), scenario-held-out

A new adapter reads the Argus `.binetflow` files. Its state is the part of S_t v1 that Argus fields
can support: counts, ports, hosts, fan-out, entropies, flags from `State`, bytes, duration, direction,
services and beaconing. CIC-only fields are dropped, not zero-filled.

Labels:
- `From-Botnet*-CC*` flows are Command and Control, a compromise stage (D-011).
- Other `From-Botnet` flows are hostile activity: Reconnaissance for scans, Impact for DDoS and spam.
- `Normal` and `Background` are benign.

The evaluation is **leave-one-family-out** over the seven families: Neris (scenarios 1, 2, 9), Rbot
(3, 4, 10, 11), Virut (5, 13), Menti (6), Sogou (7), Murlo (8) and NSIS (12). Seed 42 runs first. Each
fold gets the same number of gradient steps as a CIC-IDS2017 fold, not the same number of epochs,
because scenario 3 alone is 66 hours long. Scoring uses the same scorecard, with the botnet's first C2
window as the compromise onset. The architecture is the final E19-E24 stack, fixed before the first
CTU-13 run.

**Revisit if:**
- The five PCAPs cannot be obtained. Then E20r is reported as not run.
- E19 reproduces the r2 numbers poorly, with Thursday `comp` PR-AUC outside the E10 seed range
  (0.37-0.64). That would mean the harness changed, not the model.

---

### D-036 — CTU-13 flows become MITRE stages by their own labels; Argus-only state (E25)
*Date: 2026-09-27 · Status: accepted, fixed before any CTU-13 model was trained · Evidence: the label vocabulary of scenarios 1-3 (164 distinct botnet labels), `src/netwm/data/ctu13.py`*

**Decision.** `Background` and `Normal` flows are benign. `From-Botnet` flows map by keyword, first
match wins:

| label contains | stage | why |
|---|---|---|
| `CC` | Command and Control | the dataset's own C&C labels (`CC1-HTTP-Not-Encrypted`, `CC69-Custom-Encryption`, ...) |
| `SPAM`, `DDoS`, `Flood`, `ICMP`, `-Ad-`, `ClickFraud`, `Proxy` | Impact | abuse of the host's resources: spam relay, ad fraud, floods (T1496, T1498) |
| `Attempt`, `Scan` | Reconnaissance | unanswered connection attempts, which is what a scanning bot produces |
| anything else (`DNS`, `Established`, `HTTP-Google-Net`, ...) | Command and Control | the infected host's own channel; CTU-13 does not tag every C&C flow `CC` |

`To-Botnet` flows and flows towards an infected host are benign. They are replies or background
traffic, and labelling them hostile would mark the victim's legitimate peers as attackers.

The compromise onset is the first window at or past Lateral Movement (D-011), which here means the
bot's first C2 window.

**State.** Argus records the 5-tuple, start, duration, total packets, total and source bytes, and a
`State` string of TCP flags per side. It records no inter-arrival, packet-length, initial-window,
segment-size or active/idle statistics. The 14 S_t v1 features built from those fields are dropped
from E25's inputs (`CIC_ONLY_FEATURES`), leaving 56. The E20 packet block needs the same missing fields
and is absent. Packets are split between directions in proportion to bytes. A flow with no recorded
reply is one-way, including the 91 ICMP flows in scenario 11 that have no `State` at all.

**Why this and not a transfer test of the CIC model.** The public CTU-13 PCAPs are botnet-only
(research/ctu13.md), so neither the CIC state nor the CIC checkpoint can be rebuilt on it. E25 is
therefore a new model with the same architecture and training budget, evaluated leave-one-family-out.
It tests whether *the method* transfers across families, not whether one set of weights does.

**Known weakness, stated before the result.** Several captures are almost entirely botnet: Murlo
96 % of windows C2, Virut s13 99.5 %, Menti 98 %. Several onsets fall in the first minutes of a
capture: s06 at window 1, s08 at window 1, s03 at window 2. Those scenarios test detection, not
anticipation, and S2 has few eligible pre-onset windows there.

**Revisit if.** A labelled full-traffic CTU capture appears, or a label turns out to be misrouted by
the keyword rule. The first match wins, so `Attempt-SPAM` is Impact, not Reconnaissance, by design.

**D-035 OUTCOME (2026-09-27, E19-E25; recorded after every pre-registered run was scored).**

| step | verdict under the bar | carried forward? |
|---|---|---|
| E20 CSV packet block | clause 1 fails (+0.008); non-inferior | **yes**, under the PS-requirement rule |
| E20r real packets | clause 1 fails vs E20 and vs flow-only; non-inferior; Thursday PR-AUC 0.43 -> 0.56 | not in the final stack (the captures arrived after E22-E24 had run); the next model to train |
| E21 causal representation + host-relative | clause 1 fails (+0.008); alarm cost better | **no** |
| E22 factorised target | **passes all three** (+0.045) | **yes** |
| E23 precursor curriculum | fails all three; two seeds collapse | **no** |
| E24 Model B (RSSM) vs Model A (no latent dynamics) | **B passes all three** (+0.096, all seeds) | **yes**: the latent dynamics stay |

**Final M1 stack:** RSSM + factorised target, on S_t v1 + the CSV packet block (`configs/m1v2/e22_factorized.yaml`,
runs `m1v2-e22-s4*`). **S3 was met by no run**, so no early-warning claim follows. D-021 is unchanged.
**E25 (CTU-13):** anticipation does not transfer across botnet families (S2\* 0.551). The shipped
checkpoint stays r2 until the team decides otherwise. The E22 stack trades Thursday detection
(PR-AUC 0.389 against r2's 0.640) for cross-day anticipation, which a demo would have to explain.

---

### D-037 — Pre-registration: do E22 and real packets compose? (E26), CTU-13 completion (E25b), and the ship rule
*Date: 2026-09-28 · Status: accepted, written and pushed before E26 was trained and before E25 seeds 43/44 or
any LR baseline ran · Follows the evaluators' 10-step plan, with the five amendments listed at the end*

**Reference point (Step 1).** `results/runs/reference-m1-2026-09-28/manifest.json` records every
reference model. For each it gives the configs, the feature schema (a hash of the ordered names), the
scaler mode, seeds, parameter count, the SHA each checkpoint was trained at, the split, the threshold
policy and the scorecard numbers. It is generated from the artefacts by `scripts/reference_manifest.py`.

| reference | role | what it is |
|---|---|---|
| r2 | the shipped detection model | Thursday + Friday folds, seed 42; E18 causal Thursday F1 0.608, PR-AUC 0.640 |
| E19 | the r2 method on the D-035 contract | 5 folds x 3 seeds, 70 features: **the flow-only row of every comparison** |
| E22 | reference anticipation model | RSSM + factorised target, 87 features, S2\* 0.704 |
| E20r | reference packet model | round-2 heads, 105 features (flow + CSV packet + real packets), Thursday PR-AUC 0.564 |
| E24a | world-model control | Model A, no latent dynamics |
| E25 | CTU-13 | seed 42, leave-one-family-out |

**E26, the combined candidate (Step 2).** It is the E22 configuration, with the E22 architecture and
target unchanged. Two things change: the 18 `pcap_` features are added (the E20r ones), plus one
`has_pcap` input. That makes 87 + 18 + 1 = 106 inputs.

**Packet availability** is handled like this, fixed now:
- `has_pcap` = 1 when the window's packet features were measured from a capture, and 0 otherwise. A
  CSV-only window has every `pcap_` value set to 0 in raw feature space and `has_pcap` = 0, and then
  goes through the **same fitted scaler**.
- **Packet dropout in training: each training sequence is presented in its CSV form with probability
  0.3.** It is an otherwise identical sequence of real data. Without this, a CSV input at inference
  would be a state the model has never seen, and the "one model, both inputs" claim would be untested.
- The scaler is fitted on the training days with packets present.
- **Inference parity is part of the step:**
  - a PCAP upload gets the same 17 CSV-packet columns (the flow converter is extended to emit the
    8 per-packet fields they need) and the same 18 `pcap_` features, computed by the same function as
    training;
  - a CSV upload gets `pcap_` = 0 and `has_pcap` = 0;
  - a test checks, on real data, that the inference path's state equals the training matrix.

**Training and scoring (Step 3).** Seeds 42/43/44; the same five leave-one-day-out folds, 25 epochs,
the causal expanding q90 and the D-035 scorecard. **Every held-out day is scored twice: in PCAP mode
(packets present) and in CSV mode (the same windows with packets masked).**

**The composition bar (Step 5).** This is fixed now. The D-035 bar asks a step to *raise*
anticipation, and E20r already showed packets do not. Applied unchanged, it would reject a
combination that keeps E22's anticipation and adds E20r's detection, which is the very question
being asked. Every clause below uses 3-seed means, paired by seed, in PCAP mode, against E22:

| clause | requirement |
|---|---|
| **(a) anticipation preserved** | S2\* >= E22's S2\* - 0.03 |
| **(b) detection added** | Thursday `comp` PR-AUC >= E22's + 0.05, and higher on >= 2 of 3 seeds |
| **(c) alarm cost** | S1 precision falls < 0.05, S1 FPR rises < 0.02 |
| **(d) stability** | no seed with Thursday PR-AUC < 0.20, in either mode |
| **(e) still a world model** | open-loop rollout MSE below persistence, averaged over k = 2..10, on the Thursday and Friday folds, on >= 2 of 3 seeds (E10's form) |

**Ship rule, fixed now.** There are four outcomes:
1. **(a)-(e) hold, and CSV mode also meets (d): ship E26** as the one model for both inputs. The model
   card quotes PCAP-mode and CSV-mode numbers separately.
2. **(a)-(e) hold, but CSV mode collapses:** E26 serves PCAP uploads and is documented as not serving
   CSV. For CSV, r2 stays shipped. The "one model" claim is not made.
3. **(a) fails:** the two gains do not compose. **r2 stays shipped**, E22 and E20r stay as separate
   references, and the failure is diagnosed (which clause, which days, which seeds), with no tuning
   sweep.
4. **(b) fails:** packets add nothing on top of E22. **r2 stays shipped**, and E22 remains the
   anticipation reference.

No threshold, seed, split, metric or anticipation definition changes after the result. S3 is reported.
If it passes, that is a new claim and goes through D-021.

**The ablation matrix (Step 4).** It will contain:
- LR flow-only;
- E19 (the r2 method, flow-only);
- E22 (flow + CSV packet, factorised);
- E20r (flow + packets, round-2 heads);
- E26 in PCAP mode and in CSV mode;
- E24a for the world-model control.

Every row reports S1, S2 by bin, S2\*, S3, S4, Thursday/Friday PR-AUC and causal F1, the seed range,
and rollout-vs-persistence where the model has dynamics. **LR baseline:** `LogisticForecaster` (E3's
definition: balanced classes, C = 1, no lags) on the log-standardised S_t v1, one model per target:
`y_within_K` as `comp` and `y_attack_within_K` as `threat`. It uses the same folds and is scored by
the same scorecard. It is deterministic, so it gets one row, not a seed range.

**E25b, CTU-13 completion (Steps 6-7).**
- **Seeds 43 and 44** use exactly seed 42's definition (`configs/m1v2/e25_ctu13.yaml`,
  `configs/ctu13_folds.yaml`, a 250-step budget), in run folders `e25-ctu13-s43/s44`, marked
  `completion of E25` in their metadata.
- **The CTU-13 LR baseline** uses the same 56 features, folds, targets, scaler and scorecard.
- **The family matrix** reports, per held-out scenario and per family: world model vs LR on detection
  (ROC-AUC, PR-AUC, causal F1) and anticipation (S2, only where a scenario contributes >= 20
  pre-onset cells), plus the S3 count.
- A family is **"transfers"** when the world model's ROC-AUC is >= 0.70 on >= 2 of 3 seeds for every
  one of its scenarios. It is **"inverted"** when ROC-AUC is < 0.50 on >= 2 of 3 seeds for any of
  them. Everything else is "partial".
- No pooled average is quoted without this matrix beside it.
- CTU-13 has no mixed-traffic PCAPs, so M2 claims cover cross-family temporal behaviour on Argus flow
  state only.

**Claims (Step 8), fixed now:**
- S3 not met -> "ranks pre-attack windows above background", never "warns before attacks".
- E17 stands -> "risk score", not a probability.
- E9 -> the stage output is "the model's estimate", shown with the measured confusion.
- E11 -> "feature contributions", not causal explanations.

**Step 10.** No GNN, larger model or hyperparameter sweep until E26 and E25b show a concrete failure
mode that such a change is designed to fix.

**Amendments to the evaluators' plan, and why:**
1. The "r2 flow-only" row is **E19**, because r2 itself has two folds and one seed. r2's E14/E18
   numbers are listed beside it.
2. E26 is judged by the **composition bar** above, not by D-035's raise-anticipation bar, which would
   reject a successful combination by construction.
3. A `has_pcap` mask alone does not make CSV inference honest: it needs **packet dropout in
   training**, and the model needs **evaluating in CSV mode**.
4. The PCAP upload path **did not produce the CSV packet block's input columns**. Fixing that is part
   of Step 2.
5. The 2-minute **video recording** and making the **repository public** (G-1) are human actions. This
   work prepares the script and the checklist.

**Provenance fixes recorded here:**
- `train.py` stamps checkpoints with the SHA at process start. Previously the SHA at save time was
  used, so commits made during a sweep relabelled folds; E19's checkpoints carry three SHAs.
- `--resume` no longer rewrites a checkpoint. The five resumed E25 folds were re-stamped `df2c6ef`,
  and the manifest reads their true training SHA, `bb36594`, from the interrupted log.

**D-037 OUTCOME, E26 (2026-09-28).** The composition bar fails on clause (a): S2\* is -0.041 against
E22 (bar -0.03). Clauses (b) to (e) pass: Thursday PR-AUC +0.054 on all seeds, precision +0.053,
stable in both modes, rollout beats persistence on 3 of 3 seeds. **Ship outcome 3: r2 stays shipped.
E22 is the anticipation reference and E20r the detection reference; no tuning.**

Diagnosis, recorded as description: the packet block acts as current-state evidence. The loss sits on
Thursday and Friday, and the same weights in CSV mode rank the run-up at 0.727. **CSV mode's rollout
is worse than persistence**, so its forecasts are not world-model rollouts.

**New baseline fact:** logistic regression ranks pre-onset windows at 0.659, level with round 2
(0.651). The world model's anticipation edge over LR is the factorised target (+0.045). Its
detection edge is large: PR-AUC 0.39-0.56 against 0.14.

**D-037 OUTCOME, E25b (2026-09-28; recorded after all three seeds were scored).** Applying the rule
fixed above: **NSIS and Menti transfer; Murlo, Neris, Rbot, Sogou and Virut are inverted; none is
partial** (results.md E25b).
- **Transfers.** Only NSIS transfers on well-measured data (72 background windows, 0.98 on every
  seed). Menti's "transfers" rests on 6 background windows.
- **Inversions.** Two are well measured: Murlo (89 background windows, 0.14-0.20 on every seed) and
  Neris s02 (78). The others rest on captures with 10-26 background windows: Rbot s11, Sogou s07 and
  Virut s13.
- **Why E25 read Neris as transferring.** Seed 42 was the most favourable seed on Neris.

**World model vs LR**, on the same 56 features and folds:
- ROC-AUC is higher for the world model on 5 of 13 scenarios, and for LR on 8.
- Causal F1 is higher for the world model on 7, and for LR on 4.
- LR is not inverted on Sogou (0.737) or Virut s13 (0.991).

**Anticipation** is measurable on 6 scenarios.
- The world model ranks the run-up above LR on every seed on Neris s02 and s09 and on Rbot s04 and
  s10.
- It ranks below LR on Murlo, and on Rbot s03, where both models are below chance. s03 holds 892 of
  the 1,451 cells.
- S3 is met nowhere.

**No pooled CTU-13 number is quoted without the E25b matrix beside it.** The M2 claim is exactly
this: the method's detection transfers robustly to one botnet family and inverts on several; its
run-up ranking carries to some Neris and Rbot captures and not to Murlo; M2 covers Argus flow state
only.

---

### D-038 — Pre-registration: PCAP uploads are served by the mean of the three E20r seeds; CSV uploads stay on r2 (E27)
*Date: 2026-09-28 · Status: accepted, committed before any ensemble score was computed · Follows D-035 (packet
features are carried forward because the PS requires them) and D-037 outcome 3 (r2 stays shipped)*

**Why.** PS section 1 requires flow-level and packet-level features, in combination. The shipped r2
reads 70 flow features. On a PCAP upload the engine turns the capture into flows, and r2 ignores every
packet measurement; the payload says so (`"packet_features": "not used by this model"`). D-035 carried
packet features forward because the PS requires them, but the shipped model has none. E20r is the
existing packet-consuming reference: 105 inputs, namely S_t v1 (70), the CSV packet block (17) and
the 18 `pcap_` features measured from the real captures (TTL, fragments, retransmissions, TCP window,
payload histogram, packet timing, SYN-only and RST shares).

**What this is, and what it is not.** It is an inference-routing decision on three existing
checkpoints. No model is trained. It claims neither that packets improve anticipation (E20r's S2\* is
0.642 against 0.651 flow-only: they do not) nor that the ensemble generalises better than one seed.

**Routing, fixed now.**
- One endpoint, `/api/analyze`, routed by input modality:
  - `.csv` / `.txt` → r2 (`models/e4e7-worldmodel-r2/`), unchanged;
  - `.pcap` / `.pcapng` → the E20r ensemble.
- The ensemble is **all three seeds**, `models/m1v2-e20r-s{42,43,44}/`. For a demo slice of a held-out
  day, each seed's fold for that day; for any other capture, each seed's `thursday.pt`, the same default
  r2 uses. **No seed is chosen, dropped or weighted by held-out performance.** The per-seed Thursday
  numbers (PR-AUC 0.418 / 0.562 / 0.710) were known when this was written; the unweighted mean of all
  three is chosen so that this knowledge cannot pick one.
- Every checkpoint reads the same state, built once: flows from `pcap_to_flows`, and the packet block
  from `window_packet_features(read_packets(capture))`, the functions that built its training matrix.
  Each applies its own fitted scaler. The three feature orders are checked identical before serving.
- Alarm score per checkpoint: `p_max` on the deterministic mean path, as the engine scores r2 (D-019,
  E14). **Ensemble score = arithmetic mean of the three per-window scores**, on the shared window grid.
- Threshold: the causal expanding q90 (D-034), applied once, to the ensemble score. The E20r
  checkpoints store no threshold policy, and the engine would otherwise fall back to their fixed
  train-tuned threshold, which E14 found ~100x too high on a held-out day. The route sets the causal
  policy explicitly.
- Every other per-window output (risk curves and bands, stage distribution, surprise, attention) is the
  arithmetic mean of the three. Feature contributions are the mean of the three Integrated-Gradients
  attributions on the same windows. IG is linear in the model, so this equals IG of the mean score.
- **A PCAP upload never falls back to r2.** If an E20r checkpoint is missing, or the packet block
  cannot be built, the request fails with an error.
- The payload names the input modality, the model mode, the checkpoint set and whether packet
  features were measured. A CSV result says packet features are unavailable. D-031's synthesised demo
  capture takes the same route, and is labelled as synthesised packets, not evaluation data.

**Scoring (E27), fixed now.**
- From stored outputs only. For each held-out day, the per-window `scores` and `threat_scores` stored
  by each E20r run are averaged across the three seeds. These are `p_max` over 16 Monte-Carlo rollouts,
  the statistic of every E20r row in the benchmark and the ablation matrix.
- The averaged arrays are written as the run folder `results/runs/e27-e20r-mean/` and scored by the
  unchanged `scorecard.score_run` and `benchmark_table`'s causal metrics:
  - S1, S2 by bin and S2\*, S3 with its null, S4;
  - Thursday and Friday PR-AUC, causal F1, precision, recall and FPR.
- The three seeds are reported beside the ensemble. r2 is shown as the flow-only reference, a
  different input.
- The live mean-path statistic differs from the stored Monte-Carlo one by sampling noise. The parity
  check reports that difference per window; it does not require equality.
- The ensemble has no single rollout. Its world-model evidence is each seed's own (E26 matrix: all
  three beat persistence on Thursday and Friday).

**Acceptance of the PCAP path, fixed now.** Accepted when all three hold:
1. **Engineering.** The routing tests pass. On the processed Thursday and Friday matrices, the live
   path gives each seed the feature order and scaler it trained with. No future-dependent statistic
   enters preprocessing or the threshold. The parity check is recorded in results.md.
2. **Stability** (D-037 clause (d)): ensemble Thursday `comp` PR-AUC >= 0.20.
3. **Non-inferior anticipation against the flow-only reference:** ensemble S2\* >= E19's S2\* - 0.03,
   which is 0.651 - 0.03 = 0.621.

If 2 or 3 fails, the PCAP path is not accepted and the team decides. No seed selection, re-weighting,
threshold change or retraining follows from the result.

**Supersedes nothing.** D-037 outcome 3 stands: r2 stays the model for CSV inputs, and E22 stays the
anticipation reference. This adds a route for PCAP inputs.

**Revisit if.** A later pre-registered fusion experiment produces a packet-consuming model that passes
D-037's composition bar; it would then replace this ensemble on the PCAP route.

**D-038 OUTCOME, E27 (2026-09-28).** Accepted on all three criteria:
- engineering: the routing tests and the parity check passed;
- stability: Thursday PR-AUC 0.543 (bar 0.20);
- anticipation: S2\* 0.669 (bar 0.621).

**PCAP uploads are served by the mean of E20r seeds 42/43/44; CSV uploads stay on r2.** The mean lies
inside the seed range (Thursday PR-AUC 0.42-0.71): it removes the choice of seed, it does not beat the
best one. No anticipation or early-warning claim follows (S3 4/19, p 0.92).

Found while checking for lookahead: every model's score depends on the capture's length, through
`CausalContext`'s interpolated positional embedding (E27 finding 5, `research/positional-length.md`).
It is pre-existing, and a fix needs its own pre-registered retraining.

Check 4, on the full Tuesday capture: the 18 packet features equal the training matrix exactly. The
flow features built by `pcap_to_flows` do not: counts are inflated up to about 2x, likely because the
converter keeps the capture duplicates that `read_packets` removes. The acceptance stands as
pre-registered, since it was scored on the training-matrix state. **No live-PCAP number may be quoted
until the converter is fixed and check 4 passes** (N-9).

**Correction and Step 8 (2026-09-28, D-040).**
- *Check 4's cause.* The cause given above is wrong. On the full day, `pcap_to_flows` filled its
  100,000-session cap with quiet flows and dropped 2.87 M packets. Duplicates were not the cause: the
  corrected CSVs count them. D-040 sweeps out timed-out flows. After it, totals match the training
  matrix to about 1 %, and the flow block's median mean relative error is 0.039 (was 0.312). Several
  flow features still differ.
- *Step 8, on the real Thursday 16:40-18:50 slice.* Both routes are served exactly as routed here,
  but their risk scores correlate at 0.035.
  - The cause is the live PCAP state. The ensemble on the real capture correlates 0.111 with itself
    on the training rows for the same windows.
  - The two models agree at 0.82 when both read their training state.
  - The CSV route reproduces its training state (0.9998).
- The acceptance above stands, because it was scored on the training-matrix state. The PCAP route's
  behaviour on a live capture does not yet match it (N-9).

---

### D-039 — Step 10: no GNN and no larger model on the evidence of E24, E26 and E25b
*Date: 2026-09-28 · Status: accepted under D-037's Step 10 rule; whether to run M3 is left to the team ·
Evidence: E12, E21, E24, E26, E25b, `results/runs/reference-m1-2026-09-28/manifest.json`*

**Decision.** Neither a GNN nor a larger model is started. D-037 allows either only once E26 and E25b
show a concrete failure mode that such a change is designed to fix. Neither does.

**Why not a larger model.**
- **Size.** The world models behind every claim (r2, E22, E20r, E25) have 0.58-0.62 M parameters. D-004 set that size because training
  ran on a 4 GB GTX 1650. The RTX 4060 lifts that limit, but new hardware is not evidence that size is
  the constraint.
- **The failures are failures to transfer, not to fit.**
  - Within a day, pre-onset windows separate from background at ROC-AUC 0.88-0.96 (E12).
  - Logistic regression ranks the run-up as well as the round-2 world model on CIC-IDS2017 (0.659
    against 0.651, E26).
  - On CTU-13, LR beats the world model's detection ROC-AUC on 8 of 13 scenarios (E25b).
- **More freedom has already cost anticipation.** Adding inputs cost -0.041 (E26). More freedom to
  fit the training families points in the direction of the failure, not towards its fix.
- **What did help is not size.** The one change that raised anticipation was the target (E22,
  +0.045). The latent dynamics earn their place against a same-encoder model without them (E24).

**Why not a GNN, yet.** The evaluators named the trigger: the same CTU-13 families fail across seeds
because one infected host is drowned in the network-global state.
- **The first half is met.** Murlo, Sogou and Rbot s11 are inverted on all three seeds (E25b).
- **The second half is not supported.**
  - Drowning would push any model on the global state towards chance.
  - What E25b shows instead is strong inversion by the world model (0.05-0.20, well below chance).
  - LR on the same 56 global features is not inverted on Sogou (0.737) or Virut s13 (0.991).
  - So on those families the information is in the global state, and it is the world model's learned
    weighting that flips on unseen families.
  - Murlo stays open: LR is weak there too (0.590).
- **Per-host information has been tried once.** E21 (causal representation plus six per-host-relative
  features) did not raise anticipation (+0.008, D-035).
- **A GNN cannot fix the lateral-movement recall.** The stage head scores zero recall on lateral
  movement (E9) because no training day contains that class, and a graph model cannot learn an absent
  class either.

**What would reopen each.**
- **A per-host state (the evaluators' intermediate step).** First a descriptive diagnostic: in the
  inverted scenarios (s08, s07, s11), the bot host's windows separate from background hosts on
  per-host features but not on the network-global ones. Only then a pre-registered per-host-state
  run, against the global state, on CTU-13's folds.
- **A GNN.** Only after that run passes, and relational structure (which hosts talk to which) is shown
  to matter beyond per-host features.
- **A larger model.** Only if a model underfits its own training families, with its training-fold
  ranking no better than its held-out one.

**Is M2 enough?**
- **For the submission, yes.** M2 is the cross-dataset evidence, reported family by family (E25b).
- **M3 (CIC-IDS2018) is the next transfer test worth running, if the team has time.**
  - The corrected flow CSVs (a 9.7 GB zip, no PCAPs needed) keep the full 70-feature state, which
    CTU-13 cannot, and add compromise onsets.
  - It needs its own pre-registration, and a download the team approves.

**Revisit if.**
- A diagnostic localises E25b's inversions to per-host behaviour.
- Or M3 shows the same inversion pattern on the full feature state.

---

### D-040 — The PCAP flow converter expires timed-out flows; capture duplicates stay in the flow block
*Date: 2026-09-28 · Status: accepted · Evidence: E27 check 4 (N-9), `results/runs/e27-parity/`,
`results/runs/e27-check4-dedupe-ab/`, `tests/test_pcap_ingest.py` · Amends D-033's implementation,
not its rules; corrects the cause D-038's outcome gives for check 4*

**Decision.**
- `pcap_to_flows` finishes every open flow whose first packet is more than 120 + 60 s behind the
  current capture time, checked every 60 s of capture time.
- Capture duplicates are **not** removed from the flow block. The packet block keeps its dedupe.

**Why the sweep.** Check 4's full-day mismatch (ae3ea25) had a different cause from the one recorded
with it. Its own log says `session cap 100000 reached, 2869997 packets dropped`.
- D-033's rule already ends a flow 120 s after its first packet, but only when another packet
  arrives on the same 5-tuple. A flow that goes quiet (UDP, TCP without FIN or RST) stayed open all
  day.
- Open flows accumulated until the 100,000-session cap. From then on every new flow was dropped, so
  the served counts fell towards zero, not up to 2x: `pkts_total`'s worst window was off by 0.995.
- The sweep changes no output below the cap. Any later packet on a swept tuple would have started a
  new flow anyway. On Tuesday 13:00-14:00, which never reaches the cap, the flow table is identical
  before and after (46,799 flows).
- The one exception is a capture more than 60 s out of time order.

**Why not dedupe the flows.** The corrected CSVs count the mirrored copies. On Tuesday 13:00-14:00,
the flow counts as served match the training matrix:
- median ratio to the training matrix 0.999 for `pkts_total`, and 1.000 for the SYN, ACK and PSH
  sums;
- with `read_packets`' duplicate rule applied first, they fall to 0.939, 0.966, 0.983 and 0.955;
- `tiny_flow_rate` rises from 1.29 to 3.03 times the training value.

The packet block's `pcap_` features were built with that rule, and they match the training matrix
exactly on the full day, so each block keeps the convention its training data used.

**Effect (check 4, full Tuesday, 968 windows).**

| | before (ae3ea25) | after |
|---|---:|---:|
| median feature's mean relative error, flow block (67) | 0.312 | 0.039 |
| median feature's mean relative error, CSV packet block (20) | 0.200 | 0.068 |
| flow features within 5 % on average | 14 | 39 |
| CSV packet features within 5 % on average | 4 | 9 |
| flow + CSV packet features correlating above 0.9 | 10 | 57 |
| `pcap_` features exact | 18 of 18 | 18 of 18 |

**What remains, and does not change here.** Some features are still far off:
- `active_mean_mean` and `bwd_init_win_mean`;
- the distinct-port and distinct-host counts: `ports_per_pair_max`, `uniq_dst_port`,
  `port_fanout_max`, `uniq_src_ip`;
- `flow_iat_min_min` and `pkt_len_max_max`.

These look like definition differences between our converter and the corrected extraction, not lost
packets. Nothing in the model or in E27's stored scores changes: those were computed on the training
matrix.

**Revisit if.** A capture is more than 60 s out of time order, or a residual difference is traced to
one of D-033's rules.

### D-041 — Pre-registration: the N-8 fix. Window-relative positions, state carried across chunks, and a retrain of both served routes
*Date: 2026-09-28 · Status: pre-registered (code `4ba2559`; nothing below has been trained) · Evidence to
come: `results.md` "N-8 fix"*

**Why.** E27 finding 5 and N-8 x E25b showed the defect. `CausalContext` stretches its 16
positional vectors to the input's length, so a window's score depends on how many windows follow it.
Streaming was also impossible: every call started from an empty state, so scoring a feed in chunks
could not equal scoring it in one pass. This entry fixes deployment correctness. **It is not a
performance sweep.** No hyperparameter changes, and nothing is chosen by its score.

**The change (code `4ba2559`, already tested).**
- `pos_mode: window`. The key at distance d from its query gets `pos[15 - d]`. Slots before the
  stream began are masked out, not attended as zeros. This is length-invariant by construction and
  matches what the attention mask already assumed.
- `forecast(..., carry=, return_carry=True)` carries the last posterior state and the last 15
  embeddings. On the mean path, a stream scored chunk by chunk equals the same stream scored at once,
  to 1e-6 (`tests/test_positional_window.py`).
- Checkpoints without `pos_mode` load as `interp`, and their scores are bit-identical to before. This
  was checked on the E20r, E25 and r2 checkpoints, both Monte Carlo and mean path.

**Runs.** Each is the served method with only `pos_mode` changed. All run on the GTX 1650, so the weights
stay on one machine.

| run | what | command |
|---|---|---|
| `m1v2-n8-e20rw-s{42,43,44}` | E20r, 5 folds, 25 epochs | `bash scripts/run_m1v2.sh n8-e20rw configs/n8/e20r_pcap_window.yaml data/processed/cicids2017_m1v2p` |
| `n8-r2w-s{42,43,44}` | r2's setup, Thursday and Friday folds | `python scripts/train.py --config configs/cicids2017.yaml --model-config configs/n8/r2_window.yaml --test-days thursday friday --epochs 25 --samples 16 --run n8-r2w-s<seed> --seed <seed> --no-figures` |
| `n8-r2i-s42` | control: r2's setup with **today's code** and `interp`, to separate code drift since `55ee51d` from the positional change | the same, without `--model-config` |

**Gates, in order. Nothing ships unless G1 passes.**
- **G1, correctness.** All three conditions must hold:
  - the unit tests pass;
  - on every checkpoint a route would serve, and on each of its held-out days, the mean-path `p_max`
    from 60-window chunks with the state carried equals the one-pass `p_max` to max |diff| <= 1e-5;
  - `backend/tests/test_pcap_route.py::test_forecast_is_prefix_invariant` stops being a strict xfail
    and passes on the served checkpoints.
- **G2, PCAP route.** D-038's own bar, unchanged. The mean of `m1v2-n8-e20rw-s{42,43,44}` needs
  Thursday PR-AUC >= 0.20 and S2\* >= E19's S2\* - 0.03 (0.651 - 0.03 = 0.621), scored by
  `scorecard.score_run` and `benchmark_table.metrics` as E27 was.
  - Pass: the PCAP route serves the E20rw mean.
  - Fail: it keeps E20r, and the defect stays documented.
- **G3, CSV route.** `n8-r2w-s42`, the same seed and setup as r2, needs Thursday PR-AUC >= 0.540 and
  Thursday causal F1 >= 0.508 (causal expanding q90, `y_within_K`).
  - Those bars are r2's 0.640 and 0.608 minus 0.10. The margin is wide because r2 is a single seed
    at the top of its method's range (E19, its method on the D-035 contract, reaches 0.43 [0.41-0.46]).
  - Pass: the CSV route serves r2w seed 42.
  - Fail: it keeps r2.

**Reported, not gated.**
- The paired differences against E20r and r2, and r2w seeds 43/44.
- `n8-r2i-s42` against r2 (code drift).
- Friday numbers and the rollout gain.

**Not allowed.** No reruns except `--resume` after a crash, no change to the gates after a result is
seen, and no other hyperparameter changes. A failed gate is reported as failed.

**Revisit if.** G1 fails on real data but not in the tests. That would mean a path the tests do not
cover (the explainer's short slices, `engine/explain.py`, are one candidate).

**Amendment (2026-09-28, before any D-041 run finished; no result had been seen).**
1. **Inputs.** `data/processed/cicids2017_m1v2p` gained a `has_pcap` column for E26 after E20r was
   trained. With `exclude_blocks: [host_relative]` alone, the pushed config would have read 106 inputs,
   not E20r's 105. The config now also drops a new `has_pcap` block (`scripts/train.py`), and
   E20rw reads exactly E20r's 105 columns in E20r's order. Those 105 columns are unchanged in the
   rebuilt matrix: a scaler refit on E20r's training days reproduces E20r's stored `mean_`, `std_` and
   `log_cols` exactly. r2's 70 columns in `data/processed/cicids2017` were checked the same way.
2. **Scheduling.** At the user's request, every run goes **one at a time**, not three seeds in parallel.
   The `train.py` arguments are the ones above; only the order changes. Two earlier starts were stopped
   in their first fold and saved nothing: a parallel one, and a sequential one that read the
   106-input matrix. Their logs are in `results/runs/n8-logs/stopped-*`. In the sequential start, one
   process ended after 7 s with exit code 0 and no traceback, and the cause is unknown. So the chain
   now checks each run's outputs rather than its exit code, and repeats a run once with `--resume` if
   they are missing.

### D-042 — Pre-registration: does host-local temporal state fix E25b's cross-family inversions? (CTU-13, 7 folds x 3 seeds)
*Date: 2026-09-28 · Status: pre-registered; nothing below has been built or trained · Depends on: D-041's
code (`pos_mode: window`)*

**Why now.** N-6b showed the "drowned" pattern on Murlo:
- the bot host's own traffic ranks s08's windows at 0.93-0.96, where the global statistics sit at
  0.32-0.34;
- the bot is never the busiest internal host.

D-039 wanted that diagnostic to pass before any per-host-state run. As written, it did not: a
label-free per-host **maximum** never reached 0.70. The team has chosen to run the per-host
experiment anyway, and this entry records that choice. Here "host-local temporal" means **each host
against its own past**, which a maximum over hosts cannot express.

**The host-local block.** E21's six host-relative features, with the definitions unchanged
(`flow_features._host_relative_features`, trailing baseline 120 windows, trust after 10):
- per-host z of distinct ports and of distinct destinations, maximum over hosts;
- per-host flows over (1 + its trailing mean), maximum;
- hosts reaching a new peer;
- the most new ports on one host;
- new internal hosts.

They are label-free and causal. They are reused as they are, so no new feature is designed after
seeing CTU-13.
- **Build.** `scripts/build_ctu13_hostrel.py` computes them over each whole capture from the raw flows
  (they need each host's past, so they cannot be built in `build_ctu13.py`'s time chunks). It appends
  them to the existing matrix in `data/processed/ctu13_hostrel/`.
- **Build checks.** The 70 base columns must equal `data/processed/ctu13` exactly. On a small capture,
  the block must equal what `window_features(use_host_relative=True)` gives in one pass.

**Arms.** The E25 stack (RSSM, factorised target, 250 steps per fold, E25's folds) with D-041's window
positions. Seeds 42/43/44, 7 folds each, all on the GTX 1650.
- **G:** `configs/d042/ctu_global_window.yaml`, the 56 network-global inputs. Runs `d042-g-s<seed>`.
- **H:** `configs/d042/ctu_hostrel_window.yaml`, the 56 plus the 6 host-relative features (62).
  Runs `d042-h-s<seed>`.
- Both read `data/processed/ctu13_hostrel`, so the only difference between them is the input block.
- LR on each input set: `lr-d042-g`, `lr-d042-h`, by `scripts/lr_baseline.py`.

Command, per arm and seed:
`python scripts/train.py --data data/processed/ctu13_hostrel --model-config configs/d042/ctu_<arm>_window.yaml --group-folds configs/ctu13_folds.yaml --run d042-<g|h>-s<seed> --seed <seed> --no-figures`.

**The rule, fixed here.** It uses ROC-AUC of the stored `comp` score on `y_within_K`, per held-out
scenario, as E25b did.
- **Deciding scenarios:** D-039's s08 (Murlo), s07 (Sogou) and s11 (Rbot).
- **H helps on a scenario** if ROC(H) - ROC(G) >= +0.10 on at least 2 of 3 seeds, paired by seed.
- **The result is "host-local state helps"** only if both hold:
  - H helps on at least 2 of the 3 deciding scenarios;
  - nothing regresses: no scenario where G has ROC >= 0.70 on at least 2 seeds has H below 0.70 on at
    least 2 seeds.
- **Otherwise the result is "does not help".**

**Reported beside it, not deciding.**
- D-037's family verdicts for G and for H.
- S2\* where a scenario has at least 20 cells, and S3.
- LR's H against G.
- G against E25b, which is the positional change alone, descriptive.
- The per-scenario uncertainty below.

**Uncertainty (board item: confidence intervals on the final CTU table).**
- **Method:** a moving-block bootstrap over each scenario's windows. Blocks are 20 windows (2K, 10
  min), with 2,000 resamples and a percentile 95 % interval on ROC-AUC. A resample with only one class
  is dropped and counted.
- **Sensitivity:** block lengths 10 and 40.
- **Applied to:** E25b's final table (each world-model seed, the three-seed mean score, and LR) and
  to D-042's arms.
- **Also reported:** the range across seeds, which is a separate source of uncertainty.

**Predictions, written before any run.**
- s08 is unlikely to move. The Murlo bot host is active in 2,185 of 2,339 windows from the start of
  the capture, so its own past is already infected and gives no clean baseline.
- s07 (44 windows) and s11 (34) give each host at most 24-34 windows of past after the 10-window
  warm-up.

**What either result licenses.**
- **"Helps":** per-host temporal information is recorded as M2 evidence. It does not by itself open a
  GNN (D-039 asks for relational structure beyond per-host features), and the architecture decision
  waits for M3, as the team has said.
- **"Does not help":** host-relative summaries in the global state do not fix cross-family inversion.
  The per-host-sequence model, with each host as its own sequence and a window's risk the maximum
  over hosts, remains untested and would need its own entry.

**Not allowed.** No change to the baseline length, the minimum history or the feature list. No
feature selection. No reruns except `--resume` after a crash.

**Outcome (2026-09-28, results.md "D-042"): does not help.**
- H helps on 1 of the 3 deciding scenarios: s07, +0.44 and +0.50 on seeds 43/44.
- s08 and s11 do not move.
- Two scenarios G transfers on regress: s05 (10 background windows) and s06 (6).
- Elsewhere the block moves families both ways: Rbot s04 up on every seed, Rbot s10 down on every
  seed (-0.21 to -0.27).
- Per this entry's "does not help" branch, the per-host-sequence model stays untested and deferred,
  and the architecture decision waits for M3.
- The uncertainty tables (the board's confidence-interval item) are in results.md, "E25b with
  confidence intervals".

### D-044 — M3 on CIC-IDS2018: data handling, and the pre-registration (6 family folds x 3 seeds, GTX 1650)
*Date: 2026-09-29 · Status: pre-registered before the build and before any training · Evidence to come:
results.md "E28 - M3" · Numbered D-044 because D-043 is in use by another session's check-4 work*

**Why.** D-039 named M3 the next transfer test, and asked whether the E25b inversion pattern recurs.
CIC-IDS2018 keeps the full 70-feature S_t v1 state that CTU-13 could not supply, and has compromise
onsets. The download was approved in chat (research/cicids2018.md: sha256, inspection). At the user's
request everything runs on this machine (GTX 1650, 4 GB), one heavy job at a time.

**Part A: data handling, fixed before the build.** Evidence: `results/runs/m3-inspect/inspect.json`.
- **Release.** The corrected CSVs (Liu et al., CNS 2022) have the corrected CIC-IDS2017 release's
  exact 91 columns. So `netwm.data.cicids2018` reuses its column map, its `- Attempted` handling (D-009)
  and its stage mapping. Timestamps are UTC. The victim network is 172.31.0.0/16 (the internal prefix).
- **Two rules drop rows; the build counts them per day.**
  1. **Flows stamped before the file's capture date (UTC midnight) are dropped:** 2,609 in feb23's
     file, dated 21-22 February, none of them attack traffic. Left in, they would stretch the day's
     window grid over three days. Flows after midnight UTC belong to the same night's capture and stay.
  2. **The single flow labelled `-1` (feb28) is dropped.** Its stage is not guessed.
- **One new mapping rule.** `Infiltration - Communication Victim Attacker` becomes Command and Control
  (T1571), not the generic infiltration stage: it is the victim calling 13.58.225.34:31337.
  - No CIC-IDS2017 label contains "communication", so M1 is unchanged; this was checked on the raw
    CSVs.
  - Every other 2018 label already maps, and `tests/test_cicids2018.py` covers them.
  - Because D-009 demotes attempted traffic, all FTP brute force (14-02, 16-02) contributes no attack
    stage.
- **Families, by day.** BruteForce {feb14}, DoS {feb15, feb16}, DDoS {feb20, feb21}, Web {feb22,
  feb23}, Infiltration {feb28, mar01}, Botnet {mar02}. Only feb28, mar01 and mar02 contain compromise
  stages.
- **Build** (`scripts/build_cicids2018.py`, `configs/cicids2018.yaml`). The same S_t v1, 60 s windows at
  a 30 s stride, and K = 10 as CIC-IDS2017, built in two passes (hourly shards on D:, then an hour of
  windows at a time). Two checks:
  - `--check-chunking` on one day: identical matrices at 120- and 17-window chunks.
  - Per day: the window flow counts equal twice the rows, less the flows in the first 30 s.

**Part B: the M3 experiment, pre-registered.**
- **Folds.** Leave one attack family out: 6 folds (`configs/cicids2018_folds.yaml`). Each trains on
  every other day.
- **World model.** E25's stack (RSSM, factorised target, `target_steps: 250`) with D-041's window
  positions, on all 70 S_t v1 inputs (`configs/m3/m3_stack.yaml`). Seeds 42/43/44, runs
  `m3-s{42,43,44}`:
  `python scripts/train.py --data data/processed/cicids2018 --model-config configs/m3/m3_stack.yaml
  --group-folds configs/cicids2018_folds.yaml --run m3-s<seed> --seed <seed> --no-figures`.
- **Baseline.** LR on the same inputs, folds and scaler (`scripts/lr_baseline.py`, run `lr-m3`).
- **Target and score per held-out day, fixed by the day's content.** On a day with no compromise stage,
  `y_within_K` is zero everywhere, so:
  - **Compromise days (feb28, mar01, mar02):** the ROC-AUC of the stored `comp` score on `y_within_K`,
    as E25b.
  - **Attack-only days (the other seven):** the ROC-AUC of the stored `threat` score (the attack
    channel, as the D-035 scorecard uses) on `y_attack_within_K`.
  - Beside it: PR-AUC and causal F1 (causal expanding q90) on the same target and score; the number of
    background windows; S2\* (threat percentile of non-Impact attack onsets) where a day has at least
    20 cells; and S3.
  - **Uncertainty:** D-042's moving-block bootstrap (blocks of 20 windows, 2,000 resamples) on each
    day's primary ROC-AUC, per seed, for the seed mean and for LR.
- **Family verdicts.** D-037's rule on the primary ROC-AUC, applied as written: transfers / inverted /
  partial.
- **D-039's question, answered by a rule fixed here.**
  - **"The inversion pattern recurs on the full state"** if at least 2 families are inverted, and at
    least one of those inversions is on a day with at least 100 background windows whose seed-mean
    interval lies wholly below 0.5.
  - **"It does not recur"** if no family is inverted.
  - **"Inconclusive"** otherwise: one inverted family, or inversions only on thinly measured days.
- **Stated in advance.**
  - The web days hold about 200 attack flows each, so their positives are few, and their verdicts are
    reported with that caveat.
  - A pooled number is never quoted without the family matrix beside it.
- **Not allowed.** No tuning; no change to folds, targets, rule or budget after a result is seen; no
  reruns except `--resume` after a crash; no per-host or graph model, whatever M3 shows (that decision is
  the team's, after M3).

**Amendment (2026-09-29, after the build and before any training; no model result has been seen).**
- **The `-1` flow does not exist.**
  - The inspection's first pass over feb28 read 143 rows fewer than the file holds, plus one garbled
    row labelled `-1`.
  - A second pass with the same settings reads all 6,568,726 lines, and none carries a `-1` label.
  - The build, which read the file independently, counted 6,568,726 flows and dropped nothing on feb28.
  - The bytes read from the external D: drive therefore differed on that one pass: a transient read
    error.
  - Rule 2 of Part A drops nothing. `research/cicids2018.md` and `inspect.json` are corrected (the first
    read is kept there).
- **Integrity checks run.**
  - All ten extracted CSVs match the zip's CRC32 (`results/runs/m3-build/extracted_crc_check.log`).
  - The chunking check passed on feb15: identical matrices over 1,544 windows.
  - Every day passed the build's flow-count check; 63,195,145 flows in, and 2,609 dropped by rule 1.
- **One step added before training.** A read error during the build would pass the flow-count check if
  it changed a value rather than a row. So the build is repeated into `data/processed/cicids2018_verify`
  (`configs/cicids2018_verify.yaml`) and must be byte-identical to the first
  (`scripts/compare_builds.py`) before any M3 run starts. If it is not, the differing days are rebuilt
  and compared again; nothing trains on an unverified matrix.
- **Scheduling.** One job at a time: the verification build, the comparison, `m3-s42`, `m3-s43`,
  `m3-s44`, `lr-m3`, then `scripts/m3_family_matrix.py`. The analysis script implements Part B as
  written.

**Outcome (2026-09-29, results.md "E28 - M3"): D-039's question is inconclusive under this entry's rule.**
- One family is inverted: Infiltration, on feb28 across all three seeds. Seeds 42/43 lie wholly below
  0.5, but the seed-mean interval [0.30, 0.53] touches it, so the inversion is not well measured by the
  rule.
- The attack families transfer or partly transfer: BruteForce and DoS transfer; DDoS, Web and Botnet
  are partial.
- The failure M3 shows is the compromise score on an unseen compromise family, where LR is not
  inverted.
- S3 is met nowhere.
- The architecture decision is the team's.

### D-045 — N-7, the architecture decision: stay with the Transformer + RSSM world model; no per-host model and no GNN
*Date: 2026-09-29 · Status: accepted (team decision, N-7) · Evidence: D-039, D-042's outcome, E25b and its
intervals, E28 (D-044's outcome), E26 · D-039 stands; D-043 is another session's check-4 work*

**Decision.**
- The submission architecture is the one that ships after D-041 (`docs/architecture.md` §3):
  - an encoder, then a Transformer encoder over the last 16 windows (window positions, state carried
    across chunks);
  - the RSSM latent, with its next-state decoder, stage head and risk heads;
  - all on the network-global state `S_t`.
- Both served routes stay as they are: CSV r2w seed 42, PCAP the E20rw mean of seeds 42/43/44.
- No per-host model and no GNN is built before the submission freeze. Both are future work.
- No further training run is started to improve the compromise result.
- The project moves to the freeze: the M1-M3 evidence manifest and its tag, then the submission
  artefacts and a final end-to-end demo test.

**Why.**
- **The cheapest host-local test has run, and it failed its rule (D-042).** It added E21's six
  host-relative features beside the global state.
  - It helped on 1 of the 3 deciding scenarios: Sogou s07, on seeds 43/44.
  - Murlo (s08) and Rbot s11 did not move.
  - Two scenarios where the global state transfers regressed: s05 and s06.
  - Its other effects were family-specific: Rbot s04 rose on every seed, and Rbot s10 fell on every
    seed.
- **M3 narrows the problem (E28).** On the full 70-feature state:
  - **The held-out attack families carry.** BruteForce and DoS transfer by D-037's rule; DDoS and Web
    partially.
  - **The compromise families do not.**
    - Botnet is partial, and below LR (family mean ROC-AUC 0.72 against 0.82).
    - Infiltration is inverted on feb28 (0.26-0.42 across seeds), where LR is not (0.59).
  - **D-039's question is inconclusive** by D-044's rule: one inverted family, whose seed-mean
    interval touches 0.5.
  - So there is no longer evidence that the global-state representation is broadly broken. CTU-13's
    five inverted families were measured on a 56-feature Argus state (E25b).
- **The weakness that persists is specific: the compromise score on an unseen compromise family.** It
  shows in three places:
  - CIC-IDS2018's Infiltration and Botnet (E28);
  - CIC-IDS2017's Friday C2, near floor for every model (E27; after D-041 the served routes' Friday
    PR-AUC is 0.12 and 0.14, `results/tables/n8_fix_eval.csv`);
  - most CTU-13 families (E25b).
  Early warning against the null (S3) is met on none of the three datasets.
- **No result shows that a per-host or graph representation would fix it.**
  - D-039 set an order: a per-host state first, then a GNN only after a per-host run passes and
    relational structure is shown to matter beyond per-host features.
  - D-042 was that per-host run, in its cheapest form, and it did not pass.
  - The per-host-sequence model has no result either way. In it, each host is its own sequence and a
    window's risk is the maximum over hosts.
- **A GNN would be a new research project, not a controlled correction.** It changes several things
  at once:
  - how hosts are identified;
  - how the graph and its edges are built;
  - message passing and temporal graph dynamics;
  - the training and evaluation protocol.

  Showing that a gain came from relational structure, and not from one more dataset-specific effect,
  would need its own pre-registered programme on all three datasets. That cannot be evaluated fully
  before the freeze.

**What this does not say.**
- It does not say the current model is strong across families. On compromise it is not.
- It does not say a GNN or per-host model was tried and found wanting. Neither has been trained.
  - No document, slide or answer may imply that one was tested.
  - The wording is "deferred, untested".

**The account the submission gives (D-035's language).**
- The world model learns network dynamics: its rollouts beat "nothing changes" over steps 2-10 (E10).
- Detection transfers unevenly across families. On the full state it carries to unseen attack
  families (E28).
- Compromise transfer to an unseen family is weak.
- It ranks pre-attack windows above background. Early warning against the null has not been
  demonstrated (D-021).

**Revisit if (after the submission).**
- **A per-host model.** A pre-registered per-host-sequence run beats its global-state arm on the unseen
  compromise families (CTU-13 s08 and s11; CIC-IDS2018 feb28 and mar01), by a rule like D-042's. It
  must not regress the families that transfer.
- **A GNN.** Only after that run passes, per D-039, and only if relational structure is then shown to
  matter beyond per-host features.
