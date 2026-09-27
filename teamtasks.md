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
| **Atharv** | **G-2** (gap) | **The architecture document is about 1,750 words, roughly 4 pages; the PS allows 2.** Write the 2-page version the judges read, and keep `docs/architecture.md` as the reference it links to | a 2-page PDF in `docs/` |
| | **G-3** (gap) | **The demo video is capped at 2 minutes, but `docs/demo_script.md` is timed for 5.** Cut it to 2: the Thursday slice, the 17:00 scan and surprise, the sweep with the why panel, the model card with D-032, the gap line. PCAP upload gets 10 s once A-5b lands | a 2-minute script; H-15 records from it |
| | **G-6** (gap) | **One benchmark table** as the PS asks: F1, precision, recall and FPR for logistic regression vs NetWM, on Thursday and Friday, with the seed range. The numbers exist in E3, E14 and E10 but are spread across entries | the table in `results.md` and on slide 4 |
| | **G-5** (gap, decision) | **Packet-level features are required, but `S_t` is flow-only.** PCAPs are parsed and packet features extracted, but the corrected CIC-IDS2017 release is CSV, so the model never trained on them. Decide how the submission says so (architecture doc, slide 2) and whether the dashboard shows packet stats for a PCAP upload | a decision entry; the wording is in the doc and the deck |
| **Arun** | **G-1** (gap, **owner action**) | **The repo is PRIVATE.** The checklist had marked "public GitHub repo" done. Make it public, or confirm the evaluators will be given access, before submission | `gh repo view` shows PUBLIC, or access is confirmed in writing |
| **Atharv** (+ Arun, Harshit) | **G-9** (**before recording**) | **Move the product to the causal threshold (D-034).** `engine/predict.py` still sets the dashboard threshold from the whole capture, and the model card (D-024) still reads E14's non-causal row. <br>• **Atharv:** `predict.py` emits a per-window `threshold` series using the expanding q90 with a 20-window warm-up (the same code as `threshold_eval.expanding`). <br>• **Arun:** a contract field for the series (keeping the scalar for old payloads); the model card reads E18's primary row. <br>• **Harshit:** draw the threshold as a curve, not a line. <br>Then re-measure the demo-slice figures in `docs/demo_script.md` | the dashboard's alarms equal E18's `alarm_expanding-10pct` on the same scores; the model card shows 0.608 |
| **Yash** | **G-4** (gap) | **E9, the MITRE stage confusion matrix, was planned and never run.** Stage mapping is a named PS output, and on the demo slice the stage head calls the internal sweep Reconnaissance where the truth is Lateral Movement. Design E9 (per-stage precision and recall on the held-out days, r2 checkpoint); Atharv runs it. *(Design complete: `scripts/e9_confusion_matrix.py` added)* | E9 in `results.md`; slide 3 quotes it |
| | **G-7** (gap) | **E11, the explainability sanity check, was planned and never run.** Do the top attributions on known attacks point at the known signature, e.g. port spread on the 17:00 scan and fan-out on the sweep? Design it; Atharv runs it. *(Design complete: `scripts/e11_explain_sanity.py` added)* | E11 in `results.md` |
| **Sanchi** | **S-6b** | Deck from `docs/presentation.md` with the review fixes (branch `s6-s7-features-presentation`, unchanged since 18:49). Use D-032 for the headline, "risk score" not "probability", no "before compromise", flow-only `S_t`, and add E10/E17 to slide 5 | an exported 5-slide deck reviewed by two teammates |
| **Alok** | | No open cards: A-3c and A-5c were finished on main (`0b22d98`, `a9ff68a`). Next assignment comes from the gap list | |
| **Harshit** | **H-17** | In mock mode, an upload shows the fixture under the uploaded file's name after imitation stage texts. Say "fixture shown, your file was not analysed" | a mock upload cannot pass for an analysis |
| | **H-15** | Rehearse and record from the **2-minute** script (G-3), after R-12. The PCAP half needs A-5b | a recorded run under 2 minutes that follows the script |

**Order that matters:** G-1 is a one-click owner action and cannot slip past submission. G-9 and G-3
come before H-15 records, because a 5-minute script cannot make a 2-minute video. G-4 and G-7 are the last
two PS outputs with no measurement behind them. The model side needs no more GPU time.

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

T-15 gap check, 2026-09-26. The PS lists five deliverables; the rest are its indicative solution.

| deliverable | owner | status |
|---|---|---|
| Source code link | Arun | [ ] **repo is PRIVATE** (G-1) |
| README with setup instructions | Atharv | [x] cold-tested on a fresh clone (`c5680e7`) |
| Architecture document (max 2 pages) | Atharv | [ ] content current (`04178b9`), but about 4 pages (G-2) |
| Demo video (max 2 minutes), CSV and PCAP upload | Harshit | [ ] script is 5 minutes (G-3); PCAP demo pending (A-5b) |
| Technical presentation (max 5 slides) | Sanchi | [ ] outline only (S-6b) |
| Benchmark vs logistic regression (F1, precision, recall, FPR) | Atharv | [ ] numbers exist, one table missing (G-6) |
| Flow **and** packet-level features | Atharv | [ ] packet features extracted but not model inputs (G-5) |
| MITRE stage mapping, validated | Yash | [ ] E9 never run (G-4) |
| Explainability output | Yash | [x] attention + IG; [ ] sanity check E11 (G-7) |
| Model weights + reproducible training config | Yash | [x] r2 checkpoints and commands |
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
| G-8 | E18: the causal expanding q90 (pre-registered, D-034) keeps the signal - Thursday F1 0.608 (0.52-0.61 over seeds) - at 16.8 % of windows alarmed, FPR 0.078; 0.576 becomes a non-causal upper bound; 2/4 warned early is chance (p = 0.33) |
| A-3c, A-5c | aggregator matches the corrected extraction (from-start 120 s timeout, teardown kept, measured field encodings, 20x faster, real parity tests; D-033); demo PCAP 16:50-17:25 with the 17:00 scan, measured catalogue entry (`0b22d98`, `a9ff68a`) |
| R-8, R-9, R-11, R-12 | clean-clone skip guards, SSE `from` replay, PCAP upload end-to-end test, `in_sample` flag (PR #11; follow-up `c1fcb70`: the fallback no longer guesses in-sample from the requested name, and the real demo path is tested through the API) |
| S-6 (outline), S-7 | `docs/presentation.md` merged as a draft (PR #12); the fixes are S-6b |
| T-19, T-13, T-10, A-README, T-15 | D-032 (headline F1 with its seed range); architecture results on one statistic with E10/E16/E17; one lead-time implementation with a frozen-reference regression test; README cold-tested on a fresh clone; gap check -> G-1..G-7 (`04178b9`, `2211876`, `c5680e7`, `b186f08`) |
| H-16, Y-10, Y-11 | risk-score labels (`8ef5657`, landed from `h16` without its stale files); claims audit and research notes (`357ebd9`, corrected in `04178b9`) |
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
