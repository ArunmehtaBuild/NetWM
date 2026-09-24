"""Cut small, self-contained demo files out of the dataset for the UI and the demo video.

    python scripts/make_demo_samples.py

Each sample is a flow CSV in the corrected-release format, small enough to upload in the demo and
long enough to contain the run-up *before* an attack - the point of the product is what the model
says in those minutes, so a slice that starts after the attack begins would be useless.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.cicids2017 import COLUMN_MAP

# (name, day, window start, window end, what a viewer is meant to see)
SAMPLES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "thursday_infiltration",
        "thursday",
        "2017-07-06 16:40",
        "2017-07-06 18:50",
        "39 min of ordinary traffic, then the Meterpreter session at 17:19 and the internal sweep",
    ),
    (
        "friday_botnet_c2",
        "friday",
        "2017-07-07 12:30",
        "2017-07-07 14:30",
        "an hour of quiet, then the ARES botnet C2 channel at 13:03",
    ),
    (
        "friday_scan_to_ddos",
        "friday",
        "2017-07-07 16:30",
        "2017-07-07 19:30",
        "external port scan from 16:55 escalating to the LOIC DDoS at 18:56",
    ),
    (
        "monday_benign",
        "monday",
        "2017-07-03 13:00",
        "2017-07-03 15:00",
        "two quiet hours - the false-positive test",
    ),
    (
        "wednesday_dos",
        "wednesday",
        "2017-07-05 12:30",
        "2017-07-05 14:40",
        "four DoS tools in sequence - Impact, never a compromise",
    ),
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="data/raw/cicids2017_improved")
    ap.add_argument("--out", default="data/demo")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []

    for name, day, start, end, blurb in SAMPLES:
        # Only the columns the pipeline actually reads: the full 90-column release makes a demo
        # file three times larger for no benefit, and the upload limit is 200 MB.
        keep = [c for c in (*COLUMN_MAP, "Attempted Category") ]
        raw = pd.read_csv(
            Path(args.raw) / f"{day}.csv", parse_dates=["Timestamp"], usecols=keep, low_memory=False
        )
        mask = (raw["Timestamp"] >= pd.Timestamp(start)) & (raw["Timestamp"] < pd.Timestamp(end))
        slice_ = raw.loc[mask]
        path = out_dir / f"{name}.csv"
        slice_.to_csv(path, index=False)

        labels = slice_["Label"].value_counts().to_dict()
        index.append(
            {
                "id": name,
                "day": day,
                "start": start,
                "end": end,
                "description": blurb,
                "flows": int(len(slice_)),
                "size_mb": round(path.stat().st_size / 1e6, 2),
                "labels": labels,
                "file": path.name,
            }
        )
        print(f"{name:26s} {len(slice_):>7,} flows  {path.stat().st_size/1e6:5.1f} MB  {labels}")

    (out_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"\nwrote {out_dir}/*.csv + index.json")


if __name__ == "__main__":
    main()
