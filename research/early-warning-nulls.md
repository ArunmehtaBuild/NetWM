# Early-warning counts need a null — post-mortem of E12 → E15a → E15

Written after round 3 (Y-2). The transferable content is the *method*, not our negative result: any
team that reports "the alarm fired N windows before the attack" on a dataset with a handful of
episodes is exposed to the same three failure modes, and two of them bit us before we noticed.

## 1. Why a raw lead-time count means nothing

Lead time is scored by asking whether an alarm fired inside `[onset − K, onset)`. Two properties of
the setting make that question almost free to answer by accident:

- **The score is autocorrelated.** A rollout statistic drifts smoothly, so an alarm at a 10 % alert
  budget is not 972 independent coin flips — it is a handful of contiguous runs. Any one of them
  landing in a K-window pre-onset block is a coincidence, not foresight.
- **There are very few episodes.** CIC-IDS2017 gives 5 compromise onsets in a week (26 if episodes
  are keyed on any attack). With n that small, one lucky run is a large fraction of the score.

We measured it: a score with the autocorrelation of a real rollout, at a 10 % budget, warns early on
**~1.7 of 8 episodes by chance**. Our own published E14 figure — *"1 of 4 episodes at the oracle
threshold"* — sits at **p = 0.412** against that null, and its Friday counterpart at p = 0.550 while
firing on 47 % of the day. Both were already hedged in D-019, but neither was ever *measured* until
E15a, and both had been quoted in a results table for a day.

## 2. The null we settled on: circular shift

Roll the score array by a random offset and recount. This is a **constrained-realisation surrogate**
in Theiler's sense: it preserves the score's marginal distribution *exactly* (so the alert budget,
and hence the alarm rate, is identical by construction) and its autocorrelation almost exactly,
while destroying only its alignment with the onsets. Shifted surrogates test the null hypothesis of
**independence** between the score and the event times, which is precisely the claim "this model
anticipates attacks" asserts.

Practical details that matter:

- **Exclude small shifts.** A shift of 1–2 windows leaves the score essentially aligned. We require
  `|shift| ≥ K`.
- **Use the +1 correction**, `p = (1 + #{null ≥ observed}) / (1 + n_shifts)`, so a p-value can never
  be reported as exactly zero — with 2 000 shifts the floor is 0.0005.
- **Report the null's p95 count, not just the p-value.** It is the number a reader can check a
  headline against, and it is what exposed our own acceptance bar as unmeasurable: on a one-episode
  fold the null p95 is 1 of 1, so *no* observed count can ever exceed it. A bar of "≥ 2 of 5
  episodes" was therefore not a bar at all.
- **Two things the plain metric credits for free**, both now refused:
  *(a)* alarms sitting inside the **previous** episode's attack traffic — on Wednesday, onsets 219
  and 309 have 6 of their 10 pre-onset windows inside the run before them, so a pure detector
  collects two free "early warnings"; *(b)* a `persistence=2` run whose confirming window is the
  onset itself, which credits a one-window lead to a score that only woke up on impact.

Implementation: `src/netwm/models/leadtime.py`; standing rule in D-022; first application E15a.

## 3. Within-day separability does not imply across-day transfer

E12 found pre-onset windows separable at ROC-AUC **0.883 / 0.955** and we treated that as evidence
the target was learnable. It is not the same measurement: E12 cross-validates **within a single
day** with a scaler fitted **on that day**. Measured leave-one-day-out on the same label, plain
logistic regression gets **0.604 / 0.556** — near chance — and the trained world model gets 0.440 to
0.533 on Thursday, *below* both the linear baseline and a single unscaled column.

The gap between 0.88 and 0.60 is the entire research problem, and it was invisible for two rounds
because the two numbers were quoted in the same units. **A within-day probe is a feasibility check
on the features, never evidence about generalisation.** If a note says "signal exists", the next
sentence must say under which split.

## 4. Auxiliary heads can be a regression, not a free lunch

Round 3 added two supervision targets to the shared RSSM trunk. They did not help, and they *cost*:
Thursday PR-AUC fell from **0.640** (round 2, three heads) to **0.353–0.445** (round 3, five heads,
three seeds). This is textbook **negative transfer** — an auxiliary task degrading the primary one —
and the literature treats it as the expected case to be defended against, not a surprise.

The defence that worked: evaluating against the *same run's* primary-head score rather than against
the previous round's checkpoint. Comparing r3 to the r2 checkpoint would have confounded "new
target" with "new training run"; the within-run control made the regression unambiguous.

## 5. Monte-Carlo sampling buys nothing for ranking

`forecast()` averages 16 sampled rollouts. On the same checkpoint, the deterministic mean path
(mean of posterior, prior and rollout) ranks identically: **Spearman ρ = 0.995**, PR-AUC 0.4387 vs
0.4396; on the round-2 checkpoint the MC score reproduces E14's published 0.640. Since the alarm
threshold is a quantile of the same series, ranking is all that carries — so a lead-time count
should be produced on the mean path, where it has **no sampling variance at all**. E14's own caveat
(the same checkpoint giving 1 of 4 and then 2 of 4 on different runs) disappears.

Keep the MC band for the UI's uncertainty cone; do not pay for it in a benchmark.

## 6. What we would do differently

1. Compute the null **before** the experiment, not after. E15a took ten minutes and needed no model
   — it reads the score arrays a previous run already wrote. Had it existed at E13, two rounds of
   work would have been aimed differently.
2. Never quote a within-day number and a held-out number in the same table without labelling the
   split on each row.
3. Put the floors — raw single features, a linear model on the same label and folds, and the model's
   own primary head — on the same table as the headline, decided in advance. In E15 all three beat
   the thing under test, which is a one-line summary that took no extra experiment to obtain.
4. Expect multiple comparisons. Our final table has 1 080 cells carrying a p-value; 21 fall below
   0.05 where chance gives ~54. One cell reached p = 0.0375 and, read alone, looked exactly like the
   result we had spent a week trying to produce.

## Sources

- Theiler, Eubank, Longtin, Galdrikian, Farmer — *Testing for nonlinearity in time series: the
  method of surrogate data*, Physica D 58 (1992) 77–94.
  [doi:10.1016/0167-2789(92)90102-S](https://doi.org/10.1016/0167-2789(92)90102-S)
- Lancaster, Iatsenko, Pidde, Ticcinelli, Stefanovska — *Surrogate data for hypothesis testing of
  physical systems*, Physics Reports (2018); shifted surrogates test the null of independence.
  [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0370157318301340)
- *ForkMerge: Mitigating Negative Transfer in Auxiliary-Task Learning*, 2023 — negative transfer as
  the expected failure mode of auxiliary supervision. [arXiv:2301.12618](https://arxiv.org/abs/2301.12618)
- Our own runs: `results/runs/e15a-null-calibration-e14-pmax-rescore-e4e7-worldmodel-r2/`,
  `results/runs/e15-precursor-r3-precursor-3seeds/`; decisions D-022 (the standing rule) and D-023
  (the pre-registered bar); results.md E15a and E15.
