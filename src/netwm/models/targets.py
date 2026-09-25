"""Episode-keyed supervision targets for the round-3 precursor heads (decisions.md D-022).

The three risk channels of D-016 all answer questions about the *present* state - is it
compromised, is anything hostile happening, is this a step up the kill chain. E14 showed why that
cannot warn: every one of them is only true once the attack has landed. This module builds the two
targets round 3 adds.

``onset_now``
    1 exactly on the first window of an attack episode. A first-occurrence indicator, so
    ``1 - prod(1 - p_k)`` over a rollout is a *correct* ``P(an episode begins within k)`` - the
    hypothesis D-019 left open.

``precursor``
    1 on the ``horizon`` windows before an onset that are not themselves attack windows. The Y-2
    card's definition, and the same window set E12 probed.

Both are keyed on **attack-episode** onsets rather than compromise onsets. That is a deliberate
deviation from D-019, forced by the label counts: compromise-keyed gives a training fold 10 positive
windows from a single attack family, which is precisely the D-016 failure that broke round 1.
Lead time is still *evaluated* on the compromise onsets as well - see ``scripts/precursor_eval.py``.

These live here rather than in ``features/windowing.py`` because they are model supervision, not
state features, and because ``build_features.py`` derives ``feature_names`` by *exclusion*: a new
label column in the parquet would silently become a model input.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from netwm.features.windowing import attack_flags, compromise_flags
from netwm.labels.mitre_map import COMPROMISE_THRESHOLD, Stage

#: Onset sources. ``attack`` = any non-benign episode; ``compromise`` = D-011's definition.
ONSET_SOURCES = ("attack", "compromise")


@dataclass(frozen=True)
class EpisodeLabels:
    """Everything an episode-keyed experiment needs about one day."""

    onsets: list[int]
    families: list[str]          # stage name at each onset window, for the per-family breakdown
    onset_now: np.ndarray        # (T,) float32 - first window of an episode
    precursor: np.ndarray        # (T,) float32 - the K windows before an onset, attack ones removed
    eligible: np.ndarray         # (T,) bool    - windows allowed to count as an early warning

    def without(self, family: str) -> "EpisodeLabels":
        """Drop every episode of one family, keeping the per-window arrays intact.

        Used for the Impact-excluded row: a DDoS ramp is visible minutes ahead in flow rate, so an
        aggregate carried by Impact onsets would look like success and mean nothing for PS 26153.
        """
        keep = [i for i, f in enumerate(self.families) if f != family]
        return EpisodeLabels(
            onsets=[self.onsets[i] for i in keep],
            families=[self.families[i] for i in keep],
            onset_now=self.onset_now,
            precursor=self.precursor,
            eligible=self.eligible,
        )


def episode_onsets(flags: np.ndarray, gap: int = 4) -> list[int]:
    """First index of each run of ``flags``, runs separated by more than ``gap`` quiet windows.

    Generalises ``features.windowing.onset_windows`` to any boolean series; that function is the
    compromise-keyed special case and stays the authority for D-011's onsets.
    """
    idx = np.flatnonzero(np.asarray(flags, dtype=bool))
    if idx.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(idx) > gap) + 1
    return [int(idx[0]), *(int(i) for i in idx[breaks])]


def onset_flags(onsets: "list[int]", n: int) -> np.ndarray:
    """(T,) float32 indicator of the onset windows themselves."""
    out = np.zeros(n, dtype=np.float32)
    if onsets:
        out[np.asarray(onsets, dtype=int)] = 1.0
    return out


def precursor_flags(
    onsets: "list[int]", attack: np.ndarray, horizon: int
) -> np.ndarray:
    """(T,) float32: an onset falls within the next ``horizon`` windows and this one is quiet.

    Mirrors ``scripts/precursor_analysis.py`` (E12) exactly, so E15 is measured on the window set
    E12 found separable - ``[onset - K, onset)``, minus windows that are already attack windows.
    """
    attack = np.asarray(attack, dtype=bool)
    out = np.zeros(len(attack), dtype=np.float32)
    for onset in onsets:
        for t in range(max(0, onset - horizon), onset):
            if not attack[t]:
                out[t] = 1.0
    return out


def episode_labels(
    stages: pd.Series,
    horizon: int,
    gap: int = 4,
    source: str = "attack",
) -> EpisodeLabels:
    """Build every episode-keyed array for one day.

    ``source='attack'`` keys episodes on any non-benign stage (the round-3 supervision target);
    ``source='compromise'`` reproduces D-011 and is what lead time is still reported against.
    """
    if source not in ONSET_SOURCES:
        raise ValueError(f"onset source must be one of {ONSET_SOURCES}, got {source!r}")

    attack = attack_flags(stages)
    flags = attack if source == "attack" else compromise_flags(stages, int(COMPROMISE_THRESHOLD))
    onsets = episode_onsets(flags, gap=gap)

    stage_values = stages.to_numpy()
    families = [Stage(int(stage_values[o])).name for o in onsets]

    return EpisodeLabels(
        onsets=onsets,
        families=families,
        onset_now=onset_flags(onsets, len(attack)),
        precursor=precursor_flags(onsets, attack, horizon),
        # An alarm sitting inside the *previous* episode's traffic is detection, not foresight.
        # Wednesday's onsets 219 and 309 have 6 of their 10 pre-onset windows inside the run before
        # them, so without this mask a pure detector is credited with warning early twice.
        eligible=~attack,
    )
