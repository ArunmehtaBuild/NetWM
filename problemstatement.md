# SIH 2026 - Problem Statement 26153

| field | value |
|---|---|
| **Problem Statement ID** | **26153** |
| **Title** | AI based Network Attack Forecasting from Network Traffic Data |
| **Organisation** | National Technical Research Organisation (NTRO) |
| **Department** | National Technical Research Organisation (NTRO) |
| **Category** | Software |
| **Theme** | Blockchain & Cybersecurity |
| **YouTube link** | none provided |
| **Contact info** | none provided |
| **Dataset link** | Check nciipc.gov.in; helpdesk1@nciipc.gov.in |

**Datasets named by the organisation:** CIC-IDS2017/2018, UNSW-NB15, CTU-13, CICIoT2023, LANL
Authentication Dataset, DARPA Intrusion Detection datasets, together with public knowledge bases
such as MITRE ATT&CK, CAPEC, CVE/NVD and other open cybersecurity resources.

> Verbatim from the SIH portal (2026-09-25), mojibake dashes normalised. Everything in this repo is
> written against this document; `research/` and `decisions.md` explain where we go beyond it and why.

## Description

### Background

This challenge seeks AI systems capable of learning network behaviour, anticipating attacker
progression and supporting proactive cyber defence using the emerging concept of World Models.
Design and develop a software prototype that learns the evolving state of a computer network from
traffic telemetry and predicts the likelihood and progression of malicious activity before
compromise is completed. The solution should ingest network traffic, learn temporal behaviour,
forecast future attack states and provide interpretable decision support for defenders. Solutions
should demonstrate applicability to enterprise environments and Critical Information Infrastructure.

- Represent network state using feature vectors or graphs.
- Learn state-transition dynamics using sequence models (LSTM, Transformer), Graph Neural Networks,
  latent state models or other AI techniques.
- Forecast future network states and estimate the probability of attacker progression.
- Map predicted behaviour to recognised attack stages (e.g. MITRE ATT&CK).
- Provide explainability using attention mechanisms, feature attribution or equivalent techniques.

### Detailed description

Participants are encouraged to build world-models-based AI systems that move beyond static intrusion
classification towards predictive cyber defence. The solution may utilise flow records, packet
captures, authentication logs or other publicly available cybersecurity telemetry. It should model
temporal relationships, infer evolving network state, predict future attack progression and present
meaningful explanations for its predictions.

Traditional machine learning classifiers applied to network traffic treat each flow in isolation and
map it to a binary benign/malicious label. This discards the temporal and causal structure of an
infiltration: the sequence in which ports are probed, the pattern in which SYN flags precede ACK
floods, the inter-arrival timing of reconnaissance packets before lateral movement begins. An
infiltration is a process unfolding over time, not a single anomalous packet.

World Models - AI architectures that learn an internal causal simulation of how environment states
evolve - offer a fundamentally different approach. Rather than classifying traffic, a world model
learns the transition dynamics P(S_t+1 | S_t): given the current observed network state (active
flows, flag distributions, port activity, packet timing), what is the probability distribution over
future states. This enables forward simulation: roll out K steps ahead and identify whether the
current trajectory converges to an infiltration state, before the attacker completes the kill chain.

### 1. Input data - two levels of traffic feature

Teams must work with both flow-level and packet-level features drawn from open-source network
traffic datasets:

- **Flow-level features (NetFlow / IPFIX format):** source and destination IP/port pairs, TCP flag
  bitmask (SYN, ACK, FIN, RST, PSH, URG), protocol, bytes transferred per flow, packets per flow,
  flow duration, inter-arrival time (IAT) statistics (mean, variance, max), and bidirectional flow
  ratios.
- **Packet-level features (PCAP-derived):** Time-To-Live (TTL) values and their variance across a
  session, TCP window size, IP fragment flags, payload size distribution, port scan signatures
  (sequential or randomised port access patterns), and retransmission counts.

The combination of both levels is required because flow-level features capture aggregate behaviour
(a SYN flood) while packet-level features expose timing and sequencing patterns (a slow
reconnaissance scan designed to evade flow-based thresholds).

### 2. World model architecture

The core deliverable is a learned model of network state transition dynamics - not a static
classifier. The model must:

- Represent network state as a structured feature vector or graph encoding active flows at time t.
- Learn P(S_t+1 | S_t) - the probability distribution over the next network state given the current
  state - using a sequence model such as an LSTM, Temporal Transformer, or Graph Neural Network
  (GNN) operating over time-windowed traffic observations.
- Be trained on labelled open-source datasets using supervised dynamics learning, where ground-truth
  state transitions are derived from the attack timeline annotations in the dataset.
- Generalise to unseen attack patterns - not merely memorise signatures from the training set.

### 3. Infiltration prediction and attack stage mapping

The world model must support forward simulation: given current observed traffic, roll out K steps
and output

- A time-series probability score: likelihood of infiltration in the next K time windows.
- Predicted attack stage: mapping to MITRE ATT&CK phases - Reconnaissance, Initial Access, Lateral
  Movement, Command & Control, or Exfiltration - based on the predicted future state.
