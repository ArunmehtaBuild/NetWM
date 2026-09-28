"""A-3 / A-3c / A-5c: a .pcap becomes the canonical flows the model was trained on.

Flow semantics follow the *corrected* CIC-IDS2017 extraction (D-001): a TCP teardown does not split
the flow, RST ends it, and a flow lasts at most 120 s from its first packet. The parity tests
synthesise packets from flow rows (``netwm.features.pcap_synth``) and require ``pcap_to_flows`` to
read the same flows back - same 5-tuple, start time, packet counts per direction and flags.
"""

from pathlib import Path

import pandas as pd
import pytest

scapy = pytest.importorskip("scapy.all")
from scapy.all import IP, TCP, UDP, wrpcap  # noqa: E402

from netwm.data.base import CANONICAL_COLUMNS  # noqa: E402
from netwm.features.flow_aggregator import pcap_to_flows  # noqa: E402
from netwm.features.pcap_synth import build_packets  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CKPT = ROOT / "models" / "e4e7-worldmodel-r2" / "thursday.pt"
T0 = 1_499_353_200.0  # 2017-07-06 15:00:00 UTC - fixed, so the test never depends on the clock
LABELS = ("label", "attempted", "stage")
KEY = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol"]


def _write(path: Path, pkts: list, step: float = 0.5) -> Path:
    for i, p in enumerate(pkts):
        if not hasattr(p, "_t"):
            p.time = T0 + i * step
    wrpcap(str(path), pkts)
    return path


def _handshake_and_dns(path: Path) -> Path:
    a, b = "192.168.10.8", "192.168.10.50"
    return _write(path, [
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="S", window=8192),
        IP(src=b, dst=a) / TCP(sport=80, dport=50000, flags="SA", window=29200),
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="A"),
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="PA") / (b"x" * 100),
        IP(src=a, dst="192.168.10.3") / UDP(sport=53000, dport=53) / (b"q" * 30),
    ])


def test_pcap_becomes_canonical_unlabelled_flows(tmp_path):
    flows = pcap_to_flows(_handshake_and_dns(tmp_path / "t.pcap"))
    assert set(CANONICAL_COLUMNS) - set(LABELS) <= set(flows.columns)
    assert not set(LABELS) & set(flows.columns)  # a capture has no ground truth
    assert len(flows) == 2
    tcp = flows[flows["protocol"] == 6].iloc[0]
    assert (tcp["src_ip"], tcp["dst_port"]) == ("192.168.10.8", 80)  # first packet sets forward
    assert (tcp["fwd_pkts"], tcp["bwd_pkts"]) == (3, 1)
    assert tcp["syn_cnt"] == 2 and tcp["ack_cnt"] == 3
    assert tcp["fwd_bytes"] == 100 and tcp["pkt_len_max"] == 100  # payload lengths, not frames
    assert (tcp["fwd_init_win"], tcp["bwd_init_win"]) == (8192, 29200)
    assert tcp["fwd_seg_size_min"] == 20  # smallest forward TCP header, as the CSVs report it
    assert tcp["ts"] == pd.Timestamp(T0, unit="s")  # timezone-naive UTC, which windowing expects
    udp = flows[flows["protocol"] == 17].iloc[0]
    assert (udp["fwd_init_win"], udp["bwd_init_win"], udp["fwd_seg_size_min"]) == (0, 0, 8)


def test_teardown_stays_in_its_flow_and_a_new_syn_starts_another(tmp_path):
    a, b = "192.168.10.9", "192.168.10.3"

    def conn(sport):
        return [
            IP(src=a, dst=b) / TCP(sport=sport, dport=445, flags="S"),
            IP(src=b, dst=a) / TCP(sport=445, dport=sport, flags="SA"),
            IP(src=a, dst=b) / TCP(sport=sport, dport=445, flags="A"),
            IP(src=a, dst=b) / TCP(sport=sport, dport=445, flags="FA"),
            IP(src=b, dst=a) / TCP(sport=445, dport=sport, flags="FA"),
            IP(src=a, dst=b) / TCP(sport=sport, dport=445, flags="A"),  # the last ACK of the close
        ]

    rst = [IP(src=a, dst=b) / TCP(sport=40001, dport=22, flags="S"),
           IP(src=b, dst=a) / TCP(sport=22, dport=40001, flags="RA")]
    flows = pcap_to_flows(_write(tmp_path / "t.pcap", conn(40000) + conn(40000) + rst))
    tcp445 = flows[flows["dst_port"] == 445]
    # stock CICFlowMeter would end at the first FIN and emit the closing packets as extra flows
    assert len(tcp445) == 2  # port reuse after a full close: the new SYN starts the second flow
    assert tcp445["fwd_pkts"].tolist() == [4, 4] and tcp445["bwd_pkts"].tolist() == [2, 2]
    assert tcp445["fin_cnt"].tolist() == [2, 2]
    reset = flows[flows["dst_port"] == 22].iloc[0]
    assert (reset["fwd_pkts"], reset["bwd_pkts"], reset["rst_cnt"]) == (1, 1, 1)


