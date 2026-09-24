"""Dataset adapter interface.

Every dataset (CIC-IDS2017 now; CTU-13, CIC-IDS2018, UNSW-NB15 later) is wrapped in an adapter that
yields the *same* canonical flow schema, so the feature pipeline and the model never learn a
dataset's column names. Milestones M2-M4 are new adapters, not new pipelines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

#: Canonical per-flow columns every adapter must produce.
#: ``ts`` is timezone-naive UTC; ``stage`` is an int from ``netwm.labels.mitre_map.Stage``.
CANONICAL_COLUMNS: tuple[str, ...] = (
    "ts",
    "src_ip",
    "src_port",
    "dst_ip",
    "dst_port",
    "protocol",
    "duration_us",
    "fwd_pkts",
    "bwd_pkts",
    "fwd_bytes",
    "bwd_bytes",
    "flow_iat_mean",
    "flow_iat_std",
    "flow_iat_max",
    "flow_iat_min",
    "fin_cnt",
    "syn_cnt",
    "rst_cnt",
    "psh_cnt",
    "ack_cnt",
    "urg_cnt",
    "cwr_cnt",
    "ece_cnt",
    "pkt_len_min",
    "pkt_len_max",
    "pkt_len_mean",
    "pkt_len_std",
    "down_up_ratio",
    "fwd_init_win",
    "bwd_init_win",
    "fwd_seg_size_min",
    "active_mean",
    "idle_mean",
    "label",
    "attempted",
    "stage",
)


class DatasetAdapter(ABC):
    """Loads one dataset into the canonical flow schema."""

    name: str

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    @abstractmethod
    def splits(self) -> list[str]:
        """Names of the natural temporal splits (days for CIC-IDS, scenarios for CTU-13)."""

    @abstractmethod
    def load(self, split: str) -> pd.DataFrame:
        """Return one split as canonical flows, sorted by ``ts``."""

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fail loudly if an adapter drifts from the canonical schema."""
        missing = [c for c in CANONICAL_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: missing canonical columns {missing}")
        if not df["ts"].is_monotonic_increasing:
            raise ValueError(f"{self.name}: flows must be sorted by timestamp")
        return df
