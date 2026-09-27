"""CIC-IDS2017 adapter (corrected / "improved" release - see decisions.md D-001).

Source: https://intrusion-detection.distrinet-research.be/CNS2022/Datasets/CICIDS2017_improved.zip
Timestamps in this release are **UTC** (the capture ran 09:00-17:00 local, UTC-3, which shows up as
12:00-20:00 UTC), unlike the original CIC CSVs which are local time. See research/cicids2017.md.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from netwm.data.base import CANONICAL_COLUMNS, DatasetAdapter
from netwm.labels.mitre_map import is_attempted, refine_scan_direction, stage_of

#: raw CSV column -> canonical name
COLUMN_MAP: dict[str, str] = {
    "Timestamp": "ts",
    "Src IP": "src_ip",
    "Src Port": "src_port",
    "Dst IP": "dst_ip",
    "Dst Port": "dst_port",
    "Protocol": "protocol",
    "Flow Duration": "duration_us",
    "Total Fwd Packet": "fwd_pkts",
    "Total Bwd packets": "bwd_pkts",
    "Total Length of Fwd Packet": "fwd_bytes",
    "Total Length of Bwd Packet": "bwd_bytes",
    "Flow IAT Mean": "flow_iat_mean",
    "Flow IAT Std": "flow_iat_std",
    "Flow IAT Max": "flow_iat_max",
    "Flow IAT Min": "flow_iat_min",
    "FIN Flag Count": "fin_cnt",
    "SYN Flag Count": "syn_cnt",
    "RST Flag Count": "rst_cnt",
    "PSH Flag Count": "psh_cnt",
    "ACK Flag Count": "ack_cnt",
    "URG Flag Count": "urg_cnt",
    "CWR Flag Count": "cwr_cnt",
    "ECE Flag Count": "ece_cnt",
    "Packet Length Min": "pkt_len_min",
    "Packet Length Max": "pkt_len_max",
    "Packet Length Mean": "pkt_len_mean",
    "Packet Length Std": "pkt_len_std",
    "Down/Up Ratio": "down_up_ratio",
    "FWD Init Win Bytes": "fwd_init_win",
    "Bwd Init Win Bytes": "bwd_init_win",
    "Fwd Seg Size Min": "fwd_seg_size_min",
    "Active Mean": "active_mean",
    "Idle Mean": "idle_mean",
    "Label": "label",
}

#: Per-packet statistics the flow meter recorded that S_t v1 never read (D-035, E20). Optional: a
#: flow table without them (a PCAP upload, an older CSV) still loads, and the packet block is then
#: built from what is present - see ``flow_features.PACKET_CSV_COLUMNS``.
PACKET_STAT_MAP: dict[str, str] = {
    "Fwd Packet Length Std": "fwd_pkt_len_std",
    "Bwd Packet Length Std": "bwd_pkt_len_std",
    "Fwd IAT Std": "fwd_iat_std",
    "Bwd IAT Std": "bwd_iat_std",
    "Fwd RST Flags": "fwd_rst_cnt",
    "Bwd RST Flags": "bwd_rst_cnt",
    "Fwd Header Length": "fwd_hdr_bytes",
    "Fwd Act Data Pkts": "fwd_data_pkts",
}

DAYS: tuple[str, ...] = ("monday", "tuesday", "wednesday", "thursday", "friday")

#: Ground-truth attack windows, UTC, from the official schedule (local UTC-3) - used by the audit
#: and by lead-time scoring. Times are inclusive start, exclusive end.
ATTACK_SCHEDULE_UTC: dict[str, list[tuple[str, str, str]]] = {
    "tuesday": [
        ("2017-07-04 12:20", "2017-07-04 13:20", "FTP-Patator"),
        ("2017-07-04 17:00", "2017-07-04 18:00", "SSH-Patator"),
    ],
    "wednesday": [
        ("2017-07-05 12:47", "2017-07-05 13:10", "DoS Slowloris"),
        ("2017-07-05 13:14", "2017-07-05 13:35", "DoS Slowhttptest"),
        ("2017-07-05 13:43", "2017-07-05 14:00", "DoS Hulk"),
        ("2017-07-05 14:10", "2017-07-05 14:23", "DoS GoldenEye"),
        ("2017-07-05 18:12", "2017-07-05 18:32", "Heartbleed"),
    ],
    "thursday": [
        ("2017-07-06 12:20", "2017-07-06 13:00", "Web Attack - Brute Force"),
        ("2017-07-06 13:15", "2017-07-06 13:35", "Web Attack - XSS"),
        ("2017-07-06 13:40", "2017-07-06 13:42", "Web Attack - SQL Injection"),
        ("2017-07-06 17:19", "2017-07-06 17:21", "Infiltration (Dropbox/Meterpreter)"),
        ("2017-07-06 17:33", "2017-07-06 17:35", "Infiltration (2nd stage)"),
        ("2017-07-06 17:53", "2017-07-06 18:00", "Infiltration - Cool Disk (MAC)"),
        ("2017-07-06 18:04", "2017-07-06 18:45", "Infiltration - internal NMAP portscan"),
    ],
    "friday": [
        ("2017-07-07 13:02", "2017-07-07 14:02", "Botnet ARES"),
        ("2017-07-07 16:55", "2017-07-07 18:27", "PortScan"),
        ("2017-07-07 18:56", "2017-07-07 19:16", "DDoS LOIC"),
    ],
}

ATTACKER_IPS: tuple[str, ...] = ("205.174.165.73", "205.174.165.80", "172.16.0.1")
VICTIM_SUBNET: str = "192.168.10."


class CICIDS2017Adapter(DatasetAdapter):
    """Reads the per-day CSVs of the corrected release into canonical flows."""

    name = "cicids2017-improved"

    def splits(self) -> list[str]:
        return [d for d in DAYS if (self.root / f"{d}.csv").exists()]

    def load(self, split: str, nrows: int | None = None) -> pd.DataFrame:
        path = self.root / f"{split}.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found - run scripts/get_data.py first")

        df = pd.read_csv(
            path,
            usecols=[*COLUMN_MAP, *PACKET_STAT_MAP],
            nrows=nrows,
            parse_dates=["Timestamp"],
            low_memory=False,
        ).rename(columns={**COLUMN_MAP, **PACKET_STAT_MAP})

        # Labels -> ATT&CK stage. Mapping per *unique* label keeps this O(#labels), not O(#flows),
        # and any unmapped label raises (see mitre_map.UnknownLabelError) rather than silently
        # becoming benign.
        labels = df["label"].astype(str)
        uniq = labels.unique()
        stage_lut = {lbl: int(stage_of(lbl)) for lbl in uniq}
        attempt_lut = {lbl: bool(is_attempted(lbl)) for lbl in uniq}
        df["stage"] = labels.map(stage_lut).astype("int8")
        # An external scan and a scan from a compromised host share the label in this release;
        # separate them by source address (D-012).
        df["stage"] = refine_scan_direction(
            labels, df["stage"], df["src_ip"], (VICTIM_SUBNET,)
        ).astype("int8")
        df["attempted"] = labels.map(attempt_lut).astype(bool)
        df["day"] = split

        df = df.sort_values("ts", kind="stable").reset_index(drop=True)
        return self.validate(df[[*CANONICAL_COLUMNS, *PACKET_STAT_MAP.values(), "day"]])

    def attack_schedule(self, split: str) -> pd.DataFrame:
        """Official attack windows (UTC) for a day, as a frame with start/end/name."""
        rows = ATTACK_SCHEDULE_UTC.get(split, [])
        return pd.DataFrame(
            [
                {"start": pd.Timestamp(s), "end": pd.Timestamp(e), "attack": n}
                for s, e, n in rows
            ]
        )
