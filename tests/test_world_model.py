import torch

from netwm.models.world_model import NetWorldModel, WorldModelConfig

CFG = WorldModelConfig(n_features=12, embed_dim=32, hidden_dim=32, latent_dim=8, context_len=4,
                       n_heads=2, horizon_k=4)


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
    p = out["p_cum"]
    assert p.shape == (20, CFG.horizon_k)
    assert (p.diff(dim=1) >= -1e-6).all()                                # P(within k) cannot fall
    assert (p >= 0).all() and (p <= 1).all()
    assert (out["p_lo"] <= out["p_hi"] + 1e-6).all()


def test_losses_are_finite_and_differentiable():
    model = NetWorldModel(CFG)
    x = torch.randn(2, 24, CFG.n_features)
    losses = model.losses(x, torch.randint(0, 7, (2, 24)), torch.randint(0, 2, (2, 24)).float())
    total = sum(v for k, v in losses.items() if k != "kl_raw")
    assert torch.isfinite(total)
    total.backward()
    assert any(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())


def test_free_bits_floor_applies_to_kl():
    model = NetWorldModel(CFG)
    losses = model.losses(torch.randn(1, 12, CFG.n_features), torch.zeros(1, 12, dtype=torch.long),
                          torch.zeros(1, 12))
    assert losses["kl"] >= CFG.free_nats - 1e-6
