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
