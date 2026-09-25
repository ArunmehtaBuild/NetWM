"""Normalisation for the state vector.

Traffic features are heavy-tailed by nature: a DDoS window carries 10^5 more bytes than an idle one,
so raw standardisation leaves 99 % of windows squeezed into a sliver of the range and lets one
attack dominate every gradient. We log-compress the non-negative, heavy-tailed columns first and
standardise afterwards (decisions.md D-014).

The scaler is fitted on **training splits only** and saved with the model; fitting on all data would
leak test-day statistics into training.

``mode="rank"`` (D-025) is the alternative for the r4 experiment: every column is replaced by its
Gaussian rank *within the capture being transformed*, so no statistic crosses from the training days
to the test day at all. It is the D-020 alert-budget idea applied to features instead of scores, and
like the budget it uses no labels, so it is legal on an unseen capture at inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import ndtri

MODES = ("log_standard", "rank")


@dataclass
class StateScaler:
    skew_threshold: float = 2.0
    log_cols: list[str] = field(default_factory=list)
    mean_: np.ndarray | None = None
    std_: np.ndarray | None = None
    columns_: list[str] = field(default_factory=list)
    # D-025. Fields added after round 2 must keep immutable defaults: a dataclass leaves those as
    # class attributes, so a scaler unpickled from an older checkpoint (no such key in its __dict__)
    # reads them and transforms exactly as it did when it was trained.
    mode: str = "log_standard"
    # None ranks against the whole capture, which lets windows after an onset set the scale of the
    # windows before it; an int ranks against the trailing `rank_window` windows only, which is the
    # variant a lead-time claim may rest on (D-025).
    rank_window: int | None = None
    rank_min_periods: int = 10

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"unknown scaler mode {self.mode!r}; expected one of {MODES}")
        if self.rank_window is not None and self.rank_window < 1:
            raise ValueError("rank_window must be a positive number of windows or None")

    def fit(self, df: pd.DataFrame) -> "StateScaler":
        self.columns_ = list(df.columns)
        if self.mode == "rank":
            # Nothing to learn: rank statistics come from the capture being transformed, never from
            # the training days - that is the whole point of the mode.
            return self
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

    def _is_fitted(self) -> bool:
        return bool(self.columns_) if self.mode == "rank" else self.mean_ is not None

    def transform(self, df: pd.DataFrame, groups: "np.ndarray | pd.Series | None" = None) -> np.ndarray:
        """Scale ``df`` into model space.

        In rank mode ``df`` is treated as **one capture**. A caller holding several days in one
        frame must pass ``groups`` (e.g. ``frame["split"]``), otherwise each day would be ranked
        against the others and the per-capture property is lost. ``groups`` is ignored in
        ``log_standard`` mode, whose statistics do not depend on the capture.
        """
        if not self._is_fitted():
            raise RuntimeError("StateScaler must be fitted before transform")
        missing = [c for c in self.columns_ if c not in df.columns]
        if missing:
            raise ValueError(f"missing feature columns at transform time: {missing[:5]}")
        if self.mode == "rank":
            frame = df[self.columns_]
            if groups is None:
                return self._rank(frame)
            keys = np.asarray(groups)
            if len(keys) != len(frame):
                raise ValueError(f"groups has {len(keys)} entries for {len(frame)} rows")
            out = np.empty(frame.shape, dtype=np.float32)
            for key in pd.unique(keys):
                rows = np.flatnonzero(keys == key)
                out[rows] = self._rank(frame.iloc[rows])
            return out
        x = self._log(df[self.columns_]).to_numpy(dtype=np.float32)
        return (x - self.mean_) / self.std_

    def _rank(self, frame: pd.DataFrame) -> np.ndarray:
        """Gaussian rank of every column within one capture (rank-based inverse normal transform).

        A Gaussian rather than a uniform percentile keeps zero at the capture's *typical* window,
        which is what the all-zero Integrated-Gradients baseline assumes (engine/explain.py).
        Ties share their average rank, so a constant column maps to exactly 0.
        """
        x = frame.astype(np.float64).reset_index(drop=True)
        if self.rank_window is None:
            r = x.rank(method="average")
            n = x.notna().sum()
        else:
            roll = x.rolling(self.rank_window, min_periods=self.rank_min_periods)
            r = roll.rank(method="average")  # rank of the current row among its trailing window
            n = roll.count()
        p = ((r - 0.5) / n).to_numpy()  # strictly inside (0, 1): (0.5/n, 1 - 0.5/n)
        # warm-up rows (fewer than rank_min_periods windows seen) sit at the median
        return np.nan_to_num(ndtri(p), nan=0.0).astype(np.float32)

    def fit_transform(self, df: pd.DataFrame) -> np.ndarray:
        return self.fit(df).transform(df)

    def inverse_transform(self, x: np.ndarray) -> pd.DataFrame:
        """Back to feature space - needed to show a *predicted* future state in defender units."""
        if self.mode == "rank":
            # A rank has no fitted scale to undo; it would need the capture's own quantiles, which
            # the scaler deliberately does not keep.
            raise NotImplementedError("rank-mode scaling is not invertible (D-025)")
        out = pd.DataFrame(x * self.std_ + self.mean_, columns=self.columns_)
        if self.log_cols:
            out[self.log_cols] = np.expm1(out[self.log_cols])
        return out

    def save(self, path: Path | str) -> None:
        joblib.dump(self, Path(path))

    @staticmethod
    def load(path: Path | str) -> "StateScaler":
        return joblib.load(Path(path))
