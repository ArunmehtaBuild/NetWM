"""Packet-level window features from a real capture (D-035, E20r): what no flow CSV carries.

The flow CSVs summarise each flow, so TTL, IP fragmentation and TCP retransmissions are simply not in
them. This module reads a day's PCAP directly and measures, per window of the same grid the flow
features use (``WindowSpec``, anchored at the split's ``t0``):

- **TTL**: mean, std, distinct values, and the share of packets with TTL < 60. A new operating system
  or a crafted packet shifts these; so does traffic arriving through extra hops.
- **Fragmentation**: the share of IPv4 packets with MF set or a non-zero fragment offset.
- **Retransmissions**: the share of TCP data packets whose bytes were already sent in that direction.
- **TCP window**: the share of zero-window packets (outside RST), and the spread of advertised windows.
- **Payload distribution**: the true per-packet payload histogram, 5 bins.
- **Timing**: the spread and coefficient of variation of inter-packet gaps; regular, sparse probing is
  the slow-scan signature.
- **Scan shape**: SYN-without-ACK and RST shares of TCP packets.

Why a separate reader rather than ``flow_aggregator``: a CIC-IDS2017 day is 8-13 GB and ~10 M
packets. Records are read straight from the file with ``struct``, one Python step per packet, and all
per-window statistics are computed afterwards with numpy on 30-second buckets. A packet belongs to the
two windows that cover it, exactly as ``expand_to_windows`` assigns flows.

Only classic libpcap files are read (the CIC-IDS2017 captures are); pcapng raises.
"""

from __future__ import annotations

import struct
import time
from array import array
from pathlib import Path

import numpy as np
import pandas as pd

PCAP_WINDOW_FEATURES: tuple[str, ...] = (
    "pcap_pkts",
    "pcap_ttl_mean",
    "pcap_ttl_std",
    "pcap_ttl_distinct",
    "pcap_ttl_low_rate",
    "pcap_frag_rate",
    "pcap_retrans_rate",
    "pcap_zero_win_rate",
    "pcap_win_std",
    "pcap_payload_0_rate",
    "pcap_payload_1_64_rate",
    "pcap_payload_65_512_rate",
    "pcap_payload_513_1024_rate",
    "pcap_payload_gt1024_rate",
    "pcap_iat_std",
    "pcap_iat_cv",
    "pcap_syn_only_rate",
    "pcap_rst_rate",
)
_PAYLOAD_EDGES = (0.5, 64.5, 512.5, 1024.5)
_MAGIC = {
    b"\xd4\xc3\xb2\xa1": ("<", 1e-6), b"\xa1\xb2\xc3\xd4": (">", 1e-6),
    b"\x4d\x3c\xb2\xa1": ("<", 1e-9), b"\xa1\xb2\x3c\x4d": (">", 1e-9),
}
_SYN, _RST, _ACK = 0x02, 0x04, 0x10
_CHUNK = 1 << 24  # 16 MB reads


