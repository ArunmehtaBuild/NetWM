"""Evaluating a trained world model: forecast quality, lead time, rollout fidelity, surprise."""

from __future__ import annotations

import numpy as np
import torch

from netwm.metrics import best_threshold, forecast_metrics, lead_times, summarise_lead
from netwm.models.world_model import NetWorldModel


@torch.no_grad()
def forecast_day(
    model: NetWorldModel, x: np.ndarray, horizon: int, n_samples: int, device: torch.device
) -> dict[str, np.ndarray]:
    tensor = torch.from_numpy(np.asarray(x, dtype=np.float32)).unsqueeze(0).to(device)
    out = model.forecast(tensor, horizon=horizon, n_samples=n_samples)
    return {k: v.cpu().numpy() for k, v in out.items()}


@torch.no_grad()
def rollout_fidelity(
    model: NetWorldModel, x: np.ndarray, horizon: int, device: torch.device, stride: int = 8
) -> dict[str, list[float]]:
    """Open-loop error at each imagined step k, against the persistence floor at the same k.

    This is the test that separates a world model from a classifier: if imagined states at k = 5 are
    no better than "nothing changes", the dynamics have not been learned (research/world-models.md).
    """
    tensor = torch.from_numpy(np.asarray(x, dtype=np.float32)).unsqueeze(0).to(device)
    out = model.observe(tensor)
    t = tensor.shape[1]
    starts = list(range(model.cfg.context_len, t - horizon - 1, stride))
    model_err = np.zeros(horizon)
    persist_err = np.zeros(horizon)
    for start in starts:
        img = model.imagine(out["posts"][start], out["embeds"][:, : start + 1], horizon, sample=False)
        target = tensor[:, start + 1 : start + 1 + horizon]
        pred = img["decoded"][:, : target.shape[1]]
        model_err += ((pred - target) ** 2).mean(-1)[0].cpu().numpy()
        base = tensor[:, start : start + 1].expand_as(target)
        persist_err += ((base - target) ** 2).mean(-1)[0].cpu().numpy()
    n = max(1, len(starts))
    return {
        "k": list(range(1, horizon + 1)),
        "world_model_mse": (model_err / n).tolist(),
        "persistence_mse": (persist_err / n).tolist(),
    }


def evaluate_fold(
    model: NetWorldModel,
    train_days: dict[str, dict],
    test_day_name: str,
    test_day: dict,
    horizon: int,
    stride_s: float,
    device: torch.device,
    n_samples: int = 16,
) -> tuple[list[dict], dict]:
    """Metrics for one leave-one-day-out fold, with the threshold tuned on the training days."""
    train_scores, train_labels = [], []
    for day in train_days.values():
        out = forecast_day(model, day["x"], horizon, max(4, n_samples // 4), device)
        train_scores.append(out["p_cum"][:, -1])
        train_labels.append(day["y_within_K"])
    thr_train = best_threshold(np.concatenate(train_labels), np.concatenate(train_scores))

    out = forecast_day(model, test_day["x"], horizon, n_samples, device)
    score = out["p_cum"][:, -1]
    y = test_day["y_within_K"]

    rows = []
    for name, thr in (("train-tuned", thr_train), ("oracle", best_threshold(y, score))):
        m = forecast_metrics(y, score, thr)
        lead = summarise_lead(
            lead_times(score, test_day["onsets"], thr, horizon, persistence=2), stride_s
        )
        rows.append(
            {
                "experiment": "E6",
                "model": "world-model",
                "target": "forecast",
                "threshold_mode": name,
                "test_day": test_day_name,
                "base_rate": round(float(y.mean()), 4),
                **{k: round(v, 4) if isinstance(v, float) else v for k, v in m.as_dict().items()},
                "episodes": lead["episodes"],
                "warned_early": lead["episodes_warned_early"],
                "mean_lead_windows": round(lead["mean_lead_windows"], 2),
                "mean_lead_seconds": round(lead["mean_lead_seconds"], 1),
            }
        )

    extras = {
        "threshold_train": thr_train,
        "scores": score.tolist(),
        "p_cum": out["p_cum"].tolist(),
        "p_lo": out["p_lo"].tolist(),
        "p_hi": out["p_hi"].tolist(),
        "surprise": out["surprise"].tolist(),
        "stage_now": out["stage_now"].tolist(),
        "attention": out["attention"].tolist(),
        "lead": summarise_lead(
            lead_times(score, test_day["onsets"], thr_train, horizon, persistence=2), stride_s
        ),
        "rollout": rollout_fidelity(model, test_day["x"], horizon, device),
    }
    return rows, extras
