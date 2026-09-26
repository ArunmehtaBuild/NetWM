# Team board - NetWM (SIH 2026, PS 26153)

**This board is the single source of truth.** All work routes through the orchestrator session
(Atharv). Nothing is "done" until its task id appears in a commit message and, where it produces
numbers or a modelling choice, in `results.md` / `decisions.md`.

Re-baselined 2026-09-25 against the actual repo state, not the original sprint plan.

## Where we actually are

**Working:** feature pipeline (70 features/window), scaler, E2/E3 baselines, RSSM world model
(round 2, three risk heads), training + evaluation + explainability + inference engine, prediction
CLI, demo CSV slices, 33 passing tests, decisions D-001..D-019, experiments E1-E13.

**The one number that matters and is still wrong:** lead time is **0 of 5 episodes** at any
deployable threshold. Detection is strong (Thursday PR-AUC 0.675 vs 0.139 for logistic regression,
FPR 0.042 vs 0.608) but the system is not yet forecasting, which is the entire premise of PS 26153.
E12 proved the pre-onset signal exists (within-day ROC-AUC 0.88-0.96), so this is fixable.

**Not started at all:** the FastAPI backend, the whole frontend, packet-level features, PCAP ingestion.

**Known defects (found in the 2026-09-25 audit):**
- `engine/predict.py:123` scores alarms with the cumulative union while **D-019** says max over
  horizon - and max is the only statistic that produced *any* early warning (E13).
- `world_model.py` emits `p_cum_attack` / `p_cum_escalate`; `engine/predict.py` drops both.
- Payload drift vs `docs/api_contract.md` v1: missing `observed_stage`, `top_talkers`,
  `ground_truth.spans`; extra `until_t`, top-level `stages`.
- ~~`fixtures/api/` is empty~~ - closed by T-02/T-07: three fixtures ship, Chart.js is vendored, and
  the frontend runs standalone from `frontend/mock/`.

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

## Priority order (read this before picking anything up)

1. **P0 - unblock everyone else**: T-02 (payload + mock) unblocks Harshit *and* Arun. Do it first.
2. **P0 - the headline bug**: T-01. If max-over-horizon at an alert budget yields lead time > 0,
   the project's central claim lands; if it does not, we know today rather than in week three.
3. **P1 - make it forecast**: Y-1, Y-2, S-1. This is the research risk.
4. **P1 - deliverable completeness**: R-1, H-1, A-1/A-2. The PS mandates a UI and packet features.
5. **P2 - everything else.**

## Atharv - orchestration + ML correctness

| id | task | done when |
|---|---|---|
| ~~T-01~~ | **Verified done** (ae10e10, E14): `p_max` wired in, rescore script + figures, honest negative result - no lead time at any deployable threshold, but a real operating point found (Thu F1 0.576 @ 2.7 % FPR, self-budget 10 %). Alarm statistic: switch scoring to `p_max` (max over horizon) per D-019, re-score the existing r2 checkpoints, and report lead time at train-tuned / alert-budget / oracle thresholds | `results.md` E14 with a lead-time column; D-019 moves to `accepted` or is rewritten with the negative result |
| ~~T-02~~ | **Verified done** (419f5be, 2b2a8a0): both mocks valid v1.1, 972/968 windows, no NaN, alarm flags consistent with threshold, talkers + spans + all three risk curves present. Payload v1.1: emit `p_max`, `p_cum_attack`, `p_cum_escalate`, `observed_stage`, `top_talkers`, `ground_truth.spans` from `engine/predict.py`; regenerate `fixtures/api/thursday.json` + `friday.json` | Arun and Harshit can both start without asking anyone a question |
| ~~T-06~~ | **Verified done** (831d2d1): `observed_stage_conf` now emitted and documented as a calibration read-out; D-019 restated as accepted on E14 evidence. Two residual drifts found by the T-01/T-02 review gate: (a) `observed_stage_conf` is still documented in contract v1.0 but never emitted - emit it or delete it; (b) D-019 still reads *provisional · Evidence: E13* although E14 answered it - restate with the negative result | contract, payload and decisions agree |
| ~~T-07~~ | **Verified done** (831d2d1): `fixtures/api/thursday_oracle.json`, 14 alarms, one with a 5-window lead, `threshold_policy: fixed-override`. No mock contains an early alarm (self-budget policy gives 0 of 5), so Harshit cannot build or verify **H-4**, the lead-time panel. Ship a clearly-named `fixtures/api/thursday_oracle.json` at the oracle threshold (1 alarm, 5-window lead) **for UI development only**, and make H-4 render the honest "no early warning" state too | Harshit can build both states; no oracle number ever reaches a slide |
| **T-03** | Review gate: every incoming commit (teammate or parallel session) checked for a `results.md` / `decisions.md` entry and a task id | no orphan numbers in the repo |
| ~~D-021~~ | **Verified** (1c61eaf, d4d010d): framing frozen with claims bound to experiment ids, and its falsification test run - E3b shows lagged logistic regression buys no lead time at any deployable threshold and is *worse* on Thursday (PR-AUC 0.139 -> 0.114) |
| **T-04** | Architecture document (2 pages); stable sections now, results row parameterised until Y-2 reports | reviewed by two teammates |
| **T-05** | Keep this board current after every merge | board matches `git log` |
| ~~T-08~~ | **Done** - D-021 amendment written after E15a/E15: sub-chance bar withdrawn, null gate adopted, no-early-warning branch now operative, r2 fixed as the submission checkpoint |
| **T-09** | `evaluate.py` still scores on `p_cum[:, -1]`, not `p_max` - which is why in-training E6 rows do not match E14. Fix, then confirm no published number moves | in-training and rescored numbers agree |
| **T-10** | Promote `alarm_rate` / `eligible` / `confirm_before_onset` from `models/leadtime.py` into `metrics.py`, additive, with a regression check that E2/E3/E6/E13/E14 are unchanged | one lead-time implementation in the repo |
| **T-11** | Regenerate `fixtures/api/*` after the MC-mean fix to `p_cum_attack` / `p_cum_escalate`; re-run `scripts/sync_fixtures.py` | fixtures match the current engine |
| **T-12** | Fold E15/E15a into `docs/architecture.md` - the elimination chain is now four causes, and the null calibration belongs in the methodology section | doc matches `results.md` |

