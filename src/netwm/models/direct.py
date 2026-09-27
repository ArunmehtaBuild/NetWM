"""Model A for E24 (D-035): the same encoder and causal attention, no latent dynamics.

The question E24 asks is whether the world model's latent transition earns *lead time*, or only
reconstruction. Model A shares everything with the RSSM up to the attention context - observation
encoder, causal limited-range attention, the same width - and then predicts each risk channel
"within the next K windows" directly from that context. No GRU, no stochastic latent, no decoder, no
imagination.

It exposes the RSSM's training and forecasting interface (``losses``, ``curriculum_loss``,
``forecast``), so ``train.py``, ``evaluate.py`` and the scorecard run it unchanged. Its ``p_max`` is
the within-K probability itself, which is what the RSSM's max-over-horizon approximates.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from netwm.models.world_model import (
    BASE_CHANNELS,
    CausalContext,
    NetWorldModel,
    ObservationEncoder,
    WorldModelConfig,
)


def within_k(risk: torch.Tensor, horizon: int) -> tuple[torch.Tensor, torch.Tensor]:
    """``target[:, t] = max(risk[:, t+1 .. t+horizon])`` and a mask of the steps with a full future.

    Matches the RSSM's ``p_max``, which is the max over imagined steps 1..K of a state property.
    """
    b, t, c = risk.shape
    target = torch.zeros_like(risk)
    for k in range(1, horizon + 1):
        if k < t:
            target[:, : t - k] = torch.maximum(target[:, : t - k], risk[:, k:])
    mask = torch.zeros(t, dtype=torch.bool, device=risk.device)
    mask[: max(0, t - horizon)] = True
    return target, mask


class DirectForecaster(nn.Module):
    def __init__(self, cfg: WorldModelConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.encoder = ObservationEncoder(cfg)
        self.context = CausalContext(cfg)
        self.risk_head = nn.Sequential(
            nn.Linear(cfg.embed_dim, cfg.embed_dim), nn.SiLU(), nn.Linear(cfg.embed_dim, cfg.n_risk)
        )
        self.stage_head = nn.Sequential(
            nn.Linear(cfg.embed_dim, cfg.embed_dim), nn.SiLU(), nn.Linear(cfg.embed_dim, cfg.n_stages)
        )
        if cfg.hazard == "factorized":
            # P(compromise within K | hostile within K): the factorised target's second factor (E22),
            # in within-K form
            self.cond_head = nn.Sequential(
                nn.Linear(cfg.embed_dim, cfg.embed_dim), nn.SiLU(), nn.Linear(cfg.embed_dim, 1)
            )

    def _heads(self, ctx: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        logits = self.risk_head(ctx)
        if self.cfg.hazard == "factorized":
            p = (torch.sigmoid(logits[..., 1]) * torch.sigmoid(self.cond_head(ctx)[..., 0])).clamp(1e-6, 1 - 1e-6)
            logits = torch.cat([torch.logit(p).unsqueeze(-1), logits[..., 1:]], dim=-1)
        return logits, self.stage_head(ctx)

    def _context(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.context(self.encoder(x))

    def losses(self, x, stage, risk, horizon=None, imagine_every=4, stage_weight=None, pos_weight=None):
        cfg = self.cfg
        horizon = horizon or cfg.horizon_k
        ctx, _ = self._context(x)
        logits, stage_logits = self._heads(ctx)
        base = min(BASE_CHANNELS, cfg.n_risk)
        target, mask = within_k(risk[..., :base], horizon)
        zero = x.new_zeros(())
        comp = (F.binary_cross_entropy_with_logits(
            logits[:, mask, :base], target[:, mask],
            pos_weight=None if pos_weight is None else pos_weight[:base]) if bool(mask.any()) else zero)
        stage_loss = F.cross_entropy(stage_logits.reshape(-1, cfg.n_stages), stage.reshape(-1), weight=stage_weight)
        out = {
            "recon": zero, "kl": zero, "kl_raw": zero, "stage": stage_loss, "compromise": comp,
            "imagine_compromise": zero, "imagine_stage": zero, "imagine_recon": zero,
            "precursor": zero, "imagine_precursor": zero,
        }
        if cfg.hazard == "factorized":
            # train the conditional factor where something hostile does happen within K
            hostile = (target[..., 1] > 0) & mask[None, :]
            out["hostile_stage"] = (F.binary_cross_entropy_with_logits(
                self.cond_head(ctx)[..., 0][hostile], target[..., 0][hostile]) if bool(hostile.any()) else zero)
        return out

    def curriculum_loss(self, x, stage, risk, start, horizon, stage_weight=None, pos_weight=None):
        """E23 for Model A: the within-K prediction made at the history's last window, nothing imagined."""
        cfg = self.cfg
        ctx, _ = self._context(x[:, : start + 1])
        logits, _ = self._heads(ctx[:, -1])
        base = min(BASE_CHANNELS, cfg.n_risk)
        future = risk[:, start + 1 : start + 1 + cfg.horizon_k, :base]
        target = future.max(dim=1).values
        bce = F.binary_cross_entropy_with_logits(
            logits[:, :base], target, pos_weight=None if pos_weight is None else pos_weight[:base])
        return {"curriculum": 3.0 * bce}

    @torch.no_grad()
    def forecast(self, x, horizon=None, n_samples=16, chunk=64, sample=True):
        """The RSSM's forecast keys, filled from the direct heads (no Monte-Carlo: one path)."""
        cfg = self.cfg
        horizon = horizon or cfg.horizon_k
        self.eval()
        ctx, attention = self._context(x)
        logits, stage_logits = self._heads(ctx)
        p = torch.sigmoid(logits)[0].cpu()                     # (T, n_risk) within K
        t = p.shape[0]
        p_raw = p[:, None, :].expand(t, horizon, cfg.n_risk).clone()
        stage_now = F.softmax(stage_logits, dim=-1)[0].cpu()
        return {
            "p_cum": p_raw[..., 0],
            "p_raw": p_raw,
            "p_max": p[:, 0],
            "p_lo": p_raw[..., 0],
            "p_hi": p_raw[..., 0],
            "p_step": torch.cat([p_raw[:, :1, 0], torch.zeros(t, horizon - 1)], dim=1),
            "p_cum_attack": p_raw[..., 1] if cfg.n_risk > 1 else p_raw[..., 0],
            "p_cum_escalate": p_raw[..., 2] if cfg.n_risk > 2 else p_raw[..., 0],
            "risk_now": p,
            "stage_now": stage_now,
            "stage_future": stage_now[:, None, :].expand(t, horizon, cfg.n_stages).clone(),
            "surprise": torch.zeros(t),
            "attention": NetWorldModel._history_attention(attention[0], cfg.context_len).cpu(),
        }
