"""A-3: a .pcap becomes canonical flows, and a PCAP payload never claims ground truth it doesn't have."""

from pathlib import Path

import pandas as pd
import pytest

scapy = pytest.importorskip("scapy.all")
from scapy.all import IP, TCP, UDP, wrpcap  # noqa: E402

from netwm.data.base import CANONICAL_COLUMNS  # noqa: E402
from netwm.features.flow_aggregator import pcap_to_flows  # noqa: E402

CKPT = Path(__file__).resolve().parents[1] / "models" / "e4e7-worldmodel-r2" / "thursday.pt"
T0 = 1_499_353_200.0  # 2017-07-06 15:00:00 UTC - fixed, so the test never depends on the clock


def _handshake_and_dns(path: Path) -> Path:
    a, b = "192.168.10.8", "192.168.10.50"
    pkts = [
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="S"),
        IP(src=b, dst=a) / TCP(sport=80, dport=50000, flags="SA"),
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="A"),
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="PA") / (b"x" * 100),
        IP(src=a, dst="192.168.10.3") / UDP(sport=53000, dport=53) / (b"q" * 30),
    ]
    for i, p in enumerate(pkts):
        p.time = T0 + i * 0.5
    wrpcap(str(path), pkts)
    return path


def test_pcap_becomes_canonical_bidirectional_flows(tmp_path):
    flows = pcap_to_flows(_handshake_and_dns(tmp_path / "t.pcap"))
    assert set(CANONICAL_COLUMNS) <= set(flows.columns)
    assert len(flows) == 2  # one TCP conversation (both directions), one UDP query
    tcp = flows[flows["protocol"] == 6].iloc[0]
    assert (tcp["src_ip"], tcp["dst_port"]) == ("192.168.10.8", 80)  # first packet sets forward
    assert (tcp["fwd_pkts"], tcp["bwd_pkts"]) == (3, 1)
    assert tcp["syn_cnt"] == 2 and tcp["ack_cnt"] == 3
    assert tcp["fwd_bytes"] == 100
    assert tcp["ts"] == pd.Timestamp(T0, unit="s")  # timezone-naive UTC, which windowing expects
    assert flows["ts"].is_monotonic_increasing


@pytest.mark.skipif(not CKPT.exists(), reason="submission checkpoint not present")
def test_pcap_payload_reports_no_ground_truth(tmp_path):
    from netwm.engine.predict import analyze_file, load_checkpoint

    payload = analyze_file(_handshake_and_dns(tmp_path / "t.pcap"), load_checkpoint(CKPT))
    assert payload["source"]["kind"] == "pcap"
    assert payload["ground_truth"] == {"available": False}
