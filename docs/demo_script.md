# Demo script (T-14)

Five minutes, one capture, one checkpoint. Every number below was produced by the served CSV checkpoint
(`models/n8-r2w-s42/`: r2's setup with window positions, D-041 gate G3) on the exact slice the dashboard
loads. It was measured through the backend's own demo path under the causal alert budget the dashboard
serves (D-034), by `scripts/demo_figures.py`. Every claim stays inside D-021. If something on screen
disagrees with this script, the screen wins and the script is wrong - tell the orchestrator before
recording.

Times are **UTC, as the dashboard shows them** (the capture ran 09:00-17:00 local, UTC-3).

## Which capture, and why

**`thursday_infiltration`** (16:40-18:50, 169 135 flows, 260 windows). It is served by
`n8-r2w-s42/thursday.pt`, whose training days are Monday, Tuesday, Wednesday and Friday: **the model
has never seen this day.** It holds the only compromise-to-lateral-movement story in the dataset, and
it is the fold every headline number comes from.

Optional second beat, only if there is time: **`friday_botnet_c2`** on `friday.pt` (trained
Monday-Thursday) - a family the model never saw in training. Use the scripted answer under "Judge
follow-ups": its first alarm comes before the C2 channel exists.

**Do not demo:**

| slice | why not |
|---|---|
| `monday_benign`, `wednesday_dos` | No Monday or Wednesday fold exists, so they run on `thursday.pt`, which **trained on both days**. A quiet Monday is not a false-positive test when the model has seen it |
| `friday_scan_to_ddos` | 43 of its 80 alarmed windows are benign, and `p_max` reaches 0.99 from 17:51, an hour before the DDoS. Its target counts only compromise, and scan + DDoS are Recon + Impact |
| any `.pcap` for scores | The PCAP route works end to end (F8), but it raises no alarm on the demo capture, which is synthesised from CSV rows (D-031) and says nothing about the model. No PCAP-route detection number is quoted anywhere (N-9). If it is shown at all: 10 s of ingestion - the upload, the progress bar, the route badge - and no scores |

## Pre-flight (10 min before)

1. `run_demo.bat`; the API is on :5000, the dashboard on :8080. **Wi-Fi off** - the offline claim is
   part of the demo.
2. `GET /api/model` shows the r2w card: Thursday F1 **0.591**, FPR **0.093**, PR-AUC **0.677**, and
   LR F1 **0.112** at the same causal threshold (D-041 gate G3; G-6).
   - If it shows 0.608 / 0.640, the API is serving the replaced r2.
   - If it shows zeros, a run folder is missing (D-024) - stop.
3. Load `thursday_infiltration` once to warm the model (~15 s cold). The payload must say
   `"mock": false` and `"threshold_policy": "expanding-10pct"`. If it says `fixed`, the API predates the
   F8 serving fix (`a4bd3e8`) and will raise no alarm on this day - stop.
4. Pre-select nothing. Scroll the timeline to 16:40.

## The beats

| time | on screen | say |
|---|---|---|
| **0:00-0:30** | title | "Most intrusion detectors classify one flow at a time. We built a *world model*: it learns how the network's state moves from one 30-second window to the next, then rolls that forward ten steps without seeing any more traffic. Everything you'll see runs offline, on a day the model never trained on." |
| **0:30-1:00** | pick `thursday_infiltration`, progress bar | "This is two hours of Thursday from CIC-IDS2017, as flow records - a hundred and seventy thousand of them. The model trained on the other four days." |
| **1:00-1:45** | timeline 16:40-17:15; hover 17:00 in the ribbon | "Quiet traffic until 17:00, when an outside host scans one of our servers - 954 ports in fourteen seconds. Watch the surprise score: it's the model's own error at predicting the next window. Typical is about 0.15; here it jumps to 7.5. The infiltration risk score stays low, about 0.01 - a scan from outside is reconnaissance, not a compromise." |
| | the 17:05-17:11 alarms | **Scripted, do not improvise:** "The threshold is the stepped line: it's set only from the traffic seen so far, so it starts low on a quiet afternoon. The scan trips it at 17:00, and it fires again at 17:05, 17:07 and 17:10 - eight to fourteen minutes before the attacker gets in. We don't count those as warnings. They're outside our five-minute horizon, and when we tested early alarms against chance, ours didn't beat it (p = 0.34 on the full day). The dashboard runs that same test live and says so in the alarm panel." |
| **1:45-2:45** | 17:19-18:45; click the 18:35 alarm; open the why panel | "At 17:19, 192.168.10.8 opens a session back to the attacker's machine - it's been compromised. Nothing alarms for the next fourteen minutes: the quiet session itself doesn't move the score. From 17:33 it starts sweeping the internal network - eleven hosts, seventy thousand flows - and from 18:04 it's the top talker, 2 000 to 5 000 flows a minute. The alarm holds from 18:08 to 18:33, and surprise peaks around 52. The why panel shows the feature contributions: the database-service share, distinct destination ports and per-host port fan-out push the score up - and which earlier windows the model attended to." |
| | stage ribbon over the sweep | "The ribbon shows the model calling this reconnaissance, where our ground truth says lateral movement. They're the same technique - network service discovery, T1046 - seen from inside instead of outside. We split them by source address (D-012); the model hasn't learned that split. We'd rather show it than hide it." |
| **2:45-3:15** | the forecast cone on a sweep window | "This cone is the rollout: ten steps imagined in latent space, with Monte-Carlo bands. That's what makes it a world model rather than a classifier. Averaged over steps 2-10, it predicts the next state better than just repeating the current one. At step 1 it doesn't, and we report that too." |
| **3:15-4:00** | model card | "On the full held-out day, with a threshold set only from the traffic seen so far, the checkpoint we ship scores F1 0.59, precision 0.57, at a 9.3 % false-positive rate. That is the best of three seeds: retrained on two more, the same recipe scores 0.50 and 0.58. The logistic regression the problem statement asks us to beat scores 0.11 on the same features at the same threshold policy. On this slice, 65 of the 78 alarmed windows are attack windows, and the long alarm from 18:08 to 18:33 is the sweep." |
| **4:00-4:45** | slide 5 (S-6) | **The forecasting gap - verbatim, below.** |
| **4:45-5:00** | dashboard | "Everything here - features, model, dashboard - runs on one laptop with no network. Code, decisions and every number's source are in the repo." |

## The forecasting gap - say exactly this

> "What it does not do yet is warn *before* the attacker gets in. We tested that properly: against a
> shuffled-time baseline, across four attack days, three seeds. Our early alarms didn't beat chance.
> We withdrew our own number when it failed. Then we ruled out five causes, one experiment each - the
> scoring statistic, the threshold, the data, the training target, and how each capture is
> normalised. What's left is this: trained on one set of attack families, the model's weighting
> doesn't carry over to another. A seventy-feature model does no better than one feature. That's
> the next experiment."

**Never say:** "predicts attacks", "early warning", "forecasts intrusions N minutes ahead", "zero-day
detection", or any lead time in minutes. The PS word *forecast* is fine for the K-step state rollout
and the stage distribution; it is not fine for "before the compromise".

**E16 is in:** per-capture rank normalisation failed every clause of the D-023 bar on all three
seeds, and was unstable across them. That is the fifth cause in the paragraph above. The 70-vs-1
feature comparison is E16's Thursday logistic regression, 0.604 against `uniq_dst_port`'s 0.607.
If a judge asks "what about the one clean case?": onset 602 had a long quiet run-up and a real rise,
and none of it came from the attack (S-8, under E16). "It looked like a precursor. We checked the
flows. It wasn't one."

## Judge follow-ups

| question | answer |
|---|---|
| "So can it predict attacks?" | "No, and we can show you why we're sure. Here's the null test." (E15a, E15.) Then the gap paragraph. |
| "Why isn't your F1 0.99 like the papers?" | "Those use random splits. Near-duplicate flows from one attack burst land in both train and test. We hold out whole days, so the model has never seen this day." (D-006) |
| "How do you set the threshold?" | "From the day so far: we alarm on what's in the top 10 % of everything seen since the shift started, never using the future. Fixed probability thresholds don't transfer - the one tuned on training days is 0.92, and on held-out Thursday it fires nothing; the best one there would have been 0.01. The honest cost: because the past was quiet, it alarms on about 18 % of the day's windows, not 10 %." (D-034, E18; `n8-r2w-s42_forecast.csv`) |
| "What's the surprise score?" | "The model's negative log-likelihood of the next window, under its own prediction. High means 'this isn't how this network normally moves'. It needs no attack labels." |
| "Is this the original CIC-IDS2017?" | "No - the corrected re-extraction. The original mis-terminates TCP flows and mislabels attack onsets, and onset time is exactly what we measure." (D-001) |
| "Why is the stage wrong on the sweep?" | The ribbon answer above: same technique, different vantage point, split by source address in our labels. |
| "Does it work on packets?" | "Yes, as its own route: a PCAP upload is turned into flows and packet features and scored by the mean of three packet models, never by this flow model. We show the ingestion today. We don't quote a detection number for live captures yet, because we haven't finished proving the live packet state matches what the model was trained on." (D-038, D-043, N-9) |
| "Why no Monday demo?" | "Every checkpoint we have trained on Monday, so a clean Monday proves nothing. We only demo days the model hasn't seen." |
| "What happens on an attack it's never seen?" | Friday botnet, if shown: "Its first alarm, 12:55 to 13:02, comes before the C2 channel even opens at 13:03. Against chance, an alarm that early is unremarkable - p = 0.31 - so we don't count it as a warning. It alarms again at 13:04 and from 13:14. And it never names the stage: C2 appears in no training day, so the ribbon says benign or initial access. That's the generalisation gap, measured." |

## Numbers card - every figure above, with its source

| figure | value | source |
|---|---|---|
| held-out Thursday, `p_max`, causal expanding q90 | F1 0.591 (0.50-0.59 over 3 seeds) · precision 0.574 · recall 0.608 · FPR 0.093 · PR-AUC 0.677 (0.34-0.68 over 3 seeds) | D-041 G3, `results/tables/n8_fix_eval.csv` |
| the same day's alarm rate | 176 of 972 windows (18.1 %) | `demo-r2w-figures` (stored held-out scores) |
| logistic regression, same features, fold and causal threshold | F1 0.112 | G-6, `results/tables/benchmark_final.csv` |
| rollout vs persistence (next-state MSE, held-out Thursday) | steps 2-10: 2.47 against 2.66; step 1: 2.01 against 1.05 (Friday: 1.72 against 1.84; 1.43 against 0.69) | `results/runs/n8-r2w-s42/metrics.json`, `demo-r2w-figures` |
| early warning against the null, full Thursday | 2 of 4 onsets, p = 0.34 | `demo-r2w-figures` (the dashboard's own test) |
| E14's early warning against the null (r2, history) | 1 of 4, p = 0.412 - withdrawn | E15a |
| threshold non-transfer | train-tuned 0.921 fires nothing on held-out Thursday; the best threshold there is 0.010 | `results/tables/n8-r2w-s42_forecast.csv` |
| slice: alarms | 78 of 260 windows alarmed, in 14 runs; 65 on attack windows; 59 % of the 110 attack windows alarmed; 0 of 4 onsets warned early, null p = 1.0 | `demo-r2w-figures` |
| slice: alarm times | 17:00 (the scan); 17:05, 17:07, 17:10; none from 17:19 to 17:33; 17:33 and three single windows 17:43-17:48; 18:06; 18:08-18:33 (51 windows); four short runs 18:34-18:44 | `results/tables/demo_r2w_alarm_runs.csv` |
| slice: risk score at the scan | `p_max` 0.0097, above a threshold of 0.0043 | `demo-r2w-figures` |
| slice: surprise | benign median 0.16 (0.15 before the scan); about 7.5 at the 17:00 scan; over the sweep (18:04-18:45) median 7, peak about 52 | `demo-r2w-figures` |
| slice: the 18:35 alarm | `p_max` 0.229, the slice's highest; top contributions up: database-service share, distinct destination ports, per-host port fan-out | `demo-r2w-figures` |
| slice: ribbon over the sweep | Reconnaissance on 73 of 83 windows | `demo-r2w-figures` |
| slice: 17:00 scan | 172.16.0.1 -> 192.168.10.51, 954 ports, 17:00:31-17:00:45 | S-8, `results/tables/s8_thursday_onset602_*.csv` |
| Friday C2 slice | first alarm 12:55:30-13:02:30, before the 13:03:30 onset, null p = 0.307; next alarms 13:04 and 13:14-13:21; stage on the 116 C2 windows: benign 64, initial access 51, reconnaissance 1, C2 never | `demo-r2w-figures`, `demo_r2w_alarm_runs.csv` |
| `friday_scan_to_ddos` (not demoed) | 43 of 80 alarmed windows benign; `p_max` up to 0.99 from 17:51 | `demo-r2w-figures`, `demo_r2w_alarm_runs.csv` |

**Where the slice figures come from.** `python scripts/demo_figures.py` writes
`results/runs/demo-r2w-figures/metrics.json` and `results/tables/demo_r2w_alarm_runs.csv`.
- **How.** It uses the backend's own demo path (`backend.inference.run_job_inference`), the served
  `n8-r2w-s42` checkpoints and the causal expanding 10 % budget: the payload the dashboard draws.
- **Description, not evaluation.** The budget is computed on the slice so far, which starts at 16:40.
  So the threshold is set by 20 minutes of quiet traffic, and it alarms on 30 % of the slice's windows,
  on a capture that is 42 % attack windows.
- **What varies between loads.** Alarms and `p_max` come from the deterministic mean path and repeat
  exactly. Surprise and the stage ribbon come from Monte-Carlo samples and move slightly between loads
  (7.47 at the scan and 73 of 83 reconnaissance windows in the recorded run). Quote them rounded, as
  above.

## Fix before recording

- ~~The dashboard's threshold is still the whole-capture one.~~ Done (G-9): the dashboard, the model
  card and the fixtures use the causal expanding budget.
- ~~The served checkpoint was alarming on a fixed threshold.~~ Done (F8, `a4bd3e8`, D-041 serving
  note). The r2w checkpoints name no policy, so from D-041's swap until the fix the CSV route served
  its train-tuned 0.921 and raised no alarm on this day. Pre-flight step 3 checks for it.
- ~~Surprise is only in a ribbon tooltip.~~ Done: surprise is its own series on the timeline
  (`results/figures/f8_dashboard_thursday_demo.jpg`).
- ~~In-sample demos aren't flagged.~~ Done (R-12): the payload carries `in_sample`, and the dashboard
  badges a held-out day.
- **Length.** This script is timed for 5 minutes; the video is capped at 2 (G-3). The cut is the
  board's item, not this file's.
- **PCAP:** ingestion only, no scores (N-9; see "Do not demo").
