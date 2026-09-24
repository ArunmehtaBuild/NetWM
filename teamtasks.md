# Team tasks

Six-person SIH team. Owners are placeholders - put real names in the `owner` column. Status:
`todo` / `doing` / `review` / `done`. Keep this file in sync with [plan.md](plan.md); plan.md is the
technical breakdown, this is who does what and by when.

## Roles

| role | owner | scope |
|---|---|---|
| R1 Data / features | TBD | dataset download + audit, flow & packet feature extraction, windowing |
| R2 Modelling | TBD | world model, training loop, baselines, ablations |
| R3 Evaluation / explainability | TBD | metrics, benchmark harness, attention + IG/SHAP outputs |
| R4 Backend | TBD | Flask API, inference service, sample generation, packaging |
| R5 Frontend | TBD | dashboard, timeline, stage ribbon, flow table, explanation panels |
| R6 Docs / demo | TBD | architecture doc, slides, demo video, README, submission hygiene |

## Now (this sprint)

| # | task | role | status | notes |
|---|---|---|---|---|
| T1 | Approve + run the corrected CIC-IDS2017 download (328 MB) | R1 | todo | blocks everything downstream |
| T2 | venv + torch cu121 smoke test on the GTX 1650 | R2 | todo | confirm CUDA is actually used |
| T3 | Dataset audit E1 (labels per day, onset times, window counts) | R1 | todo | first entry in results.md |
| T4 | Flow feature extractor + windowing | R1 | todo | see plan.md P2 |
| T5 | MITRE stage mapping + hazard targets | R3 | todo | research/mitre-mapping.md is the spec |
| T6 | Logistic regression + persistence baselines | R2 | todo | E2, E3 - must land before the world model |
| T7 | Find a working source for Thursday PCAP | R1 | todo | packet-level features are a PS requirement |
| T8 | Fill in real names + a target date per row | R6 | todo | |

## Next

| # | task | role | depends on |
|---|---|---|---|
| T9 | World model implementation + training loop | R2 | T4, T6 |
| T10 | Packet-level feature extractor (Scapy streaming) | R1 | T7 |
| T11 | K-step rollout engine + metric suite (incl. lead time) | R3 | T9 |
| T12 | Flask API + inference entry point | R4 | T9 |
| T13 | Dashboard UI | R5 | T12 |
| T14 | Explainability outputs (attention + IG, SHAP for baseline) | R3 | T9 |
| T15 | Benchmark table: world model vs LR, both splits | R3 | T11 |
| T16 | Architecture doc (2 pages) + 5 slides + 2-min video | R6 | T15, T13 |

## Submission checklist (PS-153)

- [ ] Public GitHub repo link
- [ ] README with setup instructions that a fresh machine can follow
- [ ] Architecture document, max 2 pages
- [ ] Demo video, max 2 minutes, showing a CSV *and* a PCAP upload
- [ ] Technical presentation, max 5 slides
- [ ] Benchmark table vs logistic regression (F1, precision, recall, FPR)
- [ ] Model weights + reproducible training config committed
- [ ] Everything runs offline, no cloud API calls