## Yash - make it forecast (the research risk)

| id | task | done when |
|---|---|---|
| **Y-1** | Calibration: temperature-scale the risk heads on a held-out *training* day, then re-report the train-tuned threshold gap (D-017 says revisit once this exists) | train-tuned vs oracle threshold gap under 3x, or documented as unfixable |
| ~~Y-2~~ | **Done, merged 8517764** - failed its pre-registered bar on every clause; round 3 is a regression (Thu PR-AUC 0.353-0.445 vs r2 0.640) and its weights never ship. Target eliminated as the cause. **Precursor supervision.** E12 shows the 10 windows before an onset are separable at ROC-AUC 0.88-0.96, but nothing in training tells the model they are special. Add a fourth head: `precursor` = "an onset occurs within the next K windows and this window is not itself an attack window", trained on those windows explicitly | `results.md` E15: lead time > 0 on at least 2 of 5 episodes at the alert-budget threshold, or a documented negative result with the loss curves |
| **Y-3** | Formalise E8: leave-one-attack-family-out, reported as its own experiment rather than buried in the Friday fold | `results.md` E8 with Infiltration-held-out and Botnet-held-out rows |
| ~~Y-5~~ | **Satisfied** - E15a built the null, D-022 made it a standing rule, and it retired E14's own 1-of-4 (p = 0.412). **Guardrail, do this inside Y-2 before reporting any count.** Lead time is manufacturable: E3b found Thursday's `detect` target at an oracle threshold reporting *2 of 4 episodes warned early, mean lead 6.5 windows*, while scoring F1 0.021 and PR-AUC 0.069 - a score firing nearly everywhere "warns early" by accident. Every early-warning count must be reported with the FPR and alarm rate at the same threshold, on the same line | no lead-time number appears anywhere - results, slides, video - without its FPR beside it |
| **Y-4** | After Sanchi ships S-1, retrain on `S_t` v2 and run the E10 ablation (with / without trend features, with / without stochastic latent, with / without multi-step loss) | ablation table showing which components earn their place |

Constraint: architecture changes need a decisions.md entry *before* the run, not after.

## Next experiment - representation, not supervision (r4)

Four causes are eliminated: statistic (E13), threshold (E14), data (E12), target (E15). The fifth is
that the model **loses the signal before the target is reached**: on the precursor label, LODO, a
single *unscaled* column (`uniq_dst_port`, Thursday 0.607, Tuesday 0.745) and plain logistic
regression (0.604) both beat every statistic the world model produces (best 0.533). Prime suspect:
the train-day-fitted scaler under the distribution shift E2 measured (Thursday persistence NLL mean
152 010 vs median 0.85).

| id | task | owner | done when |
|---|---|---|---|
| ~~S-4~~ | **Done** - Per-capture rank / percentile normalisation as a scaler option - the D-020 alert-budget logic applied to features instead of scores. Label-free, so it is legal at inference on an unseen capture | Sanchi | `StateScaler(mode="rank")` behind a config flag; S-1 trend features built on top of it |
| **Y-6** | Retrain r4 = **r2 heads** (not r3) on rank-normalised features; evaluate under the D-023 bar and against the same raw-feature and LR floors | Yash | `results.md` E16 with the floors on the same table; claim gate is D-021 amendment point 2 |