def test_flow_timeout_runs_from_the_first_packet(tmp_path):
    a, b = "192.168.10.3", "192.168.10.1"
    pkts = [IP(src=a, dst=b) / UDP(sport=62028, dport=53) for _ in range(5)]
    for i, p in enumerate(pkts):
        p.time, p._t = T0 + i * 50.0, True  # every 50 s: never idle 120 s, but 200 s long
    flows = pcap_to_flows(_write(tmp_path / "t.pcap", pkts))
    assert flows["fwd_pkts"].tolist() == [3, 2]  # 0, 50, 100 s | 150, 200 s


def test_quiet_flows_expire_instead_of_filling_the_session_cap(tmp_path):
    """E27 check 4 / D-040: a flow that goes quiet never sees the packet that would close it. Unless
    expired flows are swept out, a full day fills the session cap and every later flow is dropped
    (Tuesday: 2.87 M packets)."""
    a, b = "192.168.10.3", "192.168.10.1"
    pkts = [IP(src=a, dst=b) / UDP(sport=40000 + i, dport=53) for i in range(20)]
    for i, p in enumerate(pkts):
        p.time, p._t = T0 + i * 60.0, True  # one quiet flow a minute for 20 minutes
    flows = pcap_to_flows(_write(tmp_path / "t.pcap", pkts), max_sessions=5)
    assert flows.attrs["dropped_packets"] == 0
    assert len(flows) == 20 and flows["src_port"].tolist() == list(range(40000, 40020))


def _rows() -> pd.DataFrame:
    base = pd.Timestamp("2017-07-06 17:00:00")
    return pd.DataFrame([
        # a full TCP conversation: handshake, data, both FINs
        dict(ts=base, src_ip="192.168.10.8", dst_ip="205.174.165.73", src_port=49200, dst_port=444,
             protocol=6, duration_us=2_000_000, fwd_pkts=6, bwd_pkts=5, fwd_bytes=600, bwd_bytes=5000,
             syn_cnt=2, fin_cnt=2, rst_cnt=0, psh_cnt=3, fwd_init_win=8192, bwd_init_win=29200),
        # a scan probe answered by RST
        dict(ts=base + pd.Timedelta(seconds=1), src_ip="172.16.0.1", dst_ip="192.168.10.51", src_port=55001,
             dst_port=3389, protocol=6, duration_us=300, fwd_pkts=1, bwd_pkts=1, fwd_bytes=0, bwd_bytes=0,
             syn_cnt=1, fin_cnt=0, rst_cnt=1, psh_cnt=0, fwd_init_win=1024, bwd_init_win=0),
        # DNS
        dict(ts=base + pd.Timedelta(seconds=2), src_ip="192.168.10.3", dst_ip="192.168.10.1", src_port=62028,
             dst_port=53, protocol=17, duration_us=46_917, fwd_pkts=1, bwd_pkts=1, fwd_bytes=40, bwd_bytes=120,
             syn_cnt=0, fin_cnt=0, rst_cnt=0, psh_cnt=0, fwd_init_win=0, bwd_init_win=0),
        # a long transfer, which the demo trims to its handshake and teardown
        dict(ts=base + pd.Timedelta(seconds=3), src_ip="192.168.10.14", dst_ip="192.168.10.50", src_port=51000,
             dst_port=80, protocol=6, duration_us=30_000_000, fwd_pkts=200, bwd_pkts=400, fwd_bytes=20_000,
             bwd_bytes=500_000, syn_cnt=2, fin_cnt=2, rst_cnt=0, psh_cnt=50, fwd_init_win=65535,
             bwd_init_win=29200),
    ])


