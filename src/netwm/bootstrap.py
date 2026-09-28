"""Moving-block bootstrap intervals for per-capture ROC-AUC (D-042's uncertainty method).

Adjacent windows overlap (60 s windows, 30 s stride) and attacks run for many windows, so resampling
single windows would treat one burst as dozens of independent draws and give intervals far too
narrow. Resampling contiguous blocks keeps that dependence inside each draw.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import rankdata


def roc_auc_ranks(y: np.ndarray, score: np.ndarray) -> float:
    """ROC-AUC by the rank-sum identity (ties get average ranks); NaN when one class is absent."""
    y = np.asarray(y, bool)
    n1 = int(y.sum())
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata(score)
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def block_indices(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """(n_boot, n) indices: ceil(n / block) blocks with uniformly drawn starts, truncated to n."""
    b = min(block, n)
    k = -(-n // b)
    starts = rng.integers(0, n - b + 1, size=(n_boot, k))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]).reshape(n_boot, k * b)
    return idx[:, :n]


def block_bootstrap_auc(
    y: np.ndarray, scores: "dict[str, np.ndarray]", block: int, n_boot: int, seed: int
) -> "dict[str, dict]":
    """Percentile 95 % interval of ROC-AUC per score series, with the *same* resamples for every series,
    so differences between series can be read pairwise. Single-class resamples are dropped and counted."""
    rng = np.random.default_rng(seed)
    idx = block_indices(len(y), block, n_boot, rng)
    y = np.asarray(y, bool)
    out = {}
    for k, s in scores.items():
        s = np.asarray(s, float)
        b = np.array([roc_auc_ranks(y[i], s[i]) for i in idx])
        ok = ~np.isnan(b)
        out[k] = {"roc_auc": roc_auc_ranks(y, s), "lo": float(np.percentile(b[ok], 2.5)) if ok.any() else float("nan"),
                  "hi": float(np.percentile(b[ok], 97.5)) if ok.any() else float("nan"),
                  "dropped": int((~ok).sum()), "boot": b}
    return out