- Driving features: which specific flags, ports, or flow patterns are contributing most to the
  infiltration prediction (via attention weights or SHAP values).

The approaches are provided only as examples and are not mandatory. Teams are free to propose
alternative architectures that satisfy the objectives.

## Expected solution (indicative)

A software-based, fully open-source solution is expected. The solution may include:

- A feature extraction pipeline that ingests CIC-IDS-2018 or CTU-13 CSV flow records and/or raw PCAP
  files (parsed using Scapy or PyShark) and outputs a timestamped, normalised feature matrix covering
  both flow-level and packet-level attributes described above.
- A trained world model (LSTM, Transformer, or GNN architecture) that demonstrably learns traffic
  state transition dynamics - not a static input-output classifier. Training scripts, model weights,
  and a reproducible training configuration must be included.
- An infiltration prediction engine that performs K-step forward simulation from a current traffic
  snapshot and outputs: infiltration probability score, predicted MITRE ATT&CK stage, and top
  contributing traffic features.
- An explainability output for each prediction - using SHAP values or model attention weights -
  identifying which flags, ports, or flow statistics are driving the prediction. Black-box outputs
  without interpretability are not acceptable.
- A working demonstration interface (Streamlit, Flask web app, or CLI) that accepts a PCAP or CSV
  file as input, runs the world model inference, and displays the infiltration probability timeline,
  flagged flows, and attack stage annotations. The interface must run fully offline without cloud API
  dependencies.
- Benchmark results comparing model performance (F1 score, precision, recall, false positive rate)
  against a logistic regression baseline trained on the same features, demonstrating that the world
  model temporal dynamics learning provides measurable improvement.

## Deliverables for evaluation

- Source code link (GitHub / Drive link)
- Readme with setup instructions
- Architecture document (max 2 pages)
- Demo video (max 2 minutes)
- Technical presentation (max 5 slides)

## How this repo maps to the requirements

| PS requirement | Where it lives | State (updated 2026-09-27, after D-035 / E19-E25) |
|---|---|---|
| Feature extraction, flow level | `src/netwm/features/flow_features.py`, `windowing.py`, `scripts/build_features.py` | done - 70-feature `S_t` from the corrected CIC-IDS2017 CSVs |
| Feature extraction, packet level (PCAP via Scapy) | `src/netwm/features/packet_windows.py`, `scripts/build_packet_features.py`, `flow_features.PACKET_CSV_FEATURES`, `flow_aggregator.py` | **done and measured** - 18 features from the five real day captures (TTL, fragments, retransmissions, windows, payload histogram, timing, SYN/RST) plus 17 CSV packet statistics. They help detection (Thursday PR-AUC 0.43 -> 0.56, E20r), not anticipation. The shipped checkpoint is still flow-only (needs a `has_pcap` mask) |
| World model, P(S_t+1 given S_t) | `src/netwm/models/world_model.py`, `src/netwm/train.py`, `configs/` | done - Transformer encoder + RSSM latent; rollout beats persistence averaged over steps 2-10 (E5, E10); the latent dynamics beat a same-encoder model without them on every seed (E24), though logistic regression ranks pre-onset windows as well as round 2 (0.66 vs 0.65, E26); the world model's edge is detection at usable alarm cost and the factorised target's anticipation gain |
| Generalise to unseen attack patterns | leave-one-day-out (CIC-IDS2017), leave-one-family-out (CTU-13, E25) | **partial** - pre-onset windows rank above background on held-out days (S2\* 0.70, E22), but no early warning beats a shuffled-time baseline; on CTU-13 anticipation does not transfer across botnet families (0.55) and detection transfers to 3 of 7 families |
| K-step forward simulation + infiltration score | `src/netwm/engine/predict.py`, `models/world_model.forecast` | done - reported as a risk score, not a calibrated probability (E17) |
| MITRE ATT&CK stage mapping | `src/netwm/labels/mitre_map.py`, `research/mitre-mapping.md`, stage head | produced and **measured (E9)** - high recall only where a relative family was in training (DDoS 0.99); 0 for Lateral Movement and C2, which no training fold contains; the internal sweep is recognised as T1046 at precision 0.885 |
| Explainability (attention + attribution) | `src/netwm/engine/explain.py` | done, **sanity check fails (E11)** - the known signature is in the top 8 attributions on 1 of 6 episodes; the panel is labelled "features pushing the compromise score" |
| Offline demo interface, CSV or PCAP upload | `backend/` (FastAPI) + `frontend/` (static), `run_demo.bat` | done - CSV live; PCAP runs, demo PCAP pending (A-5b) |
| Benchmark vs logistic regression (F1, precision, recall, FPR) | `scripts/benchmark_baselines.py`, `scripts/rescore_pmax.py`, `results.md` E3/E14/E10 | numbers exist; **one consolidated table** still to write |
| Reproducible training config + weights | `configs/`, `models/e4e7-worldmodel-r2/`, commands in `results.md` | done |
