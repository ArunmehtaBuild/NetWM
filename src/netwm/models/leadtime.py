"""Lead time that a hostile reviewer cannot take apart (decisions.md D-022, board card Y-5).

E3b found Thursday's ``detect`` target reporting *2 of 4 episodes warned early, mean lead 6.5
windows* while scoring F1 0.021 - a score firing nearly everywhere "warns early" by accident. Y-5
exists because of that. Three things the plain metric does not do by default:

1. **An eligibility mask.** Without one, ``metrics.lead_times`` credits any alarm in ``[onset - K, onset)``,
   including windows that are themselves attack windows from the *previous* episode. On Wednesday,
   onsets 219 and 309 have 6 of their 10 pre-onset windows inside the preceding attack run, so a
   pure detector collects two free early warnings.
2. **A confirmation that lands before the onset.** With ``persistence=2`` and ``t = onset - 1`` the
   confirming window is the onset itself, so a score that only wakes up once the attack starts is
   credited with a one-window lead.
3. **A null.** Warned-early counts are meaningless without knowing what an unaligned score of the
   same shape scores. The circular-shift null holds the score's distribution and autocorrelation
   fixed, destroys only its alignment with the onsets, and gives an empirical p-value.

The guards live in ``netwm.metrics.lead_times`` (T-10: one lead-time implementation in the repo);
``strict_lead_times`` is that function with both guards on, plus an eligible-window count per
episode. ``alarm_rate`` lives in ``netwm.metrics`` and is re-exported here for existing callers.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import chi2

from netwm.metrics import alarm_rate, lead_times  # noqa: F401 - alarm_rate re-exported


def strict_lead_times(
    y_score: np.ndarray,
    onsets: "list[int]",
    threshold: float,
    horizon: int,
    persistence: int = 2,
    eligible: np.ndarray | None = None,
    confirm_before_onset: bool = True,
) -> list[dict]:
    """Per-episode lead time, refusing the two kinds of credit a detector gets for free.

    ``netwm.metrics.lead_times`` with both guards on. Adds ``eligible_windows`` - how many of the
    pre-onset windows were even allowed to count, which is how a reader sees that an episode had no
    fair chance. ``summarise_lead`` consumes the rows unchanged.
    """
    rows = lead_times(y_score, onsets, threshold, horizon, persistence=persistence,
                      eligible=eligible, confirm_before_onset=confirm_before_onset)
    mask = None if eligible is None else np.asarray(eligible, dtype=bool)
    for row in rows:
        start = max(0, row["onset"] - horizon)
        row["eligible_windows"] = int(mask[start:row["onset"]].sum()) if mask is not None else row["onset"] - start
    return rows


def warned_early(rows: "list[dict]") -> int:
    return sum(1 for r in rows if r["detected_early"])


def circular_shift_null(
    y_score: np.ndarray,
    onsets: "list[int]",
    threshold: float,
    horizon: int,
    n_shifts: int = 2000,
    seed: int = 42,
    min_shift: int | None = None,
    **kwargs,
) -> dict:
    """How many episodes an *unaligned* score of the same shape warns about, by chance.

    Rolling the score preserves its marginal distribution exactly - so the alarm rate, and therefore
    the alert budget, is identical - and preserves its autocorrelation almost exactly, while
    destroying any real relationship with the onsets. Shifts smaller than ``min_shift`` (default the
    horizon) are excluded, since those leave the score still aligned with the thing it is meant to
    be unaligned from.

    The p-value uses the standard +1 correction, so it can never be reported as exactly zero.
    """
    y_score = np.asarray(y_score, dtype=float)
    n = len(y_score)
    min_shift = horizon if min_shift is None else min_shift
    observed = warned_early(
        strict_lead_times(y_score, onsets, threshold, horizon, **kwargs)
    )
    if not onsets or n <= 2 * min_shift:
        return {
            "observed": observed, "null_mean": 0.0, "null_p95": 0,
            "p_value": 1.0, "n_shifts": 0,
        }

    rng = np.random.default_rng(seed)
    shifts = rng.integers(min_shift, n - min_shift, size=n_shifts)
    counts = np.empty(n_shifts, dtype=int)
    for i, s in enumerate(shifts):
        counts[i] = warned_early(
            strict_lead_times(np.roll(y_score, int(s)), onsets, threshold, horizon, **kwargs)
        )
    return {
        "observed": observed,
        "null_mean": float(counts.mean()),
        "null_p95": int(np.quantile(counts, 0.95)),
        "null_max": int(counts.max()),
        "p_value": float((1 + int((counts >= observed).sum())) / (1 + n_shifts)),
        "exceeds_null_p95": bool(observed > int(np.quantile(counts, 0.95))),
        "n_shifts": int(n_shifts),
    }


def fisher_combine(p_values: "list[float]") -> dict:
    """Fisher's method across folds. Guards p = 0, which the +1 correction already prevents."""
    p = np.clip(np.asarray([v for v in p_values if v is not None], dtype=float), 1e-12, 1.0)
    if p.size == 0:
        return {"chi2": float("nan"), "df": 0, "p_value": float("nan")}
    stat = float(-2.0 * np.log(p).sum())
    df = int(2 * p.size)
    return {"chi2": stat, "df": df, "p_value": float(chi2.sf(stat, df))}
