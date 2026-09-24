"""Loading the processed window matrices produced by ``scripts/build_features.py``."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


class ProcessedDataset:
    """Per-split window frames plus the metadata needed to interpret them."""

    def __init__(self, directory: Path | str) -> None:
        self.dir = Path(directory)
        self.meta = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
        self.feature_names: list[str] = self.meta["feature_names"]
        self.horizon: int = int(self.meta["config"]["horizon_k"])
        self.stride_s: float = float(self.meta["config"]["window"]["stride_s"])
        self._cache: dict[str, pd.DataFrame] = {}

    @property
    def splits(self) -> list[str]:
        return [m["split"] for m in self.meta["splits"]]

    def frame(self, split: str) -> pd.DataFrame:
        if split not in self._cache:
            self._cache[split] = pd.read_parquet(self.dir / f"{split}.parquet")
        return self._cache[split]

    def states(self, split: str) -> pd.DataFrame:
        return self.frame(split)[self.feature_names]

    def target(self, split: str, column: str = "y_within_K") -> np.ndarray:
        return self.frame(split)[column].to_numpy()

    def onsets(self, split: str) -> list[int]:
        for m in self.meta["splits"]:
            if m["split"] == split:
                return list(m["onsets"])
        return []

    def concat(self, splits: "list[str]") -> pd.DataFrame:
        return pd.concat([self.frame(s) for s in splits], ignore_index=True)
