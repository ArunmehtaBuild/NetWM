"""CIC-IDS2018 adapter (corrected / "improved" release), for M3 (N-7).

Source: https://intrusion-detection.distrinet-research.be/CNS2022/Datasets/CSECICIDS2018_improved.zip
(sha256 in research/cicids2018.md). One CSV per capture day, named ``<Weekday>-DD-MM-2018.csv``.
The files carry exactly the corrected CIC-IDS2017 release's 91 columns, so the column mapping, the
``- Attempted`` handling (D-009) and the stage mapping are shared with ``cicids2017``; only the days,
the victim network and the size differ. A day is 3-4 GB of CSV (about 6 M flows), so besides
``load`` the adapter streams a day in chunks (``iter_chunks``) for a build that never holds it whole.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd

from netwm.data.base import CANONICAL_COLUMNS, DatasetAdapter
from netwm.data.cicids2017 import COLUMN_MAP, PACKET_STAT_MAP
from netwm.labels.mitre_map import is_attempted, refine_scan_direction, stage_of

#: split id -> file name, in capture order
DAY_FILES: dict[str, str] = {
    "feb14": "Wednesday-14-02-2018.csv", "feb15": "Thursday-15-02-2018.csv", "feb16": "Friday-16-02-2018.csv",
    "feb20": "Tuesday-20-02-2018.csv", "feb21": "Wednesday-21-02-2018.csv", "feb22": "Thursday-22-02-2018.csv",
    "feb23": "Friday-23-02-2018.csv", "feb28": "Wednesday-28-02-2018.csv", "mar01": "Thursday-01-03-2018.csv",
    "mar02": "Friday-02-03-2018.csv",
}

#: the victim network in the AWS deployment (research/cicids2018.md)
VICTIM_SUBNET: str = "172.31."

_DTYPES = {"Src IP": "string", "Dst IP": "string", "Label": "string"}


#: the release's placeholder label: one flow in the whole release (feb28), dropped rather than guessed (D-044)
UNLABELLED = "-1"


def capture_date(split: str) -> pd.Timestamp:
    """Midnight UTC of the day a file captures (its name). Flows starting earlier are not that day's."""
    return pd.Timestamp(pd.to_datetime(DAY_FILES[split].split("-", 1)[1].removesuffix(".csv"), format="%d-%m-%Y"))


def _canonical(df: pd.DataFrame, split: str, dropped: dict) -> pd.DataFrame:
    df = df.rename(columns={**COLUMN_MAP, **PACKET_STAT_MAP})
    df["ts"] = pd.to_datetime(df["ts"], format="mixed")
    # D-044: feb23's file carries 2,609 flows stamped two days earlier, which would stretch its window
    # grid over three days; one flow in the release is labelled "-1". Both are dropped and counted.
    early = df["ts"] < capture_date(split)
    unlabelled = df["label"].astype(str) == UNLABELLED
    dropped["before_capture_date"] = dropped.get("before_capture_date", 0) + int(early.sum())
    dropped["label_-1"] = dropped.get("label_-1", 0) + int(unlabelled.sum())
    df = df[~early & ~unlabelled].copy()
    labels = df["label"].astype(str)
    uniq = labels.unique()
    stage_lut = {lbl: int(stage_of(lbl)) for lbl in uniq}
    attempt_lut = {lbl: bool(is_attempted(lbl)) for lbl in uniq}
    df["stage"] = labels.map(stage_lut).astype("int8")
    df["stage"] = refine_scan_direction(labels, df["stage"], df["src_ip"], (VICTIM_SUBNET,)).astype("int8")
    df["attempted"] = labels.map(attempt_lut).astype(bool)
    df["day"] = split
    return df[[*CANONICAL_COLUMNS, *PACKET_STAT_MAP.values(), "day"]]


class CICIDS2018Adapter(DatasetAdapter):
    """Reads the per-day CSVs of the corrected CIC-IDS2018 release into canonical flows."""

    name = "cicids2018-improved"

    def __init__(self, root: Path | str) -> None:
        super().__init__(root)
        #: rows dropped per split by D-044's two rules, filled while a split is read
        self.dropped: dict[str, dict] = {}

    def splits(self) -> list[str]:
        return [s for s, f in DAY_FILES.items() if (self.root / f).exists()]

    def path(self, split: str) -> Path:
        return self.root / DAY_FILES[split]

    def iter_chunks(self, split: str, chunk: int = 1_000_000) -> Iterator[pd.DataFrame]:
        """Canonical flows in file order, ``chunk`` rows at a time (not sorted by time)."""
        reader = pd.read_csv(self.path(split), usecols=[*COLUMN_MAP, *PACKET_STAT_MAP], chunksize=chunk,
                             dtype=_DTYPES, low_memory=False)
        self.dropped[split] = {}
        for df in reader:
            out = _canonical(df, split, self.dropped[split])
            missing = [c for c in CANONICAL_COLUMNS if c not in out.columns]
            if missing:  # the schema half of validate(); a raw chunk is not time-sorted
                raise ValueError(f"{self.name}: missing canonical columns {missing}")
            yield out

    def load(self, split: str, nrows: int | None = None) -> pd.DataFrame:
        df = pd.read_csv(self.path(split), usecols=[*COLUMN_MAP, *PACKET_STAT_MAP], nrows=nrows,
                         dtype=_DTYPES, low_memory=False)
        self.dropped[split] = {}
        out = _canonical(df, split, self.dropped[split]).sort_values("ts", kind="stable").reset_index(drop=True)
        return self.validate(out)
