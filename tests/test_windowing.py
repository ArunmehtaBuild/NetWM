import numpy as np
import pandas as pd
import pytest

from netwm.features.windowing import (
    WindowSpec,
    compromise_flags,
    expand_to_windows,
    hazard_targets,
    onset_windows,
    window_stage_matrix,
    window_stages,
)
from netwm.labels.mitre_map import Stage

T0 = pd.Timestamp("2017-07-06 12:00:00")


def frame(offsets_s, stages, attempted=None):
    return pd.DataFrame(
        {
            "ts": [T0 + pd.Timedelta(seconds=s) for s in offsets_s],
            "stage": stages,
            "attempted": attempted if attempted is not None else [False] * len(stages),
        }
    )


def test_each_flow_lands_in_length_over_stride_windows():
    spec = WindowSpec(60, 30)
    ex, t0 = expand_to_windows(frame([75], [0]), spec, t0=T0)
    # a flow at t=75 s belongs to the windows starting at 30 s and 60 s
    assert sorted(ex["w"]) == [1, 2]
    assert t0 == T0


def test_window_never_sees_the_future():
    spec = WindowSpec(60, 30)
    ex, _ = expand_to_windows(frame([0, 10, 200], [0, 0, 3]), spec, t0=T0)
    stages = window_stages(ex)
    # the attack at 200 s must not colour the first windows
    assert stages.iloc[0] == 0 and stages.iloc[1] == 0
    assert stages.iloc[6] == int(Stage.LATERAL_MOVEMENT)


def test_attempted_traffic_does_not_set_the_stage():
    spec = WindowSpec(60, 30)
    ex, _ = expand_to_windows(frame([5], [4], attempted=[True]), spec, t0=T0)
    assert window_stages(ex).iloc[0] == 0
    assert window_stages(ex, include_attempted=True).iloc[0] == int(Stage.COMMAND_AND_CONTROL)


def test_multi_label_matrix_keeps_concurrent_stages():
    spec = WindowSpec(60, 30)
    ex, _ = expand_to_windows(frame([5, 10], [1, 6], attempted=[False, False]), spec, t0=T0)
    mat = window_stage_matrix(ex)
    assert mat.loc[0, "RECONNAISSANCE"] == 1 and mat.loc[0, "IMPACT"] == 1
    assert mat.loc[0, "BENIGN"] == 0


def test_hazard_targets_look_forward_only():
    stages = pd.Series([0, 0, 3, 3, 0])
    y = hazard_targets(stages, horizon=2, threshold=int(Stage.LATERAL_MOVEMENT))
    assert y[0].tolist() == [0, 1]      # compromise two steps after window 0
    assert y[1].tolist() == [1, 1]
    assert y[3].tolist() == [0, 0]      # nothing ahead of the last compromise window


def test_onsets_split_episodes_by_quiet_gap():
    stages = pd.Series([3, 3, 0, 0, 0, 0, 0, 3])
    assert onset_windows(stages, int(Stage.LATERAL_MOVEMENT), gap=4) == [0, 7]
    assert onset_windows(pd.Series([0, 0]), int(Stage.LATERAL_MOVEMENT)) == []


def test_impact_is_not_a_compromise():
    stages = pd.Series([int(Stage.IMPACT), int(Stage.LATERAL_MOVEMENT)])
    assert compromise_flags(stages, int(Stage.LATERAL_MOVEMENT)).tolist() == [False, True]


def test_stride_longer_than_length_is_rejected():
    with pytest.raises(ValueError):
        WindowSpec(length_s=10, stride_s=30)
