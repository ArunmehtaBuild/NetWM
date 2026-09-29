# NetWM: network attack forecasting with a world model

**SIH 2026 · Problem Statement 26153 (NTRO) · AI based Network Attack Forecasting from Network Traffic Data**

NetWM learns the *dynamics* of a network: how its state evolves from one time window to the next. It
does not classify flows one at a time. It turns traffic (flow CSVs or raw PCAPs) into a state `S_t` per
60 s window and learns `P(S_{t+1} | S_t)` with a Transformer encoder and an RSSM latent. It then rolls
that model 10 windows (5 minutes) forward, and answers three questions for every window:
- how at risk the network is of a compromise in the next 5 minutes;
- which MITRE ATT&CK stage it is heading into;
- which flags, ports and flow statistics drive that score.

Everything runs offline: a FastAPI backend and a static dashboard that accepts a CSV or a PCAP.

## Submission contents

| PS 26153 deliverable | where |
|---|---|
| Source code | this repository, tag `submission-freeze` (training, inference, API, dashboard, tests) |
| Readme with setup instructions | this file |
| Architecture document (max 2 pages) | [docs/architecture.md](docs/architecture.md), [docs/architecture.pdf](docs/architecture.pdf) |
| Demo video, technical presentation | submitted separately |
| Trained weights + reproducible training configuration | `models/` (the 17 served files), `configs/`, the commands below |
| Benchmark against logistic regression | the served models: `results/tables/n8_fix_eval.csv` ([results.md](results.md) "N-8 fix (D-041)"); every earlier method: `results/tables/benchmark_final.md` |

How each PS requirement is met, and where the solution falls short of it:
[problemstatement.md](problemstatement.md#how-this-repo-maps-to-the-requirements).

## Results on a held-out day

Leave-one-day-out on CIC-IDS2017: the Thursday numbers come from a model that never trained on
Thursday. The alarm threshold is causal (the 90th percentile of the scores before each window), and
logistic regression is scored at the same threshold.

| held-out Thursday | PR-AUC | F1 | precision | recall | FPR |
|---|---:|---:|---:|---:|---:|
| CSV route: world model (r2w seed 42) | **0.677** | 0.591 | 0.574 | 0.608 | 0.093 |
| PCAP route: world model (E20rw, mean of 3 seeds) | **0.514** | 0.583 | 0.581 | 0.584 | 0.087 |
| logistic regression (PS baseline) | 0.139 | 0.112 | 0.167 | 0.084 | 0.087 |

The CSV route serves its most favourable seed: seeds 43 and 44 of the same recipe reach 0.340 and
0.408 PR-AUC. The PCAP route averages its three seeds (0.409, 0.542, 0.726). Friday's only compromise is
a C2 family seen on no training day, and there both routes are near floor (0.118 and 0.137).

What the numbers do **not** show:
- **No early warning is validated.** Pre-attack windows rank above background, but no alarm beats a
  shuffled-time baseline.
- **No transfer to unseen compromise.** The compromise score does not carry to a compromise family
  seen on no training day (CTU-13, CIC-IDS2018).
- **Risk scores, not calibrated probabilities.**
- **Live PCAP quality is not measured.** The PCAP converter now feeds the model the state it was
  evaluated on (live vs training 0.991, D-043), but no live-PCAP detection number is measured.

These limits are in [docs/architecture.md](docs/architecture.md) §6.

## Setup

Use **Python 3.10**. `requirements.txt` pins numpy < 2, which has no Windows wheels for Python 3.13+.

```bash
git clone https://github.com/ArunmehtaBuild/NetWM.git
cd NetWM
py -3.10 -m venv .venv                 # Linux / macOS: python3.10 -m venv .venv
.venv\Scripts\activate                 # Linux / macOS: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

Install torch **before** `requirements.txt`: the PyPI torch is CPU-only on Windows, and pip would then
treat it as satisfying the CUDA build. Without an NVIDIA GPU, skip the torch line; the CPU build runs the
demo. Check with `python -c "import torch; print(torch.cuda.is_available())"`.

**Data.** One command, about 328 MB, extracted into `data/raw/cicids2017_improved/` (gitignored). It is
the corrected CIC-IDS2017 re-extraction, pinned by SHA-256: the original release mislabels attack
onsets, and onset time is what NetWM predicts (decisions.md D-001).

```bash
python scripts/get_data.py            # download, verify sha256, extract
python scripts/make_demo_samples.py   # cut the demo slices into data/demo/
```

## Run the demo

The served weights are in the repository, so nothing needs training. With the venv active:

```bash
run_demo.bat        # Windows
./run_demo.sh       # Linux / macOS
```

This starts the API on `127.0.0.1:5000` and the dashboard on `127.0.0.1:8080`, and opens the browser.
Or start them separately:

```bash
python -m uvicorn backend.server:app --host 127.0.0.1 --port 5000
python scripts/sync_fixtures.py && python -m http.server 8080 --directory frontend --bind 127.0.0.1
```

- **Routing.** A flow CSV is scored by the CSV route. A `.pcap` / `.pcapng` is scored by the PCAP route,
  which also reads packet-level features (TTL, fragments, retransmissions, TCP windows, payload sizes,
  timing).
- **Offline.** A test makes every outbound connection raise.
- **No labels on a PCAP.** A capture carries no labels, so its ground truth is reported as unavailable.

## Reproduce training and evaluation

Every experiment in [results.md](results.md) starts with the command that produced it. Every run writes
its seed, configuration and git SHA to `results/runs/<run>/metrics.json`. The served models:

```bash
python scripts/build_features.py --config configs/cicids2017.yaml            # the S_t matrices
python scripts/train.py --config configs/cicids2017.yaml --model-config configs/n8/r2_window.yaml \
    --test-days thursday friday --epochs 25 --samples 16 --run n8-r2w-s42 --seed 42 --no-figures
python scripts/train.py --data data/processed/cicids2017_m1v2p --model-config configs/n8/e20r_pcap_window.yaml \
    --test-days monday tuesday wednesday thursday friday --epochs 25 --seed 42 --run m1v2-n8-e20rw-s42 --no-figures
python scripts/n8_eval.py                                                      # the held-out evaluation
python -m pytest -q tests backend/tests                                        # 192 tests
```

The PCAP route's packet matrix needs the five CIC-IDS2017 day captures
(`scripts/build_packet_features.py`, results.md F5).

## Repository layout

```
src/netwm/     data adapters, features (flow, packet, PCAP converter), MITRE labels, world model, inference engine
scripts/       data, feature builds, training, evaluation, benchmarks, the evidence freeze
configs/       feature and model configurations
backend/       FastAPI JSON API              frontend/  static dashboard (no build step)
models/        the served checkpoints        fixtures/  API payloads shared by backend, dashboard and tests
results/       every figure, table and run   tests/     ML tests (backend/tests: API, contract, offline)
docs/          architecture document, API contract
research/      dataset and literature notes, indexed by research.md
```

## Documentation

- [docs/architecture.md](docs/architecture.md): the architecture, in 2 pages.
- [results.md](results.md): every experiment, its command, and its numbers.
- [decisions.md](decisions.md): every modelling decision, why it was taken, and what would change it.
- [research.md](research.md): the dataset and literature research behind them.
- [docs/api_contract.md](docs/api_contract.md): the API the dashboard uses.

**Frozen evidence.** Tag `submission-freeze` pins the code, weights and evidence, with
SHA-256 hashes, in `results/runs/submission-freeze/manifest.json`. The earlier M1-M3 freeze is tag
`m1-m3-evidence-freeze`.

## License

MIT, see [LICENSE](LICENSE).
