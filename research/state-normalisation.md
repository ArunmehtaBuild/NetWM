# State normalisation under day-to-day shift - why r4 ranks features per capture

Written for S-4 (board r4), before the run. Records what the scaler does to the signal, what a rank
transform changes, and the one way a per-capture transform can quietly invalidate a lead-time claim.

## 1. What a train-fitted z-score does to a shifted test day

D-014 log-compresses heavy-tailed columns and z-scores them with means and standard deviations fitted
on the training days. That is the right call against leakage, and the wrong one under shift: when the
test day's distribution differs, every window of it lands in a region the model saw rarely or never.
E2 measured it before any world model existed - a persistence baseline's next-state NLL on Thursday
has **mean 152 010, median 0.85**: a handful of internal-portscan windows sit so far outside the
training distribution that they dominate the average.

E15 then showed the cost on the precursor label, leave-one-day-out: one *unscaled* column
(`uniq_dst_port`, Thursday ROC-AUC **0.607**) and plain logistic regression (**0.604**) beat every
statistic the world model produces (**0.440-0.533**). The model is not failing to learn the target; it
is losing the signal before the target is reached (D-021 amendment point 6).

## 2. The rank-based inverse normal transform

Replace each value by its rank `r` among the `n` values of the same column, map it to
`p = (r - 1/2) / n` (the "rankit" offset; Blom's `(r - 3/8)/(n + 1/4)` differs only at the tails)
and take the standard-normal quantile `Phi^-1(p)`. Properties that matter here:

- **Invariant to any monotone transform of the column.** A day whose byte counts are 100x higher, or
  whose port counts are log-scaled, ranks identically. That is exactly the drift E2 measured.
- **Bounded.** With `n` values the output lies inside `+-Phi^-1(1 - 1/(2n))` - about +-3.3 for a
  972-window day. No window can dominate a gradient the way Thursday's portscan did.
- **Zero is the median.** Integrated Gradients (`engine/explain.py`) attributes against the all-zero
  state. Under D-014 that meant "the average window"; under a Gaussian rank it means "the capture's
  median window", so every attribution keeps its meaning. A uniform `[0, 1]` percentile would have
  moved it to the *minimum* window.
- **Not a free lunch.** Beasley et al. review the transform and show it is not uniformly beneficial -
  it discards magnitude, and ties (e.g. the many all-zero quiet windows of a count column) collapse to
  one value. We accept both: magnitude survives in the payload's raw flows and top talkers, and a
  tie block of quiet windows *should* map to one value.

## 3. The trap: whole-capture ranking uses the future

The per-capture idea comes from D-020, where the alert threshold is the 90th percentile of the
capture's own scores. Applied to *features*, whole-capture ranking has a side effect the threshold
does not: the value of window `t` depends on every window of the capture, **including the attack that
follows it**. A large portscan at window 600 pushes every pre-onset window at 580 down the ranking of
`uniq_dst_port`. Whether that helps or hurts a forecaster, it is information from after `t`, and a
lead-time count built on it is not a forecast.

The causal alternative ranks window `t` only against the `W` windows before it (and itself): a
rolling rank. It keeps shift invariance at the time scale of `W`, is computable on a live stream, and
leaks nothing. D-025 therefore makes the causal variant (`rank_window: 120`, one hour) the one any
early-warning claim rests on, and allows the whole-capture variant only as a labelled upper bound.
`tests/test_scaler.py::test_causal_rank_never_sees_the_future` pins the property.

Implementation: `src/netwm/features/scaler.py` (`StateScaler(mode="rank")`); config
`configs/model_r4_rank.yaml`; decision D-025; experiment E16 (Y-6).

## 4. Practical rules

- Rank **one capture at a time**. A frame holding several days must be transformed with
  `groups=frame["split"]`, or the days are ranked against each other and the per-capture property is
  gone. The trainer and the inference engine already do this; the concatenating logistic floor in
  `scripts/precursor_eval.py` must pass `groups` for its E16 row to be like-for-like.
- The first `rank_min_periods` windows of a capture are a warm-up and carry no information. Demo
  slices should start well before the attack they show (they do: 39 min of ordinary traffic before
  the Thursday infiltration).

## Sources

- Beasley, Erickson, Allison - *Rank-based inverse normal transformations are increasingly used, but
  are they merited?*, Behavior Genetics 39(5) (2009) 580-595.
  [doi:10.1007/s10519-009-9281-0](https://doi.org/10.1007/s10519-009-9281-0) ·
  [PMC2921808](https://pmc.ncbi.nlm.nih.gov/articles/PMC2921808/)
- Our own runs: results.md E2 (distribution shift), E15 (floors table); decisions D-014, D-020,
  D-021 amendment point 6, D-025.
