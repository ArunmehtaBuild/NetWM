"""The logistic-regression baseline on the D-035 scorecard contract (D-037).

    python scripts/lr_baseline.py --data data/processed/cicids2017_m1v2 \
        --model-config configs/m1v2/e19_base.yaml --test-days monday tuesday wednesday thursday friday \
        --run lr-flow
    python scripts/lr_baseline.py --data data/processed/ctu13 --model-config configs/m1v2/e25_ctu13.yaml \
        --group-folds configs/ctu13_folds.yaml --run lr-ctu13

E3's definition (``models/baseline.LogisticForecaster``: balanced classes, C = 1, no lags) on the same
features a model config selects, log-standardised by a scaler fitted on each fold's training splits.
Two fits per fold, one per scorecard score: ``y_within_K`` gives ``comp`` and ``y_attack_within_K``
gives ``threat``. The held-out scores are written exactly where ``scripts/train.py`` writes a world
model's, so ``scripts/scorecard.py`` scores both identically. Deterministic, so there is no seed range.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.data.processed import ProcessedDataset
from netwm.features.scaler import StateScaler
from netwm.models.baseline import LogisticForecaster
from netwm.utils import ensure_dirs, git_sha, save_run
from train import select_features


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--model-config", required=True, help="only its features: block is used")
    ap.add_argument("--test-days", nargs="*", default=None)
    ap.add_argument("--group-folds", default=None)
    ap.add_argument("--run", required=True)
    args = ap.parse_args()

    ensure_dirs()
    start_sha = git_sha()
    ds = ProcessedDataset(args.data)
    cfg = yaml.safe_load(Path(args.model_config).read_text(encoding="utf-8"))
    names = [n for n in select_features(ds.feature_names, cfg.get("features"))]
    folds = (yaml.safe_load(Path(args.group_folds).read_text(encoding="utf-8")) if args.group_folds
             else {d: [d] for d in (args.test_days or ds.splits)})
    per_day = {}
    for fold, held_out in folds.items():
        train_days = [d for d in ds.splits if d not in held_out]
        train = ds.concat(train_days)
        scaler = StateScaler().fit(train[names])
        x_train = scaler.transform(train[names])
        models = {}
        for key, target in (("comp", "y_within_K"), ("threat", "y_attack_within_K")):
            y = train[target].to_numpy().astype(int)
            models[key] = LogisticForecaster().fit(x_train, y) if 0 < y.sum() < len(y) else None
        for held in held_out:
            x = scaler.transform(ds.frame(held)[names])
            scores = {k: (m.predict_proba(x) if m is not None else np.zeros(len(x))) for k, m in models.items()}
            per_day[held] = {"scores": scores["comp"].tolist(), "threat_scores": scores["threat"].tolist(),
                             "model": "logistic regression (E3 definition)"}
        print(f"fold {fold}: train {train_days} -> {held_out}")
    save_run(args.run, {"per_day": per_day, "features": names, "complete": True},
             config={**vars(args), "n_features": len(names), "git_sha_at_start": start_sha})
    print(f"wrote results/runs/{args.run}/metrics.json ({len(names)} features)")


if __name__ == "__main__":
    main()
