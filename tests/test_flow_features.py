import numpy as np
import pandas as pd
import pytest

from netwm.data.base import CANONICAL_COLUMNS
from netwm.features.flow_features import (
    TREND_BASELINE,
    TREND_BASES,
    TREND_MIN_PERIODS,
    TREND_Z_CLIP,
    HOST_FEATURES,
    _trend_features,
    feature_flags_from_names,
    host_feature_names,
    trend_feature_names,
    window_features,
)
from netwm.features.windowing import WindowSpec, expand_to_windows

T0 = pd.Timestamp("2017-07-06 12:00:00")
INTERNAL = ("192.168.10.",)

#: S_t v1, in order. Frozen: every round-2 number and checkpoint was built on exactly these columns
#: (D-026). Taken from the pre-S-1 implementation (f7a0029), not from the code under test.
V1_COLUMNS = (
    "n_flows", "flows_per_s", "bytes_total", "bytes_per_s", "pkts_total", "pkts_per_s",
    "syn_no_ack_rate", "has_rst_rate", "has_fin_rate", "one_way_rate", "tiny_flow_rate",
    "priv_port_rate", "ephemeral_dst_rate", "is_outbound_rate", "is_inbound_rate",
    "is_internal_rate", "proto_tcp_rate", "proto_udp_rate", "proto_icmp_rate", "svc_http_rate",
    "svc_https_rate", "svc_dns_rate", "svc_ssh_rate", "svc_ftp_rate", "svc_smtp_rate",
    "svc_smb_rate", "svc_rdp_rate", "svc_db_rate", "duration_s_mean", "duration_s_max",
    "bytes_mean", "bytes_max", "pkts_mean", "pkt_len_mean_mean", "pkt_len_max_max",
    "pkt_len_std_mean", "flow_iat_mean_mean", "flow_iat_std_mean", "flow_iat_max_max",
    "flow_iat_min_min", "down_up_ratio_mean", "fwd_init_win_mean", "fwd_init_win_std",
    "bwd_init_win_mean", "fwd_seg_size_min_mean", "active_mean_mean", "idle_mean_mean",
    "syn_cnt_sum", "ack_cnt_sum", "fin_cnt_sum", "rst_cnt_sum", "psh_cnt_sum", "urg_cnt_sum",
    "uniq_src_ip", "uniq_dst_ip", "uniq_dst_port", "uniq_src_port", "dst_port_entropy",
    "dst_ip_entropy", "src_ip_entropy", "fanout_max", "fanout_mean", "port_fanout_max",
    "top_talker_share", "seq_port_ratio", "ports_per_pair_max", "outbound_bytes",
    "inbound_bytes", "byte_asymmetry", "beacon_score",
)


def flows(rows):
    """Canonical flow records: zeros everywhere except what each row dict sets (``t`` = seconds)."""
    base = {c: 0 for c in CANONICAL_COLUMNS}
    base.update(src_ip="192.168.10.5", dst_ip="192.168.10.9", protocol=6, label="BENIGN", attempted=False)
    recs = []
    for r in rows:
        rec = {**base, **{k: v for k, v in r.items() if k != "t"}}
        rec["ts"] = T0 + pd.Timedelta(seconds=r["t"])
        recs.append(rec)
    return pd.DataFrame(recs, columns=list(CANONICAL_COLUMNS))


def features(rows, n_windows=None, **kw):
    ex, _ = expand_to_windows(flows(rows), WindowSpec(60, 30), t0=T0)
    return window_features(ex, 60.0, INTERNAL, n_windows=n_windows, **kw)


def sweep(n_minutes=40):
    """One internal host touching one more port every 30 s - a slow, steadily widening scan."""
    return [
        {"t": 30 * i + 1, "dst_port": p, "fwd_pkts": 1, "fwd_bytes": 60}
        for i in range(2 * n_minutes)
        for p in range(1, i + 2)
    ]


# --- S_t v1 stays frozen ------------------------------------------------------------------------


def test_v1_state_is_exactly_the_frozen_seventy_columns():
    f = features(sweep(5))
    assert tuple(f.columns) == V1_COLUMNS
    assert f.dtypes.eq(np.float32).all()


