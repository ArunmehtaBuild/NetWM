# NetWM — AI Network Attack Forecasting with a World Model

**SIH 2026 · PS 26153 · NTRO · Theme: Blockchain & Cybersecurity**

NetWM learns the *dynamics* of a network — how its state evolves from one time window to the
next — instead of classifying flows in isolation. From a stream of traffic telemetry it builds a
state `S_t`, learns `P(S_{t+1} | S_t)`, rolls that model forward K steps, and answers:

> *"Given what the network looks like right now, what is the probability that an infiltration
> completes in the next K windows, which MITRE ATT&CK stage are we heading into, and which flags,
> ports and flow statistics are driving that forecast?"*

```
 flows (CSV) ─┐
              ├─► windowing (60 s / 30 s stride) ─► state S_t ─► world model ─► K-step rollout ─► forecast
 packets (PCAP)┘        + MITRE stage labels          (~80-d)     (RSSM-style)    (Monte-Carlo)     + explanation
```

## Status

Early build. M1 = CIC-IDS2017. See [decisions.md](decisions.md) for every modelling decision and
why it was made, [research.md](research.md) for the literature/dataset research behind them, and
[results.md](results.md) for experiment results (figures and CSVs live in `results/`).

## Roadmap

| Milestone | Dataset | Purpose |
|---|---|---|
| M1 | CIC-IDS2017 | PCAP + flows → `S_t` → world model → K-step rollout |
| M2 | CTU-13 | scenario-held-out temporal evaluation |
| M3 | CIC-IDS2018 | larger enterprise-style validation |
| M4 | UNSW-NB15 | cross-domain generalisation |

## Layout

```
src/netwm/         the ML
  data/            dataset adapters (cicids2017, ctu13, ...)
  features/        flow features, trend block, per-host channel, windowing, scaler
  labels/          MITRE ATT&CK stage mapping
  models/          world model, baselines, targets, lead-time null
  engine/          rollout, explainability, inference (predict.analyze_file)
scripts/           get_data, build_features, train, predict, benchmark, eval, sync_fixtures
backend/           FastAPI JSON API - renders nothing
                     uvicorn backend.server:app --host 127.0.0.1 --port 5000
frontend/          static dashboard - no build step, no backend needed to develop
                     python -m http.server 8080
fixtures/api/      the canonical payloads shared by the API, the UI and the contract tests
configs/           feature + model configs (v1 frozen; trend, hosts, r3, r4 are separate)
docs/              api_contract.md, architecture.md, submission artefacts
research/          research notes  ->  indexed by research.md
results/           figures + CSVs + per-run metrics  ->  indexed by results.md
models/            checkpoints (r2 is the submission checkpoint)
tests/             ML tests · backend/tests/ API + contract + offline tests
```

## Run the demo

```bash
run_demo.bat                 # starts the API on :5000 and the dashboard on :8080
```

Or separately:

```bash
uvicorn backend.server:app --host 127.0.0.1 --port 5000
python scripts/sync_fixtures.py && cd frontend && python -m http.server 8080
```

Everything runs offline. With no checkpoint present the API still serves `fixtures/api/*.json`
marked `"mock": true`, so the dashboard is never undemoable.

## Setup for a Fresh Machine

Follow these exact steps from a clean clone to get the dashboard running locally.

**1. Clone the repository and install dependencies:**

```bash
git clone https://github.com/your-org/netwm.git
cd netwm
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

*(Torch is installed separately for CUDA, e.g., `pip install torch --index-url https://download.pytorch.org/whl/cu121`)*

**2. Fetch the dataset:**

This downloads ~328 MB and extracts it to `data/raw/cicids2017_improved/`. We use the **corrected** CIC-IDS2017 re-extraction (see decisions.md D-001).

```bash
python scripts/get_data.py
```

**3. Build the feature matrices:**

```bash
python scripts/build_features.py --config configs/cicids2017.yaml
```

**4. Run the demo:**

This starts both the FastAPI backend on `:5000` and the frontend dashboard on `:8080`.

```bash
run_demo.bat
```

Everything runs completely offline. You can also upload PCAP captures (like the included 5MB demo PCAP) directly in the dashboard UI!
