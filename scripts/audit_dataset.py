"""E1 - dataset audit: what is actually in the corrected CIC-IDS2017, before we model anything.

Outputs (see results.md):
  results/tables/e1_label_counts.csv    flows per label per day, with ATT&CK stage
  results/tables/e1_attack_timeline.csv observed first/last flow per label vs the official schedule
  results/tables/e1_window_stats.csv    window counts and stage distribution at 60 s / 30 s
  results/figures/e1_<day>_timeline.png attack flows per minute, by stage
  results/runs/e1-dataset-audit/metrics.json

Usage:
    python scripts/audit_dataset.py --data data/raw/cicids2017_improved
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.cicids2017 import ATTACK_SCHEDULE_UTC, CICIDS2017Adapter
from netwm.features.windowing import (
    WindowSpec,
    expand_to_windows,
    onset_windows,
    window_stage_matrix,
    window_stages,
)
from netwm.labels.mitre_map import COMPROMISE_THRESHOLD, STAGE_LABELS, Stage, map_label
from netwm.utils import FIGURES, TABLES, ensure_dirs, save_run

STAGE_COLORS = {
    0: "#9aa7b1",
    1: "#4c9be8",
    2: "#f2a541",
    3: "#e2574c",
    4: "#8e5bd9",
    5: "#2fa87a",
    6: "#6b6b6b",
}


def per_day_tables(df: pd.DataFrame, day: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Label counts and observed attack timing for one day."""
    counts = (
        df.groupby("label")
        .agg(flows=("label", "size"), stage=("stage", "first"), attempted=("attempted", "first"))
        .reset_index()
    )
    counts["stage_name"] = counts["stage"].map(lambda s: STAGE_LABELS[Stage(s)])
    counts["technique"] = counts["label"].map(lambda l: map_label(l).technique)
    counts["day"] = day
    counts["share_pct"] = (100 * counts["flows"] / len(df)).round(3)

    timing = (
        df[df["stage"] != 0]
        .groupby("label")["ts"]
        .agg(observed_first="min", observed_last="max", flows="size")
        .reset_index()
    )
    timing["day"] = day
    sched = pd.DataFrame(
        [{"scheduled_start": s, "scheduled_end": e, "attack": n} for s, e, n in ATTACK_SCHEDULE_UTC.get(day, [])]
    )
    if not sched.empty:
        timing = timing.merge(
            sched.assign(label=sched["attack"]), on="label", how="outer", suffixes=("", "_sched")
        )
    return counts, timing


def plot_day(df: pd.DataFrame, day: str, spec: WindowSpec) -> Path:
    """Attack flows per minute, coloured by ATT&CK stage - the ground-truth attack timeline."""
    per_min = (
        df.assign(minute=df["ts"].dt.floor("min"))
        .groupby(["minute", "stage"])
        .size()
        .unstack(fill_value=0)
    )
    fig, ax = plt.subplots(figsize=(12, 3.2), dpi=140)
    bottom = None
    for stage in sorted(c for c in per_min.columns if c != 0):
        vals = per_min[stage].to_numpy()
        ax.bar(
            per_min.index,
            vals,
            bottom=bottom,
            width=1 / 1440,
            color=STAGE_COLORS.get(int(stage), "#333"),
            label=STAGE_LABELS[Stage(int(stage))],
        )
        bottom = vals if bottom is None else bottom + vals
    # attack volumes span 4 orders of magnitude (13 SQLi flows vs 4k portscan flows/min), so a
    # linear axis hides the small-but-important attacks - symlog keeps both visible.
    ax.set_yscale("symlog", linthresh=10)
    for start, end, name in ATTACK_SCHEDULE_UTC.get(day, []):
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end), color="#000", alpha=0.06, lw=0)
    ax.set_title(f"CIC-IDS2017 (corrected) - {day.capitalize()}: attack flows per minute (UTC), "
                 f"shaded = official schedule")
    ax.set_ylabel("flows / min (symlog)")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=7, ncol=4, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    out = FIGURES / f"e1_{day}_timeline.png"
    fig.savefig(out)
    plt.close(fig)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/raw/cicids2017_improved")
    ap.add_argument("--window-s", type=float, default=60.0)
    ap.add_argument("--stride-s", type=float, default=30.0)
    ap.add_argument("--nrows", type=int, default=None, help="debug: rows per day")
    args = ap.parse_args()

    ensure_dirs()
    spec = WindowSpec(args.window_s, args.stride_s)
    adapter = CICIDS2017Adapter(args.data)

    counts_all, timing_all, window_all = [], [], []
    metrics: dict = {"days": {}, "window_spec": {"length_s": spec.length_s, "stride_s": spec.stride_s}}

    for day in adapter.splits():
        df = adapter.load(day, nrows=args.nrows)
        counts, timing = per_day_tables(df, day)
        counts_all.append(counts)
        timing_all.append(timing)

        expanded, t0 = expand_to_windows(df, spec)
        stages = window_stages(expanded)
        onsets = onset_windows(stages, int(COMPROMISE_THRESHOLD))
        dist = stages.value_counts().reindex(range(7), fill_value=0)
        # multi-label view: how many windows contain each stage at all (D-010). The gap between the
        # two columns is exactly how much information the "most advanced stage" label throws away.
        mat = window_stage_matrix(expanded)
        window_all.append(
            pd.DataFrame(
                {
                    "day": day,
                    "stage": range(7),
                    "stage_name": [STAGE_LABELS[Stage(s)] for s in range(7)],
                    "windows_dominant": dist.to_numpy(),
                    "windows_present": [int(mat[Stage(s).name].sum()) for s in range(7)],
                }
            )
        )
        plot_day(df, day, spec)

        metrics["days"][day] = {
            "flows": int(len(df)),
            "attack_flows": int((df["stage"] != 0).sum()),
            "attack_share_pct": round(100 * float((df["stage"] != 0).mean()), 3),
            "attempted_flows": int(df["attempted"].sum()),
            "first_ts": str(df["ts"].min()),
            "last_ts": str(df["ts"].max()),
            "windows": int(len(stages)),
            "benign_windows": int((stages == 0).sum()),
            "compromise_onsets": onsets,
            "onset_times": [str(spec.window_start(t0, w)) for w in onsets],
        }
        print(f"{day:10s} flows={len(df):>8,} attack={metrics['days'][day]['attack_share_pct']:>6.2f}% "
              f"windows={len(stages):>5,} onsets={len(onsets)}")

    pd.concat(counts_all).to_csv(TABLES / "e1_label_counts.csv", index=False)
    pd.concat(timing_all).to_csv(TABLES / "e1_attack_timeline.csv", index=False)
    pd.concat(window_all).to_csv(TABLES / "e1_window_stats.csv", index=False)
    save_run("e1-dataset-audit", metrics, config=vars(args))
    print("\nwrote results/tables/e1_*.csv, results/figures/e1_*_timeline.png, results/runs/e1-dataset-audit/")


if __name__ == "__main__":
    main()
