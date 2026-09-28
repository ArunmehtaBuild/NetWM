"""The capture slicer cuts what ``editcap -A <start> -B <stop>`` cuts, from pcap and pcapng alike."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scapy.all import IP, TCP, wrpcap  # noqa: E402
from scapy.utils import PcapNgWriter  # noqa: E402

from netwm.features.packet_windows import read_packets  # noqa: E402
from netwm.features.pcap_slice import slice_capture  # noqa: E402

T0 = 1_499_359_200.0  # 2017-07-06 16:40:00 UTC


def _packets() -> list:
    pkts = []
    for i in range(10):
        p = IP(src="192.168.10.8", dst="192.168.10.50", id=i) / TCP(sport=50000, dport=80, flags="A", seq=i)
        p.time = T0 + i
        pkts.append(p)
    return pkts


def _pcapng(path: Path, pkts: list) -> Path:
    with PcapNgWriter(str(path)) as w:
        for p in pkts:
            w.write(p)
    return path


@pytest.mark.parametrize("fmt", ["pcap", "pcapng"])
def test_slice_keeps_start_inclusive_stop_exclusive(tmp_path, fmt):
    src = tmp_path / f"day.{fmt}"
    if fmt == "pcap":
        wrpcap(str(src), _packets())
    else:
        _pcapng(src, _packets())
    counts = slice_capture(src, tmp_path / f"cut.{fmt}", T0 + 2, T0 + 5)
    assert counts == {"kept": 3, "total": 10}
    ts = read_packets(tmp_path / f"cut.{fmt}")["ts"]
    np.testing.assert_allclose(ts, [T0 + 2, T0 + 3, T0 + 4])
    assert (tmp_path / f"cut.{fmt}").read_bytes()[:4] == src.read_bytes()[:4]  # same format out


def test_slice_refuses_a_non_capture(tmp_path):
    junk = tmp_path / "x.pcap"
    junk.write_bytes(b"not a capture at all")
    with pytest.raises(ValueError):
        slice_capture(junk, tmp_path / "out.pcap", T0, T0 + 1)
    assert not (tmp_path / "out.pcap").exists()
