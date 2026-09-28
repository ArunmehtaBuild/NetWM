"""N-8 / D-041: ``pos_mode="window"`` makes a window's score independent of the capture's length, and a
stream scored chunk by chunk (state carried) equal to the same stream scored in one pass."""

from dataclasses import replace

import numpy as np
import pytest
import torch

from netwm.models.world_model import NetWorldModel, WorldModelConfig

CFG = WorldModelConfig(n_features=12, embed_dim=32, hidden_dim=32, latent_dim=8, context_len=4,
                       n_heads=2, horizon_k=4, pos_mode="window")
KEYS = ("p_max", "p_cum", "p_raw", "p_cum_attack", "risk_now", "stage_now", "stage_future", "surprise",
        "attention")


def _model(cfg=CFG, seed=0):
    torch.manual_seed(seed)
    return NetWorldModel(cfg).eval()


def _chunked(model, x, sizes):
    parts, carry, start = [], None, 0
    for n in sizes:
        out = model.forecast(x[:, start:start + n], sample=False, carry=carry, return_carry=True)
        carry = out.pop("carry")
        parts.append(out)
        start += n
    assert start == x.shape[1]
    return {k: torch.cat([p[k] for p in parts]) for k in KEYS}


@pytest.mark.parametrize("hazard", ["direct", "factorized"])
def test_chunked_with_carry_equals_one_pass(hazard):
    model = _model(replace(CFG, hazard=hazard))
    x = torch.randn(1, 37, CFG.n_features)
    full = model.forecast(x, sample=False)
    # chunks shorter than, equal to and longer than the context, including single windows
    for sizes in ([37], [1] * 37, [3, 4, 5, 25], [16, 21], [2, 1, 30, 4]):
        got = _chunked(model, x, sizes)
        for k in KEYS:
            np.testing.assert_allclose(got[k].numpy(), full[k].numpy(), rtol=1e-5, atol=1e-6, err_msg=f"{k} {sizes}")


def test_score_does_not_depend_on_what_follows():
    """The N-8 defect: under 'interp' a prefix scores differently from the same windows in a longer input."""
    x = torch.randn(1, 60, CFG.n_features)
    window = _model()
    full = window.forecast(x, sample=False)["p_max"]
    for cut in (1, 3, 4, 17, 59):
        np.testing.assert_allclose(window.forecast(x[:, :cut], sample=False)["p_max"].numpy(),
                                   full[:cut].numpy(), rtol=1e-5, atol=1e-6)
    interp = _model(replace(CFG, pos_mode="interp"))
    part = interp.forecast(x[:, :30], sample=False)["p_max"]
    assert not np.allclose(part.numpy(), interp.forecast(x, sample=False)["p_max"][:30].numpy(), atol=1e-6)


def test_context_sees_only_its_own_window():
    model = _model()
    e = torch.randn(1, 20, CFG.embed_dim)
    e2 = e.clone()
    e2[:, :5] += 3.0                              # change windows 0-4 only
    a, attn = model.context(e)
    b, _ = model.context(e2)
    L = CFG.context_len
    assert attn.shape == (1, 20, L)
    assert torch.allclose(a[:, 5 + L - 1:], b[:, 5 + L - 1:], atol=1e-6)   # out of every later window's reach
    assert not torch.allclose(a[:, 4], b[:, 4])
    # before the stream starts there is nothing to attend to: those slots get no weight
    assert attn[0, 0, : L - 1].abs().sum() == 0 and torch.isclose(attn[0, 0, -1], torch.tensor(1.0))


def test_window_mode_trains():
    model = NetWorldModel(CFG)
    x = torch.randn(2, 24, CFG.n_features)
    losses = model.losses(x, torch.randint(0, 7, (2, 24)), torch.randint(0, 2, (2, 24, CFG.n_risk)).float())
    total = sum(v for k, v in losses.items() if k != "kl_raw")
    assert torch.isfinite(total)
    total.backward()
    assert model.context.pos.grad is not None and torch.isfinite(model.context.pos.grad).all()


def test_interp_refuses_a_carry():
    model = _model(replace(CFG, pos_mode="interp"))
    x = torch.randn(1, 8, CFG.n_features)
    with pytest.raises(ValueError, match="pos_mode='window'"):
        model.observe(x, carry={"state": None, "embeds": None, "valid": None})


def test_old_checkpoints_default_to_interp():
    """A checkpoint saved before D-041 has no pos_mode key and must load with the behaviour it was trained with."""
    saved = replace(CFG, pos_mode="interp").as_dict()
    saved.pop("pos_mode")
    assert WorldModelConfig(**saved).pos_mode == "interp"
