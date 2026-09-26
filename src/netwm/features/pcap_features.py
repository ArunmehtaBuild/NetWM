import math
from collections import defaultdict
from scapy.all import PcapReader, IP, TCP, UDP

class PCAPFeatureExtractor:
    """
    Streaming PCAP reader to extract packet-level features.
    Designed for memory efficiency by avoiding loading the whole PCAP into memory.
    """
    def __init__(self):
        # We track session stats incrementally to save memory
        # A session is identified by (src_ip, dst_ip, src_port, dst_port, protocol)
        self.sessions = defaultdict(lambda: {
            "packet_count": 0,
            
            # TTL stats
            "ttl_sum": 0,
            "ttl_sq_sum": 0,
            
            # TCP window size stats
            "tcp_win_sum": 0,
            "tcp_win_max": 0,
            "tcp_win_count": 0,
            
            # IP Fragments
            "ip_frag_count": 0,
            
            # Retransmissions
            "last_seq": None,
            "retrans_count": 0,
            
            # Payload size histogram buckets
            "payload_hist": {
                "0_64": 0, "65_128": 0, "129_512": 0, "513_1024": 0, "gt_1024": 0
            }
        })
        
        # Track ports visited by each Source IP to detect scan signatures
        self.src_ports_visited = defaultdict(list)

    def process_packet(self, pkt):
        """Extracts features from a single packet in a streaming fashion."""
        if not IP in pkt:
            return
            
        ip = pkt[IP]
        proto = ip.proto
        src_ip = ip.src
        dst_ip = ip.dst
        
        src_port = 0
        dst_port = 0
        seq = None
        tcp_win = None
        payload_len = len(ip.payload)
        
        if TCP in pkt:
            tcp = pkt[TCP]
            src_port = tcp.sport
            dst_port = tcp.dport
            seq = tcp.seq
            tcp_win = tcp.window
            payload_len = len(tcp.payload)
        elif UDP in pkt:
            udp = pkt[UDP]
            src_port = udp.sport
            dst_port = udp.dport
            payload_len = len(udp.payload)
        else:
            return # Only process TCP/UDP for session features
            
        session_key = (src_ip, dst_ip, src_port, dst_port, proto)
        s = self.sessions[session_key]
        
        # 1. Packet count and TTL stats
        s["packet_count"] += 1
        s["ttl_sum"] += ip.ttl
        s["ttl_sq_sum"] += (ip.ttl ** 2)
        
        # 2. TCP Window Size stats
        if tcp_win is not None:
            s["tcp_win_sum"] += tcp_win
            s["tcp_win_count"] += 1
            if tcp_win > s["tcp_win_max"]:
                s["tcp_win_max"] = tcp_win
                
        # 3. IP Fragment flags (MF=1 or frag offset > 0)
        if ip.flags == 1 or ip.frag > 0:
            s["ip_frag_count"] += 1
            
        # 4. Retransmission count (heuristic: seeing the exact same sequence number again)
        if seq is not None:
            if s["last_seq"] == seq:
                s["retrans_count"] += 1
            s["last_seq"] = seq
            
        # 5. Payload size histogram
        if payload_len <= 64:
            s["payload_hist"]["0_64"] += 1
        elif payload_len <= 128:
            s["payload_hist"]["65_128"] += 1
        elif payload_len <= 512:
            s["payload_hist"]["129_512"] += 1
        elif payload_len <= 1024:
            s["payload_hist"]["513_1024"] += 1
        else:
            s["payload_hist"]["gt_1024"] += 1
            
        # Track destination ports for scan detection
        # We only keep the last 100 to prevent memory blow-up on huge scans
        if len(self.src_ports_visited[src_ip]) < 100:
            self.src_ports_visited[src_ip].append(dst_port)

    def extract_from_file(self, pcap_path):
        """Reads a PCAP file using Scapy's streaming PcapReader."""
        with PcapReader(pcap_path) as pcap_reader:
            for pkt in pcap_reader:
                self.process_packet(pkt)
                
    def get_session_features(self):
        """Finalizes the math for means and variances and returns the feature dictionary."""
        features = {}
        for key, v in self.sessions.items():
            n = v["packet_count"]
            ttl_mean = v["ttl_sum"] / n if n > 0 else 0
            # Variance = E[X^2] - (E[X])^2
            ttl_variance = max(0, (v["ttl_sq_sum"] / n) - (ttl_mean ** 2)) if n > 0 else 0
            
            win_n = v["tcp_win_count"]
            tcp_win_mean = v["tcp_win_sum"] / win_n if win_n > 0 else 0
            
            features[key] = {
                "packet_count": n,
                "ttl_mean": float(ttl_mean),
                "ttl_variance": float(ttl_variance),
                "tcp_win_mean": float(tcp_win_mean),
                "tcp_win_max": float(v["tcp_win_max"]),
                "ip_frag_count": v["ip_frag_count"],
                "retrans_count": v["retrans_count"],
                "payload_0_64": v["payload_hist"]["0_64"],
                "payload_65_128": v["payload_hist"]["65_128"],
                "payload_129_512": v["payload_hist"]["129_512"],
                "payload_513_1024": v["payload_hist"]["513_1024"],
                "payload_gt_1024": v["payload_hist"]["gt_1024"]
            }
        return features

    def get_port_scan_signatures(self):
        """
        6. Sequential/randomised port-scan signature detection.
        Returns a dictionary mapping Source IPs to their scan behavior.
        """
        signatures = {}
        for src_ip, ports in self.src_ports_visited.items():
            # Need a decent sample size to call it a scan
            if len(ports) < 15:
                signatures[src_ip] = "benign"
                continue
                
            # Remove exact consecutive duplicates to find actual movement
            unique_movements = []
            for p in ports:
                if not unique_movements or unique_movements[-1] != p:
                    unique_movements.append(p)
                    
            if len(unique_movements) < 5:
                signatures[src_ip] = "benign"
                continue
                
            # Calculate distance between subsequent port targets
            deltas = [abs(unique_movements[i] - unique_movements[i-1]) for i in range(1, len(unique_movements))]
            
            # If they are hitting ports in exact sequence (e.g. 80, 81, 82), the delta is 1
            sequential_ratio = sum(1 for d in deltas if d == 1) / len(deltas)
            
            if sequential_ratio > 0.6:
                signatures[src_ip] = "sequential_scan"
            elif sequential_ratio < 0.1 and len(set(ports)) > 10:
                signatures[src_ip] = "randomised_scan"
            else:
                signatures[src_ip] = "benign"
                
        return signatures

if __name__ == "__main__":
    # Example usage / Smoke test
    print("PCAPFeatureExtractor is ready. Use extract_from_file(path) to process packets in a stream.")
