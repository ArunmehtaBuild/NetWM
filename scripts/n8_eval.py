"""D-041's gates for the N-8 fix, scored from stored outputs and the new checkpoints. Nothing is tuned.

    python scripts/n8_eval.py

The gates were pushed before any run (decisions.md D-041, 1c78e49):

- **G1, correctness** (this script's part): every checkpoint a route would serve uses
  ``pos_mode="window"``, and on its held-out day(s) the mean-path ``p_max`` from 60-window chunks with
  the state carried equals the one-pass ``p_max`` to max |diff| <= 1e-5. The unit tests and the
  backend's prefix-invariance test are the other two parts; results.md records them.
- **G2, PCAP route**: D-038's bar unchanged. The per-window mean of ``m1v2-n8-e20rw-s{42,43,44}``
  (written as the run ``n8-e20rw-mean``) needs Thursday PR-AUC >= 0.20 and S2* >= E19's S2* - 0.03,
  scored by ``scorecard.score_run`` and ``benchmark_table.metrics`` exactly as E27 was.
- **G3, CSV route**: ``n8-r2w-s42`` needs Thursday PR-AUC >= 0.540 and Thursday causal F1 >= 0.508.

Reported, not gated: E20rw seeds against E20r's (paired), r2w seeds 43/44, the ``n8-r2i-s42``
control against r2, Friday, and the rollout gain.

Writes results/runs/n8-e20rw-mean/, results/runs/n8-fix-eval/ and results/tables/n8_fix_eval{.csv,.md}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ablation_matrix import rollout_gain
from benchmark_table import metrics
from netwm.data.processed import ProcessedDataset
from netwm.models.world_model import WorldModelConfig, build_model
from netwm.utils import RUNS, TABLES, ensure_dirs, git_sha, save_run, set_seed
from scorecard import load_scores, score_run

SEEDS = (42, 43, 44)
E20RW = [f"m1v2-n8-e20rw-s{s}" for s in SEEDS]
E20R = [f"m1v2-e20r-s{s}" for s in SEEDS]
E19 = [f"m1v2-e19-s{s}" for s in SEEDS]
ENSEMBLE_RUN = "n8-e20rw-mean"
R2W = [f"n8-r2w-s{s}" for s in SEEDS]
R2I = "n8-r2i-s42"
PACKET_DATA, FLOW_DATA, R2_DATA = ("data/processed/cicids2017_m1v2p", "data/processed/cicids2017_m1v2",
                                   "data/processed/cicids2017")
DAYS = ("thursday", "friday")
CHUNK = 60
TOL = 1e-5
N_SHIFTS = 2000
G2_PR, G2_S2_MARGIN = 0.20, 0.03
G3_PR, G3_F1 = 0.540, 0.508


def chunk_parity(ckpt: Path, ds: ProcessedDataset, device: torch.device) -> list[dict]:
    """One-pass vs chunked (state carried) mean-path p_max on each held-out day of one checkpoint."""
    ck = torch.load(ckpt, map_location=device, weights_only=False)
    model = build_model(WorldModelConfig(**ck["model_config"])).to(device).eval()
    model.load_state_dict(ck["model_state"])
    out = []
    for day in ck.get("test_days") or [ck["test_day"]]:
        x = np.asarray(ck["scaler"].transform(ds.frame(day)[ck["feature_names"]]), dtype=np.float32)
        t = torch.from_numpy(x).unsqueeze(0).to(device)
        one = model.forecast(t, sample=False)["p_max"].numpy()
        parts, carry = [], None
        for a in range(0, len(x), CHUNK):
            o = model.forecast(t[:, a:a + CHUNK], sample=False, carry=carry, return_carry=True)
            carry = o["carry"]
            parts.append(o["p_max"].numpy())
        diff = float(np.max(np.abs(np.concatenate(parts) - one)))
        out.append({"checkpoint": str(ckpt).replace("\\", "/"), "day": day, "windows": len(x),
                    "pos_mode": ck["model_config"].get("pos_mode", "interp"), "max_abs_diff": diff,
                    "passes": bool(ck["model_config"].get("pos_mode") == "window" and diff <= TOL)})
    return out


def write_ensemble_run() -> None:
    """D-038's aggregation, unchanged: the per-window arithmetic mean of the three seeds' stored scores."""
    members = [json.loads((RUNS / r / "metrics.json").read_text(encoding="utf-8"))["metrics"]["per_day"] for r in E20RW]
    days = sorted(members[0])
    if any(sorted(m) != days for m in members):
        raise SystemExit("the E20rw runs do not cover the same held-out days")
    per_day = {d: {k: np.mean([np.asarray(m[d][k], float) for m in members], axis=0).tolist()
                   for k in ("scores", "threat_scores")} | {"members": E20RW} for d in days}
    save_run(ENSEMBLE_RUN, {"per_day": per_day, "complete": True,
                            "aggregation": "arithmetic mean over seeds 42/43/44, per window (D-038, D-041)",
                            "alarm_statistic": "p_max over 16 Monte-Carlo rollouts, as each seed's run stored it"},
             config={"decision": "D-041", "members": E20RW, "command": "python scripts/n8_eval.py"})


def main() -> None:
    set_seed(42)
    ensure_dirs()
    start_sha = git_sha()
    device = torch.device("cpu")  # parity is a numerical check; CPU keeps it deterministic
    packet, flow, r2data = ProcessedDataset(PACKET_DATA), ProcessedDataset(FLOW_DATA), ProcessedDataset(R2_DATA)

    # ---- G1: chunked == one pass on the real held-out days, for every checkpoint a route would serve
    parity = []
    for run in E20RW:
        for p in sorted((Path("models") / run).glob("*.pt")):
            parity += chunk_parity(p, packet, device)
    for p in sorted((Path("models") / R2W[0]).glob("*.pt")):
        parity += chunk_parity(p, r2data, device)
    g1 = bool(parity) and all(r["passes"] for r in parity)

    # ---- G2: the PCAP route, D-038's bar unchanged
    write_ensemble_run()
    cards = []
    for label, run, ds in ([("E19", r, flow) for r in E19] + [("E20r", r, packet) for r in E20R]
                           + [("E20rw", r, packet) for r in E20RW] + [("E20rw mean", ENSEMBLE_RUN, packet)]):
        sc = {"model": label, **score_run(run, ds, N_SHIFTS)}
        if run != ENSEMBLE_RUN:
            sc["rollout_gain_thursday"], sc["rollout_gain_friday"] = rollout_gain(run, "thursday"), rollout_gain(run, "friday")
        cards.append(sc)
    cards_df = pd.DataFrame(cards)
    ens = cards_df[cards_df["run"] == ENSEMBLE_RUN].iloc[0]
    e19_s2 = float(cards_df[cards_df["model"] == "E19"]["S2_star"].mean())
    g2 = {"thursday_pr_auc": float(ens["thursday_comp_pr_auc"]), "S2_star": float(ens["S2_star"]),
          "e19_S2_star": e19_s2, "bar_S2_star": e19_s2 - G2_S2_MARGIN,
          "passes": bool(ens["thursday_comp_pr_auc"] >= G2_PR and ens["S2_star"] >= e19_s2 - G2_S2_MARGIN)}

    # ---- G3: the CSV route, and every per-day detection row
    det = []
    for label, run, ds in ([("E20r", r, packet) for r in E20R] + [("E20rw", r, packet) for r in E20RW]
                           + [("E20rw mean", ENSEMBLE_RUN, packet)] + [("r2w", r, r2data) for r in R2W]
                           + [("r2i (control)", R2I, r2data)]):
        comp = load_scores(run)
        det += [{"model": label, "run": run, "day": d, **metrics(ds.target(d), comp[d]["comp"])} for d in DAYS]
    bench = pd.read_csv(TABLES / "benchmark_final.csv")
    det += [{**r, "model": "r2 (shipped)"} for r in bench[bench["model"] == "NetWM r2 - shipped checkpoint"].to_dict("records")]
    det_df = pd.DataFrame(det)
    r2w42 = det_df[(det_df["run"] == R2W[0]) & (det_df["day"] == "thursday")].iloc[0]
    g3 = {"thursday_pr_auc": float(r2w42["pr_auc"]), "thursday_f1": float(r2w42["f1"]),
          "passes": bool(r2w42["pr_auc"] >= G3_PR and r2w42["f1"] >= G3_F1)}

    verdict = {"G1_chunked_equals_one_pass": g1, "G2_pcap_route": g2, "G3_csv_route": g3,
               "pcap_route_serves": "E20rw mean" if g1 and g2["passes"] else "E20r mean (unchanged)",
               "csv_route_serves": "r2w seed 42" if g1 and g3["passes"] else "r2 (unchanged)"}
    pd.DataFrame(parity).to_csv(TABLES / "n8_fix_parity.csv", index=False)
    det_df.to_csv(TABLES / "n8_fix_eval.csv", index=False)
    cards_df.to_csv(TABLES / "n8_fix_scorecard.csv", index=False)
    save_run("n8-fix-eval", {"verdict": verdict, "parity": parity, "detection": det, "scorecard": cards},
             config={"decision": "D-041", "chunk": CHUNK, "tol": TOL, "git_sha_at_start": start_sha,
                     "command": "python scripts/n8_eval.py"})
    print(det_df.groupby(["model", "day"], sort=False)[["f1", "precision", "recall", "fpr", "pr_auc"]].mean().round(3))
    print(cards_df[["model", "run", "S1_precision", "S1_fpr", "S2_star", "thursday_comp_pr_auc", "S3_warned",
                    "S3_fisher_p"]].to_string(index=False))
    print(f"G1 parity: {len(parity)} checkpoint-days, max |diff| {max(r['max_abs_diff'] for r in parity):.2e}")
    print(json.dumps(verdict, indent=1))


if __name__ == "__main__":
    main()
