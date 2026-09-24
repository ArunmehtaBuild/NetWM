"""Explainability for a forecast (decisions.md D-007).

Two complementary answers, both required by the problem statement:

* **when** - the encoder's attention weights over the preceding windows;
* **what** - Integrated Gradients over the input features, attributed to the scalar the defender
  actually acts on: P(compromise within K) at this window.

IG is computed on a short slice (the attention context plus the current window) rather than the whole
day, and only for the windows a defender would look at (alarms, or every n-th window), because a full
per-window attribution over a day costs thousands of forward passes.
"""

from __future__ import annotations

import numpy as np
import torch
from captum.attr import IntegratedGradients

from netwm.models.world_model import NetWorldModel


class ForecastScore(torch.nn.Module):
    """Wraps the world model so Captum sees a plain (B, L, F) -> (B,) function.

    The score is the deterministic (mean-path) cumulative compromise probability over the horizon:
    sampling would make the attribution noisy for no benefit, since IG already integrates a path.
    """

    def __init__(self, model: NetWorldModel, horizon: int) -> None:
        super().__init__()
        self.model = model
        self.horizon = horizon

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.model.observe(x)
        state = out["posts"][-1]
        img = self.model.imagine(state, out["embeds"], self.horizon, sample=False)
        hazard = torch.sigmoid(img["compromise_logit"])
        return 1.0 - torch.prod(1.0 - hazard, dim=1)


@torch.enable_grad()
def explain_window(
    model: NetWorldModel,
    x: np.ndarray,
    t: int,
    horizon: int,
    device: torch.device,
    n_steps: int = 32,
    context: int | None = None,
) -> dict:
    """Integrated-Gradients attribution for the forecast made at window ``t``.

    ``x`` is the scaled state matrix for the whole capture. The baseline is the all-zero state, which
    after scaling (D-014) is the *average* window - so attributions read as "how far this window
    departs from a typical one, and in which direction that pushes the forecast".
    """
    model.eval()
    context = context or model.cfg.context_len
    lo = max(0, t - context + 1)
    window = torch.from_numpy(np.asarray(x[lo : t + 1], dtype=np.float32)).unsqueeze(0).to(device)

    scorer = ForecastScore(model, horizon).to(device)
    ig = IntegratedGradients(scorer)
    attributions = ig.attribute(window, baselines=torch.zeros_like(window), n_steps=n_steps)
    attr = attributions[0].detach().cpu().numpy()          # (L, F)
    score = float(scorer(window).detach().cpu())

    per_feature = attr[-1]                                  # the current window's own contribution
    per_step = attr.sum(axis=1)                             # contribution of each past window
    return {
        "t": int(t),
        "score": score,
        "feature_attribution": per_feature,
        "history_attribution": per_step,
        "total_attribution": attr,
    }


def top_features(
    attribution: np.ndarray, values: np.ndarray, feature_names: "list[str]", k: int = 8
) -> list[dict]:
    """The k features driving this prediction, in the API's ``top_features`` shape."""
    order = np.argsort(np.abs(attribution))[::-1][:k]
    return [
        {
            "name": feature_names[i],
            "value": float(values[i]),
            "attribution": float(attribution[i]),
            "direction": "up" if attribution[i] >= 0 else "down",
        }
        for i in order
    ]


def global_attribution(explanations: "list[dict]", feature_names: "list[str]") -> dict:
    """Mean |attribution| per feature across explained windows - the model's overall reasoning."""
    if not explanations:
        return {"feature_names": feature_names, "mean_abs_attribution": [0.0] * len(feature_names)}
    stack = np.stack([e["feature_attribution"] for e in explanations])
    return {
        "feature_names": feature_names,
        "mean_abs_attribution": np.abs(stack).mean(axis=0).tolist(),
    }