def test_trend_block_is_off_unless_asked_for():
    assert not set(trend_feature_names()) & set(features(sweep(5)).columns)


# --- S_t v2: the trend block --------------------------------------------------------------------


def test_v2_appends_twenty_four_trend_columns_after_v1():
    f = features(sweep(10), use_trend=True)
    assert tuple(f.columns[:70]) == V1_COLUMNS
    assert list(f.columns[70:]) == trend_feature_names()
    assert f.shape[1] == 70 + 4 * len(TREND_BASES) == 94
    assert f.dtypes.eq(np.float32).all()
    assert np.isfinite(f.to_numpy()).all()


def test_every_trend_base_is_a_real_v1_column():
    # a renamed base would otherwise vanish silently from S_t v2
    assert set(TREND_BASES) <= set(V1_COLUMNS)


def test_a_steady_ramp_has_its_gradient_as_delta_and_both_slopes():
    ramp = pd.DataFrame({b: 3.0 * np.arange(40.0) for b in TREND_BASES})
    t = _trend_features(ramp)
    for b in TREND_BASES:
        assert np.allclose(t[f"{b}_delta"].iloc[1:], 3.0)
        assert np.allclose(t[f"{b}_slope_5"].iloc[4:], 3.0)
        assert np.allclose(t[f"{b}_slope_10"].iloc[9:], 3.0)
        assert (t[f"{b}_slope_10"].iloc[:9] == 0.0).all()  # no complete span yet


def test_the_least_squares_slope_is_steadier_than_the_two_point_difference_it_replaced():
    noise = pd.Series(np.random.default_rng(2).normal(0.0, 1.0, 5000))
    ols = _trend_features(pd.DataFrame({b: noise for b in TREND_BASES}))["flows_per_s_slope_10"]
    two_point = (noise - noise.shift(10)) / 10  # the D-024 estimator, decided by two windows
    # theory: std ratio sqrt(50 / 82.5) = 0.78 - same unbiased trend, less noise
    assert ols.iloc[9:].std() < 0.85 * two_point.iloc[10:].std()


def test_trend_features_never_see_the_future():
    x = np.random.default_rng(0).poisson(20, 300).astype(float)
    before = _trend_features(pd.DataFrame({b: x for b in TREND_BASES}))
    x2 = x.copy()
    x2[200:] *= 50  # an attack that starts at window 200
    after = _trend_features(pd.DataFrame({b: x2 for b in TREND_BASES}))
    pd.testing.assert_frame_equal(before.iloc[:200], after.iloc[:200])


def test_zscore_baseline_excludes_the_current_window_and_is_clipped():
    x = np.full(TREND_BASELINE + 5, 10.0)
    x[::2] += 1.0  # a little benign jitter
    x[-1] = 10_000.0  # a spike: its own value must not inflate the baseline it is judged against
    z = _trend_features(pd.DataFrame({b: x for b in TREND_BASES}))["flows_per_s_zscore"]
    assert z.iloc[-1] == TREND_Z_CLIP
    assert z.abs().max() <= TREND_Z_CLIP


def test_zscore_waits_for_its_minimum_history():
    x = np.random.default_rng(1).poisson(20, 50).astype(float)
    z = _trend_features(pd.DataFrame({b: x for b in TREND_BASES}))["uniq_dst_ip_zscore"]
    assert (z.iloc[:TREND_MIN_PERIODS] == 0.0).all()
    assert (z.iloc[TREND_MIN_PERIODS:] != 0.0).any()


def test_a_widening_sweep_shows_up_as_rising_trend_not_only_as_level():
    f = features(sweep(10), use_trend=True)
    # the scan adds one port per stride: the slope sees it from the 5th window on
    assert (f["uniq_dst_port_slope_5"].iloc[6:18] > 0).all()
    assert (f["uniq_dst_port_delta"].iloc[1:18] > 0).all()


# --- inference reads the switches off the checkpoint's feature names -----------------------------


def test_flags_round_trip_through_feature_names():
    assert feature_flags_from_names(V1_COLUMNS) == {"use_trend": False, "host_slots": 0}
    v2 = [*V1_COLUMNS, *trend_feature_names()]
    assert feature_flags_from_names(v2) == {"use_trend": True, "host_slots": 0}
    both = features(sweep(3), use_trend=True, host_slots=2).columns
    assert feature_flags_from_names(both) == {"use_trend": True, "host_slots": 2}


