"""CTU-13 adapter (M2, D-035 E25): Argus bidirectional NetFlow -> the canonical flow schema.

Source: https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-<42..54>/
detailed-bidirectional-flow-labels/*.binetflow (Stratosphere Lab, CTU Prague, 2011), fetched into
``data/raw/ctu13/scenarioNN.binetflow`` by ``data/raw/ctu13/fetch.sh``. The public PCAPs are botnet-only
(research/ctu13.md), so the flow files are the only source with background traffic.

**What Argus gives and CICFlowMeter does not, and the reverse.** Argus records start time, duration,
protocol, the 5-tuple, a ``State`` string of the TCP flags seen from each side, total packets, total
bytes and source bytes. It has no inter-arrival statistics, packet-length statistics, initial windows,
segment sizes or active/idle times. Those canonical columns are filled with 0 so the schema validates,
and **every feature built from them is dropped from the model's inputs** (``CIC_ONLY_FEATURES``,
selected out by name in the E25 config) - never learned as a constant.

Derived fields:

- ``fwd_bytes`` = SrcBytes, ``bwd_bytes`` = TotBytes - SrcBytes.
- Packet split: Argus gives only the total. A flow with no reply (TCP ``State`` with nothing after
  ``_``, UDP ``INT``) is one-way; otherwise packets are split in proportion to bytes, at least one each
  way. ``one_way_rate`` and ``tiny_flow_rate`` depend on this and are exact for one-way flows.
- Flags: presence per side from ``State`` (``S`` SYN, ``A`` ACK, ``F`` FIN, ``R`` RST, ``P`` PSH, ``U``
  URG, ``E`` ECE, ``C`` CWR), so ``syn_cnt`` is 0-2, not a packet count. Rates built from presence are
  comparable; sums are on a different scale from CIC's, which is one reason E25 trains its own model.

**Labels -> stages** (D-036). ``Background`` and ``Normal`` flows are benign. ``From-Botnet`` flows:

| label contains | stage | why |
|---|---|---|
| ``CC`` | Command and Control | the dataset's own C&C labels |
| ``SPAM``, ``DDoS``, ``Flood``, ``ICMP``, ``Ad``, ``ClickFraud``, ``Proxy`` | Impact | abuse of the host's resources (T1496, T1498) |
| ``Attempt``, ``Scan`` (not spam) | Reconnaissance | unanswered connection attempts: scanning |
| anything else (DNS, established web, persistent HTTP) | Command and Control | the infected host's own channel; CTU-13 does not label every C&C flow ``CC`` |

``To-Botnet`` and other flows towards an infected host are benign here: they are replies or
background, and labelling them hostile would mark the victim's legitimate peers as attackers.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from netwm.data.base import CANONICAL_COLUMNS, DatasetAdapter
from netwm.labels.mitre_map import Stage

#: scenario number -> (botnet family, capture id, file name at the source)
SCENARIOS: dict[int, tuple[str, int, str]] = {
    1: ("Neris", 42, "capture20110810"), 2: ("Neris", 43, "capture20110811"),
    3: ("Rbot", 44, "capture20110812"), 4: ("Rbot", 45, "capture20110815"),
    5: ("Virut", 46, "capture20110815-2"), 6: ("Menti", 47, "capture20110816"),
    7: ("Sogou", 48, "capture20110816-2"), 8: ("Murlo", 49, "capture20110816-3"),
    9: ("Neris", 50, "capture20110817"), 10: ("Rbot", 51, "capture20110818"),
    11: ("Rbot", 52, "capture20110818-2"), 12: ("NSIS.ay", 53, "capture20110819"),
    13: ("Virut", 54, "capture20110815-3"),
}

#: CTU's monitored network (the university's /16); the infected hosts are 147.32.84.x
INTERNAL_PREFIXES: tuple[str, ...] = ("147.32.",)

#: S_t v1 features computed from canonical fields Argus does not record; dropped from E25's inputs.
CIC_ONLY_FEATURES: tuple[str, ...] = (
    "pkt_len_mean_mean", "pkt_len_max_max", "pkt_len_std_mean", "flow_iat_mean_mean", "flow_iat_std_mean",
    "flow_iat_max_max", "flow_iat_min_min", "down_up_ratio_mean", "fwd_init_win_mean", "fwd_init_win_std",
    "bwd_init_win_mean", "fwd_seg_size_min_mean", "active_mean_mean", "idle_mean_mean",
)

_PROTO = {"tcp": 6, "udp": 17, "icmp": 1}
_IMPACT = re.compile(r"SPAM|DDoS|Flood|ICMP|-Ad-|Ad-|ClickFraud|Proxy", re.IGNORECASE)
_RECON = re.compile(r"Attempt|Scan", re.IGNORECASE)
_FLAGS = {"S": "syn_cnt", "A": "ack_cnt", "F": "fin_cnt", "R": "rst_cnt", "P": "psh_cnt", "U": "urg_cnt",
          "E": "ece_cnt", "C": "cwr_cnt"}


def stage_of_ctu(label: str) -> int:
    """CTU-13 flow label -> ``Stage`` (see the module table, D-036)."""
    body = label.split("=", 1)[-1]
    if not body.startswith("From-Botnet"):
        return int(Stage.BENIGN)
    if "CC" in body:
        return int(Stage.COMMAND_AND_CONTROL)
    if _IMPACT.search(body):
        return int(Stage.IMPACT)
    if _RECON.search(body):
        return int(Stage.RECONNAISSANCE)
    return int(Stage.COMMAND_AND_CONTROL)


def _port(values: pd.Series) -> np.ndarray:
    """Argus writes ports as decimal, hex (``0x0303`` for ICMP type/code) or blank."""
    def conv(v) -> int:
        try:
            return int(str(v), 0)
        except ValueError:
            return 0
    uniq = values.astype(str).unique()
    lut = {u: conv(u) for u in uniq}
    return values.astype(str).map(lut).to_numpy(dtype=np.int64)


class CTU13Adapter(DatasetAdapter):
    name = "ctu13"

    def splits(self) -> list[str]:
        return [f"s{n:02d}" for n in SCENARIOS if (self.root / f"scenario{n:02d}.binetflow").exists()]

    @staticmethod
    def family(split: str) -> str:
        return SCENARIOS[int(split[1:])][0]

    def load(self, split: str, nrows: int | None = None) -> pd.DataFrame:
        path = self.root / f"scenario{int(split[1:]):02d}.binetflow"
        raw = pd.read_csv(
            path, nrows=nrows, skipinitialspace=True,
            usecols=["StartTime", "Dur", "Proto", "SrcAddr", "Sport", "DstAddr", "Dport", "State",
                     "TotPkts", "TotBytes", "SrcBytes", "Label"],
            dtype={"Proto": "category", "SrcAddr": "category", "DstAddr": "category", "Sport": "category",
                   "Dport": "category", "State": "category", "Label": "category", "Dur": "float32",
                   "TotPkts": "int64", "TotBytes": "int64", "SrcBytes": "int64"},
        )
        n = len(raw)
        df = pd.DataFrame({
            "ts": pd.to_datetime(raw["StartTime"], format="%Y/%m/%d %H:%M:%S.%f"),
            "src_ip": raw["SrcAddr"].astype(str),
            "dst_ip": raw["DstAddr"].astype(str),
            "src_port": _port(raw["Sport"]),
            "dst_port": _port(raw["Dport"]),
            "protocol": raw["Proto"].astype(str).map(_PROTO).fillna(0).astype(np.int64).to_numpy(),
            "duration_us": (raw["Dur"].astype(np.float64) * 1e6).to_numpy(),
        })
        state = raw["State"].astype(str)
        src_flags = state.str.split("_").str[0].fillna("")
        dst_flags = state.str.split("_").str[1].fillna("")
        tcp = df["protocol"].to_numpy() == 6
        replied = np.where(tcp, dst_flags.str.len().to_numpy() > 0, state.to_numpy() != "INT")
        tot = raw["TotPkts"].to_numpy()
        fwd_b = raw["SrcBytes"].to_numpy()
        tot_b = raw["TotBytes"].to_numpy()
        share = np.divide(fwd_b, tot_b, out=np.ones(n), where=tot_b > 0)
        fwd = np.where(replied, np.clip(np.round(tot * share), 1, np.maximum(tot - 1, 1)), tot)
        df["fwd_pkts"] = fwd.astype(np.int64)
        df["bwd_pkts"] = np.where(replied, np.maximum(tot - fwd, 1), 0).astype(np.int64)
        df["fwd_bytes"] = fwd_b
        df["bwd_bytes"] = np.maximum(tot_b - fwd_b, 0)
        for letter, col in _FLAGS.items():
            df[col] = np.where(tcp, src_flags.str.contains(letter, regex=False).to_numpy().astype(int)
                               + dst_flags.str.contains(letter, regex=False).to_numpy().astype(int), 0)
        for col in ("flow_iat_mean", "flow_iat_std", "flow_iat_max", "flow_iat_min", "pkt_len_min",
                    "pkt_len_max", "pkt_len_mean", "pkt_len_std", "down_up_ratio", "fwd_init_win",
                    "bwd_init_win", "fwd_seg_size_min", "active_mean", "idle_mean"):
            df[col] = 0.0  # not recorded by Argus; every feature built from these is dropped (module doc)
        labels = raw["Label"].astype(str)
        lut = {lbl: stage_of_ctu(lbl) for lbl in labels.unique()}
        df["label"] = labels.to_numpy()
        df["stage"] = labels.map(lut).astype("int8").to_numpy()
        df["attempted"] = False
        df["day"] = split
        df = df.sort_values("ts", kind="stable").reset_index(drop=True)
        return self.validate(df[[*CANONICAL_COLUMNS, "day"]])
