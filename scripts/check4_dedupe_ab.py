"""E27 check 4 diagnostic (N-9, D-040): would dropping capture duplicates bring the flow block to parity?

    CUDA_VISIBLE_DEVICES="" python scripts/check4_dedupe_ab.py --pcap data/cic-2017-pcap/tuesday_1300_1400.pcap --day tuesday

ae3ea25 guessed that the flow block's mismatch came from the CIC captures' mirrored duplicates, which
``read_packets`` drops and ``pcap_to_flows`` keeps. This builds the flow state from one real slice
twice - as the upload path does, and with every frame ``read_packets`` would call a duplicate removed
first (the same rule: an IP packet byte-identical to one of the last ``DEDUP_WINDOW``) - and compares
both with the training matrix, feature by feature, exactly as check 4 does. Descriptive; nothing is
changed in the converter.

Writes results/tables/e27_check4_dedupe_ab.csv and results/runs/e27-check4-dedupe-ab/.
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scapy.utils import RawPcapReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import load_checkpoint, state_matrix
from netwm.features import flow_aggregator
from netwm.features.packet_windows import DEDUP_WINDOW, _ip_offset
from netwm.features.windowing import WindowSpec
from netwm.utils import TABLES, ensure_dirs, save_run

EDGE = 4  # as pcap_route_parity.py: a slice's partial first and last windows are left out


class _Deduplicated:
    """``RawPcapReader`` with ``read_packets``' capture-duplicate rule applied in front of it."""

    def __init__(self, path: str) -> None:
        self._reader = RawPcapReader(path)  # scapy's own: flow_aggregator's name is patched to this class
        self.linktype = getattr(self._reader, "linktype", 1)
        self.nano = getattr(self._reader, "nano", False)
        self.dropped = 0

    def __iter__(self):
        recent: deque = deque(maxlen=DEDUP_WINDOW)
        for frame, meta in self._reader:
            off = _ip_offset(frame, 0, len(frame), getattr(meta, "linktype", self.linktype))
            if off is not None:
                digest = hash(frame[off:])
                if digest in recent:
                    self.dropped += 1
                    continue
                recent.append(digest)
            yield frame, meta

    def close(self) -> None:
        self._reader.close()


def compare(flows: pd.DataFrame, pcap: str, day: str, ds: ProcessedDataset, names: list[str]) -> pd.DataFrame:
    spec = WindowSpec(ds.meta["config"]["window"]["length_s"], ds.stride_s)
    served, _, t0, n = state_matrix(flows, names, spec, pcap_path=pcap)
    day_t0 = pd.Timestamp(next(m["t0"] for m in ds.meta["splits"] if m["split"] == day))
    offset = (pd.Timestamp(t0) - day_t0).total_seconds() / ds.stride_s
    if offset != int(offset):
        raise SystemExit(f"slice grid {t0} is not on the day's {ds.stride_s:.0f} s grid from {day_t0}")
    keep = np.arange(EDGE, n - EDGE)
    train = ds.frame(day)[names].iloc[keep + int(offset)].reset_index(drop=True)
    got = served[names].iloc[keep].reset_index(drop=True)
    rows = []
    for col in names:
        if col.startswith("pcap_"):  # the packet block does not come from pcap_to_flows
            continue
        a, b = got[col].to_numpy(float), train[col].to_numpy(float)
        rel = np.abs(a - b) / np.maximum(1.0, np.abs(b))
        nz = b != 0
        rows.append({"feature": col, "block": "pkt" if col.startswith("pkt_") else "flow",
                     "mean_rel_diff": round(float(rel.mean()), 6), "max_rel_diff": round(float(rel.max()), 6),
                     "median_ratio": round(float(np.median(a[nz] / b[nz])), 4) if nz.any() else None})
    return pd.DataFrame(rows).set_index("feature")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap", required=True, help="a real-capture slice short enough not to fill the session cap")
    ap.add_argument("--day", required=True)
    ap.add_argument("--data", default="data/processed/cicids2017_m1v2p")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    ensure_dirs()

    ds = ProcessedDataset(args.data)
    names = load_checkpoint(f"models/m1v2-e20r-s42/{args.day}.pt", torch.device("cpu"))["feature_names"]

    kept = flow_aggregator.pcap_to_flows(args.pcap)
    readers: list[_Deduplicated] = []
    flow_aggregator.RawPcapReader = lambda p: readers.append(_Deduplicated(p)) or readers[-1]
    try:
        deduped = flow_aggregator.pcap_to_flows(args.pcap)
    finally:
        flow_aggregator.RawPcapReader = RawPcapReader

    table = compare(kept, args.pcap, args.day, ds, names).join(
        compare(deduped, args.pcap, args.day, ds, names), lsuffix="_as_served", rsuffix="_deduplicated")
    table.to_csv(TABLES / "e27_check4_dedupe_ab.csv")
    counts = ["pkts_total", "syn_cnt_sum", "ack_cnt_sum", "psh_cnt_sum", "n_flows", "tiny_flow_rate"]
    summary = {
        "pcap": args.pcap, "day": args.day,
        "flows_as_served": int(len(kept)), "flows_deduplicated": int(len(deduped)),
        "duplicates_dropped": int(readers[0].dropped), "session_cap_drops": int(kept.attrs.get("dropped_packets", 0)),
        "features": int(len(table)),
        "exact_as_served": int((table["max_rel_diff_as_served"] <= 1e-6).sum()),
        "exact_deduplicated": int((table["max_rel_diff_deduplicated"] <= 1e-6).sum()),
        "median_ratio": {c: {"as_served": table.at[c, "median_ratio_as_served"],
                             "deduplicated": table.at[c, "median_ratio_deduplicated"]} for c in counts if c in table.index},
    }
    save_run("e27-check4-dedupe-ab", summary, config={**vars(args), "decision": "D-040", "command": " ".join(sys.argv)})
    pd.set_option("display.width", 200)
    print(table.sort_values("max_rel_diff_deduplicated", ascending=False).to_string())
    print(summary)


if __name__ == "__main__":
    main()
