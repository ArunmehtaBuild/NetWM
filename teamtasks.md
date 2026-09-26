# Team board - NetWM (SIH 2026, PS 26153)

**This board is the single source of truth.** All work routes through the orchestrator session
(Atharv). Task ids appear in commit messages; numbers live in `results.md`; modelling choices live in
`decisions.md`.

## Status - 2026-09-26

**Merged:** #1 dashboard · #2 FastAPI backend · #3 live wiring · #4 S-track (trend, per-host, rank
scaler) · #5 Y-scaffolding + S-3 · #6 PCAP extractor. Main runs end to end: a real CSV upload
produces a real forecast in the browser, offline. 88 ML tests + 16 API tests.

**Model status, frozen by the D-021 amendment:** detection is strong (Thursday F1 0.576 at 2.7 % FPR
against the baseline's 0.011), forecasting is unproven (0 of 5 episodes; statistic, threshold, data
and target all eliminated), `models/e4e7-worldmodel-r2/` is the submission checkpoint, and no
early-warning claim is made anywhere.

**Two open gates:** PCAP ingestion (A-3 - no `flow_aggregator.py`, so a `.pcap` upload still raises)
and the r4 result (Y-6 - the last live hypothesis, currently running).

## Current tasks

One table, one source of truth. A card closes when `results.md` carries numbers and the command that
produced them, or when the thing it describes demonstrably works end to end - not when the code exists.

Yash is running the r4 sweep (Y-6); it occupies one machine for ~90 min and gates only the results
slide. Nothing else here waits on it.

