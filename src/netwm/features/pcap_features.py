import math
from collections import defaultdict, deque
from scapy.all import PcapReader, IP, TCP, UDP

class PCAPFeatureExtractor:
    """
    Streaming PCAP reader to extract packet-level features.
    Designed for memory efficiency by avoiding loading the whole PCAP into memory.
    """
    def __init__(self, max_sessions=100000):
        # DEFENSE: Prevent Memory Exhaustion (DoS) by capping tracked sessions
        self.max_sessions = max_sessions
        
        # A session is identified by (src_ip, dst_ip, src_port, dst_port, protocol)
        self.sessions = defaultdict(lambda: {
            "packet_count": 0,
            
            # DEFENSE: Welford's online algorithm for TTL stats (prevents float overflow)
            "ttl_mean": 0.0,
            "ttl_m2": 0.0,
            
            # TCP window size stats
            "tcp_win_mean": 0.0,
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
        
        # DEFENSE: Track ports visited by each Source IP to detect scan signatures
        # Using deque prevents a hacker from "filling" the buffer early with noise
        self.src_ports_visited = defaultdict(lambda: deque(maxlen=100))

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
        
        # DEFENSE: Drop tracking for new sessions if under DoS memory exhaustion attack
        if session_key not in self.sessions and len(self.sessions) >= self.max_sessions:
            return 
            
        s = self.sessions[session_key]
        
        # 1. Packet count and TTL stats (Welford's Algorithm)
        s["packet_count"] += 1
        n = s["packet_count"]
        delta = ip.ttl - s["ttl_mean"]
        s["ttl_mean"] += delta / n
        delta2 = ip.ttl - s["ttl_mean"]
        s["ttl_m2"] += delta * delta2
        
        # 2. TCP Window Size stats
        if tcp_win is not None:
            s["tcp_win_count"] += 1
            win_n = s["tcp_win_count"]
            win_delta = tcp_win - s["tcp_win_mean"]
            s["tcp_win_mean"] += win_delta / win_n
            if tcp_win > s["tcp_win_max"]:
                s["tcp_win_max"] = tcp_win
                
        # 3. IP Fragment flags (MF=1 or frag offset > 0)
        if ip.flags == 1 or ip.frag > 0:
            s["ip_frag_count"] += 1
            
        # 4. Retransmission count (heuristic: exact same sequence number back-to-back)
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
            
        # 6. Track destination ports for scan detection
        if len(self.src_ports_visited) < self.max_sessions or src_ip in self.src_ports_visited:
            self.src_ports_visited[src_ip].append(dst_port)

    def extract_from_file(self, pcap_path):
        """Reads a PCAP file using Scapy's streaming PcapReader."""
        with PcapReader(pcap_path) as pcap_reader:
            for pkt in pcap_reader:
                self.process_packet(pkt)
                
    def get_session_features(self):
        """Finalizes the math for variances and returns the feature dictionary."""
        features = {}
        for key, v in self.sessions.items():
            n = v["packet_count"]
            ttl_variance = (v["ttl_m2"] / n) if n > 0 else 0.0
            
            features[key] = {
                "packet_count": n,
                "ttl_mean": float(v["ttl_mean"]),
                "ttl_variance": float(ttl_variance),
                "tcp_win_mean": float(v["tcp_win_mean"]),
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
        Sequential/randomised port-scan signature detection.
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
