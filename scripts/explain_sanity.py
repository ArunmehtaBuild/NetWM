"""E11 (G-7) - do the dashboard's explanations point at the attack? (bar pre-registered in D-035)

    python scripts/explain_sanity.py --run e4e7-worldmodel-r2

For six held-out episodes, runs the dashboard's own Integrated-Gradients attribution
(``engine/explain.explain_window``, unchanged) on up to 24 evenly spaced attack windows, ranks the
features by mean |attribution|, and counts how many of the episode's signature features - written
down in D-035 before this ran - land in the top 8. The hypergeometric p-value says how often a random
top 8 would do as well. An episode passes at p < 0.05; E11 passes if >= 4 of 6 episodes pass.

Two controls that do not gate: the same hit count for a ranking by mean |scaled value| (does IG say
anything beyond "these features are unusual right now"?), and the Spearman correlation between the
two rankings.

Outputs: results/tables/e11_<run>_episodes.csv, e11_<run>_rankings.csv,
results/figures/e11_<run>.png, results/runs/e11-<run>/metrics.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import hypergeom, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.explain import explain_window
from netwm.engine.predict import load_checkpoint
from netwm.labels.mitre_map import Stage
from netwm.utils import FIGURES, TABLES, ensure_dirs, save_run, set_seed

TOP = 8
MAX_WINDOWS = 24
SCAN = ("uniq_dst_port", "dst_port_entropy", "port_fanout_max", "ports_per_pair_max", "seq_port_ratio",
        "syn_no_ack_rate", "has_rst_rate", "tiny_flow_rate", "one_way_rate", "rst_cnt_sum", "syn_cnt_sum")

#: D-035, verbatim: (name, day, stage, UTC start, UTC end, signature)
EPISODES: tuple[tuple, ...] = (
    ("Thu 17:00 external port scan", "thursday", Stage.RECONNAISSANCE, "2017-07-06 17:00", "2017-07-06 17:03", SCAN),
    ("Thu internal sweep", "thursday", Stage.LATERAL_MOVEMENT, "2017-07-06 18:04", "2017-07-06 18:45",
     ("uniq_dst_ip", "fanout_max", "fanout_mean", "uniq_dst_port", "port_fanout_max", "ports_per_pair_max",
      "dst_ip_entropy", "dst_port_entropy", "n_flows", "flows_per_s", "top_talker_share", "syn_no_ack_rate",
      "has_rst_rate", "tiny_flow_rate", "is_internal_rate")),
    ("Thu web attacks", "thursday", Stage.INITIAL_ACCESS, "2017-07-06 12:20", "2017-07-06 13:42",
     ("svc_http_rate", "n_flows", "flows_per_s", "top_talker_share", "pkt_len_mean_mean", "pkt_len_max_max",
      "bytes_mean", "psh_cnt_sum", "is_inbound_rate")),
    ("Fri botnet C2 (Ares)", "friday", Stage.COMMAND_AND_CONTROL, None, None,
     ("beacon_score", "is_outbound_rate", "outbound_bytes", "byte_asymmetry", "svc_http_rate",
      "flow_iat_mean_mean", "flow_iat_std_mean", "duration_s_mean")),
    ("Fri port scan", "friday", Stage.RECONNAISSANCE, None, None, SCAN),
    ("Fri DDoS LOIC", "friday", Stage.IMPACT, None, None,
     ("flows_per_s", "n_flows", "pkts_per_s", "bytes_per_s", "svc_http_rate", "uniq_src_port",
      "is_inbound_rate", "syn_cnt_sum", "top_talker_share")),
)


def episode_windows(frame: pd.DataFrame, stage: Stage, start, end) -> np.ndarray:
    mask = frame["stage"].to_numpy() == int(stage)
    if start is not None:
        mask &= (frame["ts"] >= start).to_numpy() & (frame["ts"] < end).to_numpy()
    idx = np.flatnonzero(mask)
    if len(idx) > MAX_WINDOWS:
        idx = idx[np.linspace(0, len(idx) - 1, MAX_WINDOWS).round().astype(int)]
    return idx


def hits_and_p(ranking: list[str], signature: tuple, n_features: int) -> tuple[int, float]:
    hits = len(set(ranking[:TOP]) & set(signature))
    # P(X >= hits) drawing TOP of n_features, len(signature) of which are "successes"
    return hits, float(hypergeom.sf(hits - 1, n_features, len(signature), TOP))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="e4e7-worldmodel-r2")
    ap.add_argument("--data", default="data/processed/cicids2017")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    ds = ProcessedDataset(args.data)
    ckpts, xs = {}, {}
    rows, rank_rows = [], []
    for name, day, stage, start, end, signature in EPISODES:
        if day not in ckpts:
            ckpts[day] = load_checkpoint(Path("models", args.run, f"{day}.pt"))
            xs[day] = ckpts[day]["scaler"].transform(ds.frame(day)[ckpts[day]["feature_names"]])
        ckpt, x = ckpts[day], xs[day]
        names = list(ckpt["feature_names"])
        missing = set(signature) - set(names)
        if missing:
            raise SystemExit(f"{name}: signature features not in the state: {sorted(missing)}")
        idx = episode_windows(ds.frame(day), stage, start, end)
        attr = np.stack([explain_window(ckpt["model"], x, int(t), ds.horizon, ckpt["device"])["feature_attribution"]
                         for t in idx])
        ig = np.abs(attr).mean(axis=0)
        mag = np.abs(x[idx]).mean(axis=0)
        ig_rank = [names[i] for i in np.argsort(-ig)]
        mag_rank = [names[i] for i in np.argsort(-mag)]
        ig_hits, ig_p = hits_and_p(ig_rank, signature, len(names))
        mag_hits, mag_p = hits_and_p(mag_rank, signature, len(names))
        rho = float(spearmanr(ig, mag).statistic)
        rows.append({
            "episode": name, "test_day": day, "windows": int(len(idx)), "signature_size": len(signature),
            "ig_hits_top8": ig_hits, "ig_p": round(ig_p, 4), "passes": bool(ig_p < 0.05),
            "chance_hits": round(TOP * len(signature) / len(names), 2),
            "value_hits_top8": mag_hits, "value_p": round(mag_p, 4), "spearman_ig_vs_value": round(rho, 3),
            "ig_top8": ", ".join(ig_rank[:TOP]), "value_top8": ", ".join(mag_rank[:TOP]),
        })
        for r, f in enumerate(ig_rank):
            rank_rows.append({"episode": name, "rank": r + 1, "feature": f,
                              "mean_abs_attribution": float(ig[names.index(f)]),
                              "in_signature": f in signature})
        print(f"{name:32s} n={len(idx):2d} IG hits {ig_hits}/{TOP} p={ig_p:.4f} | |value| hits {mag_hits} "
              f"p={mag_p:.4f} | rho={rho:.2f}\n   IG top8: {', '.join(ig_rank[:TOP])}")

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / f"e11_{args.run}_episodes.csv", index=False)
    pd.DataFrame(rank_rows).to_csv(TABLES / f"e11_{args.run}_rankings.csv", index=False)
    passed = int(table["passes"].sum())
    verdict = {"episodes_passing": passed, "episodes": len(table), "e11_passes": passed >= 4}
    print(f"\nE11: {passed} of {len(table)} episodes pass (bar: >= 4) -> {'PASS' if passed >= 4 else 'FAIL'}")
    save_run(f"e11-{args.run}", {"verdict": verdict, "episodes": rows}, config={**vars(args), "top": TOP})
    plot(table, args.run)


def plot(table: pd.DataFrame, run: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=130)
    y = np.arange(len(table))
    ax.barh(y + 0.2, table["ig_hits_top8"], height=0.4, color="#2f6fdb", label="IG attribution (dashboard)")
    ax.barh(y - 0.2, table["value_hits_top8"], height=0.4, color="#bbb", label="|scaled value| (control)")
    ax.scatter(table["chance_hits"], y, marker="|", s=300, color="#e2574c", label="chance", zorder=3)
    ax.set_yticks(y, [f"{e} ({'pass' if p else 'fail'})" for e, p in zip(table["episode"], table["passes"])], fontsize=8)
    ax.set_xlabel(f"signature features in the top {TOP}")
    ax.set_title(f"E11 - do explanations point at the known signature? ({run})", fontsize=9)
    ax.legend(fontsize=7, loc="lower right")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(FIGURES / f"e11_{run}.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
