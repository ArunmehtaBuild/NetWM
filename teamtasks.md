# Team board - NetWM (SIH 2026, PS 26153)

**This board is the single source of truth.** All work routes through the orchestrator session
(Atharv). Task ids appear in commit messages; numbers live in `results.md`; modelling choices live in
`decisions.md`.

## Status - 2026-09-26, evening

**Merged:** #1 dashboard · #2 FastAPI backend · #3 live wiring · #4 S-track · #5 Y-scaffolding + S-3
· #6 PCAP extractor · Arun's `run_demo.bat` fix (`mehta`, with a readiness wait that actually waits).
Main runs end to end: a real CSV upload produces a real forecast in the browser, offline.
95 ML tests + 16 API tests.

**Model status, final for the submission.** Detection is strong: Thursday F1 0.576 at 2.7 % FPR,
against the baseline's 0.011. Forecasting is unproven. **E16 is in:** per-capture rank normalisation
fails every clause of the D-023 bar and is unstable across training seeds. That makes five causes
eliminated, one experiment each: statistic (E13), threshold (E14), data (E12), target (E15) and
representation (E16). The signal dies in cross-day transfer: on Thursday, logistic regression on all
70 features scores 0.604 and `uniq_dst_port` alone scores 0.607. `models/e4e7-worldmodel-r2/`
remains the submission checkpoint, and no artefact claims early warning (D-021).

