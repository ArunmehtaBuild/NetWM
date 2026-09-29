# NetWM: Architecture

**SIH 2026 · PS 26153 (NTRO) · AI based Network Attack Forecasting from Network Traffic Data**

NetWM learns how a network's state evolves from one time window to the next, and rolls those dynamics
forward to score the next five minutes. It is a world model with prediction heads, not a flow
classifier. Every number below comes from `results/`; every design choice has its reason in
`decisions.md` (D-xxx).

```
 flow CSV ─► 60 s windows,  ─► CSV route:  70 flow features ──────────────────────► r2w (seed 42)
 PCAP ─────► 30 s stride    ─► PCAP route: 70 flow + 17 packet-stat + 18 pcap_ ────► E20rw, mean of seeds 42/43/44
 each model:  S_t ─► encoder ─► attention over the last 16 windows ─► RSSM latent ─┬► next-state decoder → surprise
                                                                                   ├► stage head        → MITRE stage
                                                                                   └► risk heads        → K = 10 rollout
 alarm: p_max on the mean path ≥ causal 90th percentile of earlier scores · explanation: attention + Integrated Gradients
```

## 1. Network state `S_t`

- **Windows.** Traffic is aggregated into 60 s windows at a 30 s stride. `S_t` is one feature vector per
  window, because consecutive flow records are not consecutive states (D-002).
- **Flow features (70, both routes).** TCP flag ratios, the protocol and service mix, bytes, packets,
  duration and inter-arrival statistics, bidirectional ratios, unique IPs and ports, port entropy,
  fan-out, and ports per pair.
- **Packet features (35, PCAP route).** 17 per-packet statistics a flow meter records, and 18
  measured from the packets themselves: TTL, fragments, retransmissions, zero windows, the payload
  histogram, inter-packet timing, SYN-only and RST shares.
- **PCAP converter.** A capture becomes flows by the corrected extraction's rules (D-033, D-043),
  traced flow by flow against the corrected CSVs.
- **Scaling.** `log1p` on heavy tails, then a scaler fitted on training days only (D-014).
- **Data.** The corrected CIC-IDS2017 re-extraction (D-001). Labels are ordered MITRE stages, with Impact
  off the progression axis (D-003); `- Attempted` traffic sets no stage (D-009).

## 2. World model

An RSSM-style latent model of about 0.6 M parameters (r2w: 584,470; E20rw: 593,500 each).
- An encoder, then causal attention over the last 16 windows. Each key is positioned by its distance
  from the query, so a window's score never depends on how much of the capture follows it (D-041).
- A stochastic latent with a learned prior: the transition function the rollouts imagine with.
- Heads on any real or imagined state: a next-state decoder (its error is the *surprise*), a MITRE
  stage head, and compromise, attack and escalation risk (D-016).
- **Streaming.** The latent and the last 15 embeddings carry across calls. Scoring a feed in 60-window
  chunks equals one pass to 2.3e-10 on every served checkpoint (D-041, gate G1).
- **What the dynamics earn.**
  - Against the same encoder predicting "within K" directly, the world model ranks pre-onset windows
    better (0.70 against 0.61) and detects better (PR-AUC 0.39 against 0.22) (E24).
  - Its rollouts beat "nothing changes" averaged over steps 2-10, though not at k = 1 (E10).
  - Logistic regression ranks pre-onset windows as well (0.66 against 0.65, E26). Anticipation as a
    ranking does not need a world model; detection at a usable alarm cost does.

## 3. Forecast, alarm and explanation

- **Forecast.** From each window's filtered state the model imagines K = 10 steps (5 minutes, D-013).
  The alarm score `p_max` is the largest compromise risk over the rollout, on the deterministic mean path
  (D-019); Monte-Carlo rollouts give the uncertainty band.
- **Alarm.** A causal alert budget: each window's threshold is the 90th percentile of the scores before
  it, with no alarm in the first 10 minutes (D-034). Thresholds tuned on training days fire nothing on a
  held-out day (D-017).
