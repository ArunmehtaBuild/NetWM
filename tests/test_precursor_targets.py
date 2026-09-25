import numpy as np
import pandas as pd
import pytest

from netwm.metrics import lead_times
from netwm.models.leadtime import (
    alarm_rate,
    circular_shift_null,
    fisher_combine,
    strict_lead_times,
    warned_early,
)
from netwm.models.targets import (
    EpisodeLabels,
    episode_labels,
    episode_onsets,
    onset_flags,
    precursor_flags,
)

# stages: benign until 6, a short attack, a quiet gap, then a second attack at 14
STAGES = pd.Series([0, 0, 0, 0, 0, 0, 2, 2, 2, 0, 0, 0, 0, 0, 6, 6, 0, 0], dtype="int8")


def test_episodes_are_split_by_a_quiet_gap_not_by_every_zero():
    assert episode_onsets(STAGES.to_numpy() > 0, gap=4) == [6, 14]
    # a gap of 5 quiet windows is wider than gap=4, so the runs stay separate; with gap=10 they merge
    assert episode_onsets(STAGES.to_numpy() > 0, gap=10) == [6]


def test_onset_flag_marks_only_the_first_window_of_an_episode():
    flags = onset_flags([6, 14], len(STAGES))
    assert flags.sum() == 2
    assert flags[6] == 1 and flags[7] == 0  # the second attack window is not an onset


def test_precursor_never_marks_a_window_that_is_itself_an_attack():
    attack = STAGES.to_numpy() > 0
    p = precursor_flags([6, 14], attack, horizon=10)
    assert p[5] == 1 and p[4] == 1           # quiet run-up to the first onset
    assert p[7] == 0 and p[8] == 0           # inside the first attack, so never a precursor
    assert not (p.astype(bool) & attack).any()


def test_precursor_window_is_the_same_set_the_lead_time_metric_credits():
    # this equality is the circularity D-022 states up front: it must be visible, not discovered
    attack = np.zeros(40, dtype=bool)
    attack[20:25] = True
    p = precursor_flags([20], attack, horizon=10)
    assert sorted(np.flatnonzero(p)) == list(range(10, 20))


def test_labels_carry_the_family_of_each_onset_and_can_drop_one():
    labels = episode_labels(STAGES, horizon=10)
    assert labels.onsets == [6, 14]
    assert labels.families == ["INITIAL_ACCESS", "IMPACT"]
    dropped = labels.without("IMPACT")
    assert dropped.onsets == [6] and dropped.families == ["INITIAL_ACCESS"]
    assert dropped.precursor is labels.precursor  # per-window arrays are untouched


def test_compromise_source_reproduces_the_stricter_onset_definition():
    # INITIAL_ACCESS is below the compromise threshold, IMPACT is off the progression axis entirely
    assert episode_labels(STAGES, horizon=10, source="compromise").onsets == []
    assert episode_labels(STAGES, horizon=10, source="attack").onsets == [6, 14]


def test_unknown_onset_source_raises_rather_than_guessing():
    with pytest.raises(ValueError):
        episode_labels(STAGES, horizon=10, source="whatever")


def test_strict_lead_times_matches_the_published_metric_when_both_guards_are_off():
    # the two implementations must not drift: this is the whole reason the wrapper is allowed to exist
    rng = np.random.default_rng(0)
    score = rng.random(200)
    onsets = [50, 120, 180]
    plain = lead_times(score, onsets, 0.5, horizon=10, persistence=2)
    strict = strict_lead_times(
        score, onsets, 0.5, horizon=10, persistence=2, eligible=None, confirm_before_onset=False
    )
    assert [r["first_alarm"] for r in plain] == [r["first_alarm"] for r in strict]
    assert [r["lead_windows"] for r in plain] == [r["lead_windows"] for r in strict]


def test_an_alarm_inside_the_previous_attack_is_not_foresight_about_the_next_onset():
    score = np.zeros(40)
    attack = np.zeros(40, dtype=bool)
    attack[10:18] = True          # the previous episode is still running
    score[14:16] = 0.9            # the detector is firing on it, two windows in a row
    onsets = [20]
    assert lead_times(score, onsets, 0.5, horizon=10, persistence=2)[0]["detected_early"]
    rows = strict_lead_times(score, onsets, 0.5, horizon=10, persistence=2, eligible=~attack)
    assert rows[0]["detected_early"] is False
    assert rows[0]["eligible_windows"] == 2   # only windows 18 and 19 could ever have counted


def test_a_confirmation_that_lands_on_the_onset_earns_no_lead():
    score = np.zeros(30)
    score[19] = score[20] = 0.9   # window 20 is the onset itself, so the run straddles it
    rows = strict_lead_times(score, [20], 0.5, horizon=10, persistence=2)
    assert rows[0]["detected_early"] is False
    relaxed = strict_lead_times(score, [20], 0.5, horizon=10, persistence=2,
                                confirm_before_onset=False)
    assert relaxed[0]["lead_windows"] == 1   # what the unguarded metric would have credited


def test_alarm_rate_counts_every_window_at_or_above_the_threshold():
    assert alarm_rate(np.array([0.0, 0.5, 0.9, 1.0]), 0.5) == 0.75


def test_the_shift_null_preserves_the_alarm_rate_it_is_compared_at():
    rng = np.random.default_rng(1)
    score = np.cumsum(rng.normal(size=300))
    thr = float(np.quantile(score, 0.90))
    assert alarm_rate(np.roll(score, 57), thr) == pytest.approx(alarm_rate(score, thr))


def test_the_null_p_value_is_bounded_and_never_exactly_zero():
    rng = np.random.default_rng(2)
    score = rng.random(300)
    null = circular_shift_null(score, [100, 200], 0.9, horizon=10, n_shifts=200, persistence=2)
    assert 0.0 < null["p_value"] <= 1.0
    assert null["p_value"] >= 1 / 201           # the +1 correction
    assert null["observed"] == warned_early(
        strict_lead_times(score, [100, 200], 0.9, horizon=10, persistence=2)
    )


def test_a_score_with_no_episodes_reports_no_null_rather_than_a_spurious_one():
    null = circular_shift_null(np.random.default_rng(3).random(100), [], 0.5, horizon=10)
    assert null["n_shifts"] == 0 and null["p_value"] == 1.0


def test_fisher_combines_folds_and_survives_a_p_value_of_zero():
    combined = fisher_combine([0.04, 0.04])
    assert combined["df"] == 4 and combined["p_value"] < 0.05
    assert np.isfinite(fisher_combine([0.0, 0.5])["chi2"])
    assert np.isnan(fisher_combine([])["p_value"])