**No open gate for the CSV demo.** PCAP ingestion landed (PR #8): a `.pcap` returns a v1.1 payload.
The PCAP demo capture was withdrawn and is being redone (A-5b). The demo script is `docs/demo_script.md`.

## Current tasks

One table, one source of truth. A card closes when `results.md` carries numbers and the command that
produced them, or when the thing it describes demonstrably works end to end - not when the code exists.

| person | id | task | done when |
|---|---|---|---|
| **Atharv** | **T-19** (decision, **first**) | **How the headline F1 is quoted.** E10: the full model's Thursday F1 is 0.568 / 0.432 / 0.470 over seeds 42/43/44. The 0.576 quoted everywhere is the seed-42 submission checkpoint, at the top of that range. Recommended: keep 0.576 as "the submission checkpoint" and always show "0.43-0.57 over three seeds" beside it. Record it as D-032. It gates Y-10, S-6b and H-15 | D-032 on main |
| | **A-README** | Cold-test the README on a fresh clone: clone -> `get_data.py` -> `make_demo_samples.py` -> `run_demo.bat` | the dashboard shows `mock: false` from a fresh clone |
| | **T-13** | Results section of `docs/architecture.md`: E16 (representation eliminated), E17 (calibration does not transfer), E10 (components unsupported; the multi-step loss is a detection component) | it matches `results.md` |
| | **T-10** | Promote `alarm_rate`, `eligible` and `confirm_before_onset` into `metrics.py`, with a regression check | one lead-time implementation in the repo |
| | **T-15** | Submission gap-check against the PS deliverables list | every deliverable has an owner and a state |
| **Yash** | | **No GPU and no working Python on Yash's machine.** Numbers run on Atharv's machine; Yash designs, pre-registers and writes. Y-4b and Y-1x landed (`0092920`, `d74ea57`); corrections in `88cb8a3` | |
| | **Y-10** (writing, after T-19) | **Claims audit.** Check every number and claim in `README.md`, `docs/architecture.md`, `docs/demo_script.md`, `docs/presentation.md` and the model card (`backend/inference.py`, D-024). Each must cite an experiment and not contradict what we now know: <br>• "probability" -> "risk score" (E17). <br>• "beats persistence from k = 2 onward" -> "averaged over steps 2-10, on both held-out days" (E10; r2 loses at k = 2 on Friday). <br>• The headline F1 quoted per D-032. <br>• Nothing implies warning *before* compromise (D-021). <br>• Stochastic latent and multi-step loss described as E10 found them | `docs/claims_audit.md` (claim -> source -> verdict) plus the text fixes, on main |
| | **Y-11** (writing) | Fold E10 and E17 into `research/early-warning-nulls.md` and the findings list in `research.md`. <br>• Seed spread as the real margin: a 0.01 bar inside a 0.14 spread. <br>• Pre-registration drift, twice (the NLL metric; the either/or gate). <br>• Calibration that cannot be held out when positives live on one day | research notes updated and indexed |
| **Sanchi** | **S-6b** | **Turn `docs/presentation.md` into the 5-slide deck, with the review fixes** (branch `s6-s7-features-presentation`, not merged). <br>• Slide 2: the model's state is *flow* features. PCAP ingestion exists, but packet features are not in `S_t`. Remove "before compromise completes" (D-021), and say "risk score", not "probability" (E17). Add the world-model evidence: the rollout beats persistence averaged over steps 2-10 (E10). <br>• Slide 3: stage mapping is shown, not validated. <br>• Slide 4: "the held-out infiltration day (Thursday)", not "held-out days" (Friday F1 is 0.000). Quote F1 per D-032. <br>• Slide 5: add E17 (probabilities don't transfer) and E10 (the components didn't earn their place; the multi-step loss drives detection) | an exported deck (PDF or PPTX, 5 slides) reviewed by two teammates; the gap wording still matches `docs/demo_script.md` |
| **Alok** | **A-3b** | **Make the aggregator match CICFlowMeter semantics.** <br>• Packet lengths from payload, not `len(pkt)`. <br>• Flow IAT over both directions. <br>• FIN/RST and 120 s idle termination. <br>• Init windows from the SYN and SYN-ACK. <br>• A session cap; time a 100 MB file. <br>Extend `tests/test_pcap_ingest.py` | features from a PCAP of known flows match the CSV values for the same flows |
| | **A-5b** | **Redo the demo PCAP** from a slice of the real Thursday flows. At least 50 min, fixed start time, the training address plan, in git via `!data/demo/*.pcap`, under 5 MB. Describe it from what the dashboard actually shows | the demo picker runs it in under 10 s; its description is measured |
| **Arun** | **R-12** | `in_sample: true/false` in the payload when the demo day is / isn't in the checkpoint's `train_days`; note it in the contract. **The frontend is ready** (H-14 renders it) | a contract test; Monday shows IN-SAMPLE in the browser |
| | **R-11** | PCAP end-to-end upload test. Unblocked: the aggregator exists | the PCAP path has the same end-to-end test as the CSV path |
| | **R-8** | `skipif` when the generated `data/demo/*.csv` files are missing | a fresh clone passes `pytest backend/tests` |
| | **R-9** | H-10's SSE replay is merged. Verify a full day replays from the dashboard against the API, fix what breaks | a full day replays without stutter |
| **Harshit** | **H-16** | Wherever `p_max` / `p_cum` is shown as a probability, call it a *risk score*, with a tooltip: "ranked against this capture's alert budget, not a calibrated probability (E17)" | no screen calls these numbers a probability |
| | **H-17** (new) | In mock mode, an upload shows the Thursday fixture under the *uploaded* file's name, after fake stage texts ("Rolling out RSSM world model..."). If a presenter ever runs with `?mock`, the screen would claim to have analysed their file. Say "fixture shown, your file was not analysed", and drop the imitation stages | a mock upload cannot be mistaken for an analysis |
| | **H-15** | Rehearse `docs/demo_script.md` twice against the live API, then record. Needs H-16 and R-12 first; the PCAP half needs A-5b | a recorded run that follows the script |

**Order that matters:** T-19 first, because the headline number's wording gates the slides, the
demo script and the model card. R-12 and H-16 land before H-15 records. A-5b gates the PCAP half of
the video. Nothing on the model side still needs the GPU before submission.

**Ownership, 2026-09-26.** Alok's cards moved to Atharv, then Alok delivered A-1/A-3/A-5 himself
(PR #8). The follow-ups from that review (A-3b, A-5b) go back to **Alok**; the README cold test stays
with Atharv.

## Tracks and owners

| person | track | owns |
|---|---|---|
| **Atharv** | Orchestration + ML correctness | this board, decisions/results discipline, inference engine correctness, architecture doc, README |
| **Alok** | Packets & demo data | PCAP->flows fidelity, demo PCAP |
| **Yash** | Model evidence (CPU only) | calibration, ablation design and write-ups, unseen-family evaluation, M2 research |
| **Sanchi** | State & features | feature matrix, trend/derivative features, per-host channels |
| **Arun** | Backend | FastAPI, job runner, SSE replay, offline packaging |
| **Harshit** | Frontend | the SOC dashboard, replay, demo video |

## Repo structure and who owns what

The backend and the frontend are **separate deployables** as of 21a9786 - pull before you start.

```
src/netwm/        the ML: data adapters, features, labels, models, engine   (Sanchi, Yash)
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
| packets & baselines | `src/netwm/features/pcap_features.py`, `flow_aggregator.py`, `src/netwm/models/baseline.py`, `scripts/make_demo_samples.py`, `scripts/make_demo_pcap.py` | Alok (Atharv reviews) |
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
| README with setup instructions a fresh machine can follow | Atharv | [ ] |
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
| A-1, A-3 | D-031 (Scapy synthesis); `pcap_to_flows` - a `.pcap` returns a v1.1 payload, with ground truth reported unavailable (PR #8 + fix-up) |
| H-10, H-12, H-13, H-14 | live SSE replay, upload states, surprise series, in-sample badge (PR #9, verified live; follow-up `dc063e8`: dev files out of the site root, honest scenario labels, UTC times) |
| Y-4b, Y-1x, S-7 | E10 and E17 written (`0092920`, `d74ea57`; corrections `88cb8a3`); features doc note (on Sanchi's branch) |
| T-18b | nine E10 runs scored; `results/tables/e10_ablation_summary.csv` via `scripts/e10_collect.py` (`a7909db`) |
| T-18, Y-4d, Y-1w | E10 sweep (9 runs, all exit 0, released only after D-030 was fixed); D-030 amended by Yash (`6390d6b`) and clarified before any number was read (`93e96f9`: E5 MSE, Thursday F1 alone gates); E17 written (`6390d6b`) |
| Y-4c, Y-8b | D-030 seed rule and a separate criterion for each ablation; CTU-13 note corrected (botnet-only PCAPs, scenario table, sizes) (`e5a7a45`) |
| Y-1 (numbers) | E17 data: forecast probabilities do not transfer to an unseen day (`ac4ec62`); write-up is Y-1w |
| Y-6b, Y-4a, Y-3c, Y-8 | gap-helper test; ablation script + D-030 pre-registration; D-006(b) closed by evidence; CTU-13 note (PR #7; follow-ups Y-4c, Y-8b) |
| Y-6 | E16: rank normalisation fails the D-023 bar and is seed-unstable; representation eliminated |
| T-14 | demo script, `docs/demo_script.md`, every figure checked against the live API |
| T-16 | baseline harness ranks each capture on its own; no published number affected |
| S-8 | onset 602 audit: no attempted traffic, rise carried by bystander hosts (`scripts/onset_audit.py`, under E16) |

Merged scaffolding that still owed a run: **Y-1** and **Y-4** are now live cards (Y-1, Y-4a/T-18/Y-4b).
