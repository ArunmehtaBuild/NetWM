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
from netwm.features.packet_windows import HAS_PCAP, mask_packets
from netwm.features.scaler import StateScaler
from netwm.models.targets import episode_labels
from netwm.models.world_model import NetWorldModel, WorldModelConfig, build_model

#: What each risk channel is supervised on, in order. The first three are D-016 and are what every
#: round-2 checkpoint carries; the last two are round 3 (D-023). ``n_risk`` must equal the length of
#: the slice in use - ``scripts/train.py`` asserts it.
RISK_COLUMNS: tuple[str, ...] = (
    "compromise", "attack_now", "escalate_step", "onset_now", "precursor",
)

#: ``class_weights`` caps inverse-frequency weights at 50x by default. ``onset_now`` fires on ~18
#: windows in a four-day fold, which wants ~199 - capping it there would flatten the channel that
#: carries the whole forecasting claim. The cap exists to stop a near-absent channel dominating the
#: gradient; for a first-occurrence target that risk is the point, so it is raised deliberately.
POS_WEIGHT_CAP: dict[str, float] = {"onset_now": 250.0}
DEFAULT_POS_WEIGHT_CAP = 50.0


class CurriculumSequences(Dataset):
    """E23 (D-035): histories that end a fixed number of windows before an attack onset.

    One item per (training-day onset, offset): ``history`` windows ending ``offset`` windows before the
    onset, followed by ``horizon`` windows of true future, so the model can be asked to imagine from
    the last history window into the attack. Items whose span leaves the day are skipped.
    """

    def __init__(self, days: dict[str, dict], offsets: "list[int]", history: int, horizon: int) -> None:
        self.history = history
        self.items: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        for day in days.values():
            n = len(day["x"])
            for onset in day["attack_onsets"]:
                for offset in offsets:
                    end = onset - offset                      # last window of history
                    lo, hi = end - history + 1, end + horizon + 1
                    if lo < 0 or hi > n:
                        continue
                    self.items.append((day["x"][lo:hi], day["stage"][lo:hi], day["risk"][lo:hi]))

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        x, stage, risk = self.items[i]
        return torch.from_numpy(x).float(), torch.from_numpy(stage).long(), torch.from_numpy(risk).float()


class WindowSequences(Dataset):
    """Overlapping fixed-length slices of consecutive windows, never crossing a day boundary.

    ``packet_dropout`` (D-037): with that probability a sequence is served in its CSV form - the
    same windows with every packet feature absent and ``has_pcap`` = 0 (``day["x_csv"]``) - so a
    flow-CSV input at inference is a state the model has trained on.
    """

    def __init__(self, days: dict[str, dict], seq_len: int, stride: int, packet_dropout: float = 0.0) -> None:
        self.items: list[tuple] = []
        self.packet_dropout = packet_dropout
        for day in days.values():
            x, stage, comp = day["x"], day["stage"], day["risk"]
            x_csv = day.get("x_csv")
            for start in range(0, max(1, len(x) - seq_len + 1), stride):
                end = start + seq_len
                if end > len(x):
                    break
                alt = x_csv[start:end] if x_csv is not None else None
                self.items.append((x[start:end], stage[start:end], comp[start:end], alt))

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        x, stage, risk, alt = self.items[i]
        if alt is not None and self.packet_dropout > 0 and float(torch.rand(())) < self.packet_dropout:
            x = alt
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
    risk_columns: "tuple[str, ...]" = RISK_COLUMNS[:3]
    onset_source: str = "attack"
    onset_gap: int = 4
    # E23 (D-035): {"offsets": [...], "history": int, "horizon": int, "weight": float}; None = off
    curriculum: dict | None = None
    # E25: train for this many optimiser steps, whatever the fold's size (D-035: CTU-13 folds get a
    # CIC-IDS2017 fold's step budget, not its epoch count). None = `epochs` epochs.
    target_steps: int | None = None
    # E26 (D-037): probability a training sequence is shown in its CSV form (packets absent)
    packet_dropout: float = 0.0

    def __post_init__(self) -> None:
        self.risk_columns = tuple(self.risk_columns)
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
        # Every term losses() can emit is declared here, including at round-2 width where the
        # precursor channels do not exist and the terms are a constant zero. train_model refuses to
        # run on an undeclared term, and that guard is only worth having if the dict is complete.
        round_three = len(self.risk_columns) > 3
        # Round 3 mirrors the compromise weights: it asks the same question one step earlier, so
        # there is no prior reason to weight it differently. Revisited in the E15 ablation.
        self.weights.setdefault("precursor", 2.0 if round_three else 0.0)
        self.weights.setdefault("imagine_precursor", 3.0 if round_three else 0.0)
        # emitted only by the E22 factorised hazard and the E23 curriculum; declared so the
        # unweighted-term guard can stay strict
        self.weights.setdefault("hostile_stage", 1.0)
        self.weights.setdefault("curriculum", float((self.curriculum or {}).get("weight", 1.0)))


