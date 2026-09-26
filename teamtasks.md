# Team board - NetWM (SIH 2026, PS 26153)

**This board is the single source of truth.** All work routes through the orchestrator session
(Atharv). Task ids appear in commit messages; numbers live in `results.md`; modelling choices live in
`decisions.md`.

## Status - 2026-09-26, evening

**Merged:** #1 dashboard · #2 FastAPI backend · #3 live wiring · #4 S-track · #5 Y-scaffolding + S-3
· #6 PCAP extractor · Arun's `run_demo.bat` fix (`mehta`, with a readiness wait that actually waits).
Main runs end to end: a real CSV upload produces a real forecast in the browser, offline.
92 ML tests + 16 API tests.

**Model status, final for the submission.** Detection is strong: Thursday F1 0.576 at 2.7 % FPR,
against the baseline's 0.011. Forecasting is unproven. **E16 is in:** per-capture rank normalisation
fails every clause of the D-023 bar and is unstable across training seeds. That makes five causes
eliminated, one experiment each: statistic (E13), threshold (E14), data (E12), target (E15) and
representation (E16). The signal dies in cross-day transfer: on Thursday, logistic regression on all
70 features scores 0.604 and `uniq_dst_port` alone scores 0.607. `models/e4e7-worldmodel-r2/`
remains the submission checkpoint, and no artefact claims early warning (D-021).

**One open gate:** PCAP ingestion (A-3). The demo script is written (`docs/demo_script.md`), so
rehearsal can start today.

## Current tasks

One table, one source of truth. A card closes when `results.md` carries numbers and the command that
produced them, or when the thing it describes demonstrably works end to end - not when the code exists.

