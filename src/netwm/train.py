"""Training loop for the world model (decisions.md D-004, D-005).

Sequences are contiguous slices of a day's windows - shuffling windows would destroy the very thing
we are trying to learn. The scaler and all class weights are fitted on the training days only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from netwm.data.processed import ProcessedDataset
from netwm.features.scaler import StateScaler
from netwm.models.world_model import NetWorldModel, WorldModelConfig


class WindowSequences(Dataset):
    """Overlapping fixed-length slices of consecutive windows, never crossing a day boundary."""

    def __init__(self, days: dict[str, dict], seq_len: int, stride: int) -> None:
        self.items: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        for day in days.values():
            x, stage, comp = day["x"], day["stage"], day["risk"]
            for start in range(0, max(1, len(x) - seq_len + 1), stride):
                end = start + seq_len
                if end > len(x):
                    break
                self.items.append((x[start:end], stage[start:end], comp[start:end]))

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        x, stage, risk = self.items[i]
        return (
            torch.from_numpy(x).float(),
            torch.from_numpy(stage).long(),
            torch.from_numpy(risk).float(),
        )


@dataclass
class TrainConfig:
    seq_len: int = 96
    stride: int = 48
    batch_size: int = 8
    epochs: int = 20
    lr: float = 3e-4
    grad_clip: float = 100.0
    imagine_every: int = 8
    weights: dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.weights is None:
            self.weights = {
                "recon": 1.0,
                "kl": 0.5,
                "stage": 1.0,
                "compromise": 2.0,
                "imagine_compromise": 3.0,
                "imagine_stage": 0.5,
                "imagine_recon": 1.0,
            }


def prepare_days(ds: ProcessedDataset, days: list[str], scaler: StateScaler) -> dict[str, dict]:
    out = {}
    for day in days:
        frame = ds.frame(day)
        out[day] = {
            "x": scaler.transform(frame[ds.feature_names]),
            "stage": frame["stage"].to_numpy().astype(np.int64),
            "compromise": frame["compromise"].to_numpy().astype(np.float32),
            # what the risk head reads off a state: compromised / hostile / stepping up (D-016)
            "risk": frame[["compromise", "attack_now", "escalate_step"]].to_numpy().astype(np.float32),
            "y_within_K": frame["y_within_K"].to_numpy().astype(np.int64),
            "y_escalate_within_K": frame["y_escalate_within_K"].to_numpy().astype(np.int64),
            "ts": frame["ts"],
            "onsets": ds.onsets(day),
        }
    return out


def class_weights(days: dict[str, dict], n_stages: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Inverse-frequency stage weights and a positive weight for the compromise head.

    Attack windows are 0-17 % of a day depending on the split, and some stages never appear in a
    given fold - an unweighted loss simply predicts Benign everywhere.
    """
    stages = np.concatenate([d["stage"] for d in days.values()])
    counts = np.bincount(stages, minlength=n_stages).astype(np.float64)
    weights = np.where(counts > 0, counts.sum() / np.maximum(counts, 1), 0.0)
    weights = weights / weights[weights > 0].mean()

    risk = np.concatenate([d["risk"] for d in days.values()])
    pos = np.maximum(risk.sum(axis=0), 1.0)
    pos_weight = np.minimum((len(risk) - pos) / pos, 50.0)
    return (
        torch.tensor(weights, dtype=torch.float32),
        torch.tensor(pos_weight, dtype=torch.float32),
    )


def train_model(
    ds: ProcessedDataset,
    train_days: list[str],
    cfg: TrainConfig,
    model_cfg: WorldModelConfig,
    device: torch.device,
    scaler: StateScaler,
    log_every: int = 1,
    progress=print,
) -> tuple[NetWorldModel, list[dict]]:
    days = prepare_days(ds, train_days, scaler)
    dataset = WindowSequences(days, cfg.seq_len, cfg.stride)
    loader = DataLoader(dataset, batch_size=cfg.batch_size, shuffle=True, drop_last=False)

    stage_w, pos_w = class_weights(days, model_cfg.n_stages)
    stage_w, pos_w = stage_w.to(device), pos_w.to(device)

    model = NetWorldModel(model_cfg).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, cfg.epochs))

    history: list[dict] = []
    for epoch in range(cfg.epochs):
        model.train()
        totals: dict[str, float] = {}
        for x, stage, risk in loader:
            x, stage, risk = x.to(device), stage.to(device), risk.to(device)
            losses = model.losses(
                x,
                stage,
                risk,
                horizon=model_cfg.horizon_k,
                imagine_every=cfg.imagine_every,
                stage_weight=stage_w,
                pos_weight=pos_w,
            )
            loss = sum(cfg.weights[k] * v for k, v in losses.items() if k in cfg.weights)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            opt.step()

            totals["total"] = totals.get("total", 0.0) + float(loss)
            for k, v in losses.items():
                totals[k] = totals.get(k, 0.0) + float(v)
        sched.step()

        n = max(1, len(loader))
        row = {"epoch": epoch, **{k: round(v / n, 4) for k, v in totals.items()}}
        history.append(row)
        if epoch % log_every == 0 or epoch == cfg.epochs - 1:
            progress(
                f"  epoch {epoch:>3d}  total={row['total']:.3f}  recon={row['recon']:.3f}  "
                f"kl={row['kl_raw']:.3f}  comp={row['compromise']:.3f}  "
                f"imag_comp={row['imagine_compromise']:.3f}"
            )
    return model, history
