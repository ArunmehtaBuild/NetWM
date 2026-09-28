"""E4-E7 - train the world model leave-one-day-out and evaluate forecasting + rollout fidelity.

    python scripts/train.py --config configs/cicids2017.yaml --test-days thursday friday
    python scripts/train.py --smoke            # 2 epochs, one fold - checks the plumbing

Saves per fold: ``models/<run>/<test_day>.pt`` (weights + config + scaler + feature names),
metrics into ``results/runs/<run>/`` and figures into ``results/figures/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.evaluate import evaluate_fold
from netwm.data.ctu13 import CIC_ONLY_FEATURES
from netwm.features.flow_features import HOST_RELATIVE_FEATURES, PACKET_CSV_FEATURES
from netwm.features.packet_windows import HAS_PCAP, PACKET_INPUTS
from netwm.features.scaler import RELATIVE_VIEWS, StateScaler
from netwm.models.world_model import WorldModelConfig, build_model
from netwm.train import TrainConfig, prepare_days, train_model
from netwm.utils import FIGURES, TABLES, ensure_dirs, git_sha, run_dir, save_run, set_seed


def plot_forecast(ds, day: str, extras: dict, threshold: float, out: Path) -> None:
    frame = ds.frame(day)
    p = np.asarray(extras["p_cum"])[:, -1]
    lo, hi = np.asarray(extras["p_lo"])[:, -1], np.asarray(extras["p_hi"])[:, -1]

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(12, 5), dpi=140, sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    ax.fill_between(frame["ts"], lo, hi, color="#2f6fdb", alpha=0.18, label="MC 5-95 %")
    ax.plot(frame["ts"], p, lw=1.3, color="#2f6fdb", label="P(compromise within K)")
    ax.axhline(threshold, ls="--", lw=0.9, color="#888", label=f"threshold {threshold:.2f}")
    ax.fill_between(
        frame["ts"], 0, 1, where=frame["y_within_K"] == 1, color="#e2574c", alpha=0.12,
        label="ground truth window",
    )
    for onset in ds.onsets(day):
        ax.axvline(frame["ts"].iloc[onset], color="#e2574c", lw=1.0)
    ax.set_ylim(0, 1)
    ax.set_ylabel("probability")
    ax.set_title(f"World model forecast - {day.capitalize()} (held out)")
    ax.legend(fontsize=7, frameon=False, ncol=4)
    ax.spines[["top", "right"]].set_visible(False)

    ax2.plot(frame["ts"], extras["surprise"], lw=0.9, color="#8e5bd9")
    ax2.set_ylabel("surprise")
    ax2.set_yscale("symlog", linthresh=1)
    ax2.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_rollout(rollout: dict, day: str, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 3.2), dpi=140)
    ax.plot(rollout["k"], rollout["world_model_mse"], "o-", color="#2f6fdb", label="world model")
    ax.plot(rollout["k"], rollout["persistence_mse"], "s--", color="#888", label="persistence")
    ax.set_xlabel("imagined steps ahead (k)")
    ax.set_ylabel("next-state MSE")
    ax.set_title(f"Open-loop rollout fidelity - {day.capitalize()}")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


#: Named feature blocks a model config may drop (D-035). By exact name, never by prefix: three S_t v1
#: features also start with ``pkt_len_``.
FEATURE_BLOCKS: dict[str, tuple[str, ...]] = {
    "packet_csv": PACKET_CSV_FEATURES,
    "host_relative": HOST_RELATIVE_FEATURES,
    # E25: S_t v1 columns built from fields Argus does not record - dropped, never learned as constants
    "cic_only": CIC_ONLY_FEATURES,
    "pcap": PACKET_INPUTS,
}


def select_features(names: "list[str]", spec: dict | None) -> "list[str]":
    """``spec = {"exclude_blocks": [...]}``; an absent spec keeps every column the build produced."""
    drop: set[str] = set()
    for block in (spec or {}).get("exclude_blocks", []):
        if block not in FEATURE_BLOCKS:
            raise SystemExit(f"unknown feature block {block!r}; known: {sorted(FEATURE_BLOCKS)}")
        drop |= set(FEATURE_BLOCKS[block])
    return [n for n in names if n not in drop]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/cicids2017.yaml")
    ap.add_argument("--model-config", default=None,
                    help="YAML overriding WorldModelConfig / TrainConfig (e.g. the round-3 heads)")
    ap.add_argument("--data", default=None, help="override processed_dir from the config")
    ap.add_argument("--test-days", nargs="*", default=["thursday", "friday"])
    ap.add_argument("--group-folds", default=None,
                    help="YAML {fold: [test splits]}: hold out a whole group per fold (E25 leave-one-family-out)")
    ap.add_argument("--run", default="e4e7-worldmodel")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--samples", type=int, default=16, help="Monte-Carlo rollouts per window")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--smoke", action="store_true", help="2 epochs, first test day only")
    ap.add_argument("--no-figures", action="store_true",
                    help="skip the per-fold E5/E6 PNGs (sweeps: the scorecard is the result)")
    ap.add_argument("--resume", action="store_true",
                    help="a fold whose checkpoint already exists is loaded and evaluated, not retrained "
                         "(recovery after an interrupted run; the weights are the ones that run trained)")
    ap.add_argument("--note", default=None,
                    help="free-text provenance stored with the run (D-037: E25b's seeds are 'completion of E25')")
    args = ap.parse_args()

    set_seed(args.seed)
    ensure_dirs()
    # The code this process runs is the code at start-up; commits made while a sweep runs must not
    # relabel its checkpoints (D-037: E19's folds carried three different save-time SHAs).
    start_sha = git_sha()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    ds = ProcessedDataset(args.data or cfg["processed_dir"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # --config is the *data* config; model and training knobs live in their own file so a run
    # without --model-config is byte-for-byte the round-2 setup (D-023).
    overrides = (
        yaml.safe_load(Path(args.model_config).read_text(encoding="utf-8"))
        if args.model_config
        else {}
    )
    test_days = args.test_days[:1] if args.smoke else args.test_days
    # D-035: a run may drop named feature blocks; everything downstream (prepare_days, the checkpoint's
    # feature_names, inference) reads ds.feature_names, so narrowing it here narrows all of them.
    ds.feature_names = select_features(ds.feature_names, overrides.get("features"))
    train_cfg = TrainConfig(epochs=2 if args.smoke else args.epochs, **overrides.get("train", {}))
    views = len(RELATIVE_VIEWS) if overrides.get("scaler", {}).get("mode") == "relative" else 1
    model_cfg = WorldModelConfig(
        n_features=len(ds.feature_names) * views, horizon_k=ds.horizon, n_stages=7,
        **overrides.get("model", {}),
    )
    print(f"{len(ds.feature_names)} features x {views} view(s) = {model_cfg.n_features} model inputs; "
          f"arch={model_cfg.arch} hazard={model_cfg.hazard} curriculum={bool(train_cfg.curriculum)}")
    if len(train_cfg.risk_columns) != model_cfg.n_risk:
        raise SystemExit(
            f"config mismatch: n_risk={model_cfg.n_risk} but "
            f"{len(train_cfg.risk_columns)} risk_columns {train_cfg.risk_columns}"
        )
    run_id = f"{args.run}-smoke" if args.smoke else args.run
    model_root = Path("models") / run_id
    model_root.mkdir(parents=True, exist_ok=True)

    rows, per_day, histories = [], {}, {}
    # D-037: a model with the has_pcap input is also scored with packets masked (its CSV form)
    csv_mode = HAS_PCAP in ds.feature_names
    rows_csv, per_day_csv = [], {}
    # one fold per held-out day, or one per group of splits held out together (D-035, E25)
    folds = (yaml.safe_load(Path(args.group_folds).read_text(encoding="utf-8")) if args.group_folds
             else {d: [d] for d in test_days})
    if args.smoke:
        folds = dict(list(folds.items())[:1])
    for fold, held_out in folds.items():
        test_day = fold
        train_days = [d for d in ds.splits if d not in held_out]
        print(f"\n== fold: {fold} test={held_out}  train={train_days}  device={device}")
        # an absent `scaler:` block is the D-014 log-standardiser, i.e. round 2 exactly (D-025)
        ckpt_path = model_root / f"{test_day}.pt"
        resumed = bool(args.resume and ckpt_path.exists())
        if resumed:
            saved = torch.load(ckpt_path, map_location=device, weights_only=False)
            model = build_model(WorldModelConfig(**saved["model_config"])).to(device)
            model.load_state_dict(saved["model_state"])
            scaler, history = saved["scaler"], []
            print(f"  resumed: {ckpt_path} (trained at {saved.get('git_sha')}), evaluating only")
        else:
            scaler = StateScaler(**overrides.get("scaler", {})).fit(ds.concat(train_days)[ds.feature_names])
            model, history = train_model(ds, train_days, train_cfg, model_cfg, device, scaler)

        def fold_checkpoint(threshold):
            return {
                "model_state": model.state_dict(),
                "model_config": model_cfg.as_dict(),
                "train_config": train_cfg.__dict__,
                "feature_names": ds.feature_names,
                "scaler": scaler,
                "train_days": train_days,
                "test_day": test_day,
                "test_days": list(held_out),
                "git_sha": start_sha,
                "horizon_k": ds.horizon,
                "stride_s": ds.stride_s,
                "threshold": threshold,
                # so precursor_eval.py never has to guess which logit is which
                "risk_columns": list(train_cfg.risk_columns),
                "onset_source": train_cfg.onset_source,
            }

        if not resumed:
            # saved as soon as training ends, so a power cut during evaluation keeps the weights
            torch.save(fold_checkpoint(None), ckpt_path)
        histories[test_day] = history

        prepared = prepare_days(ds, ds.splits, scaler, train_cfg.risk_columns,
                                train_cfg.onset_source, train_cfg.onset_gap)
        train_cache: dict = {}
        for held in held_out:
            fold_rows, extras = evaluate_fold(
                model,
                {d: prepared[d] for d in train_days},
                held,
                prepared[held],
                ds.horizon,
                ds.stride_s,
                device,
                n_samples=4 if args.smoke else args.samples,
                train_cache=train_cache,
            )
            rows.extend(fold_rows)
            per_day[held] = {k: v for k, v in extras.items() if k not in {"p_cum", "p_lo", "p_hi", "attention"}}
            if csv_mode:
                held_csv = prepare_days(ds, [held], scaler, train_cfg.risk_columns, train_cfg.onset_source,
                                        train_cfg.onset_gap, csv_mode=True)[held]
                csv_rows, csv_extras = evaluate_fold(
                    model, {d: prepared[d] for d in train_days}, held, held_csv, ds.horizon, ds.stride_s,
                    device, n_samples=4 if args.smoke else args.samples, train_cache=train_cache,
                )
                rows_csv.extend({**r, "input_mode": "csv"} for r in csv_rows)
                per_day_csv[held] = {k: v for k, v in csv_extras.items()
                                     if k not in {"p_cum", "p_lo", "p_hi", "attention"}}

        if not resumed:
            torch.save(fold_checkpoint(extras["threshold_train"]), ckpt_path)
        elif saved.get("threshold") is None:
            # trained, then interrupted before evaluation: add the threshold, keep its provenance
            saved["threshold"] = extras["threshold_train"]
            torch.save(saved, ckpt_path)
        # Namespaced by run id: these filenames used to be run-independent, so any training run
        # silently overwrote the published E5/E6 figures of a previous one.
        if not args.no_figures:
            plot_forecast(ds, test_day, extras, extras["threshold_train"],
                          FIGURES / f"e6_{run_id}_{test_day}_worldmodel_forecast.png")
        if extras["rollout"] is not None and not args.no_figures:
            plot_rollout(extras["rollout"], test_day,
                         FIGURES / f"e5_{run_id}_{test_day}_rollout_fidelity.png")

        for row in fold_rows:
            keys = ("target", "threshold_mode", "f1", "precision", "recall", "fpr", "pr_auc",
                    "roc_auc", "warned_early", "episodes", "mean_lead_windows")
            print("   " + json.dumps({k: row[k] for k in keys if k in row}))
        # after every fold, so an interrupted run keeps what it finished
        save_run(run_id, {"rows": rows, "per_day": per_day, "complete": False},
                 config={**vars(args), "model": model_cfg.as_dict(), "git_sha_at_start": start_sha})
        if csv_mode:
            save_run(f"{run_id}-csvmode", {"rows": rows_csv, "per_day": per_day_csv, "complete": False,
                                           "input_mode": "csv (pcap_ = 0, has_pcap = 0)"},
                     config={**vars(args), "model": model_cfg.as_dict(), "git_sha_at_start": start_sha})

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / f"{run_id}_forecast.csv", index=False)
    pd.DataFrame(
        [{"test_day": d, **h} for d, hist in histories.items() for h in hist]
    ).to_csv(TABLES / f"{run_id}_training_curves.csv", index=False)
    save_run(run_id, {"rows": rows, "per_day": per_day, "complete": True},
             config={**vars(args), "model": model_cfg.as_dict(), "git_sha_at_start": start_sha})
    if csv_mode:
        save_run(f"{run_id}-csvmode", {"rows": rows_csv, "per_day": per_day_csv, "complete": True,
                                       "input_mode": "csv (pcap_ = 0, has_pcap = 0)"},
                 config={**vars(args), "model": model_cfg.as_dict(), "git_sha_at_start": start_sha})
    print(f"\nwrote {model_root}/*.pt, results/tables/{run_id}_*.csv, results/figures/e5_*, e6_*")


if __name__ == "__main__":
    main()
