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
| **Yash** | | **No GPU, and no working Python on Yash's machine** (Python 3.14, no numpy wheels). Numbers run on Atharv's machine; Yash designs, pre-registers and writes. Y-4c and Y-8b landed (`e5a7a45`) | |
| | **Y-4b** (writing, **unblocked**) | Write **E10** from `results/tables/e10_ablation_summary.csv` (Atharv, from `scripts/e10_collect.py`), scored **exactly** by D-030 as it stands on main (`93e96f9`): rollout R = mean over k = 2..10 of E5's MSE minus persistence, on both folds; detection = Thursday `p_max` F1 at the 10 % budget; margin 0.01; paired by seed, >= 2 of 3; the ablation must be worse on *both* to count. The `*_vs_full` columns are signed so that positive means the ablation made it worse. Report per seed, not only means (E16). Correct `docs/architecture.md` wherever E10 does not support a claim | E10 in `results.md`; architecture claims match it |
| | **Y-1x** (writing, small) | **Finish E17.** Two points are missing: <br>• **What was scored:** `p_cum[:, K-1]` (P(compromise within K)) against `y_within_K`. <br>• **The in-sample caveat:** the temperature was fitted on the checkpoint's own training days, because no held-out training day with positives exists. So E17 answers "does an in-sample temperature transfer". <br>Add the Friday over-forecast too: mean forecast 0.274 against a 0.131 base rate, and its most confident bins are nearly always wrong. Add an E17 row to the index table at the top of `results.md` | E17 complete |
| **Sanchi** | **S-6** | 5-slide deck. Slide 5, "what we measured that did not work", now carries five eliminations, "70 features score no better than 1", and onset 602 (a precursor's shape without its content, S-8). **The gap wording must match `docs/demo_script.md` word for word** | draft reviewed by two teammates |
| | **S-7** | Extend `research/features.md` to the v2 trend block and the per-host channel. Record that slope and delta features carry no Thursday precursor signal (0.475-0.487 univariate, E16) | every v2 column maps to a behaviour |
| **Arun** | **R-12** (new) | Flag in-sample demos. `monday_benign` and `wednesday_dos` run on `thursday.pt`, which **trained on both days**. Add `in_sample: true` to the payload when the demo day is in the checkpoint's `train_days`, and note it in the contract | a contract test; the Monday demo reports in-sample |
| | **R-8** | `skipif` when the generated `data/demo/*.csv` files are missing | a fresh clone passes `pytest backend/tests` with no generated data |
| | **R-9** | Drive SSE replay from the dashboard | a full day replays in the browser without stutter |
| | **R-11** | PCAP end-to-end test, `skipif` until A-3's aggregator is importable | the PCAP path has the same end-to-end test as the CSV path |
| **Harshit** | **H-13** (new) | Plot surprise as a second timeline series. Today it lives only in a ribbon tooltip, yet it is the strongest live signal on the demo slice: benign median 0.15, 7.5 at the 17:00 scan, 15-52 during the sweep | visible without hovering |
| | **H-14** (new) | Badge in-sample demos (pairs with R-12) | Monday shows the badge |
| | **H-10** | Replay against the live stream (pairs with R-9) | play, pause and scrub against the API, not a fixture |
| | **H-12** | Large-upload states: progress, cancel, and an honest error for an unreadable capture | a 200 MB upload never looks frozen |
| | **H-16** (new) | Label the dashboard's probabilities honestly. E17: they are not calibrated on an unseen day (on Friday, worse than a constant forecast), and D-017 keeps the alert budget. Wherever `p_max` / `p_cum` is shown as a probability, call it a *risk score* and add a one-line tooltip: "ranked against this capture's alert budget, not a calibrated probability (E17)" | no screen calls these numbers a probability |
| | **H-15** (new) | Rehearse `docs/demo_script.md` twice against the live API, then record the video. Report anything on screen that disagrees with the script | a recorded run that follows the script |
| **Alok** | **A-3b** | **Make the aggregator match what the model was trained on (CICFlowMeter semantics).** Found at merge (PR #8): <br>• Packet-length stats use the whole frame (`len(pkt)`); CICFlowMeter uses payload length. <br>• Flow IAT is forward-only; CICFlowMeter's Flow IAT spans both directions. <br>• No FIN/RST termination and no 120 s activity timeout, so one 5-tuple is one flow for the whole capture. <br>• `fwd_init_win`, `bwd_init_win`, `fwd_seg_size_min`, `active_mean` and `idle_mean` are hard-coded 0; the init windows are in the first SYN and SYN-ACK. <br>• No session cap (A-2 has one) and every packet length is kept, so time a 100 MB file. <br>Extend `tests/test_pcap_ingest.py` | features from a PCAP of known flows match the CSV values for the same flows (parity test, see A-5b) |
| | **A-5b** | **Redo the demo PCAP (A-5 was withdrawn at merge).** Measured: 6.7 KB and 70 s, which is 3 windows. The one alarm fell on the benign window, the scan was labelled Impact, addresses sat outside `192.168.10.`, and timestamps come from `time.time()`. The catalogue entry claimed 4.5 MB, 10 min and labels. Recommended approach: **synthesize packets *from* a slice of the real Thursday flows** (timestamps, 5-tuples, flag and packet counts). The PCAP then tells the same story as the CSV demo, stays in the training distribution, and doubles as A-3b's parity fixture. Make it at least 50 min (`seq_len` is 96 windows), fix its start time, and get it into git (`*.pcap` is ignored: add `!data/demo/*.pcap`, under 5 MB). Run it through `thursday.pt` and report what the dashboard shows *before* writing the description | picker runs it in under 10 s; its description is measured, not intended |
| **Atharv** | **T-18b** (running) | Score the nine E10 runs with `rescore_pmax.py`, then `scripts/e10_collect.py` -> `results/tables/e10_ablation_summary.csv`, handed to Yash. The E10 runs are on main (`d7dbd2a`) | summary table on main |
| | **A-README** | Cold-test the README on a fresh clone: clone -> `get_data.py` -> `make_demo_samples.py` -> `run_demo.bat`. Fixed at merge: the placeholder clone URL, the missing demo-slice step (without it the demo endpoint returns 503), and the claimed 5 MB PCAP | the dashboard shows `mock: false` from a fresh clone |
| | **T-13** | Refresh the results section of `docs/architecture.md` with E16 (unblocked) | it matches `results.md` |
| | **T-10** | Promote `alarm_rate`, `eligible` and `confirm_before_onset` into `metrics.py`, with a regression check | one lead-time implementation in the repo |
| | **T-15** | Submission gap-check against the PS deliverables list; put the gaps on this board | every deliverable has an owner and a state |

**Order that matters:** PCAP ingestion works end to end (PR #8), so no gate remains that can break
the CSV demo. The PCAP half of the video waits on A-5b. H-13 and R-12 land before H-15 records. Y-4c
lands before T-18 uses the GPU, because a bar written after the numbers is not a pre-registration.

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
| T-18, Y-4d, Y-1w | E10 sweep (9 runs, all exit 0, released only after D-030 was fixed); D-030 amended by Yash (`6390d6b`) and clarified before any number was read (`93e96f9`: E5 MSE, Thursday F1 alone gates); E17 written (`6390d6b`) |
| Y-4c, Y-8b | D-030 seed rule and a separate criterion for each ablation; CTU-13 note corrected (botnet-only PCAPs, scenario table, sizes) (`e5a7a45`) |
| Y-1 (numbers) | E17 data: forecast probabilities do not transfer to an unseen day (`ac4ec62`); write-up is Y-1w |
| Y-6b, Y-4a, Y-3c, Y-8 | gap-helper test; ablation script + D-030 pre-registration; D-006(b) closed by evidence; CTU-13 note (PR #7; follow-ups Y-4c, Y-8b) |
| Y-6 | E16: rank normalisation fails the D-023 bar and is seed-unstable; representation eliminated |
| T-14 | demo script, `docs/demo_script.md`, every figure checked against the live API |
| T-16 | baseline harness ranks each capture on its own; no published number affected |
| S-8 | onset 602 audit: no attempted traffic, rise carried by bystander hosts (`scripts/onset_audit.py`, under E16) |

Merged scaffolding that still owed a run: **Y-1** and **Y-4** are now live cards (Y-1, Y-4a/T-18/Y-4b).