| person | id | task | done when |
|---|---|---|---|
| **Yash** | | **No GPU on Yash's machine.** Everything below runs on CPU or is writing and research. The one GPU job (the Y-4 ablation) is prepared by Yash, run by Atharv as T-18, and written up by Yash | |
| | **Y-6b** | A test for `windows_since_previous_attack`: strictly-quiet counting, first onset measured from the start of the capture, adjacent episodes. It feeds a published table (E16) and has no test | test in `tests/`, passing |
| | **Y-1** (CPU, do first) | **Measure calibration, don't assume it.** The PS asks for an infiltration *probability*, and the dashboard shows numbers that look like one. Score `e4e7-worldmodel-r2` on its held-out days; report reliability, ECE and Brier per fold, raw and temperature-scaled. Two traps: <br>• D-017's route (temperature on a *held-out* training day) can't work here. Only Thursday and Friday have compromise positives, and each fold tests one of them, so holding out the other leaves training with none. <br>• `scripts/calibrate.py` sets `val_day = train_days[-1]`, and the checkpoint trained on that day. Its temperature is fitted in-sample, so label the result "does in-sample calibration transfer to an unseen day", not "held-out calibration" | **E17** in `results.md`, plus D-017's status updated either way. If calibration does not transfer, that is the documented reason we quote alert budgets, and the dashboard's p-values get labelled as scores (tell Harshit) |
| | **Y-4a** (CPU, before T-18) | **Prepare the ablation on the checkpoint we ship.** Base: r2 on v1 (`configs/cicids2017.yaml`, `--epochs 25 --samples 16`). Not v2: Thursday LR 0.626 vs 0.604 is a 0.022 gap, and E16 calls 0.04 noise at about 8 episodes. Tasks: <br>• Rewrite `scripts/run_y4_ablation.bat`: three arms (full, `model_no_stochastic.yaml`, `model_no_multistep.yaml`) × seeds 42/43/44 × `--test-days thursday friday`. The current file uses v2, one seed and 20 epochs. <br>• Confirm each ablation config differs from r2 in **exactly one** field (`model_no_multistep.yaml` restates `kl`/`compromise`; check they equal r2's 0.5/2.0). <br>• `--smoke` each arm on CPU: `latent_dim: 0` may not be supported. <br>• Pre-register in `decisions.md` what "earns its place" means, before any number exists: removing the multi-step loss must worsen k >= 2 rollout NLL against persistence (E5) on both folds, on >= 2 of 3 seeds; detection is compared on E14's `p_max` at the 10 % budget | fixed `.bat` and the decision entry merged; every arm passes `--smoke` on CPU; handed to Atharv |
| | **Y-4b** (writing, after T-18) | Write **E10**, the ablation table planned in `results.md`, from Atharv's runs. Report per-seed, not just means (E16's lesson). Correct `docs/architecture.md` wherever it claims a component earns its place and E10 does not show it | E10 in `results.md`; architecture claims match it |
| | **Y-3c** (writing) | **Close D-006(b) with evidence instead of a run.** On CIC-IDS2017 every compromise family is confined to one day (infiltration Thursday, botnet Friday; `meta.json`: compromise positives Mon/Tue/Wed 0, Thu 166, Fri 127). So leave-one-day-out *is* leave-one-family-out for compromise. The proposed "drop Friday's botnet from the Thursday fold" would leave the hazard head with zero positives. Write it as a D-006 amendment, with the day -> family table, and tick `plan.md:43` pointing to it | amendment merged; `plan.md:43` closed |
| | **Y-8** (research) | **Plan the experiment that can test transfer: M2, CTU-13.** E16 says what's learned on one family doesn't carry to another, and that needs *more* compromise families, not fewer. Write `research/ctu13.md`: <br>• the 13 scenarios and their botnet families <br>• the label scheme <br>• the flow format (Argus binetflow, not CICFlowMeter) mapped onto the canonical schema <br>• sizes <br>• a scenario-held-out design pre-registered under the D-023 bar <br>Then an adapter plan for `src/netwm/data/ctu13.py` | note indexed in `research.md`; the adapter plan reviewed by Atharv |
| **Sanchi** | **S-6** | 5-slide deck. Slide 5, "what we measured that did not work", now carries five eliminations, "70 features score no better than 1", and onset 602 (a precursor's shape without its content, S-8). **The gap wording must match `docs/demo_script.md` word for word** | draft reviewed by two teammates |
| | **S-7** | Extend `research/features.md` to the v2 trend block and the per-host channel. Record that slope and delta features carry no Thursday precursor signal (0.475-0.487 univariate, E16) | every v2 column maps to a behaviour |
| **Alok** | **A-3** | **Critical path.** `features/flow_aggregator.py` -> `pcap_to_flows(path)`, returning the canonical flow schema (`src/netwm/data/base.py`) with the A-2 packet columns riding along per flow. It needs timestamps, so windowing (D-002) works unchanged. `analyze_file()` still raises on `.pcap` | `predict.py --input x.pcap` returns a v1.1 payload, and a PCAP upload works in the browser |
| | **A-1** | PCAP-source decision entry in `decisions.md`: real capture or Scapy synthesis | a decision entry either way |
| | **A-5** | One small PCAP demo (under 5 MB, one clean story) in `data/demo/index.json` | the demo picker runs it in under 10 s |
| **Arun** | **R-12** (new) | Flag in-sample demos. `monday_benign` and `wednesday_dos` run on `thursday.pt`, which **trained on both days**. Add `in_sample: true` to the payload when the demo day is in the checkpoint's `train_days`, and note it in the contract | a contract test; the Monday demo reports in-sample |
| | **R-8** | `skipif` when the generated `data/demo/*.csv` files are missing | a fresh clone passes `pytest backend/tests` with no generated data |
| | **R-9** | Drive SSE replay from the dashboard | a full day replays in the browser without stutter |
| | **R-11** | PCAP end-to-end test, `skipif` until A-3's aggregator is importable | the PCAP path has the same end-to-end test as the CSV path |
| **Harshit** | **H-13** (new) | Plot surprise as a second timeline series. Today it lives only in a ribbon tooltip, yet it is the strongest live signal on the demo slice: benign median 0.15, 7.5 at the 17:00 scan, 15-52 during the sweep | visible without hovering |
| | **H-14** (new) | Badge in-sample demos (pairs with R-12) | Monday shows the badge |
| | **H-10** | Replay against the live stream (pairs with R-9) | play, pause and scrub against the API, not a fixture |
| | **H-12** | Large-upload states: progress, cancel, and an honest error for an unreadable capture | a 200 MB upload never looks frozen |
| | **H-15** (new) | Rehearse `docs/demo_script.md` twice against the live API, then record the video. Report anything on screen that disagrees with the script | a recorded run that follows the script |
| **Atharv** | **T-18** (new, GPU) | Run the Y-4 ablation from Yash's fixed `run_y4_ablation.bat`: 3 arms × 3 seeds × 2 test days, about 2 h. Hand the run folders back for Y-4b | 18 run folders under `results/runs/`, with training curves |
| | **T-13** | Refresh the results section of `docs/architecture.md` with E16 (unblocked) | it matches `results.md` |
| | **T-10** | Promote `alarm_rate`, `eligible` and `confirm_before_onset` into `metrics.py`, with a regression check | one lead-time implementation in the repo |
| | **T-15** | Submission gap-check against the PS deliverables list; put the gaps on this board | every deliverable has an owner and a state |

**Order that matters:** A-3 is the only thing that can still break the demo. H-13 and R-12 land before
H-15 records. Yash starts on Y-6b and Y-1 (CPU); Y-4a must be finished before T-18 uses the GPU.

## Tracks and owners

| person | track | owns |
|---|---|---|
| **Atharv** | Orchestration + ML correctness | this board, decisions/results discipline, inference engine correctness, architecture doc |
| **Yash** | Model evidence (CPU only) | calibration, ablation design and write-ups, unseen-family evaluation, M2 research |
| **Sanchi** | State & features | feature matrix, trend/derivative features, per-host channels |
| **Alok** | Packets & demo data | PCAP sourcing, packet features, PCAP->flows, demo slices |
| **Arun** | Backend | FastAPI, job runner, SSE replay, offline packaging |
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
| Y-6 | E16: rank normalisation fails the D-023 bar and is seed-unstable; representation eliminated |
| T-14 | demo script, `docs/demo_script.md`, every figure checked against the live API |
| T-16 | baseline harness ranks each capture on its own; no published number affected |
| S-8 | onset 602 audit: no attempted traffic, rise carried by bystander hosts (`scripts/onset_audit.py`, under E16) |

Merged scaffolding that still owed a run: **Y-1** and **Y-4** are now live cards (Y-1, Y-4a/T-18/Y-4b).
