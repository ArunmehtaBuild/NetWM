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
  way. ``one_way_rate`` and ``tiny_flow_rate`` depend on this and are exact for one-way flows. A flow
  with no ``State`` at all (a few ICMP flows) has no recorded reply and counts as one-way.
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


def _by_category(values: pd.Series, fn, dtype) -> np.ndarray:
    """Apply ``fn`` once per distinct value of a categorical column, then broadcast by code.

    Scenario 3 is 4.7 M flows on a 7 GB machine: converting every cell to a Python string would
    cost gigabytes; the distinct values are a few hundred thousand at most.
    """
    cat = values.astype("category")
    lut = np.array([fn(str(c)) for c in cat.cat.categories], dtype=dtype)
    codes = cat.cat.codes.to_numpy()
    out = np.zeros(len(codes), dtype=dtype)
    ok = codes >= 0
    out[ok] = lut[codes[ok]]
    return out


def _to_port(text: str) -> int:
    """Argus writes ports as decimal, hex (``0x0303`` for ICMP type/code) or blank."""
    try:
        return int(text, 0)
    except ValueError:
        return 0


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
            "src_ip": raw["SrcAddr"].astype("string[pyarrow]"),
            "dst_ip": raw["DstAddr"].astype("string[pyarrow]"),
            "src_port": _by_category(raw["Sport"], _to_port, np.int64),
            "dst_port": _by_category(raw["Dport"], _to_port, np.int64),
            "protocol": _by_category(raw["Proto"], lambda s: _PROTO.get(s, 0), np.int64),
            "duration_us": (raw["Dur"].astype(np.float64) * 1e6).to_numpy(),
        })
        del raw["StartTime"]
        tcp = df["protocol"].to_numpy() == 6
        dst_side = _by_category(raw["State"], lambda s: len(s.split("_", 1)[1]) > 0 if "_" in s else False, bool)
        udp_replied = _by_category(raw["State"], lambda s: s != "INT", bool)
        replied = np.where(tcp, dst_side, udp_replied)
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
            # presence on each side of the State string, e.g. "FSPA_FSPA" -> 2 for F
            seen = _by_category(raw["State"], lambda s, L=letter: sum(L in part for part in s.split("_")[:2]),
                                np.int64)
            df[col] = np.where(tcp, seen, 0)
        for col in ("flow_iat_mean", "flow_iat_std", "flow_iat_max", "flow_iat_min", "pkt_len_min",
                    "pkt_len_max", "pkt_len_mean", "pkt_len_std", "down_up_ratio", "fwd_init_win",
                    "bwd_init_win", "fwd_seg_size_min", "active_mean", "idle_mean"):
            df[col] = 0.0  # not recorded by Argus; every feature built from these is dropped (module doc)
        df["label"] = raw["Label"].astype("category").to_numpy()
        df["stage"] = _by_category(raw["Label"], stage_of_ctu, np.int8)
        df["attempted"] = False
        df["day"] = split
        df = df.sort_values("ts", kind="stable").reset_index(drop=True)
        return self.validate(df[[*CANONICAL_COLUMNS, "day"]])
