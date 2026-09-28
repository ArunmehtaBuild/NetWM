"""D-042: does host-local temporal state (arm H) fix E25b's cross-family inversions against the same stack
on the global state alone (arm G)? The rule is decisions.md D-042's, pushed before any run.

    python scripts/d042_compare.py

- ROC-AUC of the stored ``comp`` score on ``y_within_K``, per held-out scenario and seed (the E25b
  scorer, ``ctu_family_matrix.scenario_rows``, unchanged).
- **H helps on a scenario** if ROC(H) - ROC(G) >= +0.10 on >= 2 of 3 seeds, paired by seed.
- **"Host-local state helps"** only if H helps on >= 2 of the 3 deciding scenarios (s08, s07, s11) and
  no scenario where G has ROC >= 0.70 on >= 2 seeds has H below 0.70 on >= 2 seeds.
- Reported beside it, not deciding: D-037's family verdicts for G and H, S2* / S3, LR on each input set,
  G against E25b (the positional change alone), and a paired block-bootstrap interval (blocks of 20
  windows, 2,000 resamples) on each seed's H - G difference, from the same resamples for both arms.

Writes results/tables/d042_{scenarios,paired,families}.csv and results/runs/d042-compare/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctu_family_matrix import classify, scenario_rows
from netwm.bootstrap import block_bootstrap_auc
from netwm.data.processed import ProcessedDataset
from netwm.utils import TABLES, ensure_dirs, git_sha, save_run, set_seed
from scorecard import load_scores

SEEDS = (42, 43, 44)
DECIDING = ("s08", "s07", "s11")
HELP, BAR = 0.10, 0.70
BLOCK, N_BOOT = 20, 2000
ARMS = {"G (global, 56)": [f"d042-g-s{s}" for s in SEEDS], "H (global + host-local, 62)": [f"d042-h-s{s}" for s in SEEDS],
        "E25b (global, interp)": [f"e25-ctu13-s{s}" for s in SEEDS]}
LR = {"LR G": "lr-d042-g", "LR H": "lr-d042-h"}


def main() -> None:
    set_seed(42)
    ensure_dirs()
    ds = ProcessedDataset("data/processed/ctu13_hostrel")
    rows = []
    for arm, runs in ARMS.items():
        for seed, run in zip(SEEDS, runs):
            rows += [{**r, "arm": arm, "seed": seed} for r in scenario_rows(run, "world model", ds)]
    for arm, run in LR.items():
        rows += [{**r, "arm": arm, "seed": None} for r in scenario_rows(run, "logistic regression", ds)]
    table = pd.DataFrame(rows)

    g_arm, h_arm = list(ARMS)[:2]
    roc = table.pivot_table(index="scenario", columns=["arm", "seed"], values="roc_auc")
    paired, scen_rows = [], []
    for i, scen in enumerate(ds.splits):
        y = ds.target(scen).astype(int)
        d = np.array([roc[(h_arm, s)][scen] - roc[(g_arm, s)][scen] for s in SEEDS])
        g = np.array([roc[(g_arm, s)][scen] for s in SEEDS])
        h = np.array([roc[(h_arm, s)][scen] for s in SEEDS])
        for j, s in enumerate(SEEDS):
            series = {"G": load_scores(ARMS[g_arm][j])[scen]["comp"], "H": load_scores(ARMS[h_arm][j])[scen]["comp"]}
            boot = block_bootstrap_auc(y, series, BLOCK, N_BOOT, 42 + 100 * i + s)
            diff = boot["H"]["boot"] - boot["G"]["boot"]
            diff = diff[~np.isnan(diff)]
            paired.append({"scenario": scen, "seed": s, "roc_G": round(float(g[j]), 4), "roc_H": round(float(h[j]), 4),
                           "delta": round(float(d[j]), 4), "delta_lo": round(float(np.percentile(diff, 2.5)), 4),
                           "delta_hi": round(float(np.percentile(diff, 97.5)), 4)})
        scen_rows.append({
            "scenario": scen, "family": next(m["family"] for m in ds.meta["splits"] if m["split"] == scen),
            "deciding": scen in DECIDING, "windows": len(y), "background": int((y == 0).sum()),
            "roc_G": " / ".join(f"{v:.3f}" for v in g), "roc_H": " / ".join(f"{v:.3f}" for v in h),
            "delta": " / ".join(f"{v:+.3f}" for v in d),
            "helps": bool((d >= HELP).sum() >= 2),
            "g_transfers_here": bool((g >= BAR).sum() >= 2),
            "regresses": bool((g >= BAR).sum() >= 2 and (h < BAR).sum() >= 2),
            "roc_e25b": " / ".join(f"{roc[(list(ARMS)[2], s)][scen]:.3f}" for s in SEEDS),
        })
    scen_df = pd.DataFrame(scen_rows)
    lr_roc = table[table["arm"].isin(LR)].pivot_table(index="scenario", columns="arm", values="roc_auc")
    scen_df["roc_lr_G"] = scen_df["scenario"].map(lr_roc["LR G"]).round(4)
    scen_df["roc_lr_H"] = scen_df["scenario"].map(lr_roc["LR H"]).round(4)

    helps_on = [s for s in DECIDING if bool(scen_df.set_index("scenario").loc[s, "helps"])]
    regressions = scen_df[scen_df["regresses"]]["scenario"].tolist()
    result = "host-local state helps" if len(helps_on) >= 2 and not regressions else "does not help"
    fams = []
    for arm in ARMS:
        wm = table[table["arm"] == arm]
        for family, gf in wm.groupby("family"):
            fams.append({"arm": arm, "family": family, "verdict": classify(gf),
                         "roc_auc_mean": round(float(gf["roc_auc"].mean()), 3)})
    fam_df = pd.DataFrame(fams).pivot(index="family", columns="arm", values="verdict").reset_index()

    table.to_csv(TABLES / "d042_scenarios.csv", index=False)
    pd.DataFrame(paired).to_csv(TABLES / "d042_paired.csv", index=False)
    scen_df.to_csv(TABLES / "d042_scenario_matrix.csv", index=False)
    fam_df.to_csv(TABLES / "d042_families.csv", index=False)
    verdict = {"helps_on_deciding": helps_on, "regressions": regressions, "result": result}
    save_run("d042-compare", {"verdict": verdict, "scenarios": scen_rows, "paired": paired, "families": fams},
             config={"decision": "D-042", "deciding": DECIDING, "help_margin": HELP, "bar": BAR,
                     "block": BLOCK, "n_boot": N_BOOT, "git_sha_at_start": git_sha()})
    pd.set_option("display.width", 250)
    print(scen_df.to_string(index=False))
    print("\n" + fam_df.to_string(index=False))
    print(f"\nD-042: H helps on {helps_on} of {list(DECIDING)}; regressions {regressions} -> {result}")


if __name__ == "__main__":
    main()
