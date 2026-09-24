# Team tasks - NetWM (SIH 2026, PS-153)

Six people, six tracks, four sprints. The tracks are built around **what has to exist**, not around
job titles - a couple of people are working outside their usual lane on purpose, because the
critical path needs it.

| person | track | owns |
|---|---|---|
| **Sanchi** | A - State & features | flow features, windowing, the `S_t` matrix everything trains on |
| **Yash** | B - World model | RSSM model, training loop, K-step rollout engine |
| **Atharv** | C - Evaluation & explainability | metrics (incl. lead time), benchmark harness, IG/SHAP outputs, decisions log |
| **Alok** | D - Packet pipeline & baselines | PCAP parsing, PCAP->flows, logistic-regression + persistence baselines, packaging |
| **Arun** | E - Backend | Flask API, job runner, inference service, mock server, offline packaging |
| **Harshit** | F - Frontend | the SOC dashboard: timeline, forecast cone, kill-chain ribbon, flows table, explain panels |

> **Swap freely.** If a name fits a different track better, swap the *names*, not the track
> definitions - the dependency graph below assumes the tracks, not the people.
> Frontend is one person by design: the second frontend pair works better split as
> **Harshit builds, Atharv reviews + owns the evaluation charts that feed it**. If you would rather
> have two on the UI, move Alok's baseline tasks to Yash after Sprint 1 and put Alok on F.

## What we are building (so everyone codes against the same picture)

**Backend (Arun)** - Flask, no cloud, no build step:
`POST /api/analyze` (CSV or PCAP upload) -> `job_id` -> background worker runs
feature extraction -> world-model inference -> K-step rollout -> explanation, writing progress to a
job store. `GET /api/jobs/<id>/result` returns the whole analysis as one JSON document;
`GET /api/jobs/<id>/stream` replays it window-by-window over SSE so the dashboard can *play* an
attack unfolding. Contract: [`app/api_contract.md`](app/api_contract.md) - **frozen on day 1**.

**Frontend (Harshit)** - vanilla JS + vendored Chart.js, single page, dark SOC theme:
1. **Upload / demo bar** - drop a CSV or PCAP, or pick a preloaded scenario.
2. **Forecast timeline** - observed infiltration probability, plus the K-step forecast cone
   (Monte-Carlo band), alarm threshold line, and ground-truth attack spans shaded when known.
3. **Kill-chain ribbon** - predicted MITRE stage per window as a colour band + a "current stage"
   card with the ATT&CK tactic/technique id.
4. **Why panel** - top driving features as an attribution bar chart, plus the attention heatmap over
   the last L windows ("which earlier moment made the model worried").
5. **Flagged flows table** - sortable, filterable, per-flow score, src/dst/port/flags.
6. **Alarm log** - each alarm with its lead time: *"fired 6 windows (3 min) before onset"*. This is
   the money shot of the demo video.
7. **Replay control** - play / pause / scrub, driven by the SSE stream.

**The parallelism trick:** Arun ships a **mock backend** on day 2 that serves hand-built JSON from
`app/mock/` matching the contract. Harshit then builds the entire UI without waiting for a model,
and swapping in the real model is a one-line change.

## File ownership (merge-conflict prevention)

| area | files | owner |
|---|---|---|
| features & state | `src/netwm/features/*`, `scripts/build_features.py`, `configs/features.yaml` | Sanchi |
| model & training | `src/netwm/models/world_model.py`, `src/netwm/train.py`, `src/netwm/engine/rollout.py`, `configs/model_*.yaml` | Yash |
| metrics & explain | `src/netwm/metrics.py`, `src/netwm/evaluate.py`, `src/netwm/engine/explain.py`, `scripts/benchmark.py` | Atharv |
| packets & baselines | `src/netwm/features/pcap_features.py`, `flow_aggregator.py`, `src/netwm/models/baseline.py`, `scripts/make_demo_samples.py` | Alok |
| backend | `app/server.py`, `app/jobs.py`, `app/mock/*`, `src/netwm/engine/predict.py` | Arun |
| frontend | `app/templates/*`, `app/static/*` | Harshit |
| shared (PR + a heads-up in chat) | `src/netwm/labels/*`, `src/netwm/data/*`, `src/netwm/utils.py`, `app/api_contract.md` | anyone |

Docs are shared but have rules (see [CLAUDE.md](CLAUDE.md)): decisions -> `decisions.md`,
numbers -> `results.md` + `results/`, findings -> `research/`.

## Sprint plan

Days are working days from kickoff; put real dates in when the deadline is fixed. Each sprint ends
with something runnable - **there is never a week where nothing is demo-able**.

### Sprint 0 - Day 1-2: everyone unblocked

| who | task | done when |
|---|---|---|
| Sanchi | **A1** venv + repo setup; read `decisions.md` D-001..D-012 and `results.md` E1 | audit reruns on your machine |
| Yash | **B1** torch cu121 installed, GPU smoke test; skim `research/world-models.md` | a 3-layer GRU trains on random tensors on the 1650 |
| Atharv | **C1** freeze the metric definitions (F1/precision/recall/FPR/PR-AUC/lead time) in `metrics.py` stubs + docstrings | signatures agreed, tests written first (they fail) |
| Alok | **D1** find a working CIC-IDS2017 Thursday PCAP mirror; report source + size before downloading | link posted, or fallback agreed |
| Arun | **E1** Flask skeleton + **mock backend** serving `app/mock/*.json` per `app/api_contract.md` | `curl /api/jobs/demo/result` returns the sample payload |
| Harshit | **F1** page shell, dark theme, layout grid, vendored Chart.js (no CDN) | page loads offline and renders the mock timeline |

### Sprint 1 - Day 3-6: the pipeline and the shell

| who | task | done when |
|---|---|---|
| Sanchi | **A2** flow feature extractor (flags, ports, entropy, IAT, bidirectional, host fan-out) + **A3** `scaler.py` (train-only fit) + **A4** `scripts/build_features.py` -> parquet | `S_t` matrix for all 5 days, documented feature dictionary in `research/features.md` |
| Yash | **B2** world model skeleton: encoder -> latent -> transition -> decoder/stage/hazard heads, forward pass on random data | shapes right, param count under 3 M |
| Atharv | **C2** metrics implemented + tested on synthetic cases; **C3** the split harness (leave-one-day-out, leave-one-family-out) | `pytest` green, splits print their day/label composition |
| Alok | **D2** logistic-regression + persistence baselines (E2, E3) on Sanchi's features | baseline numbers in `results.md` - the bar the model must clear |
| Arun | **E2** real job runner (upload -> background thread -> progress -> result), CSV path wired to the feature pipeline | uploading a real day CSV returns real window counts |
| Harshit | **F2** forecast timeline + cone + threshold line; **F3** kill-chain ribbon | both render from mock data, resize cleanly, colours come from `/api/model` |
