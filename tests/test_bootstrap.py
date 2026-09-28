import numpy as np
from sklearn.metrics import roc_auc_score

from netwm.bootstrap import block_bootstrap_auc, block_indices, roc_auc_ranks


def test_rank_auc_matches_sklearn_with_ties():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 300)
    s = np.round(rng.normal(size=300) + y, 1)          # rounded: plenty of ties
    assert abs(roc_auc_ranks(y, s) - roc_auc_score(y, s)) < 1e-12
    assert np.isnan(roc_auc_ranks(np.ones(5), np.arange(5)))


def test_blocks_are_contiguous_and_cover_n():
    idx = block_indices(53, 10, 7, np.random.default_rng(1))
    assert idx.shape == (7, 53) and idx.min() >= 0 and idx.max() < 53
    assert (np.diff(idx[:, :10], axis=1) == 1).all()   # the first block is a contiguous run
    assert block_indices(5, 20, 3, np.random.default_rng(1)).shape == (3, 5)   # block longer than n


def test_interval_contains_the_estimate_and_resamples_are_shared():
    rng = np.random.default_rng(2)
    y = np.repeat(rng.integers(0, 2, 40), 10)            # bursts of 10, as attacks come
    a = y + rng.normal(0, 1.0, len(y))
    out = block_bootstrap_auc(y, {"a": a, "b": a.copy()}, block=20, n_boot=300, seed=3)
    assert out["a"]["lo"] <= out["a"]["roc_auc"] <= out["a"]["hi"]
    np.testing.assert_array_equal(out["a"]["boot"], out["b"]["boot"])   # same resamples for every series
