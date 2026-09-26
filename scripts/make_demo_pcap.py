import time
from scapy.all import IP, TCP, wrpcap
from pathlib import Path

def generate_scan_pcap(output_path):
    pkts = []
    base_time = time.time() - 3600 # 1 hour ago
    
    # Benign background noise
    for i in range(10):
        pkt = IP(src="192.168.1.10", dst="192.168.1.20")/TCP(sport=50000+i, dport=80, flags="S")
        pkt.time = base_time + i * 2
        pkts.append(pkt)
        
        pkt_ack = IP(src="192.168.1.20", dst="192.168.1.10")/TCP(sport=80, dport=50000+i, flags="SA")
        pkt_ack.time = base_time + i * 2 + 0.01
        pkts.append(pkt_ack)
        
    # Malicious port scan (sequential)
    scan_time = base_time + 60
    for port in range(20, 120):
        pkt = IP(src="10.0.0.5", dst="192.168.1.50")/TCP(sport=12345, dport=port, flags="S")
        pkt.time = scan_time + (port - 20) * 0.1
        pkts.append(pkt)
        
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wrpcap(output_path, pkts)
    print(f"Generated {output_path} with {len(pkts)} packets.")

if __name__ == "__main__":
    generate_scan_pcap("data/demo/small_scan.pcap")