Do **not** carry the r3 heads into r4. Two extra targets on the shared trunk cost ~0.20 PR-AUC and
bought nothing; the only variable in r4 is the feature transform.

## Sanchi - give the model the signal E12 found

| id | task | done when |
|---|---|---|
| ~~S-1~~ | **Done** - **Trend features.** `S_t` is currently levels only - the model sees *how many* distinct destination ports, never *how fast that is rising*. Add deltas and rolling slopes (2, 5, 10 windows) for the features E12 ranked highest: `uniq_dst_port`, `ports_per_pair_max`, `port_fanout_max`, `uniq_dst_ip`, `fanout_mean`, `flows_per_s`, plus z-scores against a rolling benign baseline | `S_t` v2 built for all 5 days; feature count and build time in `results.md` F2; decisions entry for the window choices |
| ~~S-2~~ | **Done** - Per-host channel: top-N talkers as their own sub-vector (fan-out, ports touched, in/out byte ratio, new-peer rate) so lateral movement is visible per host, not only in network-wide aggregates | schema documented; Yash can train on it behind a config flag |
| ~~S-3~~ | **Done** - Feature dictionary in `research/features.md`: every feature, its formula, and which attack behaviour it is meant to expose | reviewable by someone who has not read the code |

S-1 is the highest-value ML task on the board after T-01/Y-2. Levels-only state is the most likely
reason the model detects but does not anticipate.

## Alok - packets and demo data

| id | task | done when |
|---|---|---|
| **A-1** | PCAP decision, **deadline 2 days**: find a working mirror for `Thursday-WorkingHours.pcap` (report source + size here before downloading), or lock the fallback: Scapy-synthesised PCAPs reproducing the documented signatures (slow SYN sweep, reverse shell session, DDoS burst) | a decision recorded in decisions.md either way - not an open question in week two |
| **A-2** | `features/pcap_features.py`: streaming Scapy reader -> TTL mean/variance per session, TCP window size stats, IP fragment flags, payload-size histogram, retransmission counts, sequential/randomised port-scan signature | the PS's packet-level feature list is covered, with tests on a synthetic PCAP |
| **A-3** | `features/flow_aggregator.py`: PCAP -> the canonical flow schema, so `predict.py --input x.pcap` works | same payload shape from a PCAP as from a CSV |
| **A-4** | Shrink the demo slices - 20-73 MB is too slow for a 2-minute video. Target < 5 MB each, each containing one clean story | `data/demo/index.json` updated, inference under 10 s per demo |

## Arun - backend

Full spec: [backend/PLAN.md](backend/PLAN.md).

