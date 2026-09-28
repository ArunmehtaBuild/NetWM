"""N-6 (D-039): why does the world model invert on some CTU-13 families? Descriptive, not a bar.

    python scripts/ctu_inversion_diagnostic.py

Everything below was fixed before any output was looked at.

* **Scenarios.** The three the N-6 card names (Murlo s08, Sogou s07, Rbot s11); the other two that
  decide an "inverted" verdict in E25b (Neris s02, Virut s13); and NSIS s12, which transfers, as a
  control.
* **Models.** The world model's fold checkpoints for seeds 43 and 44 (seed 42's weights are not on
  this machine), scored on the deterministic mean path (``forecast(sample=False)``, ``p_max``). And the
  fold's logistic regression, refit exactly as ``scripts/lr_baseline.py`` fits it (deterministic),
  and checked against the stored ``lr-ctu13-s42`` scores before anything is read from it: Spearman
  >= 0.99 and ROC-AUC within 0.005 on every scenario. (A first run required bit-identical
  probabilities and stopped: the refit differs by up to 1.2e-2 in probability, from library versions
  the stored run did not record, while its ranks agree - Spearman >= 0.998, ROC-AUC within 0.0021.)
* **Direction.** Per input feature, the standardised mean difference ``d`` between windows with
  ``y_within_K`` = 1 and = 0, in the fold scaler's space: once over the fold's training scenarios
  pooled, once on the held-out scenario. A feature **flips** when the two have opposite signs and
  both ``|d| >= 0.2``.
* **Reliance.** Per input feature, set it to its training mean (0 after scaling) across the whole
  held-out scenario, re-score, and record the change in ROC-AUC. A positive change means the feature
  was pushing the ranking the wrong way. Then the same with every flipped feature neutralised at once.
  One feature at a time leaves states off the data manifold, and correlated features share the
  blame: this measures what a model leans on, not what causes the traffic.

Writes ``results/tables/n6_ctu13_inversion_features.csv`` (one row per model, scenario and feature),
``results/tables/n6_ctu13_inversion_summary.csv`` and ``results/runs/n6-ctu13-inversion/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.data.processed import ProcessedDataset
from netwm.features.scaler import StateScaler
from netwm.models.baseline import LogisticForecaster
from netwm.models.world_model import WorldModelConfig, build_model
from netwm.utils import RUNS, TABLES, ensure_dirs, git_sha, save_run, set_seed
from train import select_features

SCENARIOS = {"s08": "inverted", "s07": "inverted", "s11": "inverted",
             "s02": "inverted", "s13": "inverted", "s12": "control (transfers)"}
SEEDS = (43, 44)
FLIP_D = 0.2


def smd(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Standardised mean difference per column, positives minus negatives, pooled SD."""
    pos, neg = x[y == 1], x[y == 0]
    sd = np.sqrt((pos.var(axis=0) + neg.var(axis=0)) / 2.0)
    diff = pos.mean(axis=0) - neg.mean(axis=0)
    return np.where(sd > 1e-9, diff / np.where(sd > 1e-9, sd, 1.0), 0.0)


@torch.no_grad()
def wm_score(model, x: np.ndarray, horizon: int, device: torch.device) -> np.ndarray:
    t = torch.from_numpy(np.asarray(x, dtype=np.float32)).unsqueeze(0).to(device)
    return model.forecast(t, horizon=horizon, sample=False)["p_max"].cpu().numpy()


