"""Metrics for forecasting, not just detection (decisions.md D-006).

The PS asks for F1 / precision / recall / FPR against a logistic-regression baseline. Those are
necessary but not sufficient: they score *whether* a window is flagged, never *how early*. Lead time
is the metric a per-window classifier cannot win by construction, so it is reported alongside.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


@dataclass
class ForecastMetrics:
    threshold: float
    precision: float
    recall: float
    f1: float
    fpr: float
    pr_auc: float
    roc_auc: float
    positives: int
    n: int

    def as_dict(self) -> dict:
        return asdict(self)


def forecast_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float = 0.5) -> ForecastMetrics:
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score, dtype=float)
    y_pred = (y_score >= threshold).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    single_class = len(np.unique(y_true)) < 2
    return ForecastMetrics(
        threshold=float(threshold),
        precision=float(precision_score(y_true, y_pred, zero_division=0)),
        recall=float(recall_score(y_true, y_pred, zero_division=0)),
        f1=float(f1_score(y_true, y_pred, zero_division=0)),
        fpr=float(fp / (fp + tn)) if (fp + tn) else 0.0,
        pr_auc=float("nan") if single_class else float(average_precision_score(y_true, y_score)),
        roc_auc=float("nan") if single_class else float(roc_auc_score(y_true, y_score)),
        positives=int(y_true.sum()),
        n=int(len(y_true)),
    )


def best_threshold(y_true: np.ndarray, y_score: np.ndarray, grid: int = 101) -> float:
    """Threshold maximising F1 on the given data (use on validation, never on test)."""
    thresholds = np.linspace(0.01, 0.99, grid)
    scores = [f1_score(y_true, (y_score >= t).astype(int), zero_division=0) for t in thresholds]
    return float(thresholds[int(np.argmax(scores))])


def alarm_rate(y_score: np.ndarray, threshold: float) -> float:
    """Fraction of windows the alarm fires on. Y-5 requires this beside every lead-time count.

    Note it is a tautology at a self-budget threshold, where it equals the budget by construction.
    Precision and the null are the guardrails; this is the sanity check that the threshold policy
    did what it claimed.
    """
    return float((np.asarray(y_score, dtype=float) >= threshold).mean())


#: D-034: windows of history before the causal alert budget may fire (20 x 30 s = 10 minutes), so the
#: first quantile is not taken over a handful of windows.
CAUSAL_WARMUP = 20


def causal_threshold(
    score: np.ndarray,
    quantile: float = 0.90,
    warmup: int = CAUSAL_WARMUP,
    trailing: int | None = None,
) -> np.ndarray:
    """Per-window alert-budget threshold that uses only the windows before ``t`` (D-034, E18).

    ``threshold[t]`` is the ``quantile`` of ``score[:t]`` (or of the last ``trailing`` windows before
    ``t``), and ``inf`` - no alarm possible - while ``t < warmup``. The whole-capture quantile it
    replaces let windows after ``t`` set ``t``'s threshold, which a live sensor cannot do.

    The one implementation of the policy: ``scripts/threshold_eval.py`` (E18) and the dashboard
    (``engine/predict.py``) both call it, so the product alarms on exactly the rule E18 measured.
    ``score >= threshold`` works element-wise wherever a scalar threshold did, including
    :func:`lead_times` and :func:`forecast_metrics`.
    """
    score = np.asarray(score, dtype=float)
    thr = np.full(len(score), np.inf)
    for t in range(warmup, len(score)):
        lo = 0 if trailing is None else max(0, t - trailing)
        thr[t] = np.quantile(score[lo:t], quantile)
    return thr


def lead_times(
    y_score: np.ndarray,
    onsets: "list[int]",
    threshold: "float | np.ndarray",
    horizon: int,
    persistence: int = 1,
    eligible: np.ndarray | None = None,
    confirm_before_onset: bool = False,
) -> list[dict]:
    """How many windows before each compromise onset the alarm first (and then stays) raised.

    ``persistence`` consecutive windows above ``threshold`` are required, so a single noisy spike is
    not counted as an early warning. Only alarms inside ``[onset - horizon, onset)`` count: claiming
    credit for an alarm an hour early, when the model was trained to look ``horizon`` windows ahead,
    would be measuring luck.

    Two guards against credit a detector gets for free (Y-5, D-022), both off by default so every
    number published before T-10 reproduces unchanged:

    * ``eligible`` - a boolean mask; alarms outside it are ignored. Pass the non-attack windows so an
      alarm inside the *previous* episode's traffic is not counted as a warning for the next one.
    * ``confirm_before_onset`` - the ``persistence`` confirmation must complete before the onset.
      Without it, a score that only wakes when the attack starts gets a one-window lead.

    This is the only lead-time implementation in the repo; ``netwm.models.leadtime.strict_lead_times``
    calls it with both guards on.
    """
    y_score = np.asarray(y_score, dtype=float)
    alarm = y_score >= threshold
    if eligible is not None:
        alarm = alarm & np.asarray(eligible, dtype=bool)
    out: list[dict] = []
    for onset in onsets:
        start = max(0, onset - horizon)
        lead = 0
        first = None
        for t in range(start, onset):
            end = t + persistence
            if confirm_before_onset and end > onset:
                break
            if end <= len(alarm) and alarm[t:end].all():
                first = t
                lead = onset - t
                break
        out.append(
            {
                "onset": int(onset),
                "first_alarm": None if first is None else int(first),
                "lead_windows": int(lead),
                "detected_early": bool(first is not None),
                "score_at_onset": float(y_score[onset]) if onset < len(y_score) else float("nan"),
            }
        )
    return out


def summarise_lead(lead_rows: "list[dict]", stride_s: float) -> dict:
    """Aggregate lead-time rows. Reported with n, because CIC-IDS2017 has only 5 onsets in a week."""
    leads = [r["lead_windows"] for r in lead_rows]
    early = [l for l in leads if l > 0]
    return {
        "episodes": len(leads),
        "episodes_warned_early": len(early),
        "mean_lead_windows": float(np.mean(early)) if early else 0.0,
        "mean_lead_seconds": float(np.mean(early) * stride_s) if early else 0.0,
        "max_lead_windows": int(max(leads)) if leads else 0,
        "per_episode": lead_rows,
    }
