# Demo script (T-14)

Five minutes, one capture, one checkpoint. Every number below was produced by the submission
checkpoint (`models/e4e7-worldmodel-r2/`, D-021 amendment) on the exact slice the dashboard loads,
and every claim stays inside D-021. If something on screen disagrees with this script, the screen
wins and the script is wrong - tell the orchestrator before recording.

Times are **UTC, as the dashboard shows them** (the capture ran 09:00-17:00 local, UTC-3).

## Which capture, and why

**`thursday_infiltration`** (16:40-18:50, 169 135 flows, 260 windows). It is served by
`e4e7-worldmodel-r2/thursday.pt`, whose training days are Monday, Tuesday, Wednesday and Friday:
**the model has never seen this day.** It holds the only compromise-to-lateral-movement story in
the dataset, and it is the fold every headline number comes from.

Optional second beat, only if there is time: **`friday_botnet_c2`** on `friday.pt` (trained
Monday-Thursday) - a family the model never saw in training.

**Do not demo:**

| slice | why not |
|---|---|
| `monday_benign`, `wednesday_dos` | No Monday or Wednesday fold exists, so they run on `thursday.pt`, which **trained on both days**. A quiet Monday is not a false-positive test when the model has seen it |
| `friday_scan_to_ddos` | `p_max` saturates near 0.99 across the slice; at the 10 % budget 25 of its 36 alarms land on benign windows. Its target counts only compromise, and scan + DDoS are Recon + Impact |
| any `.pcap` | not until A-3 lands and R-11 passes |

## Pre-flight (10 min before)

1. `run_demo.bat`; the API is on :5000, the dashboard on :8080. **Wi-Fi off** - the offline claim is
   part of the demo.
2. `GET /api/model` shows the r2 card: Thursday F1 **0.576**, FPR **0.027**, PR-AUC **0.640**, LR
   F1 **0.011**. If it shows zeros, a run folder is missing (D-024) - stop.
3. Load `thursday_infiltration` once to warm the model (~15 s cold). The payload must say
   `"mock": false`.
4. Pre-select nothing. Scroll the timeline to 16:40.

## The beats

