import os
import pytest
from scapy.all import wrpcap, Ether, IP, TCP, UDP
from netwm.features.pcap_features import PCAPFeatureExtractor

@pytest.fixture
def synthetic_pcap(tmp_path):
    """Generates a synthetic PCAP file with specific traffic patterns for testing."""
    pcap_path = str(tmp_path / "synthetic.pcap")
    packets = []
    
    # 1. Normal Session (src=1.1.1.1, dst=2.2.2.2)
    # Testing TTL math and TCP Window.
    # TTLs: 64, 60 -> Mean: 62, Variance: 4
    # TCP Win: 1000, 2000 -> Mean: 1500, Max: 2000
    pkt1 = Ether()/IP(src="1.1.1.1", dst="2.2.2.2", ttl=64)/TCP(sport=1000, dport=80, seq=100, window=1000)/("A"*40) # payload 40 (0_64 bucket)
    pkt2 = Ether()/IP(src="1.1.1.1", dst="2.2.2.2", ttl=60)/TCP(sport=1000, dport=80, seq=200, window=2000)/("B"*100) # payload 100 (65_128 bucket)
    packets.extend([pkt1, pkt2])
    
    # 2. Retransmission and Fragment flags (src=3.3.3.3, dst=4.4.4.4)
    # Testing MF flag (flags=1) and seeing the exact same sequence number back-to-back.
    pkt3 = Ether()/IP(src="3.3.3.3", dst="4.4.4.4", flags=1)/TCP(sport=5000, dport=443, seq=500)
    pkt4 = Ether()/IP(src="3.3.3.3", dst="4.4.4.4")/TCP(sport=5000, dport=443, seq=500)
    packets.extend([pkt3, pkt4])
    
    # 3. Port Scan: Sequential (src=10.0.0.1 -> dst 10.0.0.2)
    # Generating 20 packets hitting consecutive ports (100 to 119)
    for port in range(100, 120):
        packets.append(Ether()/IP(src="10.0.0.1", dst="10.0.0.2")/TCP(sport=12345, dport=port))
        
    # 4. Port Scan: Randomised (src=192.168.1.1 -> dst 10.0.0.2)
    # Generating 20 packets hitting widely spread ports
    import random
    random.seed(42)
    for _ in range(20):
        port = random.randint(1000, 50000)
        packets.append(Ether()/IP(src="192.168.1.1", dst="10.0.0.2")/TCP(sport=12345, dport=port))
        
    wrpcap(pcap_path, packets)
    return pcap_path


def test_pcap_extractor_session_features(synthetic_pcap):
    extractor = PCAPFeatureExtractor()
    extractor.extract_from_file(synthetic_pcap)
    features = extractor.get_session_features()
    
    # Check normal session stats
    k1 = ("1.1.1.1", "2.2.2.2", 1000, 80, 6) # proto 6 is TCP
    assert k1 in features
    f1 = features[k1]
    assert f1["packet_count"] == 2
    assert f1["ttl_mean"] == 62.0
    assert f1["ttl_variance"] == 4.0
    assert f1["tcp_win_mean"] == 1500.0
    assert f1["tcp_win_max"] == 2000.0
    assert f1["payload_0_64"] == 1
    assert f1["payload_65_128"] == 1
    assert f1["payload_129_512"] == 0
    
    # Check fragmentation and retransmission stats
    k2 = ("3.3.3.3", "4.4.4.4", 5000, 443, 6)
    assert k2 in features
    f2 = features[k2]
    assert f2["ip_frag_count"] == 1
    assert f2["retrans_count"] == 1


def test_pcap_extractor_scan_signatures(synthetic_pcap):
    extractor = PCAPFeatureExtractor()
    extractor.extract_from_file(synthetic_pcap)
    sigs = extractor.get_port_scan_signatures()
    
    # Normal user (too few ports to be a scan)
    assert sigs.get("1.1.1.1", "benign") == "benign"
    
    # Sequential Scanner
    assert sigs["10.0.0.1"] == "sequential_scan"
    
    # Randomised Scanner
    assert sigs["192.168.1.1"] == "randomised_scan"
