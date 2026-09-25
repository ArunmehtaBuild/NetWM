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

**Decision.** Flask backend, no build step, all JS/CSS assets vendored into `app/static/vendor/`.

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
*Date: 2026-09-24 · Status: provisional · Evidence: E13*

**Decision.** The alarm statistic is `max_k P(compromised at t+k)` over the K imagined steps rather
than the cumulative union `1 - prod(1 - p_k)`.

**Why.** The compromise head answers "is this state compromised", a property that *persists*, so the
union formula multiplies the same event K times and saturates near 1 - which is why the training-day
score distribution has no headroom and the 5 % alert budget landed at 0.977. Empirically (E13) the
ranking is nearly identical across statistics, but only the max produces any early warning
(2 of 4 Thursday episodes, at an oracle threshold).

**Also decided.** Thursday's four onsets are 639, 658, 708 and 729 - separated by only 10-20 windows,
with attack traffic in between. Only the **first onset of an episode chain** is a genuine
"before the attacker got in" case; the rest are re-entries. Lead time is therefore reported per
episode (never as a single mean) and the first-onset value is quoted separately.

**Revisit when.** The proper fix is a first-occurrence hazard target (`1` only at the *first*
compromise window after t, `0` afterwards), which would make the union formula correct. That is the
first item of round 3.

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
