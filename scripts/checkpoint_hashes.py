"""Record the SHA-256 of a run's checkpoints on the machine that holds them.

    python scripts/checkpoint_hashes.py --runs e25-ctu13-s43 e25-ctu13-s44

Weights stay untracked (``models/``), and some exist on one machine only (E25b's seeds 43/44 on the
RTX 4060). Run this *on that machine*: it hashes ``models/<run>/*.pt`` in place (nothing is copied)
and writes ``results/runs/<run>/checkpoints_manifest.json`` - file, bytes, SHA-256, the git SHA each
checkpoint was trained at, its feature schema hash and fold - plus the machine it was read on. Commit
and push that file; ``scripts/evidence_freeze.py`` reads it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.freeze import checkpoint_record, machine_info
from netwm.utils import RUNS


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--models-dir", default="models")
    args = ap.parse_args()
    for run in args.runs:
        ckpts = sorted((Path(args.models_dir) / run).glob("*.pt"))
        if not ckpts:
            raise SystemExit(f"no checkpoints in {Path(args.models_dir) / run}")
        out = {"run": run, "models_dir": str(Path(args.models_dir).resolve()), **machine_info(),
               "note": "hashed in place on this machine; weights are untracked",
               "checkpoints": [checkpoint_record(p) for p in ckpts]}
        dest = RUNS / run
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "checkpoints_manifest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"{run}: {len(ckpts)} checkpoints -> results/runs/{run}/checkpoints_manifest.json")
        for c in out["checkpoints"]:
            print(f"  {c['file']:14s} {c['sha256']}  trained at {c.get('git_sha')}")


if __name__ == "__main__":
    main()
