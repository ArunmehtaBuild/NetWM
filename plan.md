# Build plan

Milestones follow the dataset ladder: **M1 CIC-IDS2017 -> M2 CTU-13 -> M3 CIC-IDS2018 -> M4 UNSW-NB15**.
M1 delivers the complete PS-153 system end to end; M2-M4 are evaluation/generalisation milestones on
top of the same code, reached through dataset adapters.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

## M1 - CIC-IDS2017: flows + packets -> state -> world model -> K-step rollout

### P0. Repo + research foundation
- [x] Repo skeleton, README, requirements, .gitignore
- [x] Research notes: dataset flaws, world models, MITRE mapping, related work
- [x] decisions.md D-001..D-008, results.md experiment plan
- [~] Python venv created, core deps installed; torch (cu121) not installed yet

### P1. Data
- [x] Download corrected CIC-IDS2017 (`CICIDS2017_improved.zip`, 328 MB) -> `data/raw/cicids2017_improved/`
- [ ] Locate a working source for the day PCAPs (Thursday = infiltration day is the priority)
- [x] `DatasetAdapter` interface + `cicids2017.py`: canonical schema, UTC, per-day loading, schedule
- [x] E1 dataset audit -> results (label counts, onsets, window counts, per-day timelines)

### P2. Features and state
- [x] `features/flow_features.py` - 70 per-window features (flags, ports, IAT, direction, beaconing, scan signatures)
- [ ] `features/pcap_features.py` - TTL variance, window size, fragments, payload histogram,
      retransmissions, scan signatures (streaming Scapy reader)
- [ ] `features/flow_aggregator.py` - PCAP -> flows, so the demo accepts a raw PCAP
- [x] `features/windowing.py` + `scaler.py` (log1p + z-score, train-only fit)
- [x] `labels/mitre_map.py` - label -> stage, ordered scale, scan-direction refinement
- [x] `scripts/build_features.py` -> parquet feature matrix + meta.json

### P3. Models
- [x] `models/baseline.py` - logistic regression (PS-mandated) + persistence baseline (E2, E3)
- [x] `models/world_model.py` - encoder, causal attention, RSSM, decoder, stage + compromise heads
- [x] `train.py` - losses (NLL + KL free bits + imagination + CE + BCE), checkpoints
- [~] E2-E3 done; E4-E5 (one-step NLL, rollout fidelity) running

### P4. Forecasting, evaluation, explainability
- [x] K-step MC rollout in `models/world_model.forecast` -> cumulative curve + bands + stage path
- [x] `metrics.py` - F1 / precision / recall / FPR / PR-AUC / lead time
- [ ] `evaluate.py` + `scripts/benchmark.py` - leave-one-day-out, leave-one-family-out (E6-E9)
- [x] `engine/explain.py` - attention weights + Integrated Gradients (SHAP for the LR baseline pending)
- [ ] E10 ablations

### P5. Demo + deliverables
- [x] `engine/predict.py` + `scripts/predict.py` - one entry point shared by CLI and the Flask API
- [ ] Flask app: upload CSV/PCAP, probability timeline, stage ribbon, flagged flows, explanations
- [ ] Demo sample files (small CSV + PCAP clipped from a test day)
- [ ] README setup instructions, architecture document (2 pages), 5 slides, 2-minute demo video

## M2 - CTU-13: scenario-held-out temporal evaluation
- [ ] `data/ctu13.py` adapter (bidirectional NetFlow, botnet scenarios)
- [ ] Real C2 + exfiltration ground truth replaces the M1 exfil heuristic (revisits D-003)
- [ ] Train on a subset of scenarios, test on held-out scenarios; report the same metric set

## M3 - CIC-IDS2018: enterprise-scale validation
- [ ] `data/cicids2018.py` adapter (corrected release, ~10 GB)
- [ ] Scaling: chunked feature building, multi-day training, runtime/memory numbers

## M4 - UNSW-NB15: cross-domain generalisation
- [ ] `data/unswnb15.py` adapter, feature harmonisation across schemas
- [ ] Zero-shot transfer (train 2017 -> test NB15) and fine-tune; report the drop honestly

## Working rules
See [CLAUDE.md](CLAUDE.md). Short version: decisions -> decisions.md, numbers -> results.md +
results/, findings -> research/.
