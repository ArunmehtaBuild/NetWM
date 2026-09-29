"""Figures for the served (frozen) models, from stored per-window scores only. Nothing retrained or rescored.

    python scripts/served_figures.py

Writes results/figures/served/fig1_thursday_timeline.png (risk, causal threshold and alarms on the held-out
Thursday for both routes and logistic regression), fig2_benchmark_vs_lr.png and fig3_training_curves.png.

Reads results/runs/{n8-r2w-s42, n8-e20rw-mean, lr-flow-s42}/metrics.json and the processed Thursday labels,
recomputes the benchmark metrics exactly as scripts/benchmark_table.metrics does, and asserts they match
results/tables/n8_fix_eval.csv before drawing anything.
"""
import json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src")); sys.path.insert(0, str(REPO / "scripts"))
from netwm.data.processed import ProcessedDataset
from netwm.metrics import causal_threshold
from benchmark_table import metrics

OUT = REPO / "results" / "figures" / "served"; OUT.mkdir(parents=True, exist_ok=True)
RUNS, TABLES = REPO / "results" / "runs", REPO / "results" / "tables"

SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
CSV_C, PCAP_C, LR_C, LABEL_BG = "#2a78d6", "#eb6834", "#6f6e69", "#f3dcdc"
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID, "figure.facecolor": SURF,
                     "axes.facecolor": SURF, "savefig.facecolor": SURF, "axes.spines.top": False,
                     "axes.spines.right": False})


def scores(run, day="thursday"):
    m = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))
    return np.asarray((m.get("metrics") or m)["per_day"][day]["scores"], float)


ds_csv = ProcessedDataset(REPO / "data/processed/cicids2017")
ds_flow = ProcessedDataset(REPO / "data/processed/cicids2017_m1v2")
ds_pcap = ProcessedDataset(REPO / "data/processed/cicids2017_m1v2p")
ROUTES = [  # label, run, dataset, colour
    ("NetWM, CSV route (r2w seed 42)", "n8-r2w-s42", ds_csv, CSV_C),
    ("NetWM, PCAP route (E20rw, mean of 3 seeds)", "n8-e20rw-mean", ds_pcap, PCAP_C),
    ("Logistic regression (PS baseline)", "lr-flow-s42", ds_flow, LR_C),
]

# ---- recompute and check against the frozen table -------------------------------------------------
ref = pd.read_csv(TABLES / "n8_fix_eval.csv")
got = {}
for label, run, ds, _ in ROUTES:
    got[run] = {d: metrics(ds.target(d), scores(run, d)) for d in ("thursday", "friday")}
    row = ref[(ref.run == run) & (ref.day == "thursday")]
    if len(row):
        for k in ("f1", "precision", "recall", "fpr", "pr_auc"):
            assert abs(row[k].iloc[0] - got[run]["thursday"][k]) < 1e-9, (run, k)
lr = got["lr-flow-s42"]["thursday"]
assert (round(lr["pr_auc"], 3), round(lr["f1"], 3)) == (0.139, 0.112), lr
print("metrics match n8_fix_eval.csv and the README's LR row")

# ---- 1. held-out Thursday timeline ------------------------------------------------------------------
frame = ds_csv.frame("thursday")
ts = pd.to_datetime(frame["ts"])
y = ds_csv.target("thursday").astype(bool)
onsets = ds_csv.onsets("thursday")
for _, _, ds, _ in ROUTES:
    assert (ds.target("thursday").astype(bool) == y).all()

