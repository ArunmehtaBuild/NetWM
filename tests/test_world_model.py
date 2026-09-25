from dataclasses import replace

import torch

from netwm.models.world_model import NetWorldModel, WorldModelConfig

CFG = WorldModelConfig(n_features=12, embed_dim=32, hidden_dim=32, latent_dim=8, context_len=4,
                       n_heads=2, horizon_k=4)
CFG5 = replace(CFG, n_risk=5)   # round 3: + onset_now, + precursor


def test_attention_is_causal_and_range_limited():
    model = NetWorldModel(CFG)
    out = model.observe(torch.randn(1, 10, CFG.n_features))
    attn = out["attention"][0]
    assert torch.allclose(attn.triu(1), torch.zeros_like(attn))          # no peeking ahead
    assert attn[8, :5].abs().sum() == 0                                  # limited to context_len


def test_imagination_needs_no_observations_and_is_stochastic():
    model = NetWorldModel(CFG).eval()   # dropout off: the only randomness left is the latent sample
    out = model.observe(torch.randn(1, 8, CFG.n_features))
    a = model.imagine(out["posts"][-1], out["embeds"], horizon=4)
    b = model.imagine(out["posts"][-1], out["embeds"], horizon=4)
    assert a["decoded"].shape == (1, 4, CFG.n_features)
    assert not torch.allclose(a["decoded"], b["decoded"])                # sampled, not deterministic
    det_a = model.imagine(out["posts"][-1], out["embeds"], horizon=4, sample=False)
    det_b = model.imagine(out["posts"][-1], out["embeds"], horizon=4, sample=False)
    assert torch.allclose(det_a["decoded"], det_b["decoded"])


def test_cumulative_forecast_is_monotone_and_bounded():
    model = NetWorldModel(CFG)
    out = model.forecast(torch.randn(1, 20, CFG.n_features), n_samples=4)
    assert out["attention"].shape == (20, CFG.context_len)
    assert out["p_cum_escalate"].shape == out["p_cum"].shape
    p = out["p_cum"]
    assert p.shape == (20, CFG.horizon_k)
    assert (p.diff(dim=1) >= -1e-6).all()                                # P(within k) cannot fall
    assert (p >= 0).all() and (p <= 1).all()
    assert (out["p_lo"] <= out["p_hi"] + 1e-6).all()


def test_losses_are_finite_and_differentiable():
    model = NetWorldModel(CFG)
    x = torch.randn(2, 24, CFG.n_features)
    risk = torch.randint(0, 2, (2, 24, CFG.n_risk)).float()
    losses = model.losses(x, torch.randint(0, 7, (2, 24)), risk)
    total = sum(v for k, v in losses.items() if k != "kl_raw")
    assert torch.isfinite(total)
    total.backward()
    assert any(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


def test_free_bits_floor_applies_to_kl():
    model = NetWorldModel(CFG)
    losses = model.losses(torch.randn(1, 12, CFG.n_features), torch.zeros(1, 12, dtype=torch.long),
                          torch.zeros(1, 12, CFG.n_risk))
    assert losses["kl"] >= CFG.free_nats - 1e-6


def _losses_with(model, risk, seed=0):
    torch.manual_seed(seed)   # observe() samples the posterior, so pin the stream
    x = torch.randn(2, 24, CFG5.n_features)
    return model.losses(x, torch.randint(0, 7, (2, 24)), risk, pos_weight=torch.rand(5) + 0.5)


def test_the_new_channels_cannot_move_the_round_two_loss_terms():
    # BCE is mean-reduced over every element, so a single term spanning five channels would rescale
    # the compromise gradient by 3/5 and confound every comparison against E14.
    torch.manual_seed(0)
    model = NetWorldModel(CFG5)
    risk = torch.randint(0, 2, (2, 24, 5)).float()
    other = risk.clone()
    other[..., 3:] = 1 - other[..., 3:]          # flip only onset_now and precursor
    a, b = _losses_with(model, risk), _losses_with(model, other)
    assert torch.equal(a["compromise"], b["compromise"])
    assert torch.equal(a["imagine_compromise"], b["imagine_compromise"])
    assert not torch.equal(a["precursor"], b["precursor"])


def test_precursor_terms_are_inert_at_the_round_two_width():
    losses = NetWorldModel(CFG).losses(
        torch.randn(1, 24, CFG.n_features), torch.zeros(1, 24, dtype=torch.long),
        torch.zeros(1, 24, CFG.n_risk),
    )
    # an empty channel slice would make BCE a mean over no elements, i.e. NaN that trains to nothing
    assert losses["precursor"] == 0 and torch.isfinite(losses["precursor"])
    assert losses["imagine_precursor"] == 0 and torch.isfinite(losses["imagine_precursor"])


def test_the_precursor_channel_is_never_derived_from_a_rollout():
    out = NetWorldModel(CFG5).forecast(torch.randn(1, 20, CFG5.n_features), n_samples=4)
    assert out["p_onset_cum"].shape == (20, CFG5.horizon_k)     # onset_now may be unioned
    assert out["risk_now"].shape == (20, 5)                     # precursor is filtered-state only
    assert not any("precursor" in k for k in out)
    p = out["p_onset_cum"]
    assert (p.diff(dim=1) >= -1e-6).all() and (p >= 0).all() and (p <= 1).all()


def test_the_mean_path_forecast_has_no_monte_carlo_variance():
    model = NetWorldModel(CFG5)
    x = torch.randn(1, 20, CFG5.n_features)
    a = model.forecast(x, n_samples=8, sample=False)
    b = model.forecast(x, n_samples=8, sample=False)
    assert torch.allclose(a["p_max"], b["p_max"])
    assert torch.allclose(a["p_lo"], a["p_hi"])          # one path, so the band collapses
    assert not torch.allclose(a["p_max"], model.forecast(x, n_samples=8)["p_max"])
