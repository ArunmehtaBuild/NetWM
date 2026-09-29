"""PCAP -> canonical bidirectional flows (A-3), with the A-2 packet features riding along per flow.

The model was trained on flows from the *corrected* CIC-IDS2017 release (D-001), so this follows
that extraction's semantics rather than stock CICFlowMeter's:

* **A flow is a bidirectional 5-tuple**; its forward direction is the direction of its first packet,
  except that a flow continuing a timed-out one keeps that flow's direction (D-043).
* **TCP teardown does not split the flow.** Stock CICFlowMeter ends a flow at the *first* FIN, and
  the FIN-ACK / last ACK that follow become a spurious one- or two-packet "flow" - one of the
  defects the corrected release fixed. Here a flow is *closing* once both sides have sent FIN; the
  closing ACKs still belong to it, and only a new SYN on the same 5-tuple starts a new flow.
* **RST does not end a flow** (D-043): the corrected CSVs keep the RST, its mirrored copy and what
  follows in the same flow. Like the second FIN, it lets a new SYN on the tuple start a new flow, so
  refused connection attempts (SYN, RST, SYN, RST) stay one flow each.
* **A flow of one packet is not emitted** (D-043): the corrected CSVs hold no single-packet TCP or
  UDP flow on any day checked.
* **A flow lasts at most 120 s from its first packet** (CICFlowMeter's flow timeout); the next packet
  on the same 5-tuple starts a new flow. Flows past the timeout are also swept out as capture time
  advances: a flow that simply goes quiet (UDP, TCP without FIN/RST) would otherwise stay open until
  the session cap fills and every later flow is dropped (E27 check 4, D-040). Measured on the corrected Thursday CSVs: repeated 5-tuples
  restart no sooner than 120.7 s after the previous flow's *start*, while ~850 of them restart less
  than 120 s after its *end* - so the timeout runs from the start, not from the last packet.
* Lengths are **payload** bytes, as CICFlowMeter reports them; ``flow_iat_*`` spans both directions;
  ``fwd_seg_size_min`` is the smallest forward transport-header size; ``active_mean`` /
  ``idle_mean`` use CICFlowMeter's 5 s activity threshold, and the final active period is not
  counted; ``fwd_init_win`` is the TCP window of the first forward packet and ``bwd_init_win`` that
  of the *last* backward packet (CICFlowMeter overwrites it), 0 when unobserved; ``fwd_data_pkts``
  does not count the flow's first packet; gaps between packets are absolute, so a capture that is a
  microsecond out of order gives no negative IAT. Times are microseconds.
* **IP fragments:** a later fragment has no transport header and is not read as TCP/UDP, and a UDP
  payload is the bytes this packet carries, not the datagram length its header declares.
* Every D-043 rule was read off a flow-by-flow match with the corrected CSVs
  (``scripts/check4_flow_match.py``), not assumed.

Packets are parsed from raw header bytes rather than dissected by scapy: dissection was about two
thirds of the runtime (A-3c profile: 6 MB took 19.5 s). A capture carries no labels, so no
``label`` / ``stage`` columns are emitted (predict.analyze_file relies on that).
"""

from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scapy.utils import RawPcapReader

from netwm.data.base import CANONICAL_COLUMNS
from netwm.features.flow_features import PACKET_CSV_COLUMNS as PACKET_STAT_COLUMNS
from netwm.features.pcap_features import PCAPFeatureExtractor

logger = logging.getLogger(__name__)

FLOW_TIMEOUT_S = 120.0
# Every SWEEP_EVERY_S of capture time, flows that started more than FLOW_TIMEOUT_S + SWEEP_SLACK_S ago
# are finished. Any later packet on their tuple would start a new flow anyway, so the output is
# unchanged unless the capture runs more than SWEEP_SLACK_S out of time order.
SWEEP_EVERY_S = 60.0
SWEEP_SLACK_S = 60.0
ACTIVITY_THRESHOLD_S = 5.0
A2_KEYS = (
    "packet_count", "ttl_mean", "ttl_variance", "tcp_win_mean", "tcp_win_max", "ip_frag_count",
    "retrans_count", "payload_0_64", "payload_65_128", "payload_129_512", "payload_513_1024",
    "payload_gt_1024",
)
FIN, SYN, RST, PSH, ACK, URG, ECE, CWR = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80

