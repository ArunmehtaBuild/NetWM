"""A-5c: the demo PCAP - 35 minutes of the real Thursday capture, as packets.

    python scripts/make_demo_pcap.py

The corrected CIC-IDS2017 release ships flow CSVs, not packets (D-001, D-031), so the packets are
synthesised from the real flow rows by ``netwm.features.pcap_synth``. The slice is 16:50-17:25 UTC:
ten quiet minutes, the 14 s external port scan at 17:00 (172.16.0.1 -> 192.168.10.51), attempted
infiltration traffic from 17:13 and the Meterpreter session from 192.168.10.8 at 17:19 - the same
story as the start of the ``thursday_infiltration`` CSV demo, with the real addresses and real UTC
timestamps.

To stay small enough to commit and upload (< 5 MB), **every flow is kept** (flow counts, ports and
fan-out are what the model reads), **attack flows keep every packet**, benign flows keep at most
``--max-packets`` (handshake and teardown survive, the middle is dropped), and payloads are capped
at ``--payload-cap`` bytes. The catalogue entry in ``data/demo/index.json`` is written from the
file this produces - its size, its flows as ``pcap_to_flows`` reads them, and the labels of the
source rows - never typed in.

Needs the raw data (``python scripts/get_data.py``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from scapy.utils import wrpcap

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.cicids2017 import CICIDS2017Adapter
from netwm.features.flow_aggregator import pcap_to_flows
from netwm.features.pcap_synth import build_packets

DEMO_ID = "thursday_demo_pcap"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default="data/raw/cicids2017_improved")
    ap.add_argument("--start", default="2017-07-06 16:50")
    ap.add_argument("--end", default="2017-07-06 17:25")
    ap.add_argument("--max-packets", type=int, default=4, help="per benign flow; attack flows keep all")
    ap.add_argument("--payload-cap", type=int, default=8, help="bytes of payload kept per packet")
    ap.add_argument("--out", default="data/demo/thursday_demo.pcap")
    ap.add_argument("--index", default="data/demo/index.json")
    args = ap.parse_args()

    flows = CICIDS2017Adapter(Path(args.raw)).load("thursday")
    rows = flows[(flows["ts"] >= args.start) & (flows["ts"] < args.end)].copy()
    rows["keep_all"] = rows["label"].astype(str).str.upper() != "BENIGN"
    print(f"{len(rows):,} flows in {args.start} .. {args.end}; {int(rows['keep_all'].sum()):,} attack flows kept whole")

    packets = build_packets(rows, max_packets=args.max_packets, payload_cap=args.payload_cap)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wrpcap(str(out), packets)
    size_mb = out.stat().st_size / 1e6

    readback = pcap_to_flows(out)
    first, last = readback["ts"].min(), readback["ts"].max()
    labels = rows["label"].value_counts().to_dict()
    print(f"wrote {out}: {len(packets):,} packets, {size_mb:.2f} MB; read back as {len(readback):,} flows, "
          f"{first} -> {last} UTC")
    print(f"source labels: {labels}")

    index_path = Path(args.index)
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    index = [e for e in index if e.get("id") != DEMO_ID]
    index.append({
        "id": DEMO_ID,
        "day": "thursday",
        "start": pd.Timestamp(args.start).strftime("%Y-%m-%d %H:%M"),
        "end": pd.Timestamp(args.end).strftime("%Y-%m-%d %H:%M"),
        "description": (
            "PCAP upload demo: 35 min of the real Thursday capture as packets - the 17:00 external "
            "port scan and the 17:19 Meterpreter session, real addresses and UTC times. Every flow "
            f"kept; benign flows trimmed to {args.max_packets} packets, payloads to {args.payload_cap} bytes. "
            "Shows PCAP ingestion end to end; the trimming makes traffic look unlike the training "
            "days, so surprise runs high throughout - use the CSV demo for model behaviour."
        ),
        "flows": int(len(readback)),
        "size_mb": round(size_mb, 2),
        "labels": {str(k): int(v) for k, v in labels.items()},
        "file": out.name,
    })
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"updated {index_path} ({DEMO_ID})")


if __name__ == "__main__":
    main()
