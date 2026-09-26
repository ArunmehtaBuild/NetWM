import pandas as pd
from scapy.all import PcapReader, IP, TCP, UDP
from datetime import datetime, timezone
import math

from netwm.data.base import CANONICAL_COLUMNS
from netwm.features.pcap_features import PCAPFeatureExtractor

def pcap_to_flows(pcap_path, max_sessions=100000):
    """
    Reads a PCAP file and aggregates packets into canonical bidirectional flows,
    merging with the streaming PCAP features from A-2.
    Matches CICFlowMeter semantics.
    """
    flows = {}
    completed_flows = []
    
    extractor = PCAPFeatureExtractor(max_sessions=max_sessions)
    
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
                window = pkt[TCP].window
            elif UDP in pkt:
                sport = pkt[UDP].sport
                dport = pkt[UDP].dport
                payload_len = len(pkt[UDP].payload)
                flags = 0
                window = 0
            else:
                continue
                
            ts = float(pkt.time)
            
            # Determine flow key
            fwd_key = (ip.src, ip.dst, sport, dport, proto)
            bwd_key = (ip.dst, ip.src, dport, sport, proto)
            
            # Check 120s idle timeout
            is_fwd = True
            key = None
            if fwd_key in flows:
                if ts - flows[fwd_key]["last_ts"] > 120.0:
                    completed_flows.append(flows.pop(fwd_key))
                else:
                    key = fwd_key
                    is_fwd = True
            elif bwd_key in flows:
                if ts - flows[bwd_key]["last_ts"] > 120.0:
                    completed_flows.append(flows.pop(bwd_key))
                else:
                    key = bwd_key
                    is_fwd = False
                    
            if key is None:
                if len(flows) >= max_sessions:
                    # session cap reached, ignore new flow
                    continue
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
                    "flow_iat": [],
                    "fwd_init_win": 0,
                    "bwd_init_win": 0,
                    "is_terminated": False,
                }
                
            f = flows[key]
            
            if f["last_ts"] != ts and f["last_ts"] < ts:
                f["flow_iat"].append(ts - f["last_ts"])
                
            f["last_ts"] = max(f["last_ts"], ts)
            f["pkt_lengths"].append(payload_len)
            
            if is_fwd:
                f["fwd_pkts"] += 1
                f["fwd_bytes"] += payload_len
                if TCP in pkt and (flags & 0x02) and f["fwd_init_win"] == 0:
                    f["fwd_init_win"] = window
            else:
                f["bwd_pkts"] += 1
                f["bwd_bytes"] += payload_len
                if TCP in pkt and (flags & 0x02) and f["bwd_init_win"] == 0:
                    f["bwd_init_win"] = window
                    
            if TCP in pkt:
                if flags & 0x01: f["fin_cnt"] += 1
                if flags & 0x02: f["syn_cnt"] += 1
                if flags & 0x04: f["rst_cnt"] += 1
                if flags & 0x08: f["psh_cnt"] += 1
                if flags & 0x10: f["ack_cnt"] += 1
                if flags & 0x20: f["urg_cnt"] += 1
                if flags & 0x40: f["ece_cnt"] += 1
                if flags & 0x80: f["cwr_cnt"] += 1
                
                # Flow termination on FIN or RST
                if (flags & 0x01) or (flags & 0x04):
                    f["is_terminated"] = True
                    completed_flows.append(flows.pop(key))

    # Add any remaining flows
    completed_flows.extend(flows.values())

    a2_features = extractor.get_session_features()
    
    rows = []
    for f in completed_flows:
        key = (f["src_ip"], f["dst_ip"], f["src_port"], f["dst_port"], f["protocol"])
        dur_us = (f["last_ts"] - f["first_ts"]) * 1e6
        
        plens = f["pkt_lengths"]
        iats = [iat * 1e6 for iat in f["flow_iat"]]
        
        row = {
            "ts": f["ts"].replace(tzinfo=None), 
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
            "fwd_init_win": f["fwd_init_win"],
            "bwd_init_win": f["bwd_init_win"],
            "fwd_seg_size_min": 0,
            "active_mean": 0,
            "idle_mean": 0,
        }
        
        # Merge A-2 features
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
                
        # Fill A-2 keys if missing
        a2_keys = ["packet_count", "ttl_mean", "ttl_variance", "tcp_win_mean", 
                   "tcp_win_max", "ip_frag_count", "retrans_count", "payload_0_64", 
                   "payload_65_128", "payload_129_512", "payload_513_1024", "payload_gt_1024"]
        for k in a2_keys:
            col_name = f"a2_{k}"
            if col_name not in df.columns:
                df[col_name] = 0
                
    else:
        df = pd.DataFrame(columns=CANONICAL_COLUMNS)
        
    return df
