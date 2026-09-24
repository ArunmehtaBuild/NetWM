"""Normalisation for the state vector.

Traffic features are heavy-tailed by nature: a DDoS window carries 10^5 more bytes than an idle one,
so raw standardisation leaves 99 % of windows squeezed into a sliver of the range and lets one
attack dominate every gradient. We log-compress the non-negative, heavy-tailed columns first and
standardise afterwards (decisions.md D-014).

The scaler is fitted on **training splits only** and saved with the model; fitting on all data would
leak test-day statistics into training.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


@dataclass
class StateScaler:
    skew_threshold: float = 2.0
    log_cols: list[str] = field(default_factory=list)
    mean_: np.ndarray | None = None
    std_: np.ndarray | None = None
    columns_: list[str] = field(default_factory=list)

    def fit(self, df: pd.DataFrame) -> "StateScaler":
        self.columns_ = list(df.columns)
        skew = df.skew(numeric_only=True)
        self.log_cols = [
            c for c in self.columns_ if float(df[c].min()) >= 0.0 and float(skew.get(c, 0.0)) > self.skew_threshold
        ]
        x = self._log(df).to_numpy(dtype=np.float32)
        self.mean_ = x.mean(axis=0)
        self.std_ = x.std(axis=0)
        self.std_[self.std_ < 1e-6] = 1.0  # constant columns stay at zero instead of exploding
        return self

    def _log(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if self.log_cols:
            out[self.log_cols] = np.log1p(out[self.log_cols].clip(lower=0))
        return out

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        if self.mean_ is None:
            raise RuntimeError("StateScaler must be fitted before transform")
        missing = [c for c in self.columns_ if c not in df.columns]
        if missing:
            raise ValueError(f"missing feature columns at transform time: {missing[:5]}")
        x = self._log(df[self.columns_]).to_numpy(dtype=np.float32)
        return (x - self.mean_) / self.std_

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.fit(df).transform(df)

    def inverse_transform(self, x: np.ndarray) -> pd.DataFrame:
        """Back to feature space - needed to show a *predicted* future state in defender units."""
        out = pd.DataFrame(x * self.std_ + self.mean_, columns=self.columns_)
        if self.log_cols:
            out[self.log_cols] = np.expm1(out[self.log_cols])
        return out

    def save(self, path: Path | str) -> None:
        joblib.dump(self, Path(path))

    @staticmethod
    def load(path: Path | str) -> "StateScaler":
        return joblib.load(Path(path))
