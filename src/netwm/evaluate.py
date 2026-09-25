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
    # The alarm statistic is max-over-horizon, not the cumulative union (D-019). Until 2026-09-25
    # these in-training rows scored p_cum[:, -1] while E14 and the engine scored p_max, so the E6
    # rows and the E14 table disagreed on the same checkpoints - any of those numbers reaching a
    # slide would have been wrong.
    train_scores, train_labels = [], []
    for day in train_days.values():
        out = forecast_day(model, day["x"], horizon, max(4, n_samples // 4), device)
        train_scores.append(out["p_max"])
        train_labels.append(day["y_within_K"])
    train_score = np.concatenate(train_scores)
    thr_train = best_threshold(np.concatenate(train_labels), train_score)
    # Alert budget: the threshold that fires on 5 % of *training* windows. Absolute probabilities do
    # not transfer across days (E4-E7 round 1: 0.843 on train vs 0.059 on test), but "the noisiest
    # 5 % of windows" is a setting a SOC can actually live with (D-016).
    thr_budget = float(np.quantile(train_score, 0.95))

    out = forecast_day(model, test_day["x"], horizon, n_samples, device)
    score = out["p_max"]
    y = test_day["y_within_K"]

    rows = []
    for name, thr in (
        ("train-tuned", thr_train),
        ("alert-budget-5pct", thr_budget),
        ("oracle", best_threshold(y, score)),
    ):
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

    # secondary target: does the model see the attacker *advancing* (D-016)? Scored the same way as
    # the primary one, so the two rows are comparable.
    esc_score = (
        out["p_raw"][:, :, 2].max(axis=1) if out["p_raw"].shape[2] > 2 else out["p_cum_escalate"][:, -1]
    )
    esc_y = test_day.get("y_escalate_within_K")
    if esc_y is not None and esc_y.sum() > 0:
        m_esc = forecast_metrics(esc_y, esc_score, best_threshold(esc_y, esc_score))
        rows.append(
            {
                "experiment": "E6",
                "model": "world-model",
                "target": "escalation",
                "threshold_mode": "oracle",
                "test_day": test_day_name,
                "base_rate": round(float(esc_y.mean()), 4),
                **{k: round(v, 4) if isinstance(v, float) else v for k, v in m_esc.as_dict().items()},
            }
        )

    extras = {
        "alarm_statistic": "p_max",
        "threshold_train": thr_train,
        "threshold_budget": thr_budget,
        "escalation_scores": esc_score.tolist(),
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
