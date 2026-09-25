import joblib
import numpy as np
import pandas as pd
import pytest
from scipy.special import ndtri

from netwm.features.scaler import StateScaler

RNG = np.random.default_rng(0)
# a heavy-tailed count, a signed ratio and a constant column - the three shapes S_t is made of
DAY = pd.DataFrame(
    {
        "bytes_total": RNG.lognormal(8.0, 2.0, 200),
        "byte_asymmetry": RNG.uniform(-1.0, 1.0, 200),
        "idle": np.zeros(200),
    }
)


def old_formula(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """The D-014 scaler as it was before D-025, inlined so a regression cannot hide in a refactor."""
    skew = train.skew(numeric_only=True)
    log_cols = [c for c in train.columns if train[c].min() >= 0 and skew.get(c, 0.0) > 2.0]

    def log(df):
        out = df.copy()
        out[log_cols] = np.log1p(out[log_cols].clip(lower=0))
        return out.to_numpy(dtype=np.float32)

    x = log(train)
    mean, std = x.mean(axis=0), x.std(axis=0)
    std[std < 1e-6] = 1.0
    return (log(test) - mean) / std


# --- log_standard: the round-2 behaviour must not move -------------------------------------------


def test_default_mode_reproduces_the_round_two_scaler_exactly():
    test = DAY * 3.0
    np.testing.assert_array_equal(StateScaler().fit(DAY).transform(test), old_formula(DAY, test))


def test_transform_refuses_an_unfitted_scaler_in_either_mode():
    with pytest.raises(RuntimeError):
        StateScaler().transform(DAY)
    with pytest.raises(RuntimeError):
        StateScaler(mode="rank").transform(DAY)


def test_transform_refuses_a_missing_feature_column():
    scaler = StateScaler().fit(DAY)
    with pytest.raises(ValueError):
        scaler.transform(DAY.drop(columns="idle"))


def test_log_standard_round_trips_and_keeps_constant_columns_at_zero():
    scaler = StateScaler().fit(DAY)
    x = scaler.transform(DAY)
    assert np.all(x[:, 2] == 0.0)  # constant column: std forced to 1, not a division by ~0
    np.testing.assert_allclose(scaler.inverse_transform(x).to_numpy(), DAY.to_numpy(), rtol=1e-4, atol=1e-3)


def test_a_scaler_pickled_before_d025_still_transforms_as_log_standard():
    scaler = StateScaler().fit(DAY)
    for name in ("mode", "rank_window", "rank_min_periods"):
        del scaler.__dict__[name]  # what unpickling a round-2 checkpoint's scaler leaves behind
    assert scaler.mode == "log_standard"
    np.testing.assert_array_equal(scaler.transform(DAY), old_formula(DAY, DAY))


def test_joblib_round_trip_preserves_the_mode(tmp_path):
    scaler = StateScaler(mode="rank", rank_window=20).fit(DAY)
    scaler.save(tmp_path / "s.joblib")
    loaded = StateScaler.load(tmp_path / "s.joblib")
    assert (loaded.mode, loaded.rank_window) == ("rank", 20)
    np.testing.assert_array_equal(loaded.transform(DAY), scaler.transform(DAY))


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        StateScaler(mode="minmax")


# --- rank: per capture, label-free (D-025) --------------------------------------------------------


def test_rank_is_blind_to_any_monotone_shift_of_the_capture():
    # the r4 hypothesis in one line: a test day whose scale drifted away from the training days
    # looks exactly like the training days after rank normalisation
    scaler = StateScaler(mode="rank").fit(DAY)
    shifted = DAY.assign(bytes_total=np.log(DAY["bytes_total"]) * 50 + 1e6, byte_asymmetry=DAY["byte_asymmetry"] ** 3)
    np.testing.assert_array_equal(scaler.transform(shifted), scaler.transform(DAY))


def test_rank_learns_nothing_from_the_training_days():
    a = StateScaler(mode="rank").fit(DAY)
    b = StateScaler(mode="rank").fit(DAY * 1000)
    np.testing.assert_array_equal(a.transform(DAY), b.transform(DAY))


def test_rank_is_centred_ties_share_a_value_and_a_constant_column_is_zero():
    df = pd.DataFrame({"n": [0, 0, 0, 5, 9], "flat": [3, 3, 3, 3, 3]})
    x = StateScaler(mode="rank").fit(df).transform(df)
    assert x[0, 0] == x[1, 0] == x[2, 0] < 0 < x[3, 0] < x[4, 0]  # the quiet windows tie
    assert np.all(x[:, 1] == 0.0)
    assert np.isfinite(x).all()
    x_day = StateScaler(mode="rank").fit(DAY).transform(DAY)
    assert abs(float(np.median(x_day[:, 0]))) < 0.05  # zero is the typical window (IG baseline)


def test_groups_rank_each_capture_separately():
    monday, thursday = DAY.iloc[:100], DAY.iloc[100:] * 1e4  # thursday lives on another scale
    both = pd.concat([monday, thursday], ignore_index=True)
    split = np.array(["monday"] * 100 + ["thursday"] * 100)
    scaler = StateScaler(mode="rank").fit(DAY)
    np.testing.assert_array_equal(
        scaler.transform(both, groups=split),
        np.vstack([scaler.transform(monday), scaler.transform(thursday)]),
    )


def test_rank_mode_refuses_to_invert():
    scaler = StateScaler(mode="rank").fit(DAY)
    with pytest.raises(NotImplementedError):
        scaler.inverse_transform(scaler.transform(DAY))


# --- causal rank: nothing after window t shapes window t ------------------------------------------


def test_causal_rank_never_sees_the_future():
    scaler = StateScaler(mode="rank", rank_window=30, rank_min_periods=5).fit(DAY)
    before = scaler.transform(DAY)
    future_attack = DAY.copy()
    future_attack.loc[150:, "bytes_total"] *= 1e5  # an attack that lands at window 150
    after = scaler.transform(future_attack)
    np.testing.assert_array_equal(after[:150], before[:150])
    assert not np.array_equal(after[150:, 0], before[150:, 0])


def test_causal_rank_sits_at_the_median_during_warm_up():
    x = StateScaler(mode="rank", rank_window=30, rank_min_periods=5).fit(DAY).transform(DAY)
    assert np.all(x[:4] == 0.0)  # fewer than 5 windows seen
    assert np.any(x[4:] != 0.0)


def test_causal_rank_scores_a_new_maximum_high():
    ramp = pd.DataFrame({"uniq_dst_port": np.arange(50, dtype=float)})
    x = StateScaler(mode="rank", rank_window=10, rank_min_periods=10).fit(ramp).transform(ramp)
    # a rising count is always the largest value of its trailing window: rank n of n
    expected = float(np.float32(ndtri(9.5 / 10)))
    assert np.all(x[9:, 0] == pytest.approx(expected))
