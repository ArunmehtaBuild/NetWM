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
configs/           experiment configs (YAML)
data/raw|interim|processed
scripts/           download, build features, train, benchmark (CLI entry points)
src/netwm/
  data/            dataset adapters (cicids2017, ctu13, ...)
  features/        flow + packet feature extraction, windowing, scaling
  labels/          MITRE ATT&CK stage mapping
  models/          world model, baselines
  engine/          rollout, explainability, inference
app/               offline Flask demo (vanilla JS + vendored Chart.js)
research/          research notes  →  indexed by research.md
results/           figures + CSVs  →  indexed by results.md
tests/
```

## Setup

```bash
python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
```

Torch is installed separately for CUDA (GTX 1650 / CUDA 12.1):

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

## Data

One command, ~328 MB download, ~1.1 GB extracted into `data/raw/cicids2017_improved/` (gitignored):

```bash
python scripts/get_data.py          # download + sha256 verify + extract
python scripts/get_data.py --check  # report what is on disk, download nothing
```

This fetches the **corrected** CIC-IDS2017 re-extraction, not the CIC original - the original
mis-terminates TCP flows and mislabels attack onsets, and onset time is the quantity we predict
(decisions.md D-001, research/cicids2017.md). The checksum is pinned: every published number in
`results.md` assumes that exact archive.

Then build the state matrices:

```bash
python scripts/build_features.py --config configs/cicids2017.yaml
```

Training and demo instructions are in `plan.md` and `docs/architecture.md`.
