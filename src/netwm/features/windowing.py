"""Turn a flow table into overlapping time windows - the unit of state S_t (decisions.md D-002).

Window ``w`` covers ``[t0 + w*stride, t0 + w*stride + length)``. With the default 60 s length and
30 s stride every flow belongs to two windows, which doubles the number of training sequences
without letting a window see traffic from the future: a window is labelled only from flows whose
timestamp falls strictly inside it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from netwm.labels.mitre_map import PROGRESSION_STAGES, Stage


@dataclass(frozen=True)
class WindowSpec:
    length_s: float = 60.0
    stride_s: float = 30.0

    def __post_init__(self) -> None:
        if self.stride_s <= 0 or self.length_s <= 0:
            raise ValueError("window length and stride must be positive")
        if self.length_s < self.stride_s:
            raise ValueError("length < stride would drop traffic between windows")

    @property
    def windows_per_flow(self) -> int:
        """How many windows a single instant belongs to."""
        return int(np.ceil(self.length_s / self.stride_s))

    def n_windows(self, span_s: float) -> int:
        return max(1, int(np.floor(span_s / self.stride_s)) + 1)

    def window_start(self, t0: pd.Timestamp, w: "int | np.ndarray"):
        return t0 + pd.to_timedelta(np.asarray(w) * self.stride_s, unit="s")


def expand_to_windows(
    df: pd.DataFrame, spec: WindowSpec, t0: pd.Timestamp | None = None
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Repeat each flow once per window it falls into, adding a ``w`` (window index) column.

    Returns the expanded frame and the epoch ``t0`` the window grid is anchored to, which callers
    must keep: window indices are meaningless without it.
    """
    if df.empty:
        return df.assign(w=pd.Series(dtype="int64")), t0 or pd.Timestamp(0)

    t0 = t0 if t0 is not None else df["ts"].min().floor("min")
    offs = (df["ts"] - t0).dt.total_seconds().to_numpy()

    w_hi = np.floor(offs / spec.stride_s).astype(np.int64)
    w_lo = np.floor((offs - spec.length_s) / spec.stride_s).astype(np.int64) + 1
    np.clip(w_lo, 0, None, out=w_lo)

    counts = (w_hi - w_lo + 1).clip(min=0)
    idx = np.repeat(np.arange(len(df)), counts)
    # per-row window indices: w_lo + 0,1,..  for each repeated row
    starts = np.repeat(w_lo, counts)
    within = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)

    out = df.iloc[idx].copy()
    out["w"] = starts + within
    return out, t0


IMPACT = int(Stage.IMPACT)
_PROGRESSION = {int(s) for s in PROGRESSION_STAGES}


def _effective_stage(expanded: pd.DataFrame, include_attempted: bool) -> pd.DataFrame:
    """Optionally demote ``- Attempted`` flows to benign for ground-truth purposes (D-009)."""
    if include_attempted or "attempted" not in expanded.columns:
        return expanded
    out = expanded.copy()
    out.loc[out["attempted"].to_numpy(), "stage"] = 0
    return out


def window_stages(
    expanded: pd.DataFrame,
    n_windows: int | None = None,
    include_attempted: bool = False,
) -> pd.Series:
    """Per-window stage: most advanced *progression* stage present, else Impact, else Benign.

    (D-003: Impact is off the progression axis, so a window holding both a DDoS and an infiltration
    is an infiltration window. D-009: attempted-only traffic does not set the stage.)
    """
    expanded = _effective_stage(expanded, include_attempted)
    prog = expanded[expanded["stage"] != IMPACT]
    best = prog.groupby("w")["stage"].max() if len(prog) else pd.Series(dtype="int64")
    impact = expanded.loc[expanded["stage"] == IMPACT, "w"].unique()

    n = n_windows if n_windows is not None else int(expanded["w"].max()) + 1
    out = pd.Series(np.zeros(n, dtype=np.int8), index=pd.RangeIndex(n), name="stage")
    if len(impact):
        out.iloc[impact] = IMPACT
    if len(best):
        # a progression stage above benign always wins over Impact
        winners = best[best > 0]
        if len(winners):
            out.iloc[winners.index.to_numpy()] = winners.to_numpy().astype(np.int8)
    return out