| person | id | task | done when |
|---|---|---|---|
| **Alok** | ~~A-2~~ | **Merged (PR #6)**: streaming extractor with Welford TTL stats, session cap, scan signatures, tests on a synthetic PCAP. A building block, not the capability |
| | **A-3** | **Still the critical path.** `features/flow_aggregator.py` -> `pcap_to_flows(path)` returning the **canonical flow schema** (`src/netwm/data/base.py`: `ts`, `src_ip/port`, `dst_ip/port`, `protocol`, durations, per-direction counts, flag counts, IAT stats) with the A-2 packet columns riding along per flow. Two blockers this closes: the extractor currently has **no timestamps** (it summarises a whole capture per session, and `S_t` is a 60 s window at 30 s stride - D-002), and `analyze_file()` still raises `NotImplementedError` on `.pcap`. Do not build a parallel packet feature path - the canonical schema exists so windowing, features, the model, the API and the dashboard all work unchanged | `predict.py --input x.pcap` produces a v1.1 payload and a PCAP upload works in the browser |
| | **A-1** | Record the PCAP-source decision in `decisions.md` (real capture or Scapy synthesis) - still unwritten, and the fallback needs to be chosen this week rather than in the last 48 hours | a decision entry either way |
| | **A-5** | one small PCAP demo (< 5 MB, one clean story) registered in `data/demo/index.json` | the scenario picker offers a PCAP that runs in under 10 s |
| **Arun** | **R-8** | `skipif` on missing `data/demo/*.csv` so a clean clone stays green | fresh clone: `pytest backend/tests` passes with no generated data |
| | **R-9** | drive SSE replay from the dashboard - implemented, never exercised from the UI | a day replays in the browser without stutter |
| | **R-11** | extend `test_upload_e2e.py` to the PCAP path as soon as A-3 lands; today, write it `skipif` on the aggregator being importable | the PCAP path has the same end-to-end test the CSV path got |
| **Harshit** | **H-10** | replay against the live stream, fix whatever the integration shows | play/pause/scrub against the API, not a fixture |
| | **H-12** | upload states for a large file: progress, cancel, and an honest error for an unreadable capture | a 200 MB upload never looks frozen |
| **Sanchi** | **S-6** | the 5-slide deck. Slide 5 is **"what we measured that did not work"** - D-021 requires it, and the elimination chain (E12 -> E13 -> E14 -> E15 -> E16) is the strongest thing we have | draft reviewed by two teammates |
| | **S-7** | extend `research/features.md` to the v2 trend block and the per-host channel - it covers v1 only | a reader can map every column in S_t v2 to a behaviour |
| **Atharv** | **T-14** | the demo script: which capture, what is said at each beat, and the exact wording on the forecasting gap. Harshit cannot rehearse without it | a script that survives a judge's follow-up |
| | **T-10** | promote `alarm_rate` / `eligible` / `confirm_before_onset` into `metrics.py` with a regression check | one lead-time implementation in the repo |
| | **T-15** | submission gap-check against the PS deliverables list, top to bottom, and put the gaps on this board | every deliverable has an owner and a state |

**Blocked on r4 only:** the E16 write-up, the results slide's headline row, and the results section of
`docs/architecture.md` (T-13). Everything else in this table can finish today.

## Tracks and owners

| person | track | owns |
|---|---|---|
| **Atharv** | Orchestration + ML correctness | this board, decisions/results discipline, inference engine correctness, architecture doc |
| **Yash** | Model: make it forecast | training objectives, calibration, unseen-family evaluation |
| **Sanchi** | State & features | feature matrix, trend/derivative features, per-host channels |
| **Alok** | Packets & demo data | PCAP sourcing, packet features, PCAP->flows, demo slices |
| **Arun** | Backend | Flask API, job runner, SSE replay, offline packaging |
| **Harshit** | Frontend | the SOC dashboard, replay, demo video |

## Repo structure and who owns what

The backend and the frontend are **separate deployables** as of 21a9786 - pull before you start.

```
src/netwm/        the ML: data adapters, features, labels, models, engine   (Sanchi, Yash, Alok)
scripts/          CLI entry points: build_features, train, predict, benchmark, sync_fixtures
backend/          FastAPI JSON API - renders nothing                        (Arun)
                    uvicorn backend.server:app --host 127.0.0.1 --port 5000
frontend/         static files only - no backend needed to develop          (Harshit)
                    python -m http.server 8080
fixtures/api/     the three canonical payloads: single source of truth      (Atharv)
docs/             api_contract.md (the boundary) + submission artefacts
results/ research/ models/ configs/                                          (as before)
```

| area | paths | owner |
|---|---|---|
| features & state | `src/netwm/features/*`, `scripts/build_features.py`, `configs/features*.yaml` | Sanchi |
| model & training | `src/netwm/models/world_model.py`, `src/netwm/train.py`, `src/netwm/engine/rollout.py`, `configs/model_*.yaml` | Yash |
| metrics & explain | `src/netwm/metrics.py`, `src/netwm/evaluate.py`, `src/netwm/engine/explain.py`, `scripts/benchmark*.py` | Atharv |
| packets & baselines | `src/netwm/features/pcap_features.py`, `flow_aggregator.py`, `src/netwm/models/baseline.py`, `scripts/make_demo_samples.py` | Alok |
| backend | `backend/**` - server, schemas, jobs, inference, config, errors, tests | Arun |
| frontend | `frontend/**` - index.html, css, js, vendor | Harshit |
| inference entry point | `src/netwm/engine/predict.py`, `fixtures/api/*` | Atharv - Arun **consumes** it, does not edit it |
| shared (PR + a heads-up first) | `src/netwm/labels/*`, `src/netwm/data/*`, `src/netwm/utils.py`, `docs/api_contract.md` | anyone |

**Framework note.** The API is **FastAPI + uvicorn**, not Flask (decided 2026-09-25, rationale in
[backend/PLAN.md](backend/PLAN.md)): Pydantic response models make `docs/api_contract.md` executable,
which is the exact class of bug we shipped twice, plus one-line CORS for the split origins and free
OpenAPI at `/docs`. `requirements.txt` is updated - `pip install -r requirements.txt` again.

## How work routes through the orchestrator

1. Pick your task id from this board. If you want to do something not on it, ask first - the board
   is ordered by what unblocks other people.
2. Branch `<task-id>-short-name` (`y2-precursor-head`, `h2-forecast-timeline`).
3. When you finish, report back with: **task id · commit SHA · what you added to `results.md` /
   `decisions.md` · anything you did differently from the card**. The board gets updated here.
4. Numbers never travel in chat screenshots alone - they live in `results/` with the command that
   produced them, or they do not exist.

### Rule for parallel Claude sessions (learned the hard way)

Two sessions ran `git add -A` in this working tree on 2026-09-24 and one swept up the other's
uncommitted files into an unrelated commit. **Stage only your own paths** (`git add src/netwm/...`),
or work in a separate git worktree. Never `git add -A` in a shared tree.

## Submission checklist (PS 26153)

| deliverable | owner | status |
|---|---|---|
| Public GitHub repo link | Arun | [x] |
| README with setup instructions a fresh machine can follow | Alok | [ ] |
| Architecture document (max 2 pages) | Atharv | [ ] |
| Demo video (max 2 min), CSV **and** PCAP upload | Harshit | [ ] |
| Technical presentation (max 5 slides) | Sanchi | [ ] |
| Benchmark table vs logistic regression | Atharv | [ ] |
| Model weights + reproducible training config | Yash | [x] r2 checkpoints committed |
| Everything runs offline, no cloud API calls | Arun | [x] |

## Closed

| id | outcome |
|---|---|
| T-01, T-02, T-06, T-07 | alarm statistic, payload v1.1, contract drift, UI fixture |
| T-08 | D-021 amendment: sub-chance bar withdrawn, null gate adopted |
| T-09, T-11, T-12 | `evaluate.py` scores `p_max`; fixtures regenerated; E15/E15a in the architecture doc |
| Y-2, Y-5 | precursor supervision (E15) failed its pre-registered bar; lead time now reported against a null |
| S-1, S-2, S-3, S-4 | trend block (94 features), per-host channel (82), feature dictionary, rank scaler |
| R-1..R-7 | FastAPI API, contract tests, SSE, offline lockdown, uploads reaching the model, real model card |
| H-1..H-9 | dashboard, timeline + cone, ribbon, alarm log with the honest states, why panel, flows, upload, live scenario ids |
| A-2 | streaming PCAP packet-feature extractor |

Merged scaffolding that still owes a run: **Y-1** (calibration script), **Y-4** (ablation configs).
