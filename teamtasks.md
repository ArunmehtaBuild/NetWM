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

**Not started at all:** Flask backend, the whole frontend, packet-level features, PCAP ingestion.

**Known defects (found in the 2026-09-25 audit):**
- `engine/predict.py:123` scores alarms with the cumulative union while **D-019** says max over
  horizon - and max is the only statistic that produced *any* early warning (E13).
- `world_model.py` emits `p_cum_attack` / `p_cum_escalate`; `engine/predict.py` drops both.
- Payload drift vs `app/api_contract.md` v1: missing `observed_stage`, `top_talkers`,
  `ground_truth.spans`; extra `until_t`, top-level `stages`.
- `app/mock/` is empty, so the frontend is blocked on a file that takes one command to make.

## Tracks and owners

| person | track | owns |
|---|---|---|
| **Atharv** | Orchestration + ML correctness | this board, decisions/results discipline, inference engine correctness, architecture doc |
| **Yash** | Model: make it forecast | training objectives, calibration, unseen-family evaluation |
| **Sanchi** | State & features | feature matrix, trend/derivative features, per-host channels |
| **Alok** | Packets & demo data | PCAP sourcing, packet features, PCAP->flows, demo slices |
| **Arun** | Backend | Flask API, job runner, SSE replay, offline packaging |
| **Harshit** | Frontend | the SOC dashboard, replay, demo video |

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
| **T-01** | Alarm statistic: switch scoring to `p_max` (max over horizon) per D-019, re-score the existing r2 checkpoints, and report lead time at train-tuned / alert-budget / oracle thresholds | `results.md` E14 with a lead-time column; D-019 moves to `accepted` or is rewritten with the negative result |
| **T-02** | Payload v1.1: emit `p_max`, `p_cum_attack`, `p_cum_escalate`, `observed_stage`, `top_talkers`, `ground_truth.spans` from `engine/predict.py`; regenerate `app/mock/thursday.json` + `friday.json` | Arun and Harshit can both start without asking anyone a question |
| **T-03** | Review gate: every incoming commit (teammate or parallel session) checked for a `results.md` / `decisions.md` entry and a task id | no orphan numbers in the repo |
| **T-04** | Architecture document (2 pages) once T-01 lands | reviewed by two teammates |
| **T-05** | Keep this board current after every merge | board matches `git log` |

## Yash - make it forecast (the research risk)

| id | task | done when |
|---|---|---|
| **Y-1** | Calibration: temperature-scale the risk heads on a held-out *training* day, then re-report the train-tuned threshold gap (D-017 says revisit once this exists) | train-tuned vs oracle threshold gap under 3x, or documented as unfixable |
| **Y-2** | **Precursor supervision.** E12 shows the 10 windows before an onset are separable at ROC-AUC 0.88-0.96, but nothing in training tells the model they are special. Add a fourth head: `precursor` = "an onset occurs within the next K windows and this window is not itself an attack window", trained on those windows explicitly | `results.md` E15: lead time > 0 on at least 2 of 5 episodes at the alert-budget threshold, or a documented negative result with the loss curves |
| **Y-3** | Formalise E8: leave-one-attack-family-out, reported as its own experiment rather than buried in the Friday fold | `results.md` E8 with Infiltration-held-out and Botnet-held-out rows |
| **Y-4** | After Sanchi ships S-1, retrain on `S_t` v2 and run the E10 ablation (with / without trend features, with / without stochastic latent, with / without multi-step loss) | ablation table showing which components earn their place |

Constraint: architecture changes need a decisions.md entry *before* the run, not after.

## Sanchi - give the model the signal E12 found

| id | task | done when |
|---|---|---|
| **S-1** | **Trend features.** `S_t` is currently levels only - the model sees *how many* distinct destination ports, never *how fast that is rising*. Add deltas and rolling slopes (2, 5, 10 windows) for the features E12 ranked highest: `uniq_dst_port`, `ports_per_pair_max`, `port_fanout_max`, `uniq_dst_ip`, `fanout_mean`, `flows_per_s`, plus z-scores against a rolling benign baseline | `S_t` v2 built for all 5 days; feature count and build time in `results.md` F2; decisions entry for the window choices |
| **S-2** | Per-host channel: top-N talkers as their own sub-vector (fan-out, ports touched, in/out byte ratio, new-peer rate) so lateral movement is visible per host, not only in network-wide aggregates | schema documented; Yash can train on it behind a config flag |
| **S-3** | Feature dictionary in `research/features.md`: every feature, its formula, and which attack behaviour it is meant to expose | reviewable by someone who has not read the code |

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

| id | task | done when |
|---|---|---|
| **R-1** | `app/server.py` + `app/jobs.py`: upload -> background worker -> progress -> result, wrapping `netwm.engine.predict.analyze_file`. Serve `app/mock/*.json` when no checkpoint is present so the app is never undemoable | `POST /api/analyze` with a real CSV returns a real payload; `GET /api/jobs/<id>` reports progress |
| **R-2** | Contract v1.1: update `app/api_contract.md` to match what T-02 emits (the two extra risk curves, `p_max`, `observed_stage`, `top_talkers`, `ground_truth.spans`, `until_t` on alarms) and delete anything we decided not to ship | contract, mock and engine agree - verified by a test that validates the mock against the documented keys |
| **R-3** | SSE replay `/api/jobs/<id>/stream` at `?speed=` windows/sec | the dashboard can play an attack unfolding |
| **R-4** | Offline hardening: size caps, error codes, no outbound calls anywhere, `run_demo.bat` one-command start | works with WiFi off on a machine that has never seen the repo |

## Harshit - frontend

| id | task | done when |
|---|---|---|
| **H-1** | Shell + dark SOC theme + vendored Chart.js (no CDN), reading `app/mock/thursday.json` | loads offline, renders the timeline |
| **H-2** | Forecast timeline: observed risk line, K-step forecast cone (`p_lo`/`p_hi`), alarm threshold, ground-truth attack spans shaded | the Thursday infiltration is visually obvious |
| **H-3** | Kill-chain ribbon (predicted stage per window) + current-stage card with ATT&CK tactic id | stage colours come from the API, never hard-coded |
| **H-4** | **Alarm log with lead time** - "fired N windows (M s) before onset". This is the single most important panel in the demo video | reads `alarms[].lead_windows` |
| **H-5** | Why-panel: attribution bars + attention heatmap; flagged-flows table | every alarm can be explained on screen |
| **H-6** | Replay mode (play/pause/scrub) on the SSE stream, then record the 2-minute demo video | video shows risk rising *before* the attack lands |

H-1 and H-2 start the moment `app/mock/thursday.json` exists (Atharv, T-02). Do not wait for a model.

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
| Everything runs offline, no cloud API calls | Arun | [ ] |