# pcap linktypes we can find an IPv4 header in
_ETHERNET, _RAW, _RAW_ALT, _LINUX_SLL = 1, 101, 228, 113
_RAW_BSD = (12, 14)  # DLT_RAW on some platforms


def _ip_offset(linktype: int, frame: bytes) -> int | None:
    """Byte offset of the IPv4 header in ``frame``, or None for non-IPv4 frames."""
    if linktype == _ETHERNET:
        off, ethertype = 14, frame[12:14]
        while ethertype in (b"\x81\x00", b"\x88\xa8"):  # 802.1Q / 802.1ad VLAN tags
            ethertype, off = frame[off + 2 : off + 4], off + 4
        return off if ethertype == b"\x08\x00" else None
    if linktype in (_RAW, _RAW_ALT, *_RAW_BSD):
        return 0 if frame[:1] and frame[0] >> 4 == 4 else None
    if linktype == _LINUX_SLL:
        return 16 if frame[14:16] == b"\x08\x00" else None
    return None


def _timestamp(meta, nano: bool) -> float:
    if hasattr(meta, "sec"):
        return meta.sec + meta.usec / (1e9 if nano else 1e6)
    return ((meta.tshigh << 32) | meta.tslow) / meta.tsresol  # pcapng


def _parse(frame: bytes, linktype: int):
    """(src, dst, proto, sport, dport, ttl, mf, frag_off, flags, seq, window, hdr_len, payload_len)."""
    off = _ip_offset(linktype, frame)
    if off is None or len(frame) < off + 20:
        return None
    vihl, _, total_len, _, frag, ttl, proto = struct.unpack_from("!BBHHHBB", frame, off)
    if vihl >> 4 != 4:
        return None
    ihl = (vihl & 0x0F) * 4
    mf, frag_off = bool(frag & 0x2000), frag & 0x1FFF
    if frag_off:
        return None  # a later fragment: its first bytes are payload, not a transport header
    src = ".".join(str(b) for b in frame[off + 12 : off + 16])
    dst = ".".join(str(b) for b in frame[off + 16 : off + 20])
    l4 = off + ihl
    if proto == 6 and len(frame) >= l4 + 16:
        sport, dport, seq, _, offs, flags, window = struct.unpack_from("!HHIIBBH", frame, l4)
        hdr = (offs >> 4) * 4
        return src, dst, proto, sport, dport, ttl, mf, frag_off, flags, seq, window, hdr, max(0, total_len - ihl - hdr)
    if proto == 17 and len(frame) >= l4 + 8:
        sport, dport = struct.unpack_from("!HH", frame, l4)
        # the bytes this packet carries: a first fragment's header declares the whole datagram
        return src, dst, proto, sport, dport, ttl, mf, frag_off, 0, None, None, 8, max(0, total_len - ihl - 8)
    return None


def _new_flow(ts, src, dst, sport, dport, proto) -> dict:
    return {
        "first_ts": ts, "last_ts": ts, "src_ip": src, "dst_ip": dst, "src_port": sport,
        "dst_port": dport, "protocol": proto, "fwd_pkts": 0, "bwd_pkts": 0, "fwd_bytes": 0,
        "bwd_bytes": 0, "flag_counts": [0] * 8, "lengths": [], "iats": [], "fwd_init_win": -1,
        "bwd_init_win": -1, "fwd_seg_min": None, "fin_fwd": False, "fin_bwd": False,
        "start_active": ts, "end_active": ts, "active": [], "idle": [],
        # per-direction statistics behind the CSV packet block (D-037: a PCAP upload must build the
        # same 17 pkt_ features the model trained on from the CSVs)
        "fwd_len": [], "bwd_len": [], "fwd_last": None, "bwd_last": None, "fwd_iat": [], "bwd_iat": [],
        "fwd_rst": 0, "bwd_rst": 0, "fwd_hdr": 0, "fwd_data": 0, "rst_seen": False,
    }


def _sample_std(values: list) -> float:
    return float(np.std(values, ddof=1)) if len(values) > 1 else 0.0


def _finish(f: dict) -> dict:
    # The final active period is not counted: the corrected CSVs give active_mean 0 to every flow
    # without an idle gap (29,162 of 29,162 on Tuesday 13:00-14:00), and count only the periods
    # that an idle gap closed (D-043).
    return f


