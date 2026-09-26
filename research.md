# Research index

Deep notes live in `research/`. This file is the index + the short version of what we learned and
how it changed the build.

| Note | Covers |
|---|---|
| [research/cicids2017.md](research/cicids2017.md) | CIC-IDS2017: capture setup, attack schedule, IPs, documented dataset flaws, corrected release |
| [research/world-models.md](research/world-models.md) | What a world model is (PlaNet/Dreamer RSSM), why it differs from a sequence classifier, how it maps onto network telemetry |
| [research/mitre-mapping.md](research/mitre-mapping.md) | CIC-IDS2017 attack labels → MITRE ATT&CK tactics/techniques, and the ordered stage scale |
| [research/related-work.md](research/related-work.md) | Prior art in attack forecasting / prediction, and how NetWM differs |
| [research/early-warning-nulls.md](research/early-warning-nulls.md) | Why a lead-time count needs a circular-shift null; within-day vs leave-one-day-out separability; negative transfer from auxiliary heads; mean path vs Monte-Carlo; per-seed variance as a disqualifier; three cheap checks that retire a candidate without a training run; fixing the negative set (post-mortem of E12 → E15a → E15 → E16) |
| [research/state-normalisation.md](research/state-normalisation.md) | Why a train-fitted z-score loses the signal under day-to-day shift; the rank-based inverse normal transform; why whole-capture ranking leaks the future into a lead-time claim and the causal variant does not (S-4, D-025) |
| [research/ctu13.md](research/ctu13.md) | CTU-13 Dataset Transfer Evaluation: Scenarios, schemas, and adapter plan for M2 |

## The eight findings that shaped the design

1. **The dataset most IDS papers use is wrong in ways that matter to us.** CICFlowMeter
   mis-terminates TCP flows and the original labelling is purely time-window based, so attack
   *onset times* — the thing a forecaster must get right — are off, and some attack traffic is
   unlabelled entirely. We use the corrected re-extraction instead (→ D-001).
2. **A world model is defined by imagination, not by architecture.** RSSM's contribution is a
   latent state you can roll forward *without* decoding observations; the LSTM/Transformer is just
   the encoder. Our deliverable must therefore be judged on multi-step open-loop rollout quality,
   not one-step accuracy (→ D-004).
3. **Random splits on CIC-IDS2017 are leakage.** Near-duplicate flows from the same attack burst
   land in both train and test, which is why ~0.99 F1 is the norm in the literature and why it
   means nothing. Day-level and attack-family-level holdouts are the only honest evaluation
   (→ D-006).
4. **Lead time is the missing metric.** The published baselines report F1 on the *current* window;
   none of them report how early an alarm arrives. That is the axis on which a world model should
   beat a classifier, so it is a first-class metric in our benchmark (→ D-006).
5. **CIC-IDS2017 has no real exfiltration stage.** The infiltration day ends in an internal NMAP
   portscan from the compromised host — i.e. lateral movement/discovery — so the exfiltration stage
   is heuristic in M1 and gets real ground truth from CTU-13 in M2 (→ D-003).
6. **Seed spread is the real margin (E10).** The full model's Thursday F1 spans 0.43-0.57 over three seeds, so a 0.01 effect is noise unless it repeats across seeds. The stochastic latent never cleared that; the multi-step loss did, on detection only. The headline F1 always travels with its range (D-032).
7. **A pre-registration must be scoreable (E10).** D-030 named a metric the pipeline never recorded (rollout NLL; E5 records MSE), offered an either/or gate, and had a clause the reference model could not pass. All three were fixed before any number was read. Before a run, check that every metric exists in the outputs, that each claim has one gate, and that the reference can pass it.
8. **Calibration does not transfer to an unseen day (E17).** With compromise positives on only two days, the temperature can only be fitted in-sample, on the checkpoint's training days. Applied to held-out Friday, the result is worse than a constant forecast. The alert budget stays the deployable threshold, and outputs are called risk scores.

## Sources

- Engelen, Rimmer, Joosen — *Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study*, WTMC 2021. [PDF](https://intrusion-detection.distrinet-research.be/WTMC2021/Resources/wtmc2021_Engelen_Troubleshooting.pdf)
- Liu, Engelen, et al. — *Error Prevalence in NIDS datasets* (CNS 2022), per-attack error catalogue + corrected dataset. [Page](https://intrusion-detection.distrinet-research.be/CNS2022/CICIDS2017.html)
- Sharafaldin, Lashkari, Ghorbani — *Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic Characterization*, ICISSP 2018. [Dataset page](https://www.unb.ca/cic/datasets/ids-2017.html)
- Rocher et al. — *From CIC-IDS2017 to LYCOS-IDS2017: a corrected dataset*. [ACM](https://dl.acm.org/doi/fullHtml/10.1145/3486622.3493973)
- Hafner et al. — *Learning Latent Dynamics for Planning from Pixels* (PlaNet, RSSM), 2018. [arXiv:1811.04551](https://arxiv.org/abs/1811.04551)
- Hafner et al. — *Dream to Control* (Dreamer), 2019. [arXiv:1912.01603](https://arxiv.org/abs/1912.01603)
- Ha & Schmidhuber — *World Models*, 2018. [arXiv:1803.10122](https://arxiv.org/abs/1803.10122)
- *Multi-Stage Attack Detection via Kill Chain State Machines*. [arXiv:2103.14628](https://arxiv.org/pdf/2103.14628)
- *ProAPT: Projection of APT Threats with Deep Reinforcement Learning*. [arXiv:2209.07215](https://arxiv.org/pdf/2209.07215)
- MITRE ATT&CK Enterprise matrix. [attack.mitre.org](https://attack.mitre.org/)
- Theiler et al. — *Testing for nonlinearity in time series: the method of surrogate data*, Physica D 58 (1992) 77–94. [doi:10.1016/0167-2789(92)90102-S](https://doi.org/10.1016/0167-2789(92)90102-S)
- Lancaster et al. — *Surrogate data for hypothesis testing of physical systems*, Physics Reports 2018. [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0370157318301340)
- *ForkMerge: Mitigating Negative Transfer in Auxiliary-Task Learning*, 2023. [arXiv:2301.12618](https://arxiv.org/abs/2301.12618)
- Beasley, Erickson, Allison — *Rank-based inverse normal transformations are increasingly used, but are they merited?*, Behavior Genetics 39(5) (2009) 580–595. [doi:10.1007/s10519-009-9281-0](https://doi.org/10.1007/s10519-009-9281-0)
