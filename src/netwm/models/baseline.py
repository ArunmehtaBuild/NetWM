"""Baselines the world model has to beat.

1. ``PersistenceBaseline`` - "tomorrow looks like today": predicts S_{t+1} = S_t. Network traffic is
   strongly autocorrelated, so this scores surprisingly well on next-state error. Reporting the world
   model's NLL *without* this floor would be meaningless (research/world-models.md, failure mode 2).
2. ``LogisticForecaster`` - the PS-mandated logistic regression on the same features. Two modes:
   ``detect`` (is this window compromised now) and ``forecast`` (will a compromise happen within K).
   The gap between them is exactly what a static classifier cannot do.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression


@dataclass
class PersistenceBaseline:
    """Gaussian next-state model with the identity as its mean function."""

    sigma_: np.ndarray | None = None

    def fit(self, states: np.ndarray) -> "PersistenceBaseline":
        residual = states[1:] - states[:-1]
        self.sigma_ = residual.std(axis=0)
        self.sigma_[self.sigma_ < 1e-3] = 1e-3
        return self

    def predict_next(self, states: np.ndarray) -> np.ndarray:
        return states[:-1].copy()

    def nll(self, states: np.ndarray) -> float:
        """Mean per-feature Gaussian negative log-likelihood of the observed transitions."""
        return float(self.nll_stats(states)["mean"])

    def nll_stats(self, states: np.ndarray) -> dict[str, float]:
        """Mean/median/p95 per-window NLL.

        The mean alone is misleading across days: one portscan window whose features sit far outside
        the training distribution can move it by five orders of magnitude, which says more about
        distribution shift than about the model. We report all three.
        """
        if self.sigma_ is None:
            raise RuntimeError("fit first")
        err = states[1:] - self.predict_next(states)
        var = self.sigma_**2
        per_window = 0.5 * (np.log(2 * np.pi * var) + err**2 / var).mean(axis=1)
        return {
            "mean": float(per_window.mean()),
            "median": float(np.median(per_window)),
            "p95": float(np.percentile(per_window, 95)),
        }


@dataclass
class LogisticForecaster:
    """Logistic regression over the current state (optionally with lagged states)."""

    lags: int = 0
    C: float = 1.0
    class_weight: str | None = "balanced"
    max_iter: int = 2000
    model_: LogisticRegression | None = None

    def _design(self, states: np.ndarray) -> np.ndarray:
        if self.lags <= 0:
            return states
        cols = [states]
        for lag in range(1, self.lags + 1):
            shifted = np.vstack([np.repeat(states[:1], lag, axis=0), states[:-lag]])
            cols.append(shifted)
        return np.hstack(cols)

    def fit(self, states: np.ndarray, y: np.ndarray) -> "LogisticForecaster":
        self.model_ = LogisticRegression(
            C=self.C, class_weight=self.class_weight, max_iter=self.max_iter, n_jobs=-1
        )
        self.model_.fit(self._design(states), y)
        return self

    def predict_proba(self, states: np.ndarray) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("fit first")
        return self.model_.predict_proba(self._design(states))[:, 1]

    def coefficients(self, feature_names: "list[str]") -> "list[tuple[str, float]]":
        """Signed weights, most influential first - the baseline's built-in explanation."""
        if self.model_ is None:
            raise RuntimeError("fit first")
        names = list(feature_names)
        for lag in range(1, self.lags + 1):
            names += [f"{n}@t-{lag}" for n in feature_names]
        coefs = self.model_.coef_[0]
        order = np.argsort(np.abs(coefs))[::-1]
        return [(names[i], float(coefs[i])) for i in order]