def test_a_checkpoint_built_with_other_trend_constants_fails_loudly():
    stale = [*V1_COLUMNS, "uniq_dst_port_delta", "uniq_dst_port_slope_2"]  # a D-024-era name set
    with pytest.raises(ValueError):
        feature_flags_from_names(stale)


def test_a_checkpoint_with_a_partial_host_schema_fails_loudly():
    with pytest.raises(ValueError):
        feature_flags_from_names([*V1_COLUMNS, *host_feature_names(2)[:-1]])


# --- S-2: the per-host channel (D-027) ----------------------------------------------------------


def host(src, dst, t, port=80, sent=100, received=100):
    return {"t": t, "src_ip": src, "dst_ip": dst, "dst_port": port, "fwd_bytes": sent, "bwd_bytes": received,
            "fwd_pkts": 1, "bwd_pkts": 1}


A, B, C = "192.168.10.5", "192.168.10.8", "192.168.10.50"  # internal hosts
EXT = "205.174.165.73"  # an outside source - never gets a slot


def test_host_channel_appends_slot_major_columns_after_v1():
    f = features([host(A, B, 10)], host_slots=3)
    assert tuple(f.columns[:70]) == V1_COLUMNS
    assert list(f.columns[70:]) == host_feature_names(3)
    assert host_feature_names(1) == [f"host1_{x}" for x in HOST_FEATURES]
    assert f.dtypes.eq(np.float32).all()
    assert not f.columns.str.startswith(("stage_", "hazard_k", "attack_k", "escalate_k")).any()


def test_slots_rank_internal_hosts_by_flows_and_skip_outside_sources():
    rows = [host(A, B, 5)] + [host(C, B, 5 + i, port=i) for i in range(3)] + [host(EXT, B, 5 + i) for i in range(9)]
    f = features(rows, host_slots=3).iloc[0]
    assert f["host1_ports"] == 3  # C: 3 flows, 3 ports - the busiest *internal* host
    assert f["host2_ports"] == 1  # A: 1 flow
    assert f["host3_fanout"] == 0  # EXT had 9 flows but is outside - its slot stays empty


def test_fanout_ports_and_byte_asymmetry_per_host():
    rows = [host(A, d, 5, port=p, sent=900, received=0) for d, p in ((B, 22), (C, 22), ("192.168.10.9", 445))]
    f = features(rows, host_slots=1).iloc[0]
    assert (f["host1_fanout"], f["host1_ports"]) == (3, 2)
    assert f["host1_byte_asym"] == pytest.approx(2700 / 2701)  # pushes, never receives
    quiet = features([host(A, B, 5, sent=0, received=0)], host_slots=1).iloc[0]
    assert -1 < quiet["host1_byte_asym"] <= 0 < quiet["host1_fanout"]


def test_new_peer_rate_counts_first_contacts_within_the_capture():
    rows = [host(A, B, 5), host(A, B, 125), host(A, C, 125), host(A, B, 245)]
    f = features(rows, host_slots=1)["host1_new_peer_rate"]
    # windows are 60 s long at a 30 s stride, so a flow at 125 s sits in windows 3 and 4
    assert f.iloc[0] == 1.0  # first sight of B
    assert f.iloc[3] == 0.5  # B again, C for the first time
    assert f.iloc[4] == 0.0  # the same two peers, one window later
    assert f.iloc[7] == 0.0  # B, long known


def test_host_channel_never_sees_the_future():
    rows = [host(A, B, 5), host(A, C, 65), host(B, C, 95)]
    later = rows + [host(A, f"192.168.10.{i}", 400 + i, port=i) for i in range(60, 90)]  # a sweep at 400 s
    before = features(rows, n_windows=20, host_slots=2)
    after = features(later, n_windows=20, host_slots=2)
    early = [c for c in before.columns if c.startswith("host")]
    pd.testing.assert_frame_equal(before.loc[:11, early], after.loc[:11, early])


def test_a_capture_with_no_internal_sources_gets_empty_slots():
    f = features([host(EXT, B, 5)], host_slots=2)
    assert (f[host_feature_names(2)] == 0).all().all()