- **Stage.** The stage head maps each forecast to MITRE ATT&CK (`src/netwm/labels/mitre_map.py`).
- **Explanation.** When: attention over earlier windows. What: Integrated Gradients over the input
  features on alarm windows (D-018); the logistic-regression baseline gets exact linear SHAP.

## 4. Served routes

| input | model | inputs | why |
|---|---|---:|---|
| flow CSV | r2w, seed 42 (`models/n8-r2w-s42/`) | 70 | passed D-041's gate G3 |
| PCAP | E20rw, mean of seeds 42/43/44 (`models/m1v2-n8-e20rw-s4{2,3,4}/`) | 105 | D-038's aggregation; gate G2 |

- A PCAP never falls back to the CSV model, and a CSV never reaches the packet model.
- The PCAP route's live scores follow its training-state scores at 0.991 on a real capture (0.104
  before D-043).
- **Deployment.** A FastAPI backend and a static dashboard, fully offline: a test makes every outbound
  connection raise. The 17 served checkpoint files are in the repository (D-046), identified by SHA-256.
- **Frozen evidence.** Tag `submission-freeze` (`results/runs/submission-freeze/manifest.json`).

## 5. Results: CIC-IDS2017, leave-one-day-out, causal threshold

| held-out Thursday | PR-AUC | F1 | precision | recall | FPR |
|---|---:|---:|---:|---:|---:|
| CSV route: r2w seed 42 (seeds 43 / 44: 0.340 / 0.408) | **0.677** | 0.591 | 0.574 | 0.608 | 0.093 |
| PCAP route: E20rw mean (seeds: 0.409 / 0.542 / 0.726) | **0.514** | 0.583 | 0.581 | 0.584 | 0.087 |
| logistic regression, same features and threshold | 0.139 | 0.112 | 0.167 | 0.084 | 0.087 |

- **Friday** holds only a C2 family seen on no training day: both routes are near floor (0.118, 0.137).
- **Packets help detection, not anticipation.** They raised Thursday PR-AUC from 0.43 to 0.56 over
  flow-only (E20r), but not the pre-onset ranking.
- **Anticipation (PCAP route, 19 onsets).** Pre-onset windows rank above background at 0.675 (chance
  0.5). Alarm precision is 0.350 at FPR 0.129. Only 5 of 19 onsets are warned early (p = 0.53 against a
  circular-shift null).
- **Cross-family, not served** (each family held out in turn, 3 seeds, 95 % block-bootstrap intervals):
  - **CTU-13 (E25b).** Detection transfers firmly to NSIS (0.98). The model is inverted on Murlo and
    Rbot s11, scoring the bot below background. Most inversions are feature-direction flips (N-6a).
  - **CIC-IDS2018 (E28).** Held-out attack families are recognised:
    - BruteForce 0.89-0.99, DoS 0.81-0.93;
    - DDoS and Web partial (Web 0.64-0.77).
  - **Compromise does not carry** on CIC-IDS2018: Infiltration is inverted on one day (0.26-0.42), and
    Botnet (0.69-0.78) sits below LR (0.82).

## 6. Limitations

1. **No validated early warning** on any of the three datasets. The claim is "ranks pre-attack windows
   above background" (D-021).
2. **Compromise does not transfer to an unseen compromise family**, although attack families do (E25b,
   E28). The architecture stays as it is; no per-host or graph model was built (D-045).
3. **Risk scores, not calibrated probabilities** (E17): hence the alert budget.
4. **Explanations and stage labels are weak on unseen attacks.**
   - The top-8 attributions contain the known signature on only 1 of 6 held-out episodes (E11).
   - The stage head cannot recall a stage its fold never trained on (E9).
5. **Live-PCAP quality is not measured.** The PCAP converter's parity is substantially validated, but
   not exact: `active_mean` is still 9 % off (N-9). No live-PCAP detection number is claimed.