| id | task | done when |
|---|---|---|
| ~~R-1~~ | **Verified done** (PR #2): FastAPI app - `server.py` (routes + CORS allowlist), `schemas.py`, `jobs.py` (single worker thread), `inference.py` wrapping `analyze_file`; fixtures served with `"mock": true` when no checkpoint exists |
| ~~R-2~~ | **Verified done**: `backend/tests/test_contract.py` validates fixtures *and* fresh engine output against the v1.1 models |
| ~~R-3~~ | **Verified done**: SSE `/api/jobs/<id>/stream?speed=` from the disk cache, with heartbeats and disconnect handling |
| ~~R-4~~ | **Verified done**: size caps, uniform error shape, `test_offline.py` socket lockdown, `run_demo.bat` |
| ~~R-5~~ | **Verified fixed** - reviewed live: a 39 999-flow CSV upload returns `mock: false`, 514 windows, threshold 0.0036 under `self-budget-10pct`, 3 alarms. Root cause was a race, not a path bug: the job was enqueued before the upload finished streaming, so the worker saw `file_path=None`. Covered by `test_upload_e2e.py` |
| ~~R-6~~ | **Verified fixed**: the demo endpoint runs the model - `mock: false`, 260 windows from 169 135 flows, the real 2-hour slice rather than the full-day fixture |
| ~~R-7~~ | **Verified fixed**: `/api/model` reports F1 0.576, precision 0.775, FPR 0.027, PR-AUC 0.64, baseline F1 0.011, lead time 0.0 |
| **R-8** | `test_contract.py` and `test_offline.py` fail on a clean checkout because they need the gitignored `data/demo/*.csv`. Add `skipif` on missing demo data so a fresh clone stays green - this is the same clean-machine criterion R-4 is judged on |

## Harshit - frontend

Full spec: [frontend/PLAN.md](frontend/PLAN.md).

| id | task | done when |
|---|---|---|
| **H-1** | Shell + dark SOC theme + `js/config.js` (API_BASE / `?mock`) + `js/api.js` with the mock fallback, reading `frontend/mock/thursday.json`. Chart.js is already vendored | `python -m http.server 8080` in `frontend/`, opened with WiFi off, renders the timeline with no backend running |
| **H-2** | Forecast timeline: observed risk line, K-step forecast cone (`p_lo`/`p_hi`), alarm threshold, ground-truth attack spans shaded | the Thursday infiltration is visually obvious |
| **H-3** | Kill-chain ribbon (predicted stage per window) + current-stage card with ATT&CK tactic id | stage colours come from the API, never hard-coded |
| **H-4** | **Alarm log with lead time** - "fired N windows (M s) before onset". This is the single most important panel in the demo video | reads `alarms[].lead_windows` |
| ~~H-1..H-5~~ | **Merged** ([#1](https://github.com/ArunmehtaBuild/smart2nd/pull/1), 83af70b). Reviewed by running it: risk line plots `p_max` per D-019/D-020, the honest "0 of 4 episodes warned early" banner is front and centre, the oracle fixture carries its dev-only warning, and all three H-4 alarm states render |
| **H-7** | Cleanups from the #1 review: (a) move the 7 screenshots (~2 MB) to `docs/` and the `test_h*.html` harnesses to `frontend/dev/` - both currently deploy with the static site; (b) replace the five hard-coded `#4c9be8` in `timeline.js` with the `theme.css` token; (c) check the header layout at the width the demo video will actually be recorded at (it wraps at ~800 px) | nothing ships that is not part of the product |
| **H-9** | **The scenario selector never engages the live API.** Verified against the merged backend: `GET /api/demos` returns 200, then `POST /api/analyze/demo/thursday` returns 400 - the day name is posted instead of the `id` from that same response (`thursday_infiltration`), so it falls back to `./mock/` and the header reads "Mock Fixture" with a healthy API behind it. `GET /api/jobs/demo/flows` 404s for the same reason (literal `demo` as job id). Use the ids from `/api/demos` and thread the real `job_id` into the flows call | picking a scenario with the backend running shows **Live API**, not Mock Fixture |
| **H-8** | **Upload path verified working** against the merged backend (6 000-flow CSV -> 77 windows, badge flips to Live API, per-capture threshold 0.0030). Was on hold until R-5 landed; - the upload panel is built against an endpoint that cannot currently succeed, and the branch is 13 commits behind main. Rebase, then verify against a working API. Wire the live path when R-1 lands: upload -> job polling -> result, SSE replay, and the API/fixture badge in the header. Until then keep `?mock` working exactly as it does now | the same dashboard runs against the real API with no code change beyond `config.js` |
| **H-5** | Why-panel: attribution bars + attention heatmap; flagged-flows table | every alarm can be explained on screen |
| **H-6** | Replay mode (play/pause/scrub) on the SSE stream, then record the 2-minute demo video | video shows risk rising *before* the attack lands |

H-1 and H-2 need no backend and no model: run `python scripts/sync_fixtures.py` once, then serve the folder.

## Kickoff - the first commit each person should make

Everything below is unblocked **right now**; nothing waits on anything else.

| person | start with | first commit looks like |
|---|---|---|
| Arun | **R-1** | `backend/server.py` + `schemas.py` serving `/api/health`, `/api/model`, `/api/demos`, `/api/jobs/<id>/result` from `fixtures/api/` under uvicorn - no model loading yet |
| Harshit | **H-1** (Chart.js already vendored) | `frontend/index.html` + `css/theme.css` + `js/config.js` rendering the Thursday fixture's timeline, served statically, offline |
| Sanchi | ~~S-1~~ | trend/slope features behind a config flag, `S_t` v2 built for one day, feature count in `results.md` F2 |
| Yash | **Y-2** | a decisions.md entry for the first-occurrence hazard target *before* the run, then the head + a smoke train |
| Alok | **A-1** | a decisions.md entry recording the PCAP source **or** the synthesis fallback - closed within 2 days either way |

### Two sequencing rules, so nobody's numbers become incomparable

1. **`S_t` v1 is frozen for Y-2.** Yash trains the first-occurrence hazard experiment on the current
   70-feature matrix, so E15 is comparable with E14 and the round-2 numbers. Sanchi's v2 features
   land behind a config flag and get evaluated in **Y-4** as an ablation - one variable at a time.
2. **Frontend never blocks on the model or the backend.** Harshit works from `frontend/mock/` throughout; when Arun's
   real inference path lands, the payload shape is identical by construction.

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