def compromise_flags(stages: pd.Series, threshold: int) -> np.ndarray:
    """Boolean per window: is the network at/after ``threshold`` on the progression scale."""
    s = stages.to_numpy()
    return np.isin(s, list(_PROGRESSION)) & (s >= threshold)


def hazard_targets(stages: pd.Series, horizon: int, threshold: int) -> np.ndarray:
    """``y[t, k-1] = 1`` if a compromise window occurs at ``t + k``, for k = 1..horizon.

    This is the supervision for the hazard head (D-005): the cumulative curve
    ``P(compromise within k)`` is then ``1 - prod(1 - hazard)`` over the first k steps.
    """
    comp = compromise_flags(stages, threshold)
    n = len(comp)
    y = np.zeros((n, horizon), dtype=np.float32)
    for k in range(1, horizon + 1):
        y[: n - k, k - 1] = comp[k:]
    return y


def onset_windows(stages: pd.Series, threshold: int, gap: int = 4) -> list[int]:
    """First window of each compromise episode; episodes separated by ``gap`` quiet windows.

    Lead time is measured against these onsets: how many windows earlier did the alarm fire.
    """
    idx = np.flatnonzero(compromise_flags(stages, threshold))
    if idx.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > gap) + 1
    return [int(idx[0]), *(int(i) for i in idx[breaks])]


def window_stage_matrix(
    expanded: pd.DataFrame,
    n_windows: int | None = None,
    include_attempted: bool = False,
) -> pd.DataFrame:
    """Multi-label view: one binary column per stage, because attacks overlap (D-010).

    On Friday the botnet C2 channel runs while a port scan and then a DDoS happen; collapsing that
    to a single "most advanced stage" throws away two of the three attacks.
    """
    expanded = _effective_stage(expanded, include_attempted)
    n = n_windows if n_windows is not None else int(expanded["w"].max()) + 1
    mat = pd.DataFrame(
        np.zeros((n, len(Stage)), dtype=np.int8),
        index=pd.RangeIndex(n),
        columns=[s.name for s in Stage],
    )
    present = expanded.loc[expanded["stage"] > 0, ["w", "stage"]].drop_duplicates()
    for stage_value, grp in present.groupby("stage"):
        mat.iloc[grp["w"].to_numpy(), int(stage_value)] = 1
    mat["BENIGN"] = (mat.drop(columns=["BENIGN"]).sum(axis=1) == 0).astype("int8")
    return mat


def attack_flags(stages: pd.Series) -> np.ndarray:
    """Any non-benign stage, Impact included - 'something hostile is happening'."""
    return stages.to_numpy() > 0


def escalation_targets(stages: pd.Series, horizon: int) -> np.ndarray:
    """``y[t, k-1] = 1`` if the network is at a *more advanced* progression stage at t + k than at t.

    This is the PS's "probability of attacker progression" read literally, and unlike the compromise
    target it has positive examples on every day of the week: brute force escalating out of benign
    on Tuesday, scanning escalating to C2 on Friday, and so on. Impact is excluded because it is off
    the progression axis (D-003) - a DoS is not the attacker getting further in.
    """
    s = stages.to_numpy()
    prog = np.where(np.isin(s, [int(x) for x in PROGRESSION_STAGES]), s, 0)
    n = len(prog)
    y = np.zeros((n, horizon), dtype=np.float32)
    for k in range(1, horizon + 1):
        y[: n - k, k - 1] = (prog[k:] > prog[: n - k]).astype(np.float32)
    return y


def any_within(targets: np.ndarray) -> np.ndarray:
    """Collapse a (T, K) per-step target into 'happens at least once within K'."""
    return (targets.sum(axis=1) > 0).astype(np.int8)


def escalation_steps(stages: pd.Series) -> np.ndarray:
    """Per-window flag: this window is a *step up* the progression scale from the previous one.

    A state property (unlike :func:`escalation_targets`, which compares against a fixed anchor), so
    the model can read it off an imagined state and the cumulative probability of an escalation
    within k steps is the usual 1 - prod(1 - p).
    """
    s = stages.to_numpy()
    prog = np.where(np.isin(s, [int(x) for x in PROGRESSION_STAGES]), s, 0)
    out = np.zeros(len(prog), dtype=np.float32)
    out[1:] = (prog[1:] > prog[:-1]).astype(np.float32)
    return out
