"""Per-window flow features: the observation vector S_t (decisions.md D-002).

Everything here is computed from the canonical flow schema, so it works for any adapter. Features
are grouped so the UI and the explainability output can talk about them in defender language
("flag behaviour", "port/host spread", "timing", "direction") rather than column names.

Packet-level features (TTL variance, IP fragments, retransmissions) live in ``pcap_features.py``
and are concatenated when a PCAP is available; without one they are zero-filled and ``has_pcap``
is 0, so the same model consumes both inputs.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

#: Well-known services worth a dedicated ratio - these are the ports attacks actually touch.
SERVICE_PORTS: dict[str, tuple[int, ...]] = {
    "http": (80, 8080, 8000),
    "https": (443, 8443),
    "dns": (53,),
    "ssh": (22,),
    "ftp": (20, 21),
    "smtp": (25, 465, 587),
    "smb": (139, 445),
    "rdp": (3389,),
    "db": (1433, 3306, 5432, 1521),
}


#: S_t v2 trend block (task S-1, decisions.md D-026): the features E12 ranked highest before an
#: onset. Levels alone tell the model *how many* ports are being touched, never how fast that rises.
TREND_BASES: tuple[str, ...] = (
    "uniq_dst_port",
    "ports_per_pair_max",
    "port_fanout_max",
    "uniq_dst_ip",
    "fanout_mean",
    "flows_per_s",
)
# Module constants rather than config on purpose (D-026): a checkpoint keeps only its feature
# *names*, and inference rebuilds the state from those alone, so a config value could silently
# differ between the build that trained a model and the engine that serves it.
TREND_SLOPES: tuple[int, ...] = (5, 10)  # least-squares slope windows; over 2 windows it IS the delta
TREND_BASELINE = 120  # trailing windows for the z-score: 120 x 30 s stride = 60 min
TREND_MIN_PERIODS = 10  # windows of history (5 min) before a z-score is trusted
TREND_STD_FLOOR = 1e-6
TREND_Z_CLIP = 10.0  # a flat baseline must not mint 1e6-sized values - the E2 failure again


def _entropy(counts: np.ndarray) -> float:
    """Shannon entropy in bits of a count vector; 0 for a single value."""
    total = counts.sum()
    if total <= 0:
        return 0.0
    p = counts / total
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def _group_entropy(df: pd.DataFrame, col: str) -> pd.Series:
    """Entropy of ``col``'s distribution within each window - high = spread across many values.

    Vectorised (no per-group python callback): a groupby-apply here cost ~40 % of the whole feature
    build on a single day.
    """
    counts = df.groupby(["w", col], sort=False).size().astype(np.float64)
    totals = counts.groupby(level=0).transform("sum")
    p = counts / totals
    return (-p * np.log2(p)).groupby(level=0).sum()


def _seq_scan_score(df: pd.DataFrame) -> pd.DataFrame:
    """Sequential / randomised port-sweep signatures per window.

    ``seq_port_ratio``  - share of consecutive port hits on the same (src, dst) pair that differ by
    exactly 1, i.e. a classic sequential sweep. ``ports_per_pair_max`` - the widest single sweep in
    the window. Both are named in the problem statement as packet-level scan signatures; they are
    derivable from flow records, so we compute them here rather than requiring a PCAP.
    """
    pairs = df[["w", "src_ip", "dst_ip", "dst_port"]].drop_duplicates()
    pairs = pairs.sort_values(["w", "src_ip", "dst_ip", "dst_port"], kind="stable")
    grp = pairs.groupby(["w", "src_ip", "dst_ip"], sort=False)["dst_port"]
    diffs = grp.diff()
    pairs["is_seq"] = (diffs == 1).astype(float)
    pairs["counted"] = diffs.notna().astype(float)

    per_pair = pairs.groupby(["w", "src_ip", "dst_ip"], sort=False).agg(
        seq=("is_seq", "sum"), counted=("counted", "sum"), ports=("dst_port", "size")
    )
    per_window = per_pair.groupby(level=0).agg(
        seq_hits=("seq", "sum"), seq_total=("counted", "sum"), ports_per_pair_max=("ports", "max")
    )
    per_window["seq_port_ratio"] = np.where(
        per_window["seq_total"] > 0, per_window["seq_hits"] / per_window["seq_total"], 0.0
    )
    return per_window[["seq_port_ratio", "ports_per_pair_max"]]


def _derive_flow_columns(df: pd.DataFrame, internal_prefixes: tuple[str, ...]) -> pd.DataFrame:
    """Per-flow helper columns that the window aggregation sums or averages."""
    out = df.copy()
    out["pkts"] = out["fwd_pkts"] + out["bwd_pkts"]
    out["bytes"] = out["fwd_bytes"] + out["bwd_bytes"]
    out["duration_s"] = out["duration_us"] / 1e6

    # Handshake shape: a SYN with no ACK back is the signature shared by SYN floods and port scans;
    # an RST answer is a refused connection, which is what a scan against a closed port produces.
    out["syn_no_ack"] = ((out["syn_cnt"] > 0) & (out["ack_cnt"] == 0)).astype(np.float32)
    out["has_rst"] = (out["rst_cnt"] > 0).astype(np.float32)
    out["has_fin"] = (out["fin_cnt"] > 0).astype(np.float32)
    out["one_way"] = (out["bwd_pkts"] == 0).astype(np.float32)
    out["tiny_flow"] = (out["pkts"] <= 2).astype(np.float32)

    src_internal = out["src_ip"].astype(str).str.startswith(internal_prefixes)
    dst_internal = out["dst_ip"].astype(str).str.startswith(internal_prefixes)
    out["is_outbound"] = (src_internal & ~dst_internal).astype(np.float32)
    out["is_inbound"] = (~src_internal & dst_internal).astype(np.float32)
    out["is_internal"] = (src_internal & dst_internal).astype(np.float32)
    # True directional byte split: bytes *leaving* the monitored network are the forward bytes of an
    # outbound flow plus the backward bytes of an inbound flow (a reply from an internal host).
    # Internal-to-internal traffic counts as neither, so it cannot fake an exfiltration signal.
    out["outbound_bytes"] = (
        out["fwd_bytes"] * out["is_outbound"] + out["bwd_bytes"] * out["is_inbound"]
    )
    out["inbound_bytes"] = (
        out["bwd_bytes"] * out["is_outbound"] + out["fwd_bytes"] * out["is_inbound"]
    )

    out["priv_port"] = (out["dst_port"] < 1024).astype(np.float32)
    out["ephemeral_dst"] = (out["dst_port"] >= 32768).astype(np.float32)
    for name, ports in SERVICE_PORTS.items():
        out[f"svc_{name}"] = out["dst_port"].isin(ports).astype(np.float32)
    for name, proto in (("tcp", 6), ("udp", 17), ("icmp", 1)):
        out[f"proto_{name}"] = (out["protocol"] == proto).astype(np.float32)
    return out


#: named aggregations applied per window; (source column, pandas agg) -> feature name
_MEANS: tuple[str, ...] = (
    "syn_no_ack",
    "has_rst",
    "has_fin",
    "one_way",
    "tiny_flow",
    "priv_port",
    "ephemeral_dst",
    "is_outbound",
    "is_inbound",
    "is_internal",
    "proto_tcp",
    "proto_udp",
    "proto_icmp",
    *(f"svc_{n}" for n in SERVICE_PORTS),
)

_STATS: tuple[tuple[str, str], ...] = (
    ("duration_s", "mean"),
    ("duration_s", "max"),
    ("bytes", "mean"),
    ("bytes", "max"),
    ("pkts", "mean"),
    ("pkt_len_mean", "mean"),
    ("pkt_len_max", "max"),
    ("pkt_len_std", "mean"),
    ("flow_iat_mean", "mean"),
    ("flow_iat_std", "mean"),
    ("flow_iat_max", "max"),
    ("flow_iat_min", "min"),
    ("down_up_ratio", "mean"),
    ("fwd_init_win", "mean"),
    ("fwd_init_win", "std"),
    ("bwd_init_win", "mean"),
    ("fwd_seg_size_min", "mean"),
    ("active_mean", "mean"),
    ("idle_mean", "mean"),
    ("syn_cnt", "sum"),
    ("ack_cnt", "sum"),
    ("fin_cnt", "sum"),
    ("rst_cnt", "sum"),
    ("psh_cnt", "sum"),
    ("urg_cnt", "sum"),
)


def window_features(
    expanded: pd.DataFrame,
    window_length_s: float,
    internal_prefixes: tuple[str, ...] = ("192.168.", "10.", "172.16."),
    n_windows: int | None = None,
    use_trend: bool = False,
) -> pd.DataFrame:
    """Aggregate an expanded (flow x window) frame into one feature row per window.

    ``expanded`` comes from :func:`netwm.features.windowing.expand_to_windows`. Empty windows are
    filled with zeros rather than dropped: a gap in traffic is itself a state the dynamics model has
    to be able to represent.

    ``use_trend`` appends the S_t v2 trend block (D-026). It is off by default: S_t v1 (70 columns)
    is frozen for comparability with every round-2 number.
    """
    df = _derive_flow_columns(expanded, internal_prefixes)
    g = df.groupby("w", sort=True)

    feats = pd.DataFrame(index=g.size().index)
    feats["n_flows"] = g.size()
    feats["flows_per_s"] = feats["n_flows"] / window_length_s
    feats["bytes_total"] = g["bytes"].sum()
    feats["bytes_per_s"] = feats["bytes_total"] / window_length_s
    feats["pkts_total"] = g["pkts"].sum()
    feats["pkts_per_s"] = feats["pkts_total"] / window_length_s

    for col in _MEANS:
        feats[f"{col}_rate"] = g[col].mean()
    for col, how in _STATS:
        feats[f"{col}_{how}"] = getattr(g[col], how)()

    # spread of the conversation graph: how many hosts/ports are involved and how concentrated
    feats["uniq_src_ip"] = g["src_ip"].nunique()
    feats["uniq_dst_ip"] = g["dst_ip"].nunique()
    feats["uniq_dst_port"] = g["dst_port"].nunique()
    feats["uniq_src_port"] = g["src_port"].nunique()
    feats["dst_port_entropy"] = _group_entropy(df, "dst_port")
    feats["dst_ip_entropy"] = _group_entropy(df, "dst_ip")
    feats["src_ip_entropy"] = _group_entropy(df, "src_ip")

    fanout = df.groupby(["w", "src_ip"], sort=False)["dst_ip"].nunique().groupby(level=0)
    feats["fanout_max"] = fanout.max()
    feats["fanout_mean"] = fanout.mean()
    port_fanout = df.groupby(["w", "src_ip"], sort=False)["dst_port"].nunique().groupby(level=0)
    feats["port_fanout_max"] = port_fanout.max()
    talker = df.groupby(["w", "src_ip"], sort=False).size().groupby(level=0)
    feats["top_talker_share"] = talker.max() / feats["n_flows"]

    feats = feats.join(_seq_scan_score(df))

    # directional byte asymmetry - the shape of an exfiltration, and of a download-then-callback
    out_b, in_b = g["outbound_bytes"].sum(), g["inbound_bytes"].sum()
    feats["outbound_bytes"] = out_b
    feats["inbound_bytes"] = in_b
    feats["byte_asymmetry"] = (out_b - in_b) / (out_b + in_b + 1.0)

    # beaconing: regular inter-flow spacing between the same pair. Low relative deviation over many
    # flows is the C2 signature; benign bursts are irregular.
    feats["beacon_score"] = _beacon_score(df).reindex(feats.index)

    n = n_windows if n_windows is not None else int(feats.index.max()) + 1
    feats = feats.reindex(pd.RangeIndex(n)).fillna(0.0)

    if use_trend:
        feats = feats.join(_trend_features(feats))

    feats.index.name = "w"
    return feats.astype(np.float32)


def trend_feature_names() -> list[str]:
    """The S_t v2 trend columns, in the order :func:`window_features` appends them."""
    suffixes = ["delta", *(f"slope_{w}" for w in TREND_SLOPES), "zscore"]
    return [f"{b}_{s}" for b in TREND_BASES for s in suffixes]


def feature_flags_from_names(names: Iterable[str]) -> dict[str, Any]:
    """The :func:`window_features` switches a model was trained with, read off its feature names.

    Checkpoints store ``feature_names`` but not the data config, so this is how the inference engine
    rebuilds the exact state a model saw. A partial match means the checkpoint was built with
    different trend constants - that must fail loudly, not feed the model a different state.
    """
    names = set(names)
    trend = set(trend_feature_names())
    present = trend & names
    if present and present != trend:
        raise ValueError(
            f"checkpoint has {len(present)} of {len(trend)} trend features - built with different "
            f"trend constants than flow_features.py now defines (missing e.g. {sorted(trend - names)[:3]})"
        )
    return {"use_trend": bool(present)}


def _ols_slope(x: np.ndarray, w: int) -> np.ndarray:
    """Least-squares slope of ``x`` over each trailing ``w``-window span, per window.

    A fixed linear filter, so it is exact and fast. It uses all ``w`` points, where a two-point
    difference ``(x_t - x_{t-w}) / w`` would be decided by one noisy endpoint. The first ``w - 1``
    windows have no complete span and stay 0.
    """
    j = np.arange(w, dtype=np.float64) - (w - 1) / 2.0
    kernel = j / (j**2).sum()
    out = np.zeros(len(x), dtype=np.float64)
    if len(x) >= w:
        out[w - 1 :] = sliding_window_view(x, w) @ kernel
    return out


def _trend_features(feats: pd.DataFrame) -> pd.DataFrame:
    """Delta, least-squares slopes and a trailing z-score for each of :data:`TREND_BASES`.

    Everything is strictly causal: window ``t`` sees windows ``<= t`` only, and the z-score's
    baseline stops at ``t - 1`` so a spike cannot dilute its own anomaly. Label-free - the baseline
    is "the last hour", not "the last benign hour", because a sensor does not know which is which.
    """
    out = {}
    for base in TREND_BASES:
        x = feats[base].astype(np.float64)
        out[f"{base}_delta"] = x.diff().fillna(0.0)
        for w in TREND_SLOPES:
            out[f"{base}_slope_{w}"] = pd.Series(_ols_slope(x.to_numpy(), w), index=x.index)
        hist = x.shift(1).rolling(TREND_BASELINE, min_periods=TREND_MIN_PERIODS)
        z = (x - hist.mean()) / hist.std().clip(lower=TREND_STD_FLOOR)
        out[f"{base}_zscore"] = z.clip(-TREND_Z_CLIP, TREND_Z_CLIP).fillna(0.0)
    return pd.DataFrame(out, index=feats.index)[trend_feature_names()]


def _beacon_score(df: pd.DataFrame) -> pd.Series:
    """Per-window beaconing regularity: 1 / (1 + coefficient of variation) of a pair's flow spacing.

    Computed by sorting once and diffing, instead of a groupby-apply - the callback version was the
    single slowest step in the feature build.
    """
    cols = ["w", "src_ip", "dst_ip", "ts"]
    d = df[cols].sort_values(cols, kind="stable")
    key = d[["w", "src_ip", "dst_ip"]]
    same_pair = (key == key.shift()).all(axis=1)
    gap = d["ts"].diff().dt.total_seconds().where(same_pair)
    d = d.assign(gap=gap).dropna(subset=["gap"])
    if d.empty:
        return pd.Series(dtype=np.float64)

    stats = d.groupby(["w", "src_ip", "dst_ip"], sort=False)["gap"].agg(["mean", "std", "size"])
    stats = stats[stats["size"] >= 3]
    if stats.empty:
        return pd.Series(dtype=np.float64)
    cv = stats["std"] / (stats["mean"] + 1e-6)
    return (1.0 / (1.0 + cv)).groupby(level=0).max()