fig, axes = plt.subplots(3, 1, figsize=(16, 9), sharex=True, gridspec_kw={"hspace": 0.28})
for ax, (label, run, ds, colour) in zip(axes, ROUTES):
    s = scores(run)
    thr = causal_threshold(s, 0.90)
    alarm = s >= thr
    # label: compromise within the next 10 windows
    runs_ = np.flatnonzero(np.diff(np.r_[0, y.astype(int), 0]))
    for a, b in zip(runs_[::2], runs_[1::2]):
        ax.axvspan(ts.iloc[a], ts.iloc[b - 1], color=LABEL_BG, lw=0, zorder=0)
    for o in onsets:
        ax.axvline(ts.iloc[o], color="#c23b3b", lw=1, ls=(0, (2, 2)), zorder=1)
    ax.plot(ts, s, color=colour, lw=1.6, zorder=3)
    ax.plot(ts, np.where(np.isfinite(thr), thr, np.nan), color=INK2, lw=1.1, ls=(0, (5, 3)), zorder=2)
    ax.scatter(ts[alarm], s[alarm], s=16, color=colour, edgecolor=SURF, linewidth=0.8, zorder=4)
    m = got[run]["thursday"]
    ax.set_title(f"{label}    PR-AUC {m['pr_auc']:.3f} · F1 {m['f1']:.3f} · precision {m['precision']:.3f}"
                 f" · recall {m['recall']:.3f} · FPR {m['fpr']:.3f}", loc="left", fontsize=12, color=INK, pad=6)
    ax.set_ylabel("risk score")
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.set_ylim(bottom=0)
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
axes[-1].set_xlabel("time on the held-out Thursday (CIC-IDS2017), 60 s windows at a 30 s stride")
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
handles = [Patch(color=LABEL_BG, label="ground truth: compromise within the next 5 min"),
           Line2D([], [], color="#c23b3b", lw=1, ls=(0, (2, 2)), label="attack onset"),
           Line2D([], [], color=INK2, lw=1.1, ls=(0, (5, 3)), label="causal threshold (90th pct of earlier scores)"),
           Line2D([], [], marker="o", color=INK2, lw=0, markersize=5, label="alarm")]
fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.995), fontsize=11)
fig.suptitle("")
fig.savefig(OUT / "fig1_thursday_timeline.png", dpi=200, bbox_inches="tight")
plt.close(fig)

# ---- 2. benchmark bars --------------------------------------------------------------------------------
cols = [("pr_auc", "PR-AUC"), ("f1", "F1"), ("precision", "Precision"), ("recall", "Recall"), ("fpr", "FPR")]
fig, ax = plt.subplots(figsize=(13, 6.5))
x = np.arange(len(cols)); w = 0.26
for i, (label, run, _, colour) in enumerate(ROUTES):
    vals = [got[run]["thursday"][k] for k, _ in cols]
    bars = ax.bar(x + (i - 1) * w, vals, w - 0.03, color=colour, label=label, zorder=3)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.3f}", ha="center", va="bottom", fontsize=10, color=INK)
ax.axvline(3.5, color=GRID, lw=1)
ax.text(4, 0.74, "lower is better", ha="center", fontsize=10, color=MUTED)
ax.text(1.5, 0.74, "higher is better", ha="center", fontsize=10, color=MUTED)
ax.set_xticks(x, [c for _, c in cols], fontsize=12)
ax.set_ylim(0, 0.78); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=3, fontsize=11)
ax.set_title("Held-out Thursday, CIC-IDS2017 (leave-one-day-out) · same features, same causal threshold for every model",
             fontsize=11, color=INK2, pad=40, loc="left")
fig.savefig(OUT / "fig2_benchmark_vs_lr.png", dpi=200, bbox_inches="tight")
plt.close(fig)

# ---- 3. training curves -------------------------------------------------------------------------------
TERMS = [("recon", "next-state prediction (NLL)"), ("kl", "KL, prior vs posterior (free bits 1.0)"),
         ("compromise", "compromise risk, observed states"), ("imagine_compromise", "compromise risk, imagined states"),
         ("stage", "MITRE stage, observed states"), ("imagine_stage", "MITRE stage, imagined states")]
curves = {"CSV route (r2w seed 42)": (pd.read_csv(TABLES / "n8-r2w-s42_training_curves.csv"), CSV_C),
          "PCAP route (E20rw seed 42)": (pd.read_csv(TABLES / "m1v2-n8-e20rw-s42_training_curves.csv"), PCAP_C)}
fig, axes = plt.subplots(2, 3, figsize=(16, 8.5), gridspec_kw={"hspace": 0.42, "wspace": 0.22})
for ax, (col, title) in zip(axes.flat, TERMS):
    for name, (df, colour) in curves.items():
        d = df[df.test_day == "thursday"]
        ax.plot(d.epoch, d[col], color=colour, lw=2, label=name)
    ax.set_title(title, loc="left", fontsize=11.5)
    ax.grid(color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.set_xlabel("epoch", fontsize=10)
handles = [Line2D([], [], color=c, lw=2, label=n) for n, (_, c) in curves.items()]
fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.0), fontsize=11.5)
fig.text(0.5, -0.01, "Training losses per epoch for the fold that holds out Thursday (trained on the other four days).",
         ha="center", fontsize=10.5, color=INK2)
fig.savefig(OUT / "fig3_training_curves.png", dpi=200, bbox_inches="tight")
plt.close(fig)
print("wrote", *sorted(p.name for p in OUT.glob("*.png")))
