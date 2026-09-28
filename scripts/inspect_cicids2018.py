"""M3, step 2: look at the corrected CIC-IDS2018 CSVs before designing anything (descriptive only).

    python scripts/inspect_cicids2018.py --csv-dir D:/CIC-IDS2018-improved/csv

One chunked pass per day file (the ten files are 3-4 GB each; nothing is held whole in memory). Records,
per day: rows, the timestamp span, every label string with its count, the ``Attempted Category`` values,
and for each non-benign label its most frequent source and destination addresses - what the adapter,
the stage mapping and the internal prefix are designed from.

Writes ``results/runs/m3-inspect/inspect.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.utils import RUNS, git_sha

COLS = ["Src IP", "Dst IP", "Dst Port", "Timestamp", "Label", "Attempted Category"]


def inspect(path: Path, chunk: int) -> dict:
    rows, tmin, tmax = 0, None, None
    labels, attempted = Counter(), Counter()
    src, dst = defaultdict(Counter), defaultdict(Counter)
    ports = defaultdict(Counter)
    lab_span: dict[str, list] = {}
    for df in pd.read_csv(path, usecols=COLS, chunksize=chunk, dtype=str):
        rows += len(df)
        ts = pd.to_datetime(df["Timestamp"], errors="coerce")
        lo, hi = ts.min(), ts.max()
        tmin = lo if tmin is None or lo < tmin else tmin
        tmax = hi if tmax is None or hi > tmax else tmax
        labels.update(df["Label"].value_counts().to_dict())
        attempted.update((df["Label"] + " | attempted=" + df["Attempted Category"].astype(str)).value_counts().to_dict())
        hostile = df[df["Label"] != "BENIGN"]
        for lab, g in hostile.groupby("Label"):
            src[lab].update(g["Src IP"].value_counts().head(5).to_dict())
            dst[lab].update(g["Dst IP"].value_counts().head(5).to_dict())
            ports[lab].update(g["Dst Port"].value_counts().head(5).to_dict())
            t = pd.to_datetime(g["Timestamp"], errors="coerce")
            a, b = t.min(), t.max()
            if lab in lab_span:
                lab_span[lab] = [min(lab_span[lab][0], a), max(lab_span[lab][1], b)]
            else:
                lab_span[lab] = [a, b]
    return {
        "file": path.name, "bytes": path.stat().st_size, "rows": rows,
        "ts_min": str(tmin), "ts_max": str(tmax),
        "labels": dict(labels.most_common()),
        "label_x_attempted": dict(attempted.most_common()),
        "hostile": {lab: {"span": [str(x) for x in lab_span[lab]],
                          "top_src": dict(src[lab].most_common(5)), "top_dst": dict(dst[lab].most_common(5)),
                          "top_dst_port": dict(ports[lab].most_common(5))} for lab in lab_span},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--chunk", type=int, default=1_000_000)
    args = ap.parse_args()
    out = {"csv_dir": args.csv_dir, "git_sha": git_sha(), "days": []}
    files = sorted(Path(args.csv_dir).glob("*.csv"), key=lambda p: pd.to_datetime(p.stem.split("-", 1)[1], format="%d-%m-%Y"))
    for p in files:
        rec = inspect(p, args.chunk)
        out["days"].append(rec)
        print(f"{p.name}: {rec['rows']:,} rows, {rec['ts_min']} .. {rec['ts_max']}, "
              f"labels: {', '.join(f'{k} {v:,}' for k, v in rec['labels'].items())}", flush=True)
    dest = RUNS / "m3-inspect"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "inspect.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("wrote results/runs/m3-inspect/inspect.json")


if __name__ == "__main__":
    main()
