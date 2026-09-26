# Build plan

Milestones follow the dataset ladder: **M1 CIC-IDS2017 -> M2 CTU-13 -> M3 CIC-IDS2018 -> M4 UNSW-NB15**.
M1 delivers the complete PS 26153 system end to end; M2-M4 are evaluation/generalisation milestones on
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
- [x] `features/windowing.py` + `scaler.py` (log1p + z-score; per-capture rank mode from S-4)
- [x] S_t v2 trend block (94 features) and per-host channel (82) behind their own configs
- [x] `labels/mitre_map.py` - label -> stage, ordered scale, scan-direction refinement
- [x] `scripts/build_features.py` -> parquet feature matrix + meta.json

### P3. Models
- [x] `models/baseline.py` - logistic regression (PS-mandated) + persistence baseline (E2, E3)
- [x] `models/world_model.py` - encoder, causal attention, RSSM, decoder, stage + compromise heads
- [x] `train.py` - losses (NLL + KL free bits + imagination + CE + BCE), checkpoints
- [x] E2-E15 run: baselines, world model r1/r2, precursor r3 (rejected), null calibration

### P4. Forecasting, evaluation, explainability
- [x] K-step MC rollout in `models/world_model.forecast` -> cumulative curve + bands + stage path
- [x] `metrics.py` - F1 / precision / recall / FPR / PR-AUC / lead time
- [x] `evaluate.py`, `scripts/benchmark_baselines.py`, `rescore_pmax.py`, `precursor_eval.py` - leave-one-day-out with null calibration
- [x] E8 formalised as its own leave-one-attack-family-out experiment (Y-3) - *Closed by D-006 amendment*
- [x] `engine/explain.py` - attention weights + Integrated Gradients (SHAP for the LR baseline pending)
- [ ] E10 ablations (Y-4, after the r4 feature-transform result)

### P5. Demo + deliverables
- [x] `engine/predict.py` + `scripts/predict.py` - one entry point shared by the CLI and the API
- [x] FastAPI backend (R-1..R-7) + static dashboard (H-1..H-9): upload, timeline, cone, stage ribbon,
      alarm log with lead time, attribution, attention, flows table, SSE replay
- [~] Demo CSV slices exist (`data/demo/`, index.json); the PCAP slice waits on A-2/A-3
- [~] README + `docs/architecture.md` drafted; slides and the 2-minute video outstanding

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

## Sub-plans

- **Backend:** [backend/PLAN.md](backend/PLAN.md) - job lifecycle, model registry, threshold
  policy passthrough, offline guarantee, error codes, tests.
- **Frontend:** [frontend/PLAN.md](frontend/PLAN.md) - panel-by-panel spec, data flow, design
  tokens, empty/error states, vendoring rules.
- **API contract:** [docs/api_contract.md](docs/api_contract.md) v1.1 - the boundary both sides code to.

## Working rules
See [CLAUDE.md](CLAUDE.md). Short version: decisions -> decisions.md, numbers -> results.md +
results/, findings -> research/.
