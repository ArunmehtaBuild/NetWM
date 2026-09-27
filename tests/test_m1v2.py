"""D-035 machinery: the new feature blocks, the relative representation, the factorised hazard,
the precursor curriculum and Model A. Each test pins the property the experiment relies on."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from netwm.features.flow_features import (
    HOST_RELATIVE_FEATURES,
    PACKET_CSV_FEATURES,
    feature_flags_from_names,
    window_features,
)
from netwm.features.scaler import RELATIVE_VIEWS, StateScaler
from netwm.features.windowing import WindowSpec, expand_to_windows
from netwm.models.direct import DirectForecaster, within_k
from netwm.models.world_model import WorldModelConfig, build_model
from netwm.train import CurriculumSequences

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _flows(n_min: int = 40, seed: int = 0) -> pd.DataFrame:
    """Synthetic canonical flows: steady internal chatter, then host .8 starts sweeping at minute 30."""
    rng = np.random.default_rng(seed)
    rows = []
    t0 = pd.Timestamp("2017-07-06 12:00:00")
    for m in range(n_min):
        for i in range(30):
            src = f"192.168.10.{rng.integers(3, 8)}"
            rows.append(dict(ts=t0 + pd.Timedelta(seconds=60 * m + 2 * i), src_ip=src, dst_ip="192.168.10.50",
                             src_port=40000 + i, dst_port=int(rng.choice([80, 443, 53])), protocol=6))
        if m >= 30:  # the sweep: many new peers and ports from one host
            for j in range(40):
                rows.append(dict(ts=t0 + pd.Timedelta(seconds=60 * m + j), src_ip="192.168.10.8",
                                 dst_ip=f"192.168.10.{100 + j % 20}", src_port=50000 + j,
                                 dst_port=1000 + 40 * (m - 30) + j, protocol=6))
    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    n = len(df)
    for c in ("duration_us", "fwd_pkts", "bwd_pkts", "fwd_bytes", "bwd_bytes", "flow_iat_mean", "flow_iat_std",
              "flow_iat_max", "flow_iat_min", "fin_cnt", "syn_cnt", "rst_cnt", "psh_cnt", "ack_cnt", "urg_cnt",
              "cwr_cnt", "ece_cnt", "pkt_len_min", "pkt_len_max", "pkt_len_mean", "pkt_len_std", "down_up_ratio",
              "fwd_init_win", "bwd_init_win", "fwd_seg_size_min", "active_mean", "idle_mean"):
        df[c] = rng.integers(1, 100, n).astype(float)
    df["syn_cnt"] = 1.0
    df["fwd_init_win"] = np.where(df["src_ip"] == "192.168.10.8", 1024.0, 29200.0)
    return df


def _features(df, **kw):
    spec = WindowSpec(60, 30)
    exp, _ = expand_to_windows(df, spec)
    return window_features(exp, 60, ("192.168.10.",), n_windows=int(exp["w"].max()) + 1, **kw)


def test_packet_block_has_its_columns_and_works_without_packet_columns():
    feats = _features(_flows(), use_packet_csv=True)
    assert list(feats.columns[-len(PACKET_CSV_FEATURES):]) == list(PACKET_CSV_FEATURES)
    assert np.isfinite(feats[list(PACKET_CSV_FEATURES)].to_numpy()).all()
    hist = feats[[c for c in PACKET_CSV_FEATURES if c.startswith("pkt_payload_")]].sum(axis=1)
    assert np.allclose(hist[feats["n_flows"] > 0], 1.0)  # the payload histogram is a distribution


def test_host_relative_block_is_causal_and_sees_the_sweep():
    df = _flows()
    base = _features(df, use_host_relative=True)[list(HOST_RELATIVE_FEATURES)]
    # rewriting everything after minute 20 must leave the windows before it untouched
    later = df[df["ts"] >= pd.Timestamp("2017-07-06 12:20:00")].index
    changed = df.copy()
    changed.loc[later, "dst_port"] = 9999
    other = _features(changed, use_host_relative=True)[list(HOST_RELATIVE_FEATURES)]
    cut = 38  # windows starting before 12:19 cover only earlier flows
    assert np.array_equal(base.iloc[:cut].to_numpy(), other.iloc[:cut].to_numpy())
    # the sweep (from minute 30, window 60) opens new ports far beyond anything seen before
    assert base["hostrel_new_ports_max"].iloc[62:].max() > 10 * max(1.0, base["hostrel_new_ports_max"].iloc[20:58].max())


def test_inference_rebuilds_the_blocks_from_names():
    names = ["n_flows", *PACKET_CSV_FEATURES, *HOST_RELATIVE_FEATURES]
    flags = feature_flags_from_names(names)
    assert flags["use_packet_csv"] and flags["use_host_relative"]
    with pytest.raises(ValueError):
        feature_flags_from_names(["n_flows", PACKET_CSV_FEATURES[0]])


def test_relative_scaler_is_causal_and_names_its_views():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(rng.random((300, 3)) * 10, columns=list("abc"))
    s = StateScaler(mode="relative", rank_window=120).fit(df)
    x = s.transform(df)
    assert x.shape == (300, 3 * len(RELATIVE_VIEWS)) and s.n_outputs == x.shape[1]
    assert s.output_names()[:4] == ["a", "b", "c", "a@rank"]
    later = df.copy()
    later.iloc[200:] = 99.0
    assert np.array_equal(x[:200], s.transform(later)[:200])
    with pytest.raises(ValueError):
        StateScaler(mode="relative").fit(df)  # a whole-capture rank would not be causal


def _batch(cfg, t=40, b=2):
    torch.manual_seed(0)
    x = torch.randn(b, t, cfg.n_features)
    stage = torch.zeros(b, t, dtype=torch.long)
    stage[:, 25:] = 3
    risk = torch.zeros(b, t, cfg.n_risk)
    risk[:, 25:, 0] = 1
    risk[:, 20:, 1] = 1
    return x, stage, risk


def test_factorised_hazard_is_threat_times_conditional():
    cfg = WorldModelConfig(n_features=6, hazard="factorized", context_len=8, embed_dim=16, hidden_dim=16, latent_dim=4)
    model = build_model(cfg)
    feat = torch.randn(5, cfg.hidden_dim + cfg.latent_dim)
    logits = model._risk_logits(feat)
    q = torch.softmax(model.hostile_head(feat), -1)[:, [2, 3, 4]].sum(-1)
    assert torch.allclose(torch.sigmoid(logits[:, 0]), (torch.sigmoid(logits[:, 1]) * q).clamp(1e-6, 1 - 1e-6), atol=1e-5)
    losses = model.losses(*_batch(cfg), horizon=4)
    assert "hostile_stage" in losses and torch.isfinite(losses["hostile_stage"])


def test_curriculum_items_end_before_the_onset():
    x = np.arange(100, dtype=np.float32)[:, None].repeat(3, 1)
    day = {"x": x, "stage": np.zeros(100, int), "risk": np.zeros((100, 3), np.float32), "attack_onsets": [60, 95]}
    cur = CurriculumSequences({"d": day}, offsets=[20, 4], history=16, horizon=20)
    # onset 60: histories end at 40 and 56. Onset 95: the offset-20 history ends at 75 and its
    # 20-window future fits; the offset-4 one (ending at 91) would run past the day, so it is skipped
    ends = sorted(int(item[0][15, 0]) for item in cur.items)
    assert ends == [40, 56, 75] and all(len(item[0]) == 36 for item in cur.items)
    cfg = WorldModelConfig(n_features=3, context_len=8, embed_dim=16, hidden_dim=16, latent_dim=4)
    loss = build_model(cfg).curriculum_loss(*_batch(cfg, t=36), start=15, horizon=20)["curriculum"]
    assert torch.isfinite(loss)


def test_model_a_has_no_dynamics_and_predicts_within_k():
    cfg = WorldModelConfig(n_features=6, arch="direct", context_len=8, embed_dim=16)
    model = build_model(cfg)
    assert isinstance(model, DirectForecaster) and not hasattr(model, "imagine")
    x, stage, risk = _batch(cfg)
    target, mask = within_k(risk, 4)
    assert target[0, 20, 0] == 0 and target[0, 21, 0] == 1  # compromise from 25: in reach from 21
    assert mask.sum() == 36
    losses = model.losses(x, stage, risk, horizon=4)
    assert torch.isfinite(losses["compromise"]) and float(losses["recon"]) == 0.0
    out = model.forecast(x[:1], horizon=4)
    assert out["p_max"].shape == (40,) and out["p_raw"].shape == (40, 4, cfg.n_risk)


def test_feature_blocks_are_selected_by_name_not_prefix():
    from train import select_features

    names = ["pkt_len_mean_mean", "n_flows", *PACKET_CSV_FEATURES, *HOST_RELATIVE_FEATURES]
    kept = select_features(names, {"exclude_blocks": ["packet_csv", "host_relative"]})
    assert kept == ["pkt_len_mean_mean", "n_flows"]  # the v1 pkt_len_* column survives