def pcap_to_flows(pcap_path: Path | str, max_sessions: int = 100_000) -> pd.DataFrame:
    """Read a PCAP/PCAPNG and return canonical flows sorted by start time.

    ``max_sessions`` caps concurrently open flows (memory safety on hostile input). Packets of flows
    refused by the cap are dropped; how many is logged and stored in ``df.attrs["dropped_packets"]``.
    """
    extractor = PCAPFeatureExtractor(max_sessions=max_sessions)
    open_flows: dict[tuple, dict] = {}
    done: list[dict] = []
    dropped = 0
    next_sweep = None
    # A flow that continues a timed-out one keeps its direction, as CICFlowMeter carries the old
    # flow's endpoints into the new one. Held for the whole capture, so kept small: the oriented
    # 5-tuple (the open_flows key) of each tuple's last retired flow, never both orientations.
    directed: set[tuple] = set()

    def retire(key: tuple) -> None:
        src_, dst_, sport_, dport_, proto_ = key
        directed.discard((dst_, src_, dport_, sport_, proto_))
        directed.add(key)
        done.append(_finish(open_flows.pop(key)))

    reader = RawPcapReader(str(pcap_path))
    linktype = getattr(reader, "linktype", _ETHERNET)
    nano = bool(getattr(reader, "nano", False))
    try:
        for frame, meta in reader:
            p = _parse(frame, getattr(meta, "linktype", linktype))
            if p is None:
                continue
            src, dst, proto, sport, dport, ttl, mf, frag_off, flags, seq, window, hdr, plen = p
            ts = _timestamp(meta, nano)
            if next_sweep is None:
                next_sweep = ts + SWEEP_EVERY_S
            elif ts >= next_sweep:
                horizon = ts - FLOW_TIMEOUT_S - SWEEP_SLACK_S
                for k in [k for k, f in open_flows.items() if f["first_ts"] < horizon]:
                    retire(k)
                next_sweep = ts + SWEEP_EVERY_S
            extractor.process_fields(src, dst, proto, sport, dport, ttl, mf, frag_off, seq, window, plen)

            fkey, bkey = (src, dst, sport, dport, proto), (dst, src, dport, sport, proto)
            key = fkey if fkey in open_flows else bkey if bkey in open_flows else None
            if key is not None:
                f = open_flows[key]
                closing = (f["fin_fwd"] and f["fin_bwd"]) or f["rst_seen"]
                if ts - f["first_ts"] > FLOW_TIMEOUT_S or (closing and flags & SYN and not flags & ACK):
                    retire(key)  # timed out, or a new connection on the tuple
                    key = None
            if key is None:
                if len(open_flows) >= max_sessions:
                    dropped += 1
                    continue
                key = fkey
                pure_syn = flags & SYN and not flags & ACK
                if not pure_syn and bkey in directed:
                    key = bkey  # a continuation that began with a reply keeps the connection's direction
                    open_flows[key] = _new_flow(ts, dst, src, dport, sport, proto)
                else:
                    open_flows[key] = _new_flow(ts, src, dst, sport, dport, proto)
            f = open_flows[key]
            fwd = key == fkey

            if f["lengths"]:
                f["iats"].append(abs(ts - f["last_ts"]))
            gap = ts - f["end_active"]
            if gap > ACTIVITY_THRESHOLD_S:
                if f["end_active"] - f["start_active"] > 0:
                    f["active"].append(f["end_active"] - f["start_active"])
                f["idle"].append(gap)
                f["start_active"] = ts
            f["end_active"] = ts
            f["last_ts"] = ts
            f["lengths"].append(plen)
            side = "fwd" if fwd else "bwd"
            f[f"{side}_len"].append(plen)
            if f[f"{side}_last"] is not None:
                f[f"{side}_iat"].append(abs(ts - f[f"{side}_last"]))
            f[f"{side}_last"] = ts
            if fwd:
                f["fwd_pkts"] += 1
                f["fwd_bytes"] += plen
                f["fwd_seg_min"] = hdr if f["fwd_seg_min"] is None else min(f["fwd_seg_min"], hdr)
                f["fwd_hdr"] += hdr
                f["fwd_data"] += int(plen > 0 and f["fwd_pkts"] > 1)  # the first packet is not counted
            else:
                f["bwd_pkts"] += 1
                f["bwd_bytes"] += plen
            if proto == 6:
                for bit in range(8):
                    if flags & (1 << bit):
                        f["flag_counts"][bit] += 1
                if fwd:
                    if f["fwd_init_win"] < 0:  # the first forward TCP packet, SYN or not (as the CSVs)
                        f["fwd_init_win"] = window
                else:
                    f["bwd_init_win"] = window  # the last backward packet's: CICFlowMeter overwrites it
                if flags & FIN:
                    f["fin_fwd" if fwd else "fin_bwd"] = True
                if flags & RST:
                    f["fwd_rst" if fwd else "bwd_rst"] += 1  # counted; the flow goes on (D-043)
                    f["rst_seen"] = True  # ...until a new SYN on the tuple, as after both FINs
    finally:
        reader.close()
    done.extend(_finish(f) for f in open_flows.values())

    if dropped:
        logger.warning("pcap_to_flows: session cap %d reached, %d packets dropped", max_sessions, dropped)

    a2 = extractor.get_session_features()
    rows = []
    for f in done:
        if f["fwd_pkts"] + f["bwd_pkts"] < 2:
            continue  # the corrected CSVs hold no single-packet flow (D-043)
        lengths, iats = np.asarray(f["lengths"], float), np.asarray(f["iats"], float) * 1e6
        fc = f["flag_counts"]
        key = (f["src_ip"], f["dst_ip"], f["src_port"], f["dst_port"], f["protocol"])
        row = {
            "ts": datetime.fromtimestamp(f["first_ts"], tz=timezone.utc).replace(tzinfo=None),
            "src_ip": f["src_ip"], "src_port": f["src_port"], "dst_ip": f["dst_ip"],
            "dst_port": f["dst_port"], "protocol": f["protocol"],
            "duration_us": (f["last_ts"] - f["first_ts"]) * 1e6,
            "fwd_pkts": f["fwd_pkts"], "bwd_pkts": f["bwd_pkts"],
            "fwd_bytes": f["fwd_bytes"], "bwd_bytes": f["bwd_bytes"],
            "flow_iat_mean": float(iats.mean()) if iats.size else 0.0,
            "flow_iat_std": float(iats.std(ddof=1)) if iats.size > 1 else 0.0,
            "flow_iat_max": float(iats.max()) if iats.size else 0.0,
            "flow_iat_min": float(iats.min()) if iats.size else 0.0,
            "fin_cnt": fc[0], "syn_cnt": fc[1], "rst_cnt": fc[2], "psh_cnt": fc[3],
            "ack_cnt": fc[4], "urg_cnt": fc[5], "ece_cnt": fc[6], "cwr_cnt": fc[7],
            "pkt_len_min": float(lengths.min()), "pkt_len_max": float(lengths.max()),
            "pkt_len_mean": float(lengths.mean()),
            "pkt_len_std": float(lengths.std(ddof=1)) if lengths.size > 1 else 0.0,
            "down_up_ratio": f["bwd_pkts"] / f["fwd_pkts"] if f["fwd_pkts"] else 0.0,
            # unobserved -> 0, which is how the corrected CSVs encode it (UDP, one-way flows)
            "fwd_init_win": max(f["fwd_init_win"], 0), "bwd_init_win": max(f["bwd_init_win"], 0),
            "fwd_seg_size_min": f["fwd_seg_min"] or 0,
            "active_mean": float(np.mean(f["active"]) * 1e6) if f["active"] else 0.0,
            "idle_mean": float(np.mean(f["idle"]) * 1e6) if f["idle"] else 0.0,
            # the CSV packet block's inputs, with CICFlowMeter's definitions: sample std of payload
            # lengths and of same-direction gaps (us), RST counts, transport-header bytes and data
            # packets in the forward direction
            "fwd_pkt_len_std": _sample_std(f["fwd_len"]),
            "bwd_pkt_len_std": _sample_std(f["bwd_len"]),
            "fwd_iat_std": _sample_std(f["fwd_iat"]) * 1e6,
            "bwd_iat_std": _sample_std(f["bwd_iat"]) * 1e6,
            "fwd_rst_cnt": f["fwd_rst"], "bwd_rst_cnt": f["bwd_rst"],
            "fwd_hdr_bytes": f["fwd_hdr"], "fwd_data_pkts": f["fwd_data"],
        }
        for k in A2_KEYS:
            row[f"a2_{k}"] = a2.get(key, {}).get(k, 0)
        rows.append(row)

    cols = [c for c in CANONICAL_COLUMNS if c not in ("label", "attempted", "stage")]
    df = pd.DataFrame(rows, columns=cols + list(PACKET_STAT_COLUMNS) + [f"a2_{k}" for k in A2_KEYS])
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    df.attrs["dropped_packets"] = dropped
    return df