@pytest.mark.parametrize("max_packets", [None, 4])
def test_synthesised_packets_read_back_as_the_same_flows(tmp_path, max_packets):
    rows = _rows()
    path = tmp_path / "t.pcap"
    wrpcap(str(path), build_packets(rows, max_packets=max_packets))
    back = pcap_to_flows(path).merge(rows, on=KEY, suffixes=("", "_row"))
    assert len(back) == len(rows)  # one flow per row: no splits, no merges
    assert (back["ts"] == back["ts_row"]).all()
    for _, r in back.iterrows():
        n = r["fwd_pkts_row"] + r["bwd_pkts_row"]
        if max_packets is None or n <= max_packets:
            assert (r["fwd_pkts"], r["bwd_pkts"]) == (r["fwd_pkts_row"], r["bwd_pkts_row"])
        else:
            assert r["fwd_pkts"] + r["bwd_pkts"] == max_packets
        assert (r["syn_cnt"], r["fin_cnt"], r["rst_cnt"]) == (r["syn_cnt_row"], r["fin_cnt_row"], r["rst_cnt_row"])
        if r["protocol"] == 6:
            assert (r["fwd_init_win"], r["bwd_init_win"]) == (r["fwd_init_win_row"], r["bwd_init_win_row"])


DEMO_PCAP = ROOT / "data" / "demo" / "thursday_demo.pcap"
RAW = ROOT / "data" / "raw" / "cicids2017_improved" / "thursday.csv"


@pytest.mark.skipif(not (DEMO_PCAP.exists() and RAW.exists()), reason="demo PCAP or raw Thursday CSV missing")
def test_demo_pcap_matches_the_csv_it_was_built_from():
    from netwm.data.cicids2017 import CICIDS2017Adapter

    flows = pcap_to_flows(DEMO_PCAP)
    src = CICIDS2017Adapter(RAW.parent).load("thursday")
    src = src[(src["ts"] >= "2017-07-06 16:50") & (src["ts"] < "2017-07-06 17:25") & src["protocol"].isin([6, 17])]
    assert abs(len(flows) - len(src)) <= 0.001 * len(src)  # measured: 22,478 vs 22,486
    assert flows["ts"].min() >= pd.Timestamp("2017-07-06 16:50") and flows["ts"].max() < pd.Timestamp("2017-07-06 17:25")
    # the 17:00 external scan: 955 labelled flows from 172.16.0.1, plus 17 other flows from that host
    assert (flows["src_ip"] == "172.16.0.1").sum() == (src["src_ip"] == "172.16.0.1").sum()
    assert (src["label"] == "Infiltration - Portscan").sum() == 955
    attack = src[src["label"].astype(str).str.upper() != "BENIGN"].merge(flows, on=KEY + ["ts"], suffixes=("", "_pcap"))
    assert len(attack) >= 955  # attack flows keep every packet
    assert (attack["fwd_pkts"] == attack["fwd_pkts_pcap"]).all()
    assert (attack["bwd_pkts"] == attack["bwd_pkts_pcap"]).all()


@pytest.mark.skipif(not CKPT.exists(), reason="submission checkpoint not present")
def test_pcap_payload_reports_no_ground_truth(tmp_path):
    from netwm.engine.predict import analyze_file, load_checkpoint

    payload = analyze_file(_handshake_and_dns(tmp_path / "t.pcap"), load_checkpoint(CKPT))
    assert payload["source"]["kind"] == "pcap"
    assert payload["ground_truth"] == {"available": False}


def test_pcap_flows_carry_the_csv_packet_block_inputs(tmp_path):
    """D-037: a PCAP upload must build the 17 pkt_ features from the same 8 per-flow columns the
    CSVs give, with CICFlowMeter's definitions."""
    a, b = "192.168.10.8", "192.168.10.50"
    pkts = [
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="S"),                       # fwd, hdr 20
        IP(src=b, dst=a) / TCP(sport=80, dport=50000, flags="SA"),                      # bwd
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="PA") / (b"x" * 100),       # fwd data
        IP(src=a, dst=b) / TCP(sport=50000, dport=80, flags="PA") / (b"x" * 300),       # fwd data
        IP(src=b, dst=a) / TCP(sport=80, dport=50000, flags="RA"),                      # bwd RST
    ]
    times = [0.0, 0.1, 0.5, 1.5, 1.6]
    for p, t in zip(pkts, times):
        p.time, p._t = T0 + t, True
    row = pcap_to_flows(_write(tmp_path / "t.pcap", pkts)).iloc[0]
    assert (row["fwd_data_pkts"], row["fwd_hdr_bytes"]) == (2, 60)
    assert (row["fwd_rst_cnt"], row["bwd_rst_cnt"]) == (0, 1)
    assert row["fwd_pkt_len_std"] == pytest.approx(pd.Series([0, 100, 300]).std())      # sample std
    assert row["fwd_iat_std"] == pytest.approx(pd.Series([0.5e6, 1.0e6]).std())         # us
    assert row["bwd_iat_std"] == 0.0                                                    # one gap only
