"""Cut a real-capture slice for E27 check 4 / Step 8 - ``editcap -A <start> -B <stop>`` without Wireshark.

    python scripts/slice_pcap.py --pcap D:/CIC-2017-PCAP/Thursday-WorkingHours.pcap \
        --start 1499359200 --stop 1499367000 --out data/cic-2017-pcap/thursday_1640_1850.pcap

Keeps packets with start <= ts < stop (epoch seconds, UTC), byte for byte.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.features.pcap_slice import slice_capture


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap", required=True)
    ap.add_argument("--start", type=float, required=True, help="epoch seconds, inclusive")
    ap.add_argument("--stop", type=float, required=True, help="epoch seconds, exclusive")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    began = time.perf_counter()
    counts = slice_capture(args.pcap, args.out, args.start, args.stop)
    print(f"{counts['kept']:,} of {counts['total']:,} packets -> {args.out} "
          f"({Path(args.out).stat().st_size / 1e6:.1f} MB, {time.perf_counter() - began:.0f} s)")


if __name__ == "__main__":
    main()
