# Team board - NetWM (SIH 2026, PS 26153)

**This board is the single source of truth.** All work routes through the orchestrator session
(Atharv). Task ids appear in commit messages; numbers live in `results.md`; modelling choices live in
`decisions.md`.

## Status - 2026-09-28 (after D-037)

**D-037 ran as pre-registered.** Every run and verdict is in `results.md` (E26, E25b) and `decisions.md`
(D-037 outcomes, D-038, D-039).

- **E22 and real packets do not compose (E26).**
  - The combined model loses anticipation: S2\* -0.041 against a -0.03 bar.
  - It keeps the detection gain: Thursday PR-AUC +0.054.
  - Ship outcome 3: **r2 stays shipped for CSV input.** E22 remains the anticipation reference and
    E20r the detection reference.
- **Logistic regression ranks the run-up level with round 2** (S2\* 0.659 against 0.651). The world
  model's edge over LR is the factorised target (E22, 0.704) and detection: Thursday PR-AUC 0.640
  against 0.139 at the causal threshold (`results/tables/benchmark_final.md`).
- **CTU-13 is complete on three seeds, with an LR baseline on the same folds (E25b).**
  - By D-037's rule, 2 of 7 families transfer: NSIS robustly, Menti on only 6 background windows.
  - The other 5 are inverted: Murlo and Neris s02 are well measured; three inversions rest on 10-26
    background windows.
  - Seed 42 alone had over-read Neris and Virut.
  - Run-up ranking carries to Neris s02/s09 and Rbot s04/s10. It does not carry to Murlo, or to Rbot
    s03, where both models are below chance.
- **The PCAP route is accepted (D-038, E27):** PCAP uploads go to the mean of the three E20r seeds
  (Thursday PR-AUC 0.543, S2\* 0.669, S3 not met), and CSV stays on r2. Found on the way: every
  model's score depends on the capture's length, through the interpolated positional embedding (E27
  finding 5); a fix needs a pre-registered retrain (N-8). Pending: N-9.
- **Step 10 is decided (D-039): no GNN and no larger model.** The failures are transfer failures, and
  LR on the same global state is not inverted where the world model is. Whether to run M3
  (CIC-IDS2018) is left to the team.
- **No early warning anywhere:** S3 is met in no row, on neither dataset, so D-021 stands.
- **Second training machine:** RTX 4060 (8 GB) with 16 GB of RAM; two CTU-13 runs in parallel is its
  ceiling. The README setup was re-tested from a fresh clone (`2920382`).

## Current tasks

One table, one source of truth. A card closes when `results.md` carries numbers and the command that
produced them, or when the thing it describes demonstrably works end to end - not when the code exists.

| person | id | task | done when |
|---|---|---|---|
| **Atharv** | **G-2** (gap) | **The architecture document is about 1,750 words, roughly 4 pages; the PS allows 2.** Write the 2-page version the judges read, and keep `docs/architecture.md` as the reference it links to | a 2-page PDF in `docs/` |
| | **G-3** (gap) | **The demo video is capped at 2 minutes, but `docs/demo_script.md` is timed for 5.** Cut it to 2: the Thursday slice, the 17:00 scan and surprise, the sweep with the why panel, the model card with D-032, the gap line. PCAP upload gets 10 s once A-5b lands | a 2-minute script; H-15 records from it |
| | **G-6** (gap) | ~~One benchmark table as the PS asks~~ **Done** (`d0231e5`): `results/tables/benchmark_final.md`, LR vs NetWM at the causal threshold, Thursday and Friday, with seed ranges | closed |
| **Arun** | **G-1** (gap, **owner action**) | **The repo is PRIVATE.** The checklist had marked "public GitHub repo" done. Make it public, or confirm the evaluators will be given access, before submission | `gh repo view` shows PUBLIC, or access is confirmed in writing |
| **Sanchi** | **S-6b** | Deck from `docs/presentation.md` with the review fixes (branch `s6-s7-features-presentation`, unchanged since 18:49). Use D-032 for the headline, "risk score" not "probability", no "before compromise", flow-only `S_t`, and add E10/E17 to slide 5 | an exported 5-slide deck reviewed by two teammates |
| **Alok** | | No open cards: A-3c and A-5c were finished on main (`0b22d98`, `a9ff68a`). Next assignment comes from the gap list | |
| **Harshit** | **H-15** | Rehearse and record from the **2-minute** script (G-3), after R-12. The PCAP half needs A-5b | a recorded run under 2 minutes that follows the script |

### Open items - updated after D-037 (2026-09-28), not yet assigned