def read_packets(path: Path | str, progress=None) -> dict[str, np.ndarray]:
    """Per-packet header fields of every IPv4 TCP/UDP/other packet in a classic pcap.

    Returns arrays: ts (float64, epoch s), ttl, proto, frag (bool), tcp_flags, win, payload,
    retrans (bool; TCP data already sent in that direction), and the count of frames skipped.
    """
    path = Path(path)
    started = time.perf_counter()
    # typed arrays, ~21 bytes a packet: a 13 GB day is ~12 M packets and the box has 7 GB of RAM
    ts, win, payload = array("d"), array("i"), array("i")
    ttl, proto, frag, flags, retrans = (array("B") for _ in range(5))
    seq_end: dict[tuple, int] = {}
    skipped = 0
    with open(path, "rb") as fh:
        header = fh.read(24)
        if header[:4] not in _MAGIC:
            raise ValueError(f"{path.name}: not a classic libpcap file (pcapng is not supported)")
        endian, tick = _MAGIC[header[:4]]
        linktype = struct.unpack(endian + "I", header[20:24])[0]
        rec = struct.Struct(endian + "IIII")
        buf, pos, done_bytes = b"", 0, 24
        while True:
            if len(buf) - pos < 16 + 65535:
                more = fh.read(_CHUNK)
                buf = buf[pos:] + more
                pos = 0
                if not more and len(buf) < 16:
                    break
            if len(buf) - pos < 16:
                break
            sec, frac, incl, _ = rec.unpack_from(buf, pos)
            start = pos + 16
            if len(buf) - start < incl:
                more = fh.read(_CHUNK)
                if not more:
                    break
                buf = buf[pos:] + more
                pos = 0
                continue
            pos = start + incl
            off = _ip_offset(buf, start, incl, linktype)
            if off is None:
                skipped += 1
                continue
            vihl = buf[off]
            if vihl >> 4 != 4:
                skipped += 1
                continue
            ihl = (vihl & 0x0F) * 4
            total_len, _, fragword, t, p = struct.unpack_from("!HHHBB", buf, off + 2)
            l4 = off + ihl
            fr = bool(fragword & 0x2000) or bool(fragword & 0x1FFF)
            fl, wn, pl, rt = 0, -1, max(0, total_len - ihl), False
            if p == 6 and not (fragword & 0x1FFF) and l4 + 16 <= start + incl:
                sport, dport, sq, _, offs, fl, wn = struct.unpack_from("!HHIIBBH", buf, l4)
                pl = max(0, total_len - ihl - (offs >> 4) * 4)
                if pl:
                    key = (buf[off + 12:off + 20], sport, dport)
                    end = (sq + pl) & 0xFFFFFFFF
                    prev = seq_end.get(key)
                    # already-sent bytes: this segment ends at or before the furthest end seen
                    if prev is not None and ((prev - end) & 0xFFFFFFFF) < 0x80000000:
                        rt = True
                    else:
                        seq_end[key] = end
            elif p == 17 and l4 + 8 <= start + incl:
                pl = max(0, struct.unpack_from("!H", buf, l4 + 4)[0] - 8)
            ts.append(sec + frac * tick)
            ttl.append(t)
            proto.append(p)
            frag.append(fr)
            flags.append(fl)
            win.append(wn)
            payload.append(pl)
            retrans.append(rt)
            if progress and len(ts) % 2_000_000 == 0:
                progress(f"  {len(ts):,} packets, {time.perf_counter() - started:.0f} s")
    return {
        "ts": np.frombuffer(ts, dtype=np.float64), "ttl": np.frombuffer(ttl, dtype=np.uint8).astype(np.int16),
        "proto": np.frombuffer(proto, dtype=np.uint8).astype(np.int16),
        "frag": np.frombuffer(frag, dtype=np.uint8).astype(bool),
        "flags": np.frombuffer(flags, dtype=np.uint8).astype(np.int16),
        "win": np.frombuffer(win, dtype=np.int32), "payload": np.frombuffer(payload, dtype=np.int32),
        "retrans": np.frombuffer(retrans, dtype=np.uint8).astype(bool),
        "skipped": np.asarray(skipped), "seconds": np.asarray(time.perf_counter() - started),
    }


def _ip_offset(buf: bytes, start: int, incl: int, linktype: int) -> int | None:
    if linktype == 1:  # Ethernet, with 802.1Q / 802.1ad tags
        off = start + 14
        ethertype = buf[start + 12:start + 14]
        while ethertype in (b"\x81\x00", b"\x88\xa8") and off + 4 <= start + incl:
            ethertype, off = buf[off + 2:off + 4], off + 4
        return off if ethertype == b"\x08\x00" and off + 20 <= start + incl else None
    if linktype in (101, 228, 12, 14):  # raw IP
        return start if incl >= 20 else None
    if linktype == 113:  # Linux cooked
        return start + 16 if buf[start + 14:start + 16] == b"\x08\x00" and incl >= 36 else None
    return None


