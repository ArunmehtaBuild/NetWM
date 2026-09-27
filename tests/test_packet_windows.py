"""E20r: packet-level window features read straight from a PCAP (``features/packet_windows.py``)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

scapy = pytest.importorskip("scapy.all")
from scapy.all import IP, TCP, UDP, wrpcap  # noqa: E402

from netwm.features.packet_windows import PCAP_WINDOW_FEATURES, read_packets, window_packet_features  # noqa: E402

T0 = pd.Timestamp("2017-07-06 17:00:00")
EPOCH = T0.tz_localize("UTC").timestamp()
ROOT = Path(__file__).resolve().parents[1]


def _capture(path: Path) -> Path:
    a, b = "192.168.10.8", "192.168.10.50"
    pkts = [
        # t = 5-9 s: a TCP conversation with one retransmitted segment and a zero-window ACK
        (5.0, IP(src=a, dst=b, ttl=128) / TCP(sport=50000, dport=80, flags="S", seq=1000, window=8192)),
        (5.1, IP(src=b, dst=a, ttl=64) / TCP(sport=80, dport=50000, flags="SA", seq=5000, ack=1001, window=29200)),
        (5.2, IP(src=a, dst=b, ttl=128) / TCP(sport=50000, dport=80, flags="PA", seq=1001, window=8192) / (b"x" * 100)),
        (5.9, IP(src=a, dst=b, ttl=128) / TCP(sport=50000, dport=80, flags="PA", seq=1001, window=8192) / (b"x" * 100)),
        (6.0, IP(src=b, dst=a, ttl=64) / TCP(sport=80, dport=50000, flags="A", seq=5001, window=0)),
        # t = 40 s: a fragment and a DNS query
        (40.0, IP(src=a, dst="192.168.10.3", ttl=128, flags="MF", frag=0) / UDP(sport=53000, dport=53) / (b"q" * 30)),
        # t = 70-72 s: a SYN scan from a low-TTL source, each answered by RST
        *[(70.0 + i * 0.2, IP(src="172.16.0.1", dst=b, ttl=40) / TCP(sport=41000, dport=1000 + i, flags="S"))
          for i in range(10)],
        *[(70.1 + i * 0.2, IP(src=b, dst="172.16.0.1", ttl=64) / TCP(sport=1000 + i, dport=41000, flags="RA"))
          for i in range(10)],
    ]
    frames = []
    for t, p in sorted(pkts, key=lambda tp: tp[0]):
        p.time = EPOCH + t
        frames.append(p)
    wrpcap(str(path), frames)
    return path


def test_packet_fields_and_retransmission(tmp_path):
    pk = read_packets(_capture(tmp_path / "t.pcap"))
    assert len(pk["ts"]) == 26 and int(pk["skipped"]) == 0
    assert pk["retrans"].sum() == 1                     # the second copy of seq 1001
    assert pk["frag"].sum() == 1
    assert sorted(set(pk["ttl"].tolist())) == [40, 64, 128]
    assert (pk["payload"][pk["proto"] == 17] == 30).all()


def test_window_features_land_on_the_flow_grid(tmp_path):
    feats = window_packet_features(read_packets(_capture(tmp_path / "t.pcap")), T0, n_windows=4)
    assert list(feats.columns) == list(PCAP_WINDOW_FEATURES)
    # window 0 = [0, 60) s: the conversation and the fragment (6 packets); window 1 = [30, 90): fragment + scan
    assert feats.loc[0, "pcap_pkts"] == 6 and feats.loc[1, "pcap_pkts"] == 21 and feats.loc[2, "pcap_pkts"] == 20
    assert feats.loc[0, "pcap_retrans_rate"] == pytest.approx(0.5)      # 1 of 2 data segments
    assert feats.loc[0, "pcap_frag_rate"] == pytest.approx(1 / 6)
    assert feats.loc[0, "pcap_zero_win_rate"] == pytest.approx(1 / 5)   # 1 of 5 TCP packets
    assert feats.loc[2, "pcap_syn_only_rate"] == pytest.approx(0.5)     # 10 SYN + 10 RST
    assert feats.loc[2, "pcap_rst_rate"] == pytest.approx(0.5)
    assert feats.loc[2, "pcap_ttl_low_rate"] == pytest.approx(0.5)      # the scanner's TTL 40
    assert feats.loc[2, "pcap_ttl_distinct"] == 2
    assert feats.loc[3].sum() == 0                                        # nothing after 90 s


def test_rejects_pcapng(tmp_path):
    p = tmp_path / "x.pcapng"
    p.write_bytes(b"\x0a\x0d\x0d\x0a" + b"\x00" * 60)
    with pytest.raises(ValueError):
        read_packets(p)


DEMO = ROOT / "data" / "demo" / "thursday_demo.pcap"


@pytest.mark.skipif(not DEMO.exists(), reason="demo PCAP missing")
def test_demo_capture_packet_counts_match_the_flow_reader():
    from netwm.features.flow_aggregator import pcap_to_flows

    pk = read_packets(DEMO)
    flows = pcap_to_flows(DEMO)
    assert len(pk["ts"]) == int(flows["fwd_pkts"].sum() + flows["bwd_pkts"].sum())