def reliance(score_fn, x: np.ndarray, y: np.ndarray, flips: np.ndarray) -> tuple[float, np.ndarray, float]:
    """(baseline ROC-AUC, per-feature ROC change when neutralised, ROC with all flips neutralised)."""
    base = roc_auc_score(y, score_fn(x))
    delta = np.zeros(x.shape[1])
    for j in range(x.shape[1]):
        x2 = x.copy()
        x2[:, j] = 0.0
        delta[j] = roc_auc_score(y, score_fn(x2)) - base
    x3 = x.copy()
    x3[:, flips] = 0.0
    return base, delta, (roc_auc_score(y, score_fn(x3)) if flips.any() else base)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/processed/ctu13")
    ap.add_argument("--model-config", default="configs/m1v2/e25_ctu13.yaml")
    ap.add_argument("--group-folds", default="configs/ctu13_folds.yaml")
    ap.add_argument("--seed", type=int, default=42, help="nothing here samples; kept for the repo contract")
    ap.add_argument("--seeds", type=int, nargs="+", default=list(SEEDS),
                    help="world-model seeds whose fold checkpoints are on this machine (N-6a ran 43 44)")
    args = ap.parse_args()
    set_seed(args.seed)
    ensure_dirs()
    start_sha = git_sha()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    ds = ProcessedDataset(args.data)
    cfg = yaml.safe_load(Path(args.model_config).read_text(encoding="utf-8"))
    lr_names = select_features(ds.feature_names, cfg.get("features"))
    folds = yaml.safe_load(Path(args.group_folds).read_text(encoding="utf-8"))
    fold_of = {s: f for f, ss in folds.items() for s in ss}
    stored_lr = json.loads((RUNS / "lr-ctu13-s42" / "metrics.json").read_text(encoding="utf-8"))["metrics"]["per_day"]

    rows, summary, lr_check = [], [], {}
    seeds = tuple(args.seeds)
    for scen, role in SCENARIOS.items():
        fold = fold_of[scen]
        frame = ds.frame(scen)
        y = frame["y_within_K"].to_numpy().astype(int)
        meta = next(m for m in ds.meta["splits"] if m["split"] == scen)

        # --- logistic regression, refit as lr_baseline.py does, and checked against the stored run
        train_days = [d for d in ds.splits if d not in folds[fold]]
        train = ds.concat(train_days)
        lr_scaler = StateScaler().fit(train[lr_names])
        lr = LogisticForecaster().fit(lr_scaler.transform(train[lr_names]),
                                      train["y_within_K"].to_numpy().astype(int))
        x_lr = np.asarray(lr_scaler.transform(frame[lr_names]), dtype=np.float64)
        refit, stored = lr.predict_proba(x_lr), np.asarray(stored_lr[scen]["scores"])
        lr_check[scen] = {"max_abs": float(np.max(np.abs(refit - stored))),
                          "spearman": float(spearmanr(refit, stored).correlation),
                          "roc_refit": float(roc_auc_score(y, refit)), "roc_stored": float(roc_auc_score(y, stored))}
        c = lr_check[scen]
        if c["spearman"] < 0.99 or abs(c["roc_refit"] - c["roc_stored"]) > 0.005:
            raise SystemExit(f"{scen}: refit LR does not reproduce lr-ctu13-s42 ({c}) - stop")

        # --- direction, in the fold's scaler space (the first seed's checkpoint scaler; the fit is
        # deterministic, so every seed of a fold has the same one)
        ref = torch.load(Path("models") / f"e25-ctu13-s{seeds[0]}" / f"{fold}.pt", map_location="cpu",
                         weights_only=False)
        names, scaler = ref["feature_names"], ref["scaler"]
        assert list(names) == list(lr_names), "world model and LR must read the same inputs"
        assert sorted(ref["train_days"]) == sorted(train_days)
        x_tr = np.asarray(scaler.transform(train[names]), dtype=np.float64)
        x_te = np.asarray(scaler.transform(frame[names]), dtype=np.float64)
        d_train = smd(x_tr, train["y_within_K"].to_numpy().astype(int))
        d_held = smd(x_te, y)
        flips = (np.sign(d_train) != np.sign(d_held)) & (np.abs(d_train) >= FLIP_D) & (np.abs(d_held) >= FLIP_D)

        models = {"logistic regression": lambda x, m=lr: m.predict_proba(x)}
        for seed in seeds:
            ck = torch.load(Path("models") / f"e25-ctu13-s{seed}" / f"{fold}.pt", map_location=device,
                            weights_only=False)
            assert list(ck["feature_names"]) == list(names)
            wm = build_model(WorldModelConfig(**ck["model_config"])).to(device)
            wm.load_state_dict(ck["model_state"])
            wm.eval()
            models[f"world model s{seed}"] = (lambda x, m=wm, h=ck["horizon_k"]: wm_score(m, x, h, device))

        for model_name, fn in models.items():
            base, delta, flipped_roc = reliance(fn, x_te, y, flips)
            for j, n in enumerate(names):
                rows.append({"scenario": scen, "family": meta["family"], "role": role, "model": model_name,
                             "feature": n, "d_train": round(float(d_train[j]), 3),
                             "d_heldout": round(float(d_held[j]), 3), "flips": bool(flips[j]),
                             "delta_roc_neutralised": round(float(delta[j]), 4)})
            top = np.argsort(-delta)[:5]
            summary.append({
                "scenario": scen, "family": meta["family"], "role": role, "model": model_name,
                "windows": len(y), "background": int((y == 0).sum()),
                "roc_auc": round(float(base), 4),
                "n_flipped_features": int(flips.sum()),
                "roc_auc_flips_neutralised": round(float(flipped_roc), 4),
                "top5_wrong_way": "; ".join(f"{names[j]} {delta[j]:+.3f}" for j in top if delta[j] > 0),
            })
            print(f"{scen} {meta['family']:8s} {model_name:22s} roc={base:.3f}  flips={int(flips.sum()):2d}  "
                  f"roc|flips->0={flipped_roc:.3f}  top: {summary[-1]['top5_wrong_way']}")

    feats = pd.DataFrame(rows)
    summ = pd.DataFrame(summary)
    # the N-6a artefacts are seeds 43/44; any other seed set gets its own names instead of overwriting them
    tag = "" if seeds == SEEDS else "-s" + "-".join(map(str, seeds))
    feats.to_csv(TABLES / f"n6_ctu13_inversion{tag.replace('-', '_')}_features.csv", index=False)
    summ.to_csv(TABLES / f"n6_ctu13_inversion{tag.replace('-', '_')}_summary.csv", index=False)
    save_run(f"n6-ctu13-inversion{tag}", {"summary": summ.to_dict("records"), "lr_reproduction": lr_check},
             config={**vars(args), "scenarios": SCENARIOS, "seeds": list(seeds), "flip_d": FLIP_D,
                     "device": str(device), "git_sha_at_start": start_sha})
    print(f"wrote results/tables/n6_ctu13_inversion{tag.replace('-', '_')}_{{features,summary}}.csv and "
          f"results/runs/n6-ctu13-inversion{tag}/")


if __name__ == "__main__":
    main()
