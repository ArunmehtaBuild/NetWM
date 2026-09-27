"""E20r (D-035): packet-level window features from the real CIC-IDS2017 day captures.

    python scripts/build_packet_features.py --pcap-dir D:/CIC-2017-PCAP            # every day present
    python scripts/build_packet_features.py --pcap-dir D:/CIC-2017-PCAP --days friday --extract-only

Per day: checks the capture against UNB's ``.md5`` when one sits beside it, reads every packet
(``features/packet_windows.py``), aggregates onto the exact window grid of the M1 v2 build (its ``t0``
and window count), and caches the result in ``data/interim/packets/<day>.parquet``. The captures are
8-13 GB, so the cache is what later steps read.

**Alignment check, reported per day:** the correlation between packets per window counted from the
PCAP and ``pkts_total`` from the flow CSVs, and their ratio. A clock offset or the wrong capture shows
up here as a low correlation before any model sees the data.

Once all five days are cached, it writes ``data/processed/cicids2017_m1v2p/``: the M1 v2 build with the
18 ``pcap_`` columns joined on, plus meta.json. The CSV build is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.features.packet_windows import PCAP_WINDOW_FEATURES, read_packets, window_packet_features
from netwm.utils import git_sha, save_run

CACHE = Path("data/interim/packets")


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def check_md5(pcap: Path) -> str:
    md5_file = pcap.with_suffix(".md5")
    if not md5_file.exists():
        return "no .md5 beside the capture"
    expected = md5_file.read_text(encoding="utf-8", errors="ignore").split()[0].strip().lower()
    got = md5_of(pcap)
    if got != expected:
        raise SystemExit(f"{pcap.name}: md5 {got} != {expected} - incomplete or corrupt download")
    return f"md5 ok ({got})"


def extract_day(pcap: Path, day: str, ds: ProcessedDataset) -> dict:
    meta = next(m for m in ds.meta["splits"] if m["split"] == day)
    started = time.perf_counter()
    md5 = check_md5(pcap)
    print(f"{day}: {md5}; reading {pcap} ({pcap.stat().st_size / 1e9:.2f} GB)", flush=True)
    packets = read_packets(pcap, progress=lambda m: print(m, flush=True))
    feats = window_packet_features(packets, pd.Timestamp(meta["t0"]), int(meta["windows"]))
    CACHE.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(CACHE / f"{day}.parquet")
    flows_pkts = ds.frame(day)["pkts_total"].to_numpy()
    pcap_pkts = feats["pcap_pkts"].to_numpy()
    busy = flows_pkts > 0
    stats = {
        "day": day,
        "capture": pcap.name,
        "size_gb": round(pcap.stat().st_size / 1e9, 3),
        "integrity": md5,
        "packets": int(len(packets["ts"])),
        "frames_skipped": int(packets["skipped"]),
        "duplicate_frames_dropped": int(packets["duplicates"]),
        "first_packet_utc": str(pd.to_datetime(packets["ts"].min(), unit="s")),
        "last_packet_utc": str(pd.to_datetime(packets["ts"].max(), unit="s")),
        "read_seconds": round(float(packets["seconds"]), 1),
        "total_seconds": round(time.perf_counter() - started, 1),
        # alignment against the flow CSVs on the same grid
        "corr_pkts_vs_csv": round(float(np.corrcoef(np.log1p(pcap_pkts[busy]), np.log1p(flows_pkts[busy]))[0, 1]), 4),
        "ratio_pkts_to_csv": round(float(pcap_pkts.sum() / max(flows_pkts.sum(), 1)), 4),
        "retrans_rate_mean": round(float(feats["pcap_retrans_rate"].mean()), 5),
        "frag_rate_max": round(float(feats["pcap_frag_rate"].max()), 5),
    }
    print(json.dumps(stats, indent=1), flush=True)
    return stats


def merge(ds: ProcessedDataset, out_dir: Path, stats: list[dict]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for day in ds.splits:
        pcap = pd.read_parquet(CACHE / f"{day}.parquet")
        frame = ds.frame(day).join(pcap, on="w")
        frame.to_parquet(out_dir / f"{day}.parquet", index=False)
    meta = json.loads(json.dumps(ds.meta))
    meta["feature_names"] = [*ds.feature_names, *PCAP_WINDOW_FEATURES]
    meta["n_features"] = len(meta["feature_names"])
    meta["packet_build"] = {"git_sha": git_sha(), "days": stats}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {out_dir} ({meta['n_features']} features)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap-dir", required=True)
    ap.add_argument("--data", default="data/processed/cicids2017_m1v2")
    ap.add_argument("--out", default="data/processed/cicids2017_m1v2p")
    ap.add_argument("--days", nargs="*", default=None)
    ap.add_argument("--extract-only", action="store_true", help="cache the days given; do not merge")
    args = ap.parse_args()

    ds = ProcessedDataset(args.data)
    stats = []
    for day in args.days or ds.splits:
        pcap = Path(args.pcap_dir) / f"{day.capitalize()}-WorkingHours.pcap"
        if not pcap.exists():
            print(f"{day}: {pcap} not found - skipped")
            continue
        stats.append(extract_day(pcap, day, ds))
    if stats:
        save_run("f5-pcap-build-" + "-".join(s["day"] for s in stats), {"days": stats}, config=vars(args))
    if not args.extract_only:
        missing = [d for d in ds.splits if not (CACHE / f"{d}.parquet").exists()]
        if missing:
            print(f"not merging: no packet cache for {missing}")
            return
        merged = [json.loads((p / "metrics.json").read_text())["metrics"]["days"]
                  for p in sorted(Path("results/runs").glob("f5-pcap-build-*"))]
        merge(ds, Path(args.out), [s for group in merged for s in group])


if __name__ == "__main__":
    main()
