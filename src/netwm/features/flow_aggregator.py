import pandas as pd
from scapy.all import PcapReader, IP, TCP, UDP
from datetime import datetime, timezone
import math

from netwm.data.base import CANONICAL_COLUMNS
from netwm.features.pcap_features import PCAPFeatureExtractor

def _get_flow_key(ip_src, ip_dst, sport, dport, proto):
    """Return a canonical bidirectional flow key and direction."""
    # To keep it simple, we just use the first packet's direction as forward.
    # We will track first-seen directions in the aggregator.
    return (ip_src, ip_dst, sport, dport, proto)

def pcap_to_flows(pcap_path):
    """
    Reads a PCAP file and aggregates packets into canonical bidirectional flows,
    merging with the streaming PCAP features from A-2.
    """
    # Track bidirectional flows
    flows = {}
    
    # Also run the streaming feature extractor (A-2)
    extractor = PCAPFeatureExtractor()

    # We will need to map unidirectional A-2 features to bidirectional flows.
    # The A-2 extractor uses (src, dst, sport, dport, proto).
    
    with PcapReader(str(pcap_path)) as reader:
        for pkt in reader:
            extractor.process_packet(pkt)
            
            if not IP in pkt:
                continue
                
            ip = pkt[IP]
            proto = ip.proto
            
            if TCP in pkt:
                sport = pkt[TCP].sport
                dport = pkt[TCP].dport
                payload_len = len(pkt[TCP].payload)
                flags = pkt[TCP].flags
            elif UDP in pkt:
                sport = pkt[UDP].sport
                dport = pkt[UDP].dport
                payload_len = len(pkt[UDP].payload)
                flags = 0
            else:
                continue
                
            ts = float(pkt.time)
            
            # Determine flow key
            fwd_key = (ip.src, ip.dst, sport, dport, proto)
            bwd_key = (ip.dst, ip.src, dport, sport, proto)
            
            if fwd_key in flows:
                key = fwd_key
                is_fwd = True
            elif bwd_key in flows:
                key = bwd_key
                is_fwd = False
            else:
                key = fwd_key
                is_fwd = True
                flows[key] = {
                    "ts": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "src_ip": ip.src,
                    "dst_ip": ip.dst,
                    "src_port": sport,
                    "dst_port": dport,
                    "protocol": proto,
                    "first_ts": ts,
                    "last_ts": ts,
                    "fwd_pkts": 0,
                    "bwd_pkts": 0,
                    "fwd_bytes": 0,
                    "bwd_bytes": 0,
                    "fin_cnt": 0,
                    "syn_cnt": 0,
                    "rst_cnt": 0,
                    "psh_cnt": 0,
                    "ack_cnt": 0,
                    "urg_cnt": 0,
                    "cwr_cnt": 0,
                    "ece_cnt": 0,
                    "pkt_lengths": [],
                    "fwd_iat": [],
                    "last_fwd_ts": None,
                }
                
            f = flows[key]
            f["last_ts"] = max(f["last_ts"], ts)
            f["pkt_lengths"].append(len(pkt))
            
            if is_fwd:
                f["fwd_pkts"] += 1
                f["fwd_bytes"] += payload_len
                if f["last_fwd_ts"] is not None:
                    f["fwd_iat"].append(ts - f["last_fwd_ts"])
                f["last_fwd_ts"] = ts
            else:
                f["bwd_pkts"] += 1
                f["bwd_bytes"] += payload_len
                
            if TCP in pkt:
                if flags & 0x01: f["fin_cnt"] += 1
                if flags & 0x02: f["syn_cnt"] += 1
                if flags & 0x04: f["rst_cnt"] += 1
                if flags & 0x08: f["psh_cnt"] += 1
                if flags & 0x10: f["ack_cnt"] += 1
                if flags & 0x20: f["urg_cnt"] += 1
                if flags & 0x40: f["ece_cnt"] += 1
                if flags & 0x80: f["cwr_cnt"] += 1

    a2_features = extractor.get_session_features()
    
    rows = []
    for key, f in flows.items():
        dur_us = (f["last_ts"] - f["first_ts"]) * 1e6
        
        plens = f["pkt_lengths"]
        
        iats = [iat * 1e6 for iat in f["fwd_iat"]]
        
        row = {
            "ts": f["ts"].replace(tzinfo=None), # Make timezone-naive as required
            "src_ip": f["src_ip"],
            "dst_ip": f["dst_ip"],
            "src_port": f["src_port"],
            "dst_port": f["dst_port"],
            "protocol": f["protocol"],
            "duration_us": dur_us,
            "fwd_pkts": f["fwd_pkts"],
            "bwd_pkts": f["bwd_pkts"],
            "fwd_bytes": f["fwd_bytes"],
            "bwd_bytes": f["bwd_bytes"],
            "fin_cnt": f["fin_cnt"],
            "syn_cnt": f["syn_cnt"],
            "rst_cnt": f["rst_cnt"],
            "psh_cnt": f["psh_cnt"],
            "ack_cnt": f["ack_cnt"],
            "urg_cnt": f["urg_cnt"],
            "cwr_cnt": f["cwr_cnt"],
            "ece_cnt": f["ece_cnt"],
            
            "pkt_len_min": min(plens) if plens else 0,
            "pkt_len_max": max(plens) if plens else 0,
            "pkt_len_mean": sum(plens)/len(plens) if plens else 0,
            "pkt_len_std": pd.Series(plens).std() if len(plens) > 1 else 0.0,
            
            "flow_iat_min": min(iats) if iats else 0,
            "flow_iat_max": max(iats) if iats else 0,
            "flow_iat_mean": sum(iats)/len(iats) if iats else 0,
            "flow_iat_std": pd.Series(iats).std() if len(iats) > 1 else 0.0,
            
            "down_up_ratio": f["bwd_pkts"] / f["fwd_pkts"] if f["fwd_pkts"] > 0 else 0,
            "fwd_init_win": 0,
            "bwd_init_win": 0,
            "fwd_seg_size_min": 0,
            "active_mean": 0,
            "idle_mean": 0,
            "label": "BENIGN",
            "attempted": False,
            "stage": 0,
        }
        
        # Merge A-2 features. 
        # A-2 tracks directionally. For bidirectional, we take the forward direction features
        # or aggregate them. Here we just take the forward features.
        fwd_a2 = a2_features.get(key, {})
        for k, v in fwd_a2.items():
            row[f"a2_{k}"] = v
            
        rows.append(row)
        
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("ts").reset_index(drop=True)
        # Ensure all canonical columns exist (fill missing with 0)
        for col in CANONICAL_COLUMNS:
            if col not in df.columns:
                df[col] = 0
                
        # If any A-2 columns are missing because fwd_a2 was empty, fill with 0
        a2_keys = ["packet_count", "ttl_mean", "ttl_variance", "tcp_win_mean", 
                   "tcp_win_max", "ip_frag_count", "retrans_count", "payload_0_64", 
                   "payload_65_128", "payload_129_512", "payload_513_1024", "payload_gt_1024"]
        for k in a2_keys:
            col_name = f"a2_{k}"
            if col_name not in df.columns:
                df[col_name] = 0
                
    else:
        # Create empty DataFrame with required columns
        df = pd.DataFrame(columns=CANONICAL_COLUMNS)
        
    return df
