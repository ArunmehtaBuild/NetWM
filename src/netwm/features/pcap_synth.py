"""Flow records -> packets (A-5c): build a PCAP whose flows reproduce given CSV flow rows.

The corrected CIC-IDS2017 release ships flow CSVs, not packets (D-001), so the demo PCAP is
synthesised from the real Thursday flows (D-031). Each canonical flow row becomes a packet
sequence with a realistic shape - SYN / SYN-ACK first, FIN-ACK or RST last, ACK and PSH in
between - so ``flow_aggregator.pcap_to_flows`` reads the same flow back: same 5-tuple, same start
time, same packet counts per direction and the same SYN / FIN / RST counts. That round trip is what
``tests/test_pcap_ingest.py`` checks.

Two reductions keep a demo file small, and both are explicit arguments:

* ``max_packets`` keeps the first and last packets of a long flow and drops the middle, so the
  handshake and the teardown survive and the flow is still one flow.
* ``payload_cap`` caps each packet's payload; byte totals then differ from the CSV, packet counts
  and flags do not.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scapy.layers.inet import IP, TCP, UDP

FIN, SYN, RST, PSH, ACK = 0x01, 0x02, 0x04, 0x08, 0x10


@dataclass(frozen=True)
class SynthPacket:
    ts: float
    forward: bool
    flags: int
    payload: int


def plan_flow(row: pd.Series, max_packets: int | None = None) -> list[SynthPacket]:
    """The packet sequence for one canonical flow row (times in seconds since the epoch)."""
    n_fwd, n_bwd = int(row["fwd_pkts"]), int(row["bwd_pkts"])
    total = n_fwd + n_bwd
    if total == 0:
        return []
    start = pd.Timestamp(row["ts"]).tz_localize("UTC").timestamp() if pd.Timestamp(row["ts"]).tzinfo is None \
        else pd.Timestamp(row["ts"]).timestamp()
    duration = max(float(row.get("duration_us", 0.0)), 0.0) / 1e6

    # direction of each packet: the handshake first, the teardown last, alternating in between
    order: list[bool] = []
    fwd_left, bwd_left = n_fwd, n_bwd
    tcp = int(row["protocol"]) == 6
    syn = int(row.get("syn_cnt", 0)) if tcp else 0
    fin = int(row.get("fin_cnt", 0)) if tcp else 0
    if fwd_left:
        order.append(True)
        fwd_left -= 1
    if bwd_left and syn >= 2:
        order.append(False)
        bwd_left -= 1
    # hold back one packet per closing side so the FINs are the last packets (and survive a trim)
    tail: list[bool] = []
    if fin >= 1 and fwd_left:
        tail.append(True)
        fwd_left -= 1
    if fin >= 2 and bwd_left:
        tail.append(False)
        bwd_left -= 1
    turn = True
    while fwd_left or bwd_left:
        if (turn and fwd_left) or not bwd_left:
            order.append(True)
            fwd_left -= 1
        else:
            order.append(False)
            bwd_left -= 1
        turn = not turn
    order += tail

    flags = [0] * total
    if tcp:
        rst, psh = int(row.get("rst_cnt", 0)), int(row.get("psh_cnt", 0))
        for i in range(total):
            flags[i] = ACK if i > 0 else 0
        if syn >= 1:
            flags[0] |= SYN
        if syn >= 2 and total > 1 and not order[1]:
            flags[1] |= SYN
        # FIN on the last packet of each direction that has one (both, for a full close)
        for want_forward in (True, False):
            if fin <= 0:
                break
            idx = [i for i in range(total) if order[i] == want_forward]
            if idx and not flags[idx[-1]] & SYN:
                flags[idx[-1]] |= FIN
                fin -= 1
        if rst > 0 and not flags[-1] & (SYN | FIN):
            flags[-1] |= RST
        for i in range(1, total - 1):
            if psh <= 0:
                break
            if not flags[i] & (SYN | FIN | RST):
                flags[i] |= PSH
                psh -= 1

    fwd_bytes, bwd_bytes = int(row.get("fwd_bytes", 0)), int(row.get("bwd_bytes", 0))
    per_fwd = fwd_bytes // n_fwd if n_fwd else 0
    per_bwd = bwd_bytes // n_bwd if n_bwd else 0
    times = np.linspace(start, start + duration, total) if total > 1 else np.array([start])
    packets = [
        SynthPacket(float(times[i]), order[i], flags[i], per_fwd if order[i] else per_bwd)
        for i in range(total)
    ]
    if max_packets is not None and total > max_packets:
        head = max_packets // 2
        packets = packets[:head] + packets[total - (max_packets - head):]
    return packets


def build_packets(rows: pd.DataFrame, max_packets: int | None = None,
                  payload_cap: int | None = None) -> list:
    """scapy packets for every row, sorted by time (``row['keep_all']`` exempts a row from the cap)."""
    out = []
    for _, row in rows.iterrows():
        cap = None if bool(row.get("keep_all", False)) else max_packets
        for p in plan_flow(row, cap):
            src, dst = (row["src_ip"], row["dst_ip"]) if p.forward else (row["dst_ip"], row["src_ip"])
            sport, dport = ((int(row["src_port"]), int(row["dst_port"])) if p.forward
                            else (int(row["dst_port"]), int(row["src_port"])))
            size = p.payload if payload_cap is None else min(p.payload, payload_cap)
            body = b"\x00" * max(size, 0)
            if int(row["protocol"]) == 6:
                window = int(row.get("fwd_init_win" if p.forward else "bwd_init_win", 0) or 0)
                pkt = IP(src=src, dst=dst) / TCP(sport=sport, dport=dport, flags=p.flags,
                                                 window=min(max(window, 0), 65535)) / body
            elif int(row["protocol"]) == 17:
                pkt = IP(src=src, dst=dst) / UDP(sport=sport, dport=dport) / body
            else:
                continue
            pkt.time = p.ts
            out.append(pkt)
    out.sort(key=lambda k: float(k.time))
    return out
