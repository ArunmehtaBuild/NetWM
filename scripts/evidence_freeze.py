"""The M1-M3 evidence freeze: what the submission's scientific conclusions rest on, content-hashed.

    python scripts/checkpoint_hashes.py --runs <every local run below>     # on this machine
    python scripts/checkpoint_hashes.py --runs e25-ctu13-s43 e25-ctu13-s44 # on the RTX 4060 (the only copy)
    python scripts/evidence_freeze.py                                      # then tag m1-m3-evidence-freeze

This is the final *evidence* freeze. D-045 (N-7) keeps the architecture and starts no further training
run, so nothing after this tag adds evidence; the documentation and submission artefacts that follow cite
it. The earlier M1/M2 freeze is the tag ``m1-m2-evidence-freeze``, built by this script as it stood there.
It records, from stored artefacts only:

- **M1 (CIC-IDS2017).** The models each route serves after D-041 (CSV: r2w seed 42; PCAP: the E20rw
  mean of seeds 42/43/44, D-038's aggregation) with the gate verdict that licensed them; the models
  they replaced (r2, the E20r seeds); seed, config files, feature schema, checkpoint SHA-256 and the
  git SHA each was trained at; the threshold policy.
- **M2 (CTU-13).** E25b's runs (seeds 42/43/44) and LR, its tables and confidence intervals, and
  D-042's arms, LR, comparison and decision.
- **M3 (CIC-IDS2018).** E28's runs (seeds 42/43/44) and LR, its tables, intervals and verdicts, the
  inspection, build and chain logs; both builds hashed, and they must be identical.
- **The architecture decision** (D-045) and the items still open (N-9).
- **Data.** SHA-256 of the processed matrices and the raw inputs they were built from.
- **Every artefact results.md quotes**, checked to exist and hashed; and every tracked file under results/.

Checkpoint hashes are read from ``results/runs/<run>/checkpoints_manifest.json``, written on the
machine that holds the weights (``scripts/checkpoint_hashes.py``). Nothing is copied between machines.
A checkpoint counts as the run's only if it was trained at the run's recorded start SHA; the stray
seed-43/44 ``neris.pt`` on the GTX 1650 (an earlier run, see results.md "N-8 x E25b") fails that check.

Writes ``results/runs/m1-m3-evidence-freeze/manifest.json`` and ``files.csv``; prints whether it is
ready to tag.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.freeze import check_references, machine_info, sha256_file
from netwm.utils import RUNS, git_sha

TAG = "m1-m3-evidence-freeze"
SEEDS = (42, 43, 44)
E20RW = [f"m1v2-n8-e20rw-s{s}" for s in SEEDS]
E20R = [f"m1v2-e20r-s{s}" for s in SEEDS]
E25B = [f"e25-ctu13-s{s}" for s in SEEDS]
D042 = [f"d042-{a}-s{s}" for a in "gh" for s in SEEDS]
M3_RUNS = [f"m3-s{s}" for s in SEEDS]
#: weights that exist only on the RTX 4060 - their hashes must come from there
ONLY_ON_4060 = {"e25-ctu13-s43", "e25-ctu13-s44"}

THRESHOLD_POLICY = {
    "alarm_statistic": "p_max: the maximum over the K = 10 rollout steps of the compromise hazard, on the "
                       "deterministic mean path (E14, D-019)",
    "threshold": "causal expanding 90th percentile of the score over windows before t, no alarm in the first "
                 "20 windows (netwm.metrics.causal_threshold, CAUSAL_WARMUP = 20; D-034)",
    "backend_policy": "expanding-10pct (backend/schemas.py)",
    "label": "y_within_K (an attack or compromise window within the next K = 10 windows)",
    "stored_train_tuned_thresholds": "recorded per checkpoint; not served",
}

M1 = {
    "served": {
        "csv_route": {"runs": ["n8-r2w-s42"], "decision": "D-041 gate G3 (r2's setup, window positions)",
                      "configs": ["configs/cicids2017.yaml", "configs/n8/r2_window.yaml"],
                      "data": "data/processed/cicids2017",
                      "folds_served": "Thursday by default, Friday on request (models/registry.json)"},
        "pcap_route": {"runs": E20RW, "decision": "D-038 aggregation, D-041 gate G2 (E20r with window positions)",
                       "configs": ["configs/n8/e20r_pcap_window.yaml"], "data": "data/processed/cicids2017_m1v2p",
                       "ensemble": "the arithmetic mean, per window, of the three seeds' outputs (netwm.engine."
                                   "predict._mean_outputs); members must share inputs, horizon, stride and fold",
                       "folds_served": "each seed's fold for a held-out demo day, else its Thursday fold "
                                       "(backend/inference.pcap_ensemble_paths)"},
        "gate_run": "n8-fix-eval",
    },
    "replaced": {
        "r2": {"runs": ["e4e7-worldmodel-r2"], "configs": ["configs/cicids2017.yaml"], "data": "data/processed/cicids2017",
               "served_until": "D-041 (26680d2); reproduced by the n8-r2i-s42 control"},
        "E20r": {"runs": E20R, "configs": ["configs/m1v2/e20r_pcap.yaml"], "data": "data/processed/cicids2017_m1v2p",
                 "served_until": "D-041 (26680d2); aggregation run e27-e20r-mean (D-038)"},
    },
    "tables": ["n8_fix_eval.csv", "n8_fix_scorecard.csv", "n8_fix_parity.csv", "benchmark_final.csv",
               "benchmark_final.md", "e27_pcap_route.csv", "e27_pcap_route_scorecard.csv"],
    "run_folders": ["n8-fix-eval", "n8-e20rw-mean", "n8-r2i-s42", "e27-e20r-mean", "e27-pcap-route",
                    "benchmark-final", "e14-pmax-rescore-e4e7-worldmodel-r2", "e18-causal-threshold-e4e7-worldmodel-r2"],
}

M2 = {
    "E25b": {"runs": E25B, "lr": ["lr-ctu13-s42"], "configs": ["configs/ctu13.yaml", "configs/m1v2/e25_ctu13.yaml",
                                                             "configs/ctu13_folds.yaml"],
             "data": "data/processed/ctu13",
             "tables": ["e25b_ctu13_scenarios.csv", "e25b_ctu13_scenario_matrix.csv", "e25b_ctu13_families.csv",
                        "ctu_ci_e25b.csv"],
             "run_folders": ["e25b-ctu13-matrix", "ctu-ci-e25b"]},
    "D-042": {"runs": D042, "lr": ["lr-d042-g", "lr-d042-h"],
              "configs": ["configs/ctu13_hostrel.yaml", "configs/d042/ctu_global_window.yaml",
                          "configs/d042/ctu_hostrel_window.yaml", "configs/ctu13_folds.yaml"],
              "data": "data/processed/ctu13_hostrel",
              "tables": ["d042_scenarios.csv", "d042_scenario_matrix.csv", "d042_paired.csv", "d042_families.csv",
                         "ctu_ci_d042-g.csv", "ctu_ci_d042-h.csv"],
              "run_folders": ["d042-compare", "ctu-ci-d042-g", "ctu-ci-d042-h"],
              "decision": "does not help (decisions.md D-042 outcome)"},
}
M3 = {
    "E28": {"runs": M3_RUNS, "lr": ["lr-m3"],
            "configs": ["configs/cicids2018.yaml", "configs/cicids2018_verify.yaml", "configs/cicids2018_folds.yaml",
                        "configs/m3/m3_stack.yaml"],
            "data": "data/processed/cicids2018", "verify_data": "data/processed/cicids2018_verify",
            "tables": ["e28_m3_days.csv", "e28_m3_families.csv", "e28_m3_ci.csv"],
            "run_folders": ["e28-m3-matrix", "m3-logs", "m3-build", "m3-inspect"],
            "decision": "D-037 verdicts: BruteForce and DoS transfer; DDoS, Web, Botnet partial; Infiltration "
                        "inverted (feb28). D-039's question inconclusive by D-044's rule; S3 met nowhere"},
}
RAW = ["data/raw/CICIDS2017_improved.zip", "data/raw/cicids2017_improved", "data/raw/ctu13"]
#: CIC-IDS2018 is read from where the build config points (an external drive), with the zip beside it
RAW_CONFIGS = ["configs/cicids2018.yaml"]
DECISIONS = ("D-019", "D-034", "D-035", "D-036", "D-037", "D-038", "D-039", "D-040", "D-041", "D-042", "D-044",
             "D-045")
OPEN_ITEMS = {
    "N-9": "live-PCAP parity: the upload converter's state still differs from the training matrix on a full "
           "capture (D-040), so no live-PCAP detection number is quoted (teamtasks.md N-9)",
}


def raw_inputs() -> list[str]:
    paths = list(RAW)
    for c in RAW_CONFIGS:
        raw = Path(yaml.safe_load(Path(c).read_text(encoding="utf-8"))["raw_dir"])
        paths += [z.as_posix() for z in sorted(raw.parent.glob("*.zip"))] + [raw.as_posix()]
    return paths


def head_sha256(path: str) -> str:
    """SHA-256 of a tracked file as committed at HEAD - what the tag pins, whatever the working tree holds."""
    import hashlib

    blob = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True, check=True).stdout
    return hashlib.sha256(blob).hexdigest()


def hash_tree(path: Path) -> dict:
    if path.is_file():
        return {"path": path.as_posix(), "sha256": sha256_file(path), "bytes": path.stat().st_size}
    files = sorted(q for q in path.rglob("*") if q.is_file())
    return {"path": path.as_posix(), "files": {q.relative_to(path).as_posix(): sha256_file(q) for q in files},
            "bytes": sum(q.stat().st_size for q in files)}


def expected_folds(cfg: dict) -> int:
    if cfg.get("group_folds"):
        return len(yaml.safe_load(Path(cfg["group_folds"]).read_text(encoding="utf-8")))
    return len(cfg.get("test_days") or [])


def run_record(run: str, problems: list[str]) -> dict:
    mpath = RUNS / run / "metrics.json"
    m = json.loads(mpath.read_text(encoding="utf-8"))
    cfg = m.get("config", {})
    rec = {"run": run, "metrics_json_sha256": sha256_file(mpath), "git_sha": m.get("git_sha"),
           "git_sha_at_start": cfg.get("git_sha_at_start"), "seed": cfg.get("seed"),
           "device": (m.get("env") or {}).get("device"), "complete": m.get("metrics", {}).get("complete")}
    man = RUNS / run / "checkpoints_manifest.json"
    if not (Path("models") / run).exists() and not man.exists() and run.startswith("lr-"):
        rec["checkpoints"] = "none (deterministic baseline; refit by scripts/lr_baseline.py)"
        return rec
    if not man.exists():
        rec["checkpoints"] = "PENDING: hash on the machine that holds them (scripts/checkpoint_hashes.py)"
        problems.append(f"{run}: checkpoint hashes pending")
        return rec
    mf = json.loads(man.read_text(encoding="utf-8"))
    cks = mf["checkpoints"]
    # D-037 onwards a run records the SHA it started at and stamps every fold with it, so a checkpoint
    # trained elsewhere is caught. Earlier runs stamped the save-time SHA, which can differ between folds
    # of one run when a commit landed mid-sweep (E19, E20r): for those only the fold count is checked.
    want = cfg.get("git_sha_at_start")
    bad = [c["file"] for c in cks if want and c.get("git_sha") != want]
    n = expected_folds(cfg)
    rec["checkpoints"] = {"hashed_on": {k: mf.get(k) for k in ("machine", "device", "utc", "models_dir")},
                          "files": [{k: c.get(k) for k in ("file", "bytes", "sha256", "git_sha", "pos_mode", "n_features",
                                                           "feature_schema_sha256", "test_days", "params")} for c in cks]}
    if bad or (n and len(cks) != n):
        rec["checkpoints"]["check"] = f"FAILED: {len(cks)} of {n} folds; trained at another SHA than {want}: {bad}"
        problems.append(f"{run}: checkpoint check failed ({rec['checkpoints']['check']})")
    elif want:
        rec["checkpoints"]["check"] = f"ok: {len(cks)} folds, all trained at the run's start SHA {want}"
    else:
        shas = sorted({str(c.get("git_sha")) for c in cks})
        rec["checkpoints"]["check"] = (f"ok: {len(cks)} folds; pre-D-037 run, save-time SHAs {shas} "
                                       f"(no start SHA recorded to check against)")
    return rec


def group(spec: dict, problems: list[str]) -> dict:
    out = {k: v for k, v in spec.items() if k not in ("runs", "lr", "configs", "data", "verify_data", "tables",
                                                      "run_folders")}
    out["runs"] = [run_record(r, problems) for r in spec.get("runs", [])]
    out["lr"] = [run_record(r, problems) for r in spec.get("lr", [])]
    out["configs"] = {c: head_sha256(c) for c in spec.get("configs", [])}
    if spec.get("data"):
        out["data"] = hash_tree(Path(spec["data"]))
    if spec.get("verify_data"):
        # an independent second build: every file must hash the same as the first
        out["verify_data"] = hash_tree(Path(spec["verify_data"]))
        out["builds_identical"] = out["verify_data"]["files"] == out["data"]["files"]
        if not out["builds_identical"]:
            problems.append(f"{spec['data']} and {spec['verify_data']} differ")
    out["tables"] = {t: sha256_file(Path("results/tables") / t) for t in spec.get("tables", [])}
    out["run_folders"] = {r: hash_tree(RUNS / r)["files"] for r in spec.get("run_folders", [])}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-raw", action="store_true", help="do not hash the raw inputs (tens of GB)")
    args = ap.parse_args()
    problems: list[str] = []
    head = git_sha()
    # the evidence must be committed: tracked results, configs and the two ledgers unmodified (another
    # session's untracked or in-progress files elsewhere do not enter the freeze; code is hashed at HEAD)
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "results", "configs",
                            "results.md", "decisions.md"], capture_output=True, text=True).stdout.strip()
    results_md = Path("results.md").read_text(encoding="utf-8")
    decisions_md = Path("decisions.md").read_text(encoding="utf-8")
    refs = check_references(results_md, Path("."))
    missing = [r["path"] for r in refs if r["status"] == "MISSING"]

    served = {k: group(v, problems) if isinstance(v, dict) else v for k, v in M1["served"].items()}
    gate = json.loads((RUNS / M1["served"]["gate_run"] / "metrics.json").read_text(encoding="utf-8"))["metrics"]["verdict"]
    if not (gate["G1_chunked_equals_one_pass"] and gate["G2_pcap_route"]["passes"] and gate["G3_csv_route"]["passes"]):
        problems.append("D-041 gates did not all pass - the served models are not licensed")
    manifest = {
        "tag": TAG,
        "scope": "M1-M3 evidence freeze - the final evidence freeze. D-045 keeps the architecture and starts no "
                 "further training run; the documentation and submission artefacts that follow cite this tag. "
                 "The M1/M2 freeze is the tag m1-m2-evidence-freeze",
        "built_at_git_sha": head, "working_tree_clean_for_evidence": not dirty, "built_on": machine_info(),
        "decisions": {d: next((ln.strip("# ").strip() for ln in decisions_md.splitlines() if ln.startswith(f"### {d} ")), None)
                      for d in DECISIONS},
        "decisions_md_sha256": sha256_file("decisions.md"), "results_md_sha256": sha256_file("results.md"),
        "m1_cicids2017": {
            "served": {**served, "d041_gate_verdict": gate},
            "replaced": {k: group(v, problems) for k, v in M1["replaced"].items()},
            "threshold_policy": THRESHOLD_POLICY,
            "serving_code_at_head": {p: head_sha256(p) for p in ("backend/inference.py", "models/registry.json",
                                                                 "src/netwm/engine/predict.py", "src/netwm/models/world_model.py",
                                                                 "src/netwm/metrics.py")},
            "tables": {t: sha256_file(Path("results/tables") / t) for t in M1["tables"]},
            "run_folders": {r: hash_tree(RUNS / r)["files"] for r in M1["run_folders"]},
        },
        "m2_ctu13": {k: group(v, problems) for k, v in M2.items()},
        "m3_cicids2018": {k: group(v, problems) for k, v in M3.items()},
        "architecture_decision": "D-045 (N-7): stay with the Transformer + RSSM world model on the network-global "
                                 "state; no per-host model and no GNN (deferred, untested); no further training run",
        "open_items": OPEN_ITEMS,
        "raw_inputs": "skipped" if args.skip_raw else [hash_tree(Path(p)) for p in raw_inputs() if Path(p).exists()],
        "results_md_references": {"checked": len(refs), "missing": missing, "rows": refs},
        "problems": problems,
    }
    if missing:
        problems.append(f"{len(missing)} artefact path(s) quoted in results.md do not exist")
    tracked = subprocess.run(["git", "ls-files", "results"], capture_output=True, text=True).stdout.split()
    out = RUNS / TAG
    out.mkdir(parents=True, exist_ok=True)
    lines = ["path,sha256"] + [f"{p},{sha256_file(p)}" for p in tracked if Path(p).is_file() and not p.startswith(f"results/runs/{TAG}/")]
    (out / "files.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest["tracked_results_files"] = {"count": len(lines) - 1, "list": f"results/runs/{TAG}/files.csv",
                                         "list_sha256": sha256_file(out / "files.csv")}
    manifest["ready_to_tag"] = not problems and not dirty
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(f"results.md quotes {len(refs)} artefact paths; missing: {len(missing)}")
    for p in missing:
        print(f"  MISSING {p}")
    print(f"tracked results files hashed: {len(lines) - 1}")
    print(f"working tree clean for evidence paths: {not dirty}")
    for p in problems:
        print(f"PROBLEM: {p}")
    print(f"ready to tag {TAG}: {manifest['ready_to_tag']}")


if __name__ == "__main__":
    main()
