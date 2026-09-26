import csv
from scapy.all import IP, TCP, UDP, wrpcap
import argparse
from pathlib import Path
from datetime import datetime

def synthesize_flow(row, start_time, duration):
    pkts = []
    
    src_ip = row['Src IP']
    dst_ip = row['Dst IP']
    src_port = int(row['Src Port'])
    dst_port = int(row['Dst Port'])
    proto = int(row['Protocol'])
    
    fwd_pkts = int(row['Total Fwd Packet'])
    bwd_pkts = int(row['Total Bwd packets'])
    
    fwd_bytes = int(row['Total Length of Fwd Packet'])
    bwd_bytes = int(row['Total Length of Bwd Packet'])
    
    fin_cnt = int(row['FIN Flag Count'])
    syn_cnt = int(row['SYN Flag Count'])
    rst_cnt = int(row['RST Flag Count'])
    psh_cnt = int(row['PSH Flag Count'])
    ack_cnt = int(row['ACK Flag Count'])
    
    total_pkts = fwd_pkts + bwd_pkts
    if total_pkts == 0:
        return pkts
        
    dt = duration / total_pkts if total_pkts > 1 else 0
    
    fwd_payload_len = fwd_bytes // fwd_pkts if fwd_pkts > 0 else 0
    bwd_payload_len = bwd_bytes // bwd_pkts if bwd_pkts > 0 else 0
    
    fwd_payload_len = min(fwd_payload_len, 100)
    bwd_payload_len = min(bwd_payload_len, 100)
    
    t = start_time
    
    for i in range(total_pkts):
        is_fwd = (i % 2 == 0) if (fwd_pkts > 0 and bwd_pkts > 0) else (fwd_pkts > 0)
        
        if is_fwd and fwd_pkts > 0:
            fwd_pkts -= 1
            ip = IP(src=src_ip, dst=dst_ip)
            if proto == 6:
                flags = ""
                if syn_cnt > 0: flags += "S"; syn_cnt -= 1
                elif fin_cnt > 0: flags += "F"; fin_cnt -= 1
                elif rst_cnt > 0: flags += "R"; rst_cnt -= 1
                elif psh_cnt > 0: flags += "P"; psh_cnt -= 1
                elif ack_cnt > 0: flags += "A"; ack_cnt -= 1
                l4 = TCP(sport=src_port, dport=dst_port, flags=flags)
                pkt = ip/l4/(b"X" * fwd_payload_len)
            elif proto == 17:
                l4 = UDP(sport=src_port, dport=dst_port)
                pkt = ip/l4/(b"X" * fwd_payload_len)
            else:
                continue
        elif not is_fwd and bwd_pkts > 0:
            bwd_pkts -= 1
            ip = IP(src=dst_ip, dst=src_ip)
            if proto == 6:
                flags = ""
                if syn_cnt > 0: flags += "S"; syn_cnt -= 1
                elif fin_cnt > 0: flags += "F"; fin_cnt -= 1
                elif rst_cnt > 0: flags += "R"; rst_cnt -= 1
                elif psh_cnt > 0: flags += "P"; psh_cnt -= 1
                elif ack_cnt > 0: flags += "A"; ack_cnt -= 1
                l4 = TCP(sport=dst_port, dport=src_port, flags=flags)
                pkt = ip/l4/(b"X" * bwd_payload_len)
            elif proto == 17:
                l4 = UDP(sport=dst_port, dport=src_port)
                pkt = ip/l4/(b"X" * bwd_payload_len)
            else:
                continue
        else:
            continue
            
        pkt.time = t
        pkts.append(pkt)
        t += dt
        
    return pkts

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/raw/cicids2017_improved/thursday.csv")
    parser.add_argument("--out", default="data/demo/thursday_demo.pcap")
    args = parser.parse_args()
    
    print(f"Reading {args.csv}...")
    
    all_pkts = []
    base_time = 1499353200.0 # Fixed start time
    
    start_ts = None
    count = 0
    with open(args.csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # We need to sort by timestamp first? The CSV is usually sorted.
        # But let's just collect rows that are within the first 50 minutes.
        rows = []
        for row in reader:
            ts_str = row['Timestamp'].strip()
            # Handle formats like 2017-07-06 11:59:05.720779 or 6/7/2017 8:59
            try:
                if '/' in ts_str:
                    ts = datetime.strptime(ts_str, '%d/%m/%Y %H:%M')
                elif '.' in ts_str:
                    ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            except Exception as e:
                continue
                
            rows.append((ts, row))
            
    rows.sort(key=lambda x: x[0])
    
    if not rows:
        print("No valid rows found.")
        return
        
    # Find the start of the infiltration block, or just the first row.
    # Atharv said "a 14 s external port scan at 17:00, the Meterpreter session at 17:19"
    # So we should start at '2017-07-06 16:40:00'
    start_ts = datetime.strptime('2017-07-06 16:40:00', '%Y-%m-%d %H:%M:%S')
    end_ts = datetime.strptime('2017-07-06 17:30:00', '%Y-%m-%d %H:%M:%S')
    
    slice_rows = [r for r in rows if start_ts <= r[0] <= end_ts]
    
    print(f"Synthesizing {len(slice_rows)} flows...")
    
    for ts, row in slice_rows:
        offset = (ts - start_ts).total_seconds()
        t = base_time + offset
        try:
            dur = float(row['Flow Duration']) / 1e6
        except:
            dur = 0
        
        pkts = synthesize_flow(row, t, dur)
        all_pkts.extend(pkts)
        
    all_pkts.sort(key=lambda x: x.time)
    
    if len(all_pkts) > 50000:
        all_pkts = all_pkts[:50000]
        
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Writing {len(all_pkts)} packets to {args.out}...")
    wrpcap(str(out_path), all_pkts)
    print("Done.")

if __name__ == "__main__":
    main()
