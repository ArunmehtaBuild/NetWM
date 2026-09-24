import numpy as np

from netwm.metrics import forecast_metrics, lead_times, summarise_lead


def test_perfect_scores():
    y = np.array([0, 0, 1, 1])
    m = forecast_metrics(y, np.array([0.1, 0.2, 0.9, 0.8]), 0.5)
    assert m.f1 == 1.0 and m.fpr == 0.0 and m.recall == 1.0


def test_fpr_counts_only_negatives():
    y = np.array([0, 0, 0, 1])
    m = forecast_metrics(y, np.array([0.9, 0.9, 0.1, 0.9]), 0.5)
    assert m.fpr == 2 / 3


def test_single_class_gives_nan_auc_not_a_crash():
    m = forecast_metrics(np.zeros(5, dtype=int), np.linspace(0, 1, 5), 0.5)
    assert np.isnan(m.pr_auc) and np.isnan(m.roc_auc)


def test_lead_time_requires_persistent_alarm():
    scores = np.zeros(20)
    scores[7] = 0.9                      # a single spike is noise, not a warning
    rows = lead_times(scores, [10], threshold=0.5, horizon=10, persistence=2)
    assert rows[0]["lead_windows"] == 0 and not rows[0]["detected_early"]

    scores[8] = 0.9                      # two in a row counts
    rows = lead_times(scores, [10], threshold=0.5, horizon=10, persistence=2)
    assert rows[0]["first_alarm"] == 7 and rows[0]["lead_windows"] == 3


def test_alarm_outside_the_horizon_earns_no_credit():
    scores = np.zeros(40)
    scores[0:5] = 0.9                    # 30 windows before onset, far outside K
    rows = lead_times(scores, [35], threshold=0.5, horizon=10, persistence=2)
    assert rows[0]["lead_windows"] == 0


def test_summary_reports_sample_size():
    rows = lead_times(np.ones(20) * 0.9, [10, 15], threshold=0.5, horizon=10, persistence=2)
    summary = summarise_lead(rows, stride_s=30.0)
    assert summary["episodes"] == 2 and summary["episodes_warned_early"] == 2
    assert summary["mean_lead_seconds"] == summary["mean_lead_windows"] * 30.0
