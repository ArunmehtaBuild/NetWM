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

**Revisit if.** Calibration (temperature scaling on a held-out training day) closes the gap - then
we can quote probabilities honestly and drop the budget.

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

