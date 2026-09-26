"""T-10: one lead-time implementation. ``metrics.lead_times`` now carries the eligibility mask and
the confirm-before-onset rule; ``leadtime.strict_lead_times`` is a wrapper around it.

The references below are the two implementations exactly as they stood before the merge. Every
published number came from one of them, so the unified function must reproduce both, row for row,
on every combination of the flags.
"""

import numpy as np
import pytest

from netwm.metrics import alarm_rate, lead_times
from netwm.models import leadtime


def _old_metrics_lead_times(y_score, onsets, threshold, horizon, persistence=1):
    y_score = np.asarray(y_score, dtype=float)
    alarm = y_score >= threshold
    out = []
    for onset in onsets:
        start = max(0, onset - horizon)
        lead, first = 0, None
        for t in range(start, onset):
            if alarm[t : t + persistence].all() and len(alarm[t : t + persistence]) == persistence:
                first, lead = t, onset - t
                break
        out.append({"onset": int(onset), "first_alarm": None if first is None else int(first),
                    "lead_windows": int(lead), "detected_early": bool(first is not None),
                    "score_at_onset": float(y_score[onset]) if onset < len(y_score) else float("nan")})
    return out


def _old_strict_lead_times(y_score, onsets, threshold, horizon, persistence=2, eligible=None,
                           confirm_before_onset=True):
    y_score = np.asarray(y_score, dtype=float)
    alarm = y_score >= threshold
    if eligible is not None:
        alarm = alarm & np.asarray(eligible, dtype=bool)
    rows = []
    for onset in onsets:
        start = max(0, onset - horizon)
        first, lead = None, 0
        for t in range(start, onset):
            end = t + persistence
            if confirm_before_onset and end > onset:
                break
            if end <= len(alarm) and alarm[t:end].all():
                first, lead = t, onset - t
                break
        n_eligible = (int(np.asarray(eligible, dtype=bool)[start:onset].sum())
                      if eligible is not None else onset - start)
        rows.append({"onset": int(onset), "first_alarm": None if first is None else int(first),
                     "lead_windows": int(lead), "detected_early": bool(first is not None),
                     "score_at_onset": float(y_score[onset]) if onset < len(y_score) else float("nan"),
                     "eligible_windows": n_eligible})
    return rows


def _cases(n=200):
    rng = np.random.default_rng(7)
    for _ in range(n):
        T = int(rng.integers(20, 120))
        score = rng.random(T)
        onsets = sorted(rng.choice(np.arange(1, T), size=int(rng.integers(1, 5)), replace=False).tolist())
        eligible = rng.random(T) > 0.3
        yield score, onsets, float(rng.choice([0.3, 0.5, 0.8])), int(rng.integers(1, 12)), int(rng.integers(1, 4)), eligible


def _same(a, b):
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x.keys() == y.keys()
        for k in x:
            if isinstance(x[k], float) and np.isnan(x[k]):
                assert np.isnan(y[k])
            else:
                assert x[k] == y[k], k


def test_default_lead_times_is_unchanged():
    for score, onsets, thr, k, p, _ in _cases():
        _same(lead_times(score, onsets, thr, k, persistence=p), _old_metrics_lead_times(score, onsets, thr, k, p))


@pytest.mark.parametrize("use_eligible", [False, True])
@pytest.mark.parametrize("confirm", [False, True])
def test_strict_wrapper_is_unchanged(use_eligible, confirm):
    for score, onsets, thr, k, p, eligible in _cases():
        e = eligible if use_eligible else None
        _same(leadtime.strict_lead_times(score, onsets, thr, k, persistence=p, eligible=e, confirm_before_onset=confirm),
              _old_strict_lead_times(score, onsets, thr, k, persistence=p, eligible=e, confirm_before_onset=confirm))


def test_alarm_rate_has_one_home():
    assert leadtime.alarm_rate is alarm_rate
    assert alarm_rate(np.array([0.1, 0.6, 0.9, 0.2]), 0.5) == 0.5