def prepare_days(
    ds: ProcessedDataset,
    days: list[str],
    scaler: StateScaler,
    risk_columns: "tuple[str, ...]" = RISK_COLUMNS[:3],
    onset_source: str = "attack",
    onset_gap: int = 4,
    csv_mode: bool = False,
    with_csv_view: bool = False,
) -> dict[str, dict]:
    """Scaled states plus every supervision target, one entry per day.

    ``onset_now`` and ``precursor`` are derived here rather than read from the parquet on purpose:
    ``build_features.py`` picks ``feature_names`` by *exclusion*, so a new label column there would
    silently become a model input and leak its own answer (D-023).
    """
    out = {}
    for day in days:
        frame = ds.frame(day)
        labels = episode_labels(
            frame["stage"], ds.horizon, gap=onset_gap, source=onset_source
        )
        derived = {"onset_now": labels.onset_now, "precursor": labels.precursor}
        # what the risk head reads off a state: compromised / hostile / stepping up (D-016),
        # then whether an episode begins here and whether one is about to (D-023)
        risk = np.stack(
            [
                (frame[c].to_numpy() if c in frame.columns else derived[c]).astype(np.float32)
                for c in risk_columns
            ],
            axis=1,
        )
        states = frame[ds.feature_names]
        # csv_mode: the day as a flow-CSV input would present it (D-037); the scaler is the same
        x = scaler.transform(mask_packets(states) if csv_mode else states)
        out[day] = {
            "x": x,
            **({"x_csv": scaler.transform(mask_packets(states))}
               if with_csv_view and HAS_PCAP in ds.feature_names else {}),
            "stage": frame["stage"].to_numpy().astype(np.int64),
            "compromise": frame["compromise"].to_numpy().astype(np.float32),
            "risk": risk,
            "risk_columns": list(risk_columns),
            "y_within_K": frame["y_within_K"].to_numpy().astype(np.int64),
            "y_escalate_within_K": frame["y_escalate_within_K"].to_numpy().astype(np.int64),
            "ts": frame["ts"],
            "onsets": ds.onsets(day),
            "attack_onsets": labels.onsets,
            "attack_families": labels.families,
            "eligible": labels.eligible,
        }
    return out


def class_weights(
    days: dict[str, dict],
    n_stages: int,
    risk_columns: "tuple[str, ...]" = RISK_COLUMNS[:3],
) -> tuple[torch.Tensor, torch.Tensor]:
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
    caps = np.array([POS_WEIGHT_CAP.get(c, DEFAULT_POS_WEIGHT_CAP) for c in risk_columns])
    pos_weight = np.minimum((len(risk) - pos) / pos, caps)
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
    if len(cfg.risk_columns) != model_cfg.n_risk:
        raise ValueError(
            f"n_risk={model_cfg.n_risk} but {len(cfg.risk_columns)} risk columns "
            f"{cfg.risk_columns} - the head width and its supervision must agree"
        )
    days = prepare_days(ds, train_days, scaler, cfg.risk_columns, cfg.onset_source, cfg.onset_gap,
                        with_csv_view=cfg.packet_dropout > 0)
    if cfg.packet_dropout > 0 and HAS_PCAP not in ds.feature_names:
        raise ValueError("packet_dropout needs the has_pcap input (data/processed/cicids2017_m1v2p)")
    dataset = WindowSequences(days, cfg.seq_len, cfg.stride, packet_dropout=cfg.packet_dropout)
    loader = DataLoader(dataset, batch_size=cfg.batch_size, shuffle=True, drop_last=False)

    stage_w, pos_w = class_weights(days, model_cfg.n_stages, cfg.risk_columns)
    stage_w, pos_w = stage_w.to(device), pos_w.to(device)

    curriculum = None
    if cfg.curriculum:
        cur = CurriculumSequences(days, list(cfg.curriculum["offsets"]), int(cfg.curriculum["history"]),
                                  int(cfg.curriculum["horizon"]))
        progress(f"  curriculum: {len(cur)} pre-onset sequences")
        if len(cur):
            curriculum = DataLoader(cur, batch_size=cfg.batch_size, shuffle=True, drop_last=False)

    model = build_model(model_cfg).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=1e-4)
    epochs = cfg.epochs
    if cfg.target_steps:
        epochs = max(1, -(-int(cfg.target_steps) // max(1, len(loader))))
        progress(f"  {len(loader)} batches/epoch -> {epochs} epochs for ~{cfg.target_steps} steps")
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, epochs))

    history: list[dict] = []
    for epoch in range(epochs):
        model.train()
        totals: dict[str, float] = {}
        cur_iter = iter(curriculum) if curriculum is not None else None
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
            if cur_iter is not None:
                # one curriculum batch per regular batch, cycling over the pre-onset set
                try:
                    cx, cs, cr = next(cur_iter)
                except StopIteration:
                    cur_iter = iter(curriculum)
                    cx, cs, cr = next(cur_iter)
                losses.update(model.curriculum_loss(
                    cx.to(device), cs.to(device), cr.to(device), start=int(cfg.curriculum["history"]) - 1,
                    horizon=int(cfg.curriculum["horizon"]), stage_weight=stage_w, pos_weight=pos_w,
                ))
            unweighted = {k for k in losses if k not in cfg.weights and not k.endswith("_raw")}
            if unweighted:
                # A loss term absent from the weight dict contributes nothing, trains a dead head
                # and still prints a falling curve. Fail instead of spending a run finding out.
                raise KeyError(f"loss terms produced but never weighted: {sorted(unweighted)}")
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
        if epoch % log_every == 0 or epoch == epochs - 1:
            line = (
                f"  epoch {epoch:>3d}  total={row['total']:.3f}  recon={row['recon']:.3f}  "
                f"kl={row['kl_raw']:.3f}  comp={row['compromise']:.3f}  "
                f"imag_comp={row['imagine_compromise']:.3f}"
            )
            if len(cfg.risk_columns) > 3:
                # Y-2 asks for the loss curves either way, so the terms under test are always shown.
                line += f"  prec={row['precursor']:.3f}  imag_prec={row['imagine_precursor']:.3f}"
            progress(line)
    return model, history