| id | task | done when |
|---|---|---|
| **N-1** (decision) | ~~Which checkpoint ships~~ **Done: D-038 accepted (E27).** PCAP -> the mean of E20r seeds 42/43/44; CSV -> r2. `results.md` E27 | closed; follow-ups N-8, N-9 |
| **N-2** | ~~Train E22 + real packets with a `has_pcap` mask~~ **Done: E26 (D-037).** The combination does not compose on anticipation (outcome 3), and CSV mode's rollout is worse than persistence | closed |
| **N-3** | ~~CTU-13 seeds 43 and 44 and an LR floor~~ **Done: E25b** (`c704587`, `8815fd9`, `d2c4185`). 2 of 7 families transfer, 5 inverted; family matrix in `results/tables/e25b_ctu13_*.csv` | closed |
| **N-4** | **Carry the new results into the submission artefacts**: slides (S-6b), the 2-page doc (G-2), the demo script (G-3). Use D-035's language: "ranks the run-up above background on unseen days", never "warns before". **E25b changes the M2 line:** `docs/architecture.md` still says detection transfers to "Neris, NSIS, Virut: ROC-AUC 0.85-0.99", which is seed 42 only (deferred by the team, 2026-09-28) | every number traced to `results.md` E19-E26 and E25b |
| **N-5** | **E21's representation for alarm quality.** It cut FPR 0.137 -> 0.110 and raised precision 0.35 -> 0.42 without an anticipation gain; test it against a bar written for alarm cost | a pre-registered bar and a run |
| **N-6** | **Diagnose E25b's inversions (D-039), descriptive.** **(a) Done: N-6a in `results.md`.** Murlo, Neris s02 and Rbot s11 are mostly direction flips: 18-25 of 56 global features move opposite to the training families, and neutralising them lifts the world model to 0.62-0.81. Virut s13 and Sogou rest on one or two features (HTTPS share; max duration, ephemeral ports). Seed 42 added ("N-6a, seed 42"): Murlo and Rbot s11 are flips on all three seeds; Virut s13 is also a flip on seed 42 (0.44 -> 0.75); Sogou is unexplained on seed 42. **(b) Done: N-6b in `results.md`.** D-039's reopen condition is **not met**: a label-free per-host max never reaches 0.70 on s08/s11, and on s07 the global statistics already separate (0.80-0.92). But on Murlo the bot host's own traffic ranks windows at 0.93-0.96 where global (0.32-0.34) and per-host max (<= 0.58) fail, and the bot is never the busiest internal host: the "drowned" pattern. Whether that warrants a pre-registered per-host-state run (each host against its own past) is a team call | (b) as a descriptive entry in `results.md`; a pre-registered per-host run only if it points there |
| **N-7** (decision, team) | **M3, CIC-IDS2018: run it or not.** The corrected flow CSVs are a 9.7 GB zip (`intrusion-detection.distrinet-research.be/CNS2022/Datasets/CSECICIDS2018_improved.zip`), no PCAPs needed. It keeps the full 70-feature state CTU-13 cannot, and adds compromise onsets. It needs a pre-registration and a download the team approves (D-039) | a decision entry |
| **N-8** | ~~Positional-length defect (E27 finding 5)~~ **Done: D-041, gates G1-G3 pass (results.md "N-8 fix").** Window positions plus carried state: chunked scoring = one pass to 2e-10 on every served checkpoint; `test_forecast_is_prefix_invariant` passes. PCAP route now serves the E20rw mean (Thu PR-AUC 0.514, S2* 0.675), CSV route r2w seed 42 (Thu PR-AUC 0.677; seeds 43/44 0.34/0.41). CTU-13 effect bounded in "N-8 x E25b" | closed |
| **N-9** | **PCAP route follow-ups (D-038, D-040).** **(b) Live-state parity, half done.** Check 4's full-day failure was the converter's session cap, not capture duplicates: 2.87 M packets were dropped once quiet flows filled 100,000 sessions, and the corrected CSVs count duplicates anyway (`e27-check4-dedupe-ab`). D-040 sweeps out timed-out flows. Totals now match within about 1 % on full Tuesday and on the Thursday 16:40 slice, and the flow block's median mean relative error is 0.04. Still off: `bwd_init_win_mean`, `active_mean_mean`, the distinct port and host counts, and `n_flows` (10-15 %). Next: trace these to the corrected extraction (`GintsEngelen/CNS2022_Code`), fix, and re-run `pcap_route_parity.py --pcap` on full Tuesday and with `--tag thursday-1640`. **(c) Step 8 done.** Both routes are served as routed, but their scores correlate at 0.035, all from the live PCAP state: the ensemble live against its own training state correlates at 0.111, while the two models agree at 0.82 on training state (`e27-step8-decompose`). Until (b) passes, quote no live-PCAP number, and do not present PCAP-route demo scores as E27's model. **(a) Team decision:** track or publish the six E20r fold files the demo needs; a fresh clone's PCAP route returns `no_model` | check 4 flow block exact; `step8_decompose.py`'s live-vs-training correlation re-reported after the fix; results in `results/runs/e27-parity*/`, `results/runs/e27-same-traffic/`, `results/runs/e27-step8-decompose/` |

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
| H-17 | a mock upload says "fixture shown, your file was not analysed" throughout: stage texts, payload identity, success state (Yash `77eaf96`, completed `527daf4`; PR #14 closed with review, its G-9 spline and re-carried PR #13 files not taken) |
| G-9 | the dashboard, model card and fixtures run E18's causal rule through one function (`f2bb6de`); the alarm panel carries the D-022 null ("not distinguishable from chance", p = 0.331) |
| G-4 (E9) | stage recall is high only where a relative family was in training (DDoS 0.99); 0 for Lateral Movement and C2; T1046 technique view 0.885 precision on the sweep (`59838be`, five-fold `14277fb`). Yash's PR #13 reproduced the matrices once fixed; closed with review |
| G-7 (E11) | fails its bar: 1 of 6 episodes; the why panel relabelled (`59838be`, `9893362`) |
| G-5 | packet features built from the five real captures and measured (E20, E20r): detection yes, anticipation no; wording in the architecture doc and the PS map (`c305236`) |
| D-035 programme | E19-E25 run and scored; outcome recorded in D-035; results in `results.md` (`515a74e`) |
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
