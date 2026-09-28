"""Cut a time range out of a pcap / pcapng capture, as ``editcap -A <start> -B <stop>`` does.

Why here rather than editcap: E27's Step 8 and check 4 need real-capture slices of the CIC-IDS2017
days, and Wireshark is not installed on every team machine. Blocks are copied byte for byte, so the
slice carries exactly the frames the full capture had in that range - duplicates included, which is
what the upload path must learn to handle (N-9).

Semantics follow editcap: a packet is kept when ``start <= ts < stop`` (epoch seconds). pcapng
section headers, interface descriptions and every other non-packet block are kept, so interface
indices and ``if_tsresol`` stay valid. Simple packet blocks carry no timestamp and are dropped; the
whole file is read, because a merged capture is not guaranteed to be time-ordered.
"""

from __future__ import annotations

import struct
from pathlib import Path

_CLASSIC = {
    b"\xd4\xc3\xb2\xa1": ("<", 1e-6), b"\xa1\xb2\xc3\xd4": (">", 1e-6),
    b"\x4d\x3c\xb2\xa1": ("<", 1e-9), b"\xa1\xb2\x3c\x4d": (">", 1e-9),
}
_SHB = b"\x0a\x0d\x0d\x0a"
_BUFFER = 1 << 24


def slice_capture(src: Path | str, dst: Path | str, start: float, stop: float) -> dict[str, int]:
    """Write the packets of ``src`` with ``start <= ts < stop`` to ``dst``; returns kept/total counts."""
    src, dst = Path(src), Path(dst)
    with open(src, "rb", buffering=_BUFFER) as fin, open(dst, "wb", buffering=_BUFFER) as fout:
        magic = fin.read(4)
        fin.seek(0)
        if magic in _CLASSIC:
            return _slice_classic(fin, fout, start, stop)
        if magic == _SHB:
            return _slice_pcapng(fin, fout, start, stop)
    dst.unlink(missing_ok=True)
    raise ValueError(f"{src.name}: neither pcap nor pcapng")


def _slice_classic(fin, fout, start: float, stop: float) -> dict[str, int]:
    header = fin.read(24)
    endian, tick = _CLASSIC[header[:4]]
    fout.write(header)
    rec = struct.Struct(endian + "IIII")
    kept = total = 0
    while True:
        head = fin.read(16)
        if len(head) < 16:
            break
        sec, frac, incl, _ = rec.unpack(head)
        body = fin.read(incl)
        if len(body) < incl:
            break
        total += 1
        if start <= sec + frac * tick < stop:
            fout.write(head)
            fout.write(body)
            kept += 1
    return {"kept": kept, "total": total}


def _slice_pcapng(fin, fout, start: float, stop: float) -> dict[str, int]:
    endian = "<"
    ticks: list[float] = []  # seconds per timestamp unit, per interface of the current section
    kept = total = 0
    while True:
        head = fin.read(12)
        if len(head) < 12:
            break
        if head[:4] == _SHB:
            endian = "<" if head[8:12] == b"\x4d\x3c\x2b\x1a" else ">"
            ticks = []
        btype, blen = struct.unpack(endian + "II", head[:8])
        if blen < 12 or blen % 4:
            raise ValueError(f"corrupt pcapng block (type {btype:#x}, length {blen})")
        rest = fin.read(blen - 12)
        if len(rest) < blen - 12:
            break
        block = head + rest
        if btype == 1:  # interface description: its if_tsresol sets the timestamp unit
            tick, opt = 1e-6, 16
            while opt + 4 <= blen - 4:
                code, olen = struct.unpack_from(endian + "HH", block, opt)
                if code == 0:
                    break
                if code == 9 and olen >= 1:
                    r = block[opt + 4]
                    tick = 2.0 ** -(r & 0x7F) if r & 0x80 else 10.0 ** -r
                opt += 4 + ((olen + 3) & ~3)
            ticks.append(tick)
        elif btype == 6:  # enhanced packet
            total += 1
            iface, hi, lo = struct.unpack_from(endian + "III", block, 8)
            if start <= ((hi << 32) | lo) * ticks[iface] < stop:
                kept += 1
            else:
                continue
        elif btype in (2, 3):  # obsolete / simple packet: no usable timestamp
            total += 1
            continue
        fout.write(block)
    return {"kept": kept, "total": total}