| time | on screen | say |
|---|---|---|
| **0:00-0:30** | title | "Most intrusion detectors classify one flow at a time. We built a *world model*: it learns how the network's state moves from one 30-second window to the next, then rolls that forward ten steps without seeing any more traffic. Everything you'll see runs offline, on a day the model never trained on." |
| **0:30-1:00** | pick `thursday_infiltration`, progress bar | "This is two hours of Thursday from CIC-IDS2017, as flow records - a hundred and seventy thousand of them. The model trained on the other four days." |
| **1:00-1:45** | timeline 16:40-17:15; hover 17:00 in the ribbon | "Quiet traffic until 17:00, when an outside host scans one of our servers - 954 ports in fourteen seconds. Watch the surprise score: it's the model's own error at predicting the next window. Typical is about 0.15; here it jumps to 7.5. Infiltration probability stays low, correctly - a scan from outside is reconnaissance, not a compromise." |
| | the 17:10 alarm | **Scripted, do not improvise:** "There's one alarm here at 17:10, eight minutes before the attacker gets in. We don't count it as a warning. It's outside our five-minute horizon, and when we tested early alarms against chance, ours didn't beat it (p = 0.41). So it's a false positive, and we score it as one." |
| **1:45-2:45** | 18:04-18:45; click the 18:23 alarm; open the why panel | "At 17:19, 192.168.10.8 opens a session back to the attacker's machine - it's been compromised. From 17:33 it starts sweeping the internal network - eleven hosts, seventy thousand flows - and from 18:04 it's the top talker, 2 000 to 5 000 flows a minute. Surprise goes to 15-50. The why panel shows what the model looked at: destination-port spread up, and which earlier windows it attended to." |
| | stage ribbon over the sweep | "The ribbon shows the model calling this reconnaissance, where our ground truth says lateral movement. They're the same technique - network service discovery, T1046 - seen from inside instead of outside. We split them by source address (D-012); the model hasn't learned that split. We'd rather show it than hide it." |
| **2:45-3:15** | the forecast cone on a sweep window | "This cone is the rollout: ten steps imagined in latent space, with Monte-Carlo bands. That's what makes it a world model rather than a classifier. From step 2 on, it predicts the next state better than just repeating the current one. At step 1 it doesn't, and we report that too." |
| **3:15-4:00** | model card | "On the full held-out day: F1 0.576 at a 2.7 % false-positive rate, precision 0.78. The logistic regression the problem statement asks us to beat scores 0.011 on the same features at its own threshold. On this slice, 24 of the 26 alarms land on attack windows. You'll also see nothing fired between 17:18 and 18:23: at a 10 % alert budget, the model spends its alarms on the loudest phase, the sweep." |
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
| "Why a 10 % alert budget?" | "Probability thresholds don't transfer between days - the best threshold was 0.84 on training days and 0.06 on Thursday, about 14x apart. A budget is what a SOC actually sets: how many alerts per shift." (D-020) |
| "What's the surprise score?" | "The model's negative log-likelihood of the next window, under its own prediction. High means 'this isn't how this network normally moves'. It needs no attack labels." |
| "Is this the original CIC-IDS2017?" | "No - the corrected re-extraction. The original mis-terminates TCP flows and mislabels attack onsets, and onset time is exactly what we measure." (D-001) |
| "Why is the stage wrong on the sweep?" | The ribbon answer above: same technique, different vantage point, split by source address in our labels. |
| "Does it work on packets?" | Only if A-3 has landed and been demoed. Otherwise: "The packet feature extractor is built and tested; the packet-to-flow step is in progress. Today's demo is flow records, which is what most SOCs export." |
| "Why no Monday demo?" | "Every checkpoint we have trained on Monday, so a clean Monday proves nothing. We only demo days the model hasn't seen." |
| "What happens on an attack it's never seen?" | Friday botnet, if shown: it catches the C2 channel 13 minutes late, and gives it the wrong stage - C2 appears in no training day. "That's the generalisation gap, measured." |

## Numbers card - every figure above, with its source

| figure | value | source |
|---|---|---|
| held-out Thursday, `p_max`, 10 % budget | F1 0.576 · FPR 0.027 · precision 0.776 · PR-AUC 0.640 | E14, D-024 |
| logistic regression, same features and fold | F1 0.011 at its own threshold | E3 |
| rollout vs persistence | better from k = 2, worse at k = 1 | E5 |
| E14's early warning against the null | 1 of 4, p = 0.412 - withdrawn | E15a |
| threshold non-transfer | 0.843 train vs 0.059 Thursday | E4-E7 |
| slice: alarms on attack windows | 24 of 26; 22 % of attack windows alarmed | this slice, see below |
| slice: surprise | benign median 0.15; 7.5 at the 17:00 scan; 15-52 during the sweep | this slice |
| slice: 17:00 scan | 172.16.0.1 -> 192.168.10.51, 954 ports, 17:00:31-17:00:45 | S-8, `results/tables/s8_thursday_onset602_*.csv` |

The slice figures come from `analyze_file("data/demo/thursday_infiltration.csv",
load_checkpoint("models/e4e7-worldmodel-r2/thursday.pt"))`, the same call the demo endpoint makes
(D-024). They are description, not evaluation: the 10 % budget is computed on the slice itself.

## Fix before recording

- **Surprise is only in a ribbon tooltip.** It's the strongest live signal on this slice, and it's
  the world model's own quantity. Plot it as a second series on the timeline (Harshit).
- **In-sample demos aren't flagged.** The payload should say when the demo day is one of the
  checkpoint's `train_days`, and the dashboard should badge it (Arun + Harshit). Until then this
  script simply doesn't use those slices.
- **PCAP:** out of the demo until A-3 + R-11.
