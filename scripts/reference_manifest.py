"""Freeze the M1 reference models before the combined run (D-037, Step 1).

    python scripts/reference_manifest.py --tag reference-m1-2026-09-28

Writes ``results/runs/<tag>/manifest.json`` and ``results/tables/<tag>.csv``. Every value is read from
stored artefacts: the checkpoints (config, feature schema, scaler, parameter count, the git SHA each
was trained at), the scorecard CSVs and run folders. Nothing is typed in. The references are named so
the next experiment is a controlled continuation, not a moving target:

  r2    - the shipped detection model (Thursday/Friday folds, seed 42; E14/E18 numbers)
  E19   - the r2 method on all five folds x three seeds, the scorecard's flow-only baseline
  E22   - the reference anticipation model (factorised target, the final D-035 stack)
  E20r  - the reference packet-feature model (flow + CSV packet block + real-capture packets)
  E24a  - Model A (no latent dynamics), the world-model control
  E25   - CTU-13 leave-one-family-out, seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.utils import RUNS, TABLES, git_sha

REFERENCES = {
    "r2": {"role": "shipped detection reference", "runs": ["e4e7-worldmodel-r2"], "config": "configs/cicids2017.yaml",
           "data": "data/processed/cicids2017", "split": "leave-one-day-out, Thursday and Friday folds"},
    "E19": {"role": "r2 method, scorecard flow-only baseline", "runs": [f"m1v2-e19-s{s}" for s in (42, 43, 44)],
            "config": "configs/m1v2/e19_base.yaml", "data": "data/processed/cicids2017_m1v2", "scorecard": "e19"},
    "E22": {"role": "reference anticipation model (final D-035 stack)", "runs": [f"m1v2-e22-s{s}" for s in (42, 43, 44)],
            "config": "configs/m1v2/e22_factorized.yaml", "data": "data/processed/cicids2017_m1v2", "scorecard": "e22"},
    "E20r": {"role": "reference packet-feature model", "runs": [f"m1v2-e20r-s{s}" for s in (42, 43, 44)],
             "config": "configs/m1v2/e20r_pcap.yaml", "data": "data/processed/cicids2017_m1v2p", "scorecard": "e20r"},
    "E24a": {"role": "Model A: no latent dynamics (world-model control)", "runs": [f"m1v2-e24a-s{s}" for s in (42, 43, 44)],
             "config": "configs/m1v2/e24_modelA_nocurr.yaml", "data": "data/processed/cicids2017_m1v2", "scorecard": "e24"},
    "E25": {"role": "CTU-13 leave-one-family-out", "runs": ["e25-ctu13-s42"], "config": "configs/m1v2/e25_ctu13.yaml",
            "data": "data/processed/ctu13", "scorecard": "e25", "split": "leave-one-family-out, 7 families"},
}
SCORE_COLS = ["S1_precision", "S1_fpr", "S2_0-2min", "S2_2-4min", "S2_4-6min", "S2_6-10min", "S2_star",
              "diag_S2_star_isolated", "S4_worst_day", "S3_warned", "S3_fisher_p", "S3_passes",
              "thursday_comp_pr_auc", "thursday_causal_f1", "friday_comp_pr_auc", "friday_causal_f1"]


def trained_sha(run: str, fold: str, ckpt_sha: str) -> str:
    """The SHA a checkpoint was trained at. Before D-037's fix, --resume re-saved checkpoints with the
    resume-time SHA; the interrupted log still records the training SHA, so prefer it when present."""
    log = RUNS / "m1v2-sweep-logs" / f"{run}.interrupted.log"
    if log.exists():
        m = re.search(rf"resumed: .*{fold}\.pt \(trained at (\w+)\)", (RUNS / "m1v2-sweep-logs" / f"{run}.log").read_text(errors="ignore"))
        if m:
            return m.group(1)
    return ckpt_sha


def describe_run(run: str) -> dict:
    folds = {}
    for ckpt_path in sorted(Path("models", run).glob("*.pt")):
        c = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        names = list(c["feature_names"])
        folds[ckpt_path.stem] = {
            "git_sha_trained": trained_sha(run, ckpt_path.stem, str(c.get("git_sha"))),
            "params": int(sum(v.numel() for v in c["model_state"].values())),
            "n_inputs": int(c["model_config"]["n_features"]),
            "arch": c["model_config"].get("arch", "rssm"),
            "hazard": c["model_config"].get("hazard", "direct"),
            "scaler_mode": getattr(c["scaler"], "mode", "log_standard"),
            "n_features": len(names),
            "feature_schema_sha1": hashlib.sha1("\n".join(names).encode()).hexdigest()[:12],
            "train_days": c.get("train_days"),
            "test_days": c.get("test_days", [c.get("test_day")]),
            "threshold_policy_stored": c.get("threshold_policy", "train-tuned (evaluation uses the causal expanding q90)"),
        }
    meta = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))
    return {"run": run, "seed": (meta.get("config") or {}).get("seed"), "run_git_sha": meta.get("git_sha"),
            "folds": folds}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tag", default="reference-m1-2026-09-28")
    args = ap.parse_args()

    manifest = {"tag": args.tag, "git_sha": git_sha(), "threshold_policy": "causal expanding q90, 20-window warm-up (D-034)",
                "scorecard": "D-035 S1-S4 (scripts/scorecard.py)", "references": {}}
    rows = []
    for name, ref in REFERENCES.items():
        entry = {**ref, "runs_detail": [describe_run(r) for r in ref["runs"]]}
        if "scorecard" in ref:
            sc = pd.read_csv(TABLES / f"scorecard_{ref['scorecard']}.csv")
            variant = {"E24a": "A"}.get(name, name)
            sc = sc[sc["variant"] == variant]
            entry["scorecard_rows"] = sc[[c for c in ["run", "seed", *SCORE_COLS] if c in sc]].to_dict("records")
            for _, r in sc.iterrows():
                rows.append({"reference": name, "run": r["run"], "seed": r["seed"],
                             **{c: r[c] for c in SCORE_COLS if c in r}})
        if name == "r2":
            e18 = json.loads((RUNS / "e18-causal-threshold-e4e7-worldmodel-r2" / "metrics.json").read_text())["metrics"]["rows"]
            e14 = json.loads((RUNS / "e14-pmax-rescore-e4e7-worldmodel-r2" / "metrics.json").read_text())["metrics"]["rows"]
            entry["accepted_numbers"] = {
                "thursday_causal": next(r for r in e18 if r["run"] == "e4e7-worldmodel-r2" and r["test_day"] == "thursday" and r["policy"] == "expanding-10pct"),
                "thursday_pr_auc": next(r["pr_auc"] for r in e14 if r["test_day"] == "thursday" and r["threshold_mode"] == "self-budget-10pct"),
                "friday_causal": next(r for r in e18 if r["run"] == "e4e7-worldmodel-r2" and r["test_day"] == "friday" and r["policy"] == "expanding-10pct"),
            }
        manifest["references"][name] = entry
    out = RUNS / args.tag
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(rows).to_csv(TABLES / f"{args.tag}.csv", index=False)
    for name, e in manifest["references"].items():
        d = e["runs_detail"][0]["folds"]
        f0 = next(iter(d.values()))
        print(f"{name:5s} {e['role'][:48]:48s} params={f0['params']:>7,} inputs={f0['n_inputs']:>3} "
              f"{f0['arch']}/{f0['hazard']}/{f0['scaler_mode']} schema={f0['feature_schema_sha1']} "
              f"trained_at={sorted({v['git_sha_trained'] for r in e['runs_detail'] for v in r['folds'].values()})}")
    print(f"wrote {out}/manifest.json and results/tables/{args.tag}.csv")


if __name__ == "__main__":
    main()