def window_packet_features(
    packets: dict[str, np.ndarray],
    t0: pd.Timestamp,
    n_windows: int,
    length_s: float = 60.0,
    stride_s: float = 30.0,
) -> pd.DataFrame:
    """Aggregate per-packet fields into the flow features' window grid (index ``w``, 0..n_windows-1)."""
    if length_s != 2 * stride_s:
        raise ValueError("bucket aggregation assumes windows are two strides long (D-002)")
    origin = pd.Timestamp(t0).tz_localize("UTC").timestamp() if pd.Timestamp(t0).tzinfo is None \
        else pd.Timestamp(t0).timestamp()
    ts = packets["ts"]
    # packets are nearly time-ordered in a capture; the gap to the previous packet is the IAT
    order = np.argsort(ts, kind="stable")
    ts = ts[order]
    f = {k: v[order] for k, v in packets.items() if isinstance(v, np.ndarray) and v.shape == order.shape}
    bucket = np.floor((ts - origin) / stride_s).astype(np.int64)
    gap = np.diff(ts, prepend=np.nan)
    # a packet in bucket b is in windows b-1 and b; expand once
    w = np.concatenate([bucket, bucket - 1])
    keep = (w >= 0) & (w < n_windows)
    idx = np.concatenate([np.arange(len(ts))] * 2)[keep]
    w = w[keep]

    def count(mask=None):
        return np.bincount(w, weights=None if mask is None else mask[idx].astype(float), minlength=n_windows)

    def total(values):
        return np.bincount(w, weights=values[idx].astype(np.float64), minlength=n_windows)

    n = count()
    safe = np.where(n > 0, n, np.nan)
    tcp = f["proto"] == 6
    n_tcp = count(tcp)
    safe_tcp = np.where(n_tcp > 0, n_tcp, np.nan)
    ttl = f["ttl"].astype(np.float64)
    out = pd.DataFrame(index=pd.RangeIndex(n_windows, name="w"))
    out["pcap_pkts"] = n
    mean = total(ttl) / safe
    out["pcap_ttl_mean"] = mean
    out["pcap_ttl_std"] = np.sqrt(np.maximum(total(ttl ** 2) / safe - mean ** 2, 0.0))
    pairs = np.unique(w.astype(np.int64) * 256 + f["ttl"][idx].astype(np.int64))
    out["pcap_ttl_distinct"] = np.bincount(pairs // 256, minlength=n_windows)[:n_windows]
    out["pcap_ttl_low_rate"] = count(f["ttl"] < 60) / safe
    out["pcap_frag_rate"] = count(f["frag"]) / safe
    data = tcp & (f["payload"] > 0)
    n_data = count(data)
    out["pcap_retrans_rate"] = count(f["retrans"]) / np.where(n_data > 0, n_data, np.nan)
    has_win = tcp & (f["win"] >= 0) & ((f["flags"] & _RST) == 0)
    out["pcap_zero_win_rate"] = count(has_win & (f["win"] == 0)) / safe_tcp
    win = np.where(has_win, f["win"], 0).astype(np.float64)
    n_win = count(has_win)
    wmean = total(win) / np.where(n_win > 0, n_win, np.nan)
    out["pcap_win_std"] = np.sqrt(np.maximum(total(win ** 2) / np.where(n_win > 0, n_win, np.nan) - wmean ** 2, 0.0))
    bins = np.digitize(f["payload"], _PAYLOAD_EDGES)
    for b, name in enumerate(("pcap_payload_0_rate", "pcap_payload_1_64_rate", "pcap_payload_65_512_rate",
                              "pcap_payload_513_1024_rate", "pcap_payload_gt1024_rate")):
        out[name] = count(bins == b) / safe
    # inter-packet gaps inside the window: each gap is assigned to its later packet
    g = np.where(np.isfinite(gap) & (gap >= 0), gap, 0.0)
    has_gap = np.isfinite(gap) & (gap >= 0)
    ng = count(has_gap)
    gmean = total(g) / np.where(ng > 1, ng, np.nan)
    gstd = np.sqrt(np.maximum(total(g ** 2) / np.where(ng > 1, ng, np.nan) - gmean ** 2, 0.0))
    out["pcap_iat_std"] = gstd
    out["pcap_iat_cv"] = gstd / np.where(gmean > 0, gmean, np.nan)
    flags = f["flags"]
    out["pcap_syn_only_rate"] = count(tcp & ((flags & _SYN) > 0) & ((flags & _ACK) == 0)) / safe_tcp
    out["pcap_rst_rate"] = count(tcp & ((flags & _RST) > 0)) / safe_tcp
    return out[list(PCAP_WINDOW_FEATURES)].fillna(0.0).astype(np.float64)
