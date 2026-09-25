"""NetWM - a latent world model of network state dynamics (decisions.md D-004).

The model is an RSSM in the PlaNet/Dreamer sense, adapted to traffic telemetry:

    e_t          = Encoder(S_t)                          observation embedding
    c_t          = CausalAttention(e_{t-L+1..t})         short-range context (+ the attention
                                                          weights we surface as explanation)
    h_t          = GRU(h_{t-1}, [z_{t-1}, c_t])          deterministic path
    p(z_t|h_t)                                            prior     - what the model expects
    q(z_t|h_t,e_t)                                        posterior - what it sees
    S_hat_{t+1}  = Decoder(h_t, z_t)                      next-state prediction (-> surprise)
    stage, compromise heads on [h_t, z_t]

Forecasting is *imagination*: from the posterior state at time t we roll the prior forward K steps
without observations, decoding each imagined state so the next step has something to encode. The
compromise head read off each imagined state gives a per-step hazard, and the cumulative product
gives P(compromise within k). Sampling N trajectories gives the uncertainty band.

Everything is small on purpose: the training box is a 4 GB GTX 1650.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class WorldModelConfig:
    n_features: int = 70
    n_stages: int = 7
    # [compromise, attack, escalation] read off a state (D-016), optionally followed by
    # [onset_now, precursor] for round 3 (D-023). The default stays 3 so every round-2 checkpoint
    # and the E14 reproduction path are untouched; round 3 sets n_risk=5 from its own config.
    n_risk: int = 3
    embed_dim: int = 128
    hidden_dim: int = 192          # deterministic GRU state
    latent_dim: int = 32           # stochastic state
    context_len: int = 16          # windows visible to the attention encoder (8 min at 30 s stride)
    n_heads: int = 4
    n_layers: int = 2
    dropout: float = 0.1
    min_std: float = 0.1
    free_nats: float = 1.0         # KL free bits, per Dreamer - stops posterior collapse
    horizon_k: int = 10
    obs_logvar_init: float = 0.0

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


#: The D-016 triple [compromise, attack, escalation], as an exclusive upper bound on the channel
#: index. Kept as its own loss term so its value is identical to round 2 whatever n_risk becomes.
BASE_CHANNELS = 3

#: Channels that may be read off an *imagined* state and unioned over a rollout. Channels 0-2 are
#: state properties; channel 3 (``onset_now``) is a first-occurrence indicator, so for all four
#: ``1 - prod(1 - p_k)`` answers a real question. Channel 4 (``precursor``) is already a statement
#: about the next K windows, so unioning it over a rollout would ask about a horizon of up to 2K.
#: It is supervised and read on the filtered state only, and never leaves this file via a
#: rollout-derived key (D-023).
IMAGINED_CHANNELS = 4


class ObservationEncoder(nn.Module):
    def __init__(self, cfg: WorldModelConfig) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(cfg.n_features, cfg.embed_dim),
            nn.LayerNorm(cfg.embed_dim),
            nn.SiLU(),
            nn.Linear(cfg.embed_dim, cfg.embed_dim),
            nn.SiLU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class CausalContext(nn.Module):
    """Transformer encoder over the last ``context_len`` window embeddings.

    Returns the context vector for every timestep and the attention weights of each query over its
    own history. Those weights are half of the explanation the PS asks for: *when* did the evidence
    the model is reacting to actually happen.
    """

    def __init__(self, cfg: WorldModelConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.pos = nn.Parameter(torch.zeros(1, cfg.context_len, cfg.embed_dim))
        nn.init.trunc_normal_(self.pos, std=0.02)
        self.attn = nn.MultiheadAttention(
            cfg.embed_dim, cfg.n_heads, dropout=cfg.dropout, batch_first=True
        )
        self.norm1 = nn.LayerNorm(cfg.embed_dim)
        self.norm2 = nn.LayerNorm(cfg.embed_dim)
        self.ff = nn.Sequential(
            nn.Linear(cfg.embed_dim, 2 * cfg.embed_dim),
            nn.SiLU(),
            nn.Linear(2 * cfg.embed_dim, cfg.embed_dim),
        )

    def forward(self, embeds: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """embeds: (B, T, E) -> context (B, T, E), attention (B, T, T) averaged over heads."""
        b, t, _ = embeds.shape
        pos = self.pos[:, :t] if t <= self.cfg.context_len else F.interpolate(
            self.pos.transpose(1, 2), size=t, mode="linear", align_corners=False
        ).transpose(1, 2)
        x = self.norm1(embeds + pos)

        # causal + limited-range mask: a window may attend to itself and the previous context_len-1
        # windows, never to the future.
        idx = torch.arange(t, device=embeds.device)
        distance = idx[:, None] - idx[None, :]
        mask = (distance < 0) | (distance >= self.cfg.context_len)

        attended, weights = self.attn(x, x, x, attn_mask=mask, need_weights=True, average_attn_weights=True)
        h = embeds + attended
        return h + self.ff(self.norm2(h)), weights


class GaussianHead(nn.Module):
    """Diagonal Gaussian parameterisation shared by prior, posterior and decoder."""

    def __init__(self, in_dim: int, out_dim: int, hidden: int, min_std: float) -> None:
        super().__init__()
        self.min_std = min_std
        self.net = nn.Sequential(nn.Linear(in_dim, hidden), nn.SiLU(), nn.Linear(hidden, 2 * out_dim))

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        mean, std = self.net(x).chunk(2, dim=-1)
        return mean, F.softplus(std) + self.min_std


@dataclass
class RSSMState:
    h: torch.Tensor           # deterministic
    z: torch.Tensor           # sampled stochastic state
    mean: torch.Tensor
    std: torch.Tensor

    def feat(self) -> torch.Tensor:
        return torch.cat([self.h, self.z], dim=-1)

    def detach(self) -> "RSSMState":
        return RSSMState(self.h.detach(), self.z.detach(), self.mean.detach(), self.std.detach())


class NetWorldModel(nn.Module):
    """The world model: dynamics first, prediction heads second."""

    def __init__(self, cfg: WorldModelConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.encoder = ObservationEncoder(cfg)
        self.context = CausalContext(cfg)
        self.cell = nn.GRUCell(cfg.latent_dim + cfg.embed_dim, cfg.hidden_dim)

        feat_dim = cfg.hidden_dim + cfg.latent_dim
        self.prior = GaussianHead(cfg.hidden_dim, cfg.latent_dim, cfg.hidden_dim, cfg.min_std)
        self.posterior = GaussianHead(
            cfg.hidden_dim + cfg.embed_dim, cfg.latent_dim, cfg.hidden_dim, cfg.min_std
        )
        self.decoder = nn.Sequential(
            nn.Linear(feat_dim, cfg.embed_dim), nn.SiLU(), nn.Linear(cfg.embed_dim, cfg.n_features)
        )
        self.obs_logvar = nn.Parameter(torch.full((cfg.n_features,), cfg.obs_logvar_init))
        self.stage_head = nn.Sequential(
            nn.Linear(feat_dim, cfg.embed_dim), nn.SiLU(), nn.Linear(cfg.embed_dim, cfg.n_stages)
        )
        # One head, three questions about a state: is it compromised, is anything hostile
        # happening, and is it a step up the kill chain. Compromise alone gives the model a single
        # positive family per fold (see results.md, E4-E7 round 1).
        self.risk_head = nn.Sequential(
            nn.Linear(feat_dim, cfg.embed_dim), nn.SiLU(), nn.Linear(cfg.embed_dim, cfg.n_risk)
        )

    # ---- state transitions ------------------------------------------------------------------
    def initial_state(self, batch: int, device: torch.device) -> RSSMState:
        zeros = torch.zeros(batch, self.cfg.hidden_dim, device=device)
        z = torch.zeros(batch, self.cfg.latent_dim, device=device)
        return RSSMState(zeros, z, z.clone(), torch.ones_like(z))

    def _prior_step(self, state: RSSMState, context: torch.Tensor, sample: bool = True) -> RSSMState:
        h = self.cell(torch.cat([state.z, context], dim=-1), state.h)
        mean, std = self.prior(h)
        z = mean + std * torch.randn_like(std) if sample else mean
        return RSSMState(h, z, mean, std)

    def _posterior_step(
        self, prior: RSSMState, embed: torch.Tensor, sample: bool = True
    ) -> RSSMState:
        mean, std = self.posterior(torch.cat([prior.h, embed], dim=-1))
        z = mean + std * torch.randn_like(std) if sample else mean
        return RSSMState(prior.h, z, mean, std)

    # ---- observation (teacher forcing) -------------------------------------------------------
    def observe(self, x: torch.Tensor, sample: bool = True) -> dict:
        """Filter a sequence of observed states. x: (B, T, F).

        ``sample=False`` takes the mean of both the prior and the posterior, giving a fully
        deterministic filtered trajectory. Training always samples; only the mean-path forecast
        turns it off, so that a lead-time count carries no Monte-Carlo variance at all.
        """
        b, t, _ = x.shape
        embeds = self.encoder(x)
        context, attention = self.context(embeds)

        state = self.initial_state(b, x.device)
        posts, priors, buffers = [], [], []
        for i in range(t):
            prior = self._prior_step(state, context[:, i], sample=sample)
            post = self._posterior_step(prior, embeds[:, i], sample=sample)
            posts.append(post)
            priors.append(prior)
            buffers.append(embeds[:, i])
            state = post
        return {
            "posts": posts,
            "priors": priors,
            "embeds": embeds,
            "context": context,
            "attention": attention,
        }

    # ---- imagination (no observations) -------------------------------------------------------
    def imagine(
        self, state: RSSMState, history: torch.Tensor, horizon: int, sample: bool = True
    ) -> dict:
        """Roll the prior forward ``horizon`` steps from ``state``.

        ``history`` is the buffer of the last ``context_len`` observation embeddings (B, L, E). Each
        imagined step decodes a predicted state, re-encodes it and appends it to the buffer, so the
        attention context keeps working exactly as it does during observation - the model dreams in
        the same representation it perceives in.
        """
        buf = history[:, -self.cfg.context_len :]
        states, decoded, risk, stage_logits = [], [], [], []
        for _ in range(horizon):
            ctx, _ = self.context(buf)
            state = self._prior_step(state, ctx[:, -1], sample=sample)
            feat = state.feat()
            obs_hat = self.decoder(feat)
            states.append(state)
            decoded.append(obs_hat)
            risk.append(self.risk_head(feat))
            stage_logits.append(self.stage_head(feat))
            buf = torch.cat([buf[:, 1:], self.encoder(obs_hat).unsqueeze(1)], dim=1)
        risk_logits = torch.stack(risk, dim=1)                       # (B, K, n_risk)
        return {
            "states": states,
            "decoded": torch.stack(decoded, dim=1),
            "risk_logits": risk_logits,
            "compromise_logit": risk_logits[..., 0],
            "stage_logits": torch.stack(stage_logits, dim=1),
        }

    # ---- losses ------------------------------------------------------------------------------
    def _gaussian_nll(self, pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        var = self.obs_logvar.exp()
        return 0.5 * (self.obs_logvar + (pred - target) ** 2 / var).mean()

    def losses(
        self,
        x: torch.Tensor,
        stage: torch.Tensor,
        risk: torch.Tensor,
        horizon: int | None = None,
        imagine_every: int = 4,
        stage_weight: torch.Tensor | None = None,
        pos_weight: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        """All training objectives. x: (B,T,F), stage: (B,T) long, risk: (B,T,n_risk) float."""
        cfg = self.cfg
        horizon = horizon or cfg.horizon_k
        out = self.observe(x)
        feats = torch.stack([p.feat() for p in out["posts"]], dim=1)          # (B,T,D)

        # one-step dynamics: predict the *next* observation from the current posterior state
        recon = self._gaussian_nll(self.decoder(feats[:, :-1]), x[:, 1:])

        kl_terms = []
        for post, prior in zip(out["posts"], out["priors"]):
            kl = torch.distributions.kl_divergence(
                torch.distributions.Normal(post.mean, post.std),
                torch.distributions.Normal(prior.mean, prior.std),
            ).sum(-1)
            kl_terms.append(kl)
        kl = torch.stack(kl_terms, dim=1).mean()
        kl_loss = torch.clamp(kl, min=cfg.free_nats)                          # free bits

        stage_loss = F.cross_entropy(
            self.stage_head(feats).reshape(-1, cfg.n_stages), stage.reshape(-1), weight=stage_weight
        )

        # The D-016 triple and the round-3 precursor family are separate loss terms with separate
        # weights. BCE is mean-reduced over every element, so slicing the first three channels keeps
        # this term *numerically identical* to round 2 - a single term spanning all five channels
        # would quietly rescale the compromise gradient by 3/5 and confound every E14 comparison.
        base = min(BASE_CHANNELS, cfg.n_risk)
        risk_now = self.risk_head(feats)
        comp_loss = F.binary_cross_entropy_with_logits(
            risk_now[..., :base], risk[..., :base],
            pos_weight=None if pos_weight is None else pos_weight[:base],
        )
        # Guarded: BCE over an empty channel slice is a mean of no elements, i.e. NaN.
        prec_loss = x.new_zeros(())
        if cfg.n_risk > base:
            prec_loss = F.binary_cross_entropy_with_logits(
                risk_now[..., base:], risk[..., base:],
                pos_weight=None if pos_weight is None else pos_weight[base:],
            )

        # open-loop: imagine from a subset of start points and supervise the imagined future
        b, t, _ = x.shape
        starts = list(range(cfg.context_len, max(cfg.context_len + 1, t - horizon), imagine_every))
        img_comp = img_stage = img_recon = img_prec = x.new_zeros(())
        if starts:
            for start in starts:
                state = out["posts"][start]
                img = self.imagine(state, out["embeds"][:, : start + 1], horizon)
                target_slice = slice(start + 1, start + 1 + horizon)
                tgt_risk = risk[:, target_slice]
                tgt_stage = stage[:, target_slice]
                tgt_obs = x[:, target_slice]
                k = tgt_risk.shape[1]
                img_comp = img_comp + F.binary_cross_entropy_with_logits(
                    img["risk_logits"][:, :k, :base], tgt_risk[..., :base],
                    pos_weight=None if pos_weight is None else pos_weight[:base],
                )
                if cfg.n_risk > base:
                    # onset_now only. The precursor channel is a statement about the next K windows,
                    # so supervising it on an imagined state asks about a nested horizon - it gets
                    # no gradient here, and forecast() correspondingly never derives it from a
                    # rollout (D-023).
                    img_prec = img_prec + F.binary_cross_entropy_with_logits(
                        img["risk_logits"][:, :k, base:IMAGINED_CHANNELS],
                        tgt_risk[..., base:IMAGINED_CHANNELS],
                        pos_weight=None if pos_weight is None
                        else pos_weight[base:IMAGINED_CHANNELS],
                    )
                img_stage = img_stage + F.cross_entropy(
                    img["stage_logits"][:, :k].reshape(-1, cfg.n_stages),
                    tgt_stage.reshape(-1),
                    weight=stage_weight,
                )
                img_recon = img_recon + F.mse_loss(img["decoded"][:, :k], tgt_obs)
            n = len(starts)
            img_comp, img_stage, img_recon = img_comp / n, img_stage / n, img_recon / n
            img_prec = img_prec / n

        return {
            "recon": recon,
            "kl": kl_loss,
            "kl_raw": kl.detach(),
            "stage": stage_loss,
            "compromise": comp_loss,
            "imagine_compromise": img_comp,
            "imagine_stage": img_stage,
            "imagine_recon": img_recon,
            "precursor": prec_loss,
            "imagine_precursor": img_prec,
        }

    # ---- inference ---------------------------------------------------------------------------
    @torch.no_grad()
    def forecast(
        self,
        x: torch.Tensor,
        horizon: int | None = None,
        n_samples: int = 16,
        chunk: int = 64,
        sample: bool = True,
    ) -> dict[str, torch.Tensor]:
        """Per-window K-step forecast for one sequence. x: (1, T, F).

        Returns (all on CPU-friendly tensors):
          p_step  (T, K)  mean per-step hazard from the imagined trajectories
          p_cum   (T, K)  P(compromise within k) = 1 - prod(1 - hazard)
          p_lo/p_hi       5th / 95th percentile of p_cum across Monte-Carlo samples
          stage_now (T,S) stage distribution of the current filtered state
          stage_future (T,K,S) stage distribution of each imagined step
          surprise (T,)   next-state NLL of the actually-observed window (unseen-behaviour signal)
          attention (T,L) attention of each window over its own history, newest last
        """
        cfg = self.cfg
        horizon = horizon or cfg.horizon_k
        self.eval()
        b, t, _ = x.shape
        assert b == 1, "forecast expects a single sequence"
        if not sample:
            # Mean path: the posterior, the prior and the rollout all take their means, so the whole
            # trajectory is deterministic and 16 rollouts would be 16 identical tensors. Used when a
            # lead-time count must not carry Monte-Carlo variance (E14's caveat: the same checkpoint
            # at the same threshold gave 1 of 4 and then 2 of 4). Note sigmoid(head(E[z])) is not
            # E[sigmoid(head(z))], so the mean path under-states saturating probabilities - the
            # threshold is a quantile of the same series, so ranks are what carry over.
            n_samples = 1

        out = self.observe(x, sample=sample)
        feats = torch.stack([p.feat() for p in out["posts"]], dim=1)
        stage_now = F.softmax(self.stage_head(feats), dim=-1)[0]

        pred_next = self.decoder(feats[:, :-1])
        var = self.obs_logvar.exp()
        surprise = 0.5 * (self.obs_logvar + (pred_next - x[:, 1:]) ** 2 / var).mean(-1)[0]
        surprise = torch.cat([surprise.new_zeros(1), surprise])

        attention = self._history_attention(out["attention"][0], cfg.context_len)

        p_cum_samples = torch.zeros(n_samples, t, horizon)
        p_raw_samples = torch.zeros(n_samples, t, horizon, cfg.n_risk)
        stage_future = torch.zeros(t, horizon, cfg.n_stages)
        for begin in range(0, t, chunk):
            end = min(begin + chunk, t)
            idx = torch.arange(begin, end, device=x.device)
            state = RSSMState(
                torch.cat([out["posts"][i].h for i in range(begin, end)]),
                torch.cat([out["posts"][i].z for i in range(begin, end)]),
                torch.cat([out["posts"][i].mean for i in range(begin, end)]),
                torch.cat([out["posts"][i].std for i in range(begin, end)]),
            )
            history = self._history_buffer(out["embeds"][0], idx)
            for s in range(n_samples):
                img = self.imagine(state, history, horizon, sample=sample)
                risk = torch.sigmoid(img["risk_logits"])
                p_raw_samples[s, begin:end] = risk.cpu()
                p_cum_samples[s, begin:end] = (1 - torch.cumprod(1 - risk[..., 0], dim=1)).cpu()
                if s == 0:
                    stage_future[begin:end] = F.softmax(img["stage_logits"], dim=-1).cpu()

        p_cum = p_cum_samples.mean(0)
        p_raw = p_raw_samples.mean(0)
        # Union per sample, then average - 1 - prod(1 - E[p]) is not E[1 - prod(1 - p)]. Until
        # 2026-09-25 these curves came from Monte-Carlo sample 0 alone while p_cum was a 16-sample
        # mean; the two were being read side by side in the same payload (D-023).
        n_union = min(IMAGINED_CHANNELS, cfg.n_risk)
        extra_cum = (
            (1 - torch.cumprod(1 - p_raw_samples[..., 1:n_union], dim=2)).mean(0).permute(2, 0, 1)
        )
        return {
            "p_cum": p_cum,
            # Per-step P(state has this property at t+k), before any union formula. The compromise
            # head predicts a *state property*, not a first-occurrence hazard, so the cumulative
            # product over-counts a compromise that simply persists - keep both and let the
            # evaluation pick (see decisions D-019).
            "p_raw": p_raw,
            "p_max": p_raw[..., 0].max(dim=1).values,
            "p_lo": torch.quantile(p_cum_samples, 0.05, dim=0),
            "p_hi": torch.quantile(p_cum_samples, 0.95, dim=0),
            "p_step": torch.cat([p_cum[:, :1], p_cum[:, 1:] - p_cum[:, :-1]], dim=1),
            "p_cum_attack": extra_cum[0],
            "p_cum_escalate": extra_cum[1] if cfg.n_risk > 2 else extra_cum[0],
            # Round 3 (D-023). onset_now is a first-occurrence indicator, so its union over the
            # rollout is a genuine P(an attack episode begins within k) - this is the forecasting
            # statistic. The precursor channel is never derived from a rollout: it is read off the
            # filtered posterior in risk_now, and is a representation result, not a forecast.
            **(
                {
                    "p_onset_cum": extra_cum[2],
                    "p_onset_max": p_raw[..., 3].max(dim=1).values,
                }
                if cfg.n_risk > 3
                else {}
            ),
            "risk_now": torch.sigmoid(self.risk_head(feats))[0].cpu(),
            "stage_now": stage_now.cpu(),
            "stage_future": stage_future,
            "surprise": surprise.cpu(),
            "attention": attention.cpu(),
        }

    def _history_buffer(self, embeds: torch.Tensor, idx: torch.Tensor) -> torch.Tensor:
        """(len(idx), context_len, E) buffer of the embeddings preceding each index, zero-padded."""
        cfg = self.cfg
        offsets = torch.arange(-cfg.context_len + 1, 1, device=embeds.device)
        positions = idx[:, None] + offsets[None, :]
        valid = positions >= 0
        buf = embeds[positions.clamp(min=0)]
        return buf * valid[..., None]

    @staticmethod
    def _history_attention(attn: torch.Tensor, context_len: int = 16) -> torch.Tensor:
        """Reshape the (T, T) causal attention into (T, context_len), newest weight last."""
        t = attn.shape[0]
        out = attn.new_zeros(t, context_len)
        for i in range(t):
            lo = max(0, i - context_len + 1)
            row = attn[i, lo : i + 1]
            out[i, context_len - row.shape[0] :] = row
        return out
