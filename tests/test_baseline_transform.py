"""The baseline harness must transform each capture on its own (T-16, D-025).

`scripts/benchmark_baselines.py` fits on several training days concatenated into one frame. In rank
mode a frame is treated as a single capture, so without `groups` the training days are ranked
against each other while the test day is ranked alone - the baseline would then be fitted and scored
under two different transforms, and the "like-for-like floor" it exists to provide would not be
like-for-like. These tests pin both halves of the invariant.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from netwm.features.scaler import StateScaler


def _frame(seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    days = []
    for offset, name in enumerate(["monday", "tuesday", "wednesday"]):
        n = 40 + 10 * offset
        days.append(
            pd.DataFrame(
                {
                    # a column whose level differs per day - exactly the drift rank mode exists for
                    "uniq_dst_port": rng.gamma(2.0, 5.0, n) + 50 * offset,
                    "flows_per_s": rng.gamma(1.5, 2.0, n),
                    "split": name,
                }
            )
        )
    frame = pd.concat(days, ignore_index=True)
    return frame, frame["split"]


FEATURES = ["uniq_dst_port", "flows_per_s"]


def test_log_standard_ignores_groups() -> None:
    """Published baselines all ran in log_standard mode: the fix must not move a single number."""
    frame, groups = _frame()
    scaler = StateScaler(mode="log_standard").fit(frame[FEATURES])
    np.testing.assert_allclose(
        scaler.transform(frame[FEATURES]),
        scaler.transform(frame[FEATURES], groups=groups),
    )


def test_rank_grouped_equals_per_capture_transforms() -> None:
    """Grouped transform == transforming each day separately and stacking."""
    frame, groups = _frame()
    scaler = StateScaler(mode="rank", rank_window=120, rank_min_periods=10).fit(frame[FEATURES])

    grouped = scaler.transform(frame[FEATURES], groups=groups)
    stacked = np.vstack(
        [scaler.transform(frame.loc[frame["split"] == d, FEATURES]) for d in frame["split"].unique()]
    )
    np.testing.assert_allclose(grouped, stacked)


def test_rank_pooled_transform_is_wrong_and_differs_materially() -> None:
    """Without groups the days are pooled, and the error is large enough to change conclusions."""
    frame, groups = _frame()
    scaler = StateScaler(mode="rank", rank_window=120, rank_min_periods=10).fit(frame[FEATURES])

    pooled = scaler.transform(frame[FEATURES])
    grouped = scaler.transform(frame[FEATURES], groups=groups)
    assert not np.allclose(pooled, grouped)
    # on real data this reached 2.6 standard-normal units; anything on that scale moves a result
    assert np.abs(pooled - grouped).max() > 0.5


def test_groups_length_is_checked() -> None:
    frame, _ = _frame()
    scaler = StateScaler(mode="rank").fit(frame[FEATURES])
    with pytest.raises(ValueError):
        scaler.transform(frame[FEATURES], groups=np.array(["monday"] * 3))
