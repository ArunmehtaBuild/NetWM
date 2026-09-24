# CLAUDE.md - working agreement for this repo

NetWM: a world model for network attack forecasting. SIH 2026, PS-153 (NTRO).
Read [problemstatement.md](problemstatement.md) first - it is the spec everything is judged against.

## Non-negotiable repo habits

1. **Every ML decision goes in [decisions.md](decisions.md)** - the decision, the reason, what would
   make us revisit it. Append a new `D-0xx` entry; never silently change an old one (mark it
   `superseded` and add the new one). If a change to code contradicts a decision entry, update the
   entry in the same commit.
2. **Every experiment goes in [results.md](results.md)** with its command, and its artefacts in
   `results/`: PNG -> `results/figures/`, CSV -> `results/tables/`, metrics JSON + resolved config
   -> `results/runs/<run-id>/`. A number quoted anywhere (slides, README, architecture doc) must
   exist in `results/`.
3. **Anything learned from a paper, dataset doc or experiment post-mortem goes in `research/`** and
   gets one line in [research.md](research.md). Cite the URL.
4. **No unreproducible numbers.** Every training / benchmark run writes its seed, config and git SHA
   into its run folder.

## Environment

- Windows 11, PowerShell. Python 3.10.6, venv at `.venv`.
- GPU: GTX 1650, 4 GB -> keep models ~1-3 M params, batch sizes small, mixed precision where useful.
- Torch is installed from the cu121 index (see README), everything else from `requirements.txt`.

## Code conventions

- Package lives in `src/netwm/`, imported as `netwm`. Scripts in `scripts/` are thin CLI wrappers -
  no logic that is not importable.
- Configs are YAML in `configs/`; scripts take `--config`. No hard-coded paths or hyperparameters.
- Determinism: every script takes `--seed` (default 42) and seeds numpy + torch.
- Data never gets committed (`data/` is gitignored); regeneration is a documented command.
- Type hints on public functions; docstrings that say *why*, not *what*.

## Vocabulary (use these words consistently)

- **window** - one 60 s slice of traffic, stride 30 s. Indexed by `t`.
- **state `S_t`** - the feature vector for window `t`.
- **rollout** - K-step open-loop imagination in latent space from `S_t`.
- **hazard** - P(compromise at step k | not compromised before k).
- **lead time** - windows between the first alarm and ground-truth attack onset.
- **surprise** - next-state prediction NLL, used as an unseen-attack signal.

## What "done" means for a component

Code + a config + a test + an entry in results.md (if it produces numbers) + a decisions.md entry
(if it involved a modelling choice).
