"""D-038 Step 5 (E27): correctness of the PCAP route - a check, not a performance experiment.

    CUDA_VISIBLE_DEVICES="" python scripts/pcap_route_parity.py
    CUDA_VISIBLE_DEVICES="" python scripts/pcap_route_parity.py --pcap data/demo/thursday_1640_1850.pcap

1. **One method.** For every fold, the three E20r checkpoints read the same 105 feature names in the
   same order, share one model config, horizon, stride and training days; whether their fitted
   scalers transform the held-out matrix identically is reported.
2. **Stored outputs reproduced.** Each seed's fold, fed the processed held-out matrix through its own
   scaler, gives per-window ``p_max`` over 16 Monte-Carlo rollouts - the statistic its run stored -
   and the deterministic mean path the live route alarms on. Both are compared with the stored
   scores. Sampling noise is reported, not required to vanish (D-038).
3. **No lookahead.** On real Thursday and Friday the scaler is a per-window transform and the causal
   threshold at t reads windows before t only (gating, D-038 criterion 1). The forecast itself is
   measured the same way - the ensemble's score for windows 0..N-1 from the first N windows against
   the whole day - and reported: the model's positional embedding depends on the input length (E27
   finding), so it is not prefix-invariant.
4. **Live PCAP state (``--pcap``, a real-capture slice).** The state the upload path builds -
   ``pcap_to_flows`` for the flow features, ``window_packet_features`` for the packet block - against
   the processed matrix on the windows both cover, feature by feature. The flow half comes from our
   own aggregator (D-033), not the corrected CSVs the matrix was built from, so differences there are
   the aggregator's and are reported per feature; the slice's first and last windows are partial and
   are left out.

Gating (D-038 criterion 1): checks 1 and 3. Checks 2 and 4 are reported for review.
Writes results/runs/e27-parity/metrics.json and results/tables/e27_parity.csv.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import _forecast, load_checkpoint, load_ensemble, state_matrix
from netwm.features.flow_aggregator import pcap_to_flows
from netwm.features.windowing import WindowSpec
from netwm.metrics import causal_threshold
from netwm.utils import RUNS, TABLES, ensure_dirs, save_run

SEEDS = (42, 43, 44)
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
EDGE = 4  # windows dropped at each end of a slice: a flow lasts up to 120 s, a window is 60 s


def fold_paths(day: str) -> list[Path]:
    return [Path("models") / f"m1v2-e20r-s{s}" / f"{day}.pt" for s in SEEDS]


def stored(seed: int, day: str) -> np.ndarray:
    m = json.loads((RUNS / f"m1v2-e20r-s{seed}" / "metrics.json").read_text(encoding="utf-8"))["metrics"]
    return np.asarray(m["per_day"][day]["scores"], float)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/processed/cicids2017_m1v2p")
    ap.add_argument("--pcap", default=None, help="a real-capture slice for check 4 (the synthesised demo PCAP is not one)")
    ap.add_argument("--day", default="thursday", help="the day the --pcap slice was cut from")
    ap.add_argument("--seed", type=int, default=42, help="torch seed for the Monte-Carlo rollouts")
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    ensure_dirs()
    cpu = torch.device("cpu")

    ds = ProcessedDataset(args.data)
    rows, one_method, no_lookahead = [], True, True
    for day in DAYS:
        paths = fold_paths(day)
        if not all(p.exists() for p in paths):
            raise SystemExit(f"missing E20r checkpoint(s) for the {day} fold: {[str(p) for p in paths if not p.exists()]}")
        try:
            ens = load_ensemble(paths, cpu)  # check 1: raises on a differing name order, horizon, stride or fold
        except ValueError as exc:
            one_method = False
            rows.append({"day": day, "check": "one_method", "ok": False, "detail": str(exc)})
            continue
        names, members = ens["feature_names"], ens["members"]
        configs_equal = all(m["model_config"] == members[0]["model_config"] for m in members)
        one_method &= configs_equal
        frame = ds.frame(day)
        y = ds.target(day)
        xs = [m["scaler"].transform(frame[names]) for m in members]
        scalers_identical = all(np.array_equal(xs[0], x) for x in xs[1:])
        rows.append({"day": day, "check": "one_method", "ok": configs_equal, "inputs": len(names),
                     "configs_equal": configs_equal, "scalers_identical": scalers_identical,
                     "train_days": ",".join(ens["train_days"])})

        # check 2: the stored held-out scores, reproduced per seed
        mean_paths = []
        for s, m, x in zip(SEEDS, members, xs):
            out = _forecast(m, x, int(ens["horizon_k"]), 16, True)
            ref = stored(s, day)
            mc, mp = out["p_max_mc"], out["p_max"]
            mean_paths.append(mp)
            both = 0 < y.sum() < len(y)
            rows.append({
                "day": day, "check": "stored_scores", "seed": s, "windows": len(ref), "live_windows": len(mc),
                "mc_corr": round(float(np.corrcoef(mc, ref)[0, 1]), 5),
                "mc_mean_abs_diff": round(float(np.abs(mc - ref).mean()), 6),
                "mc_max_abs_diff": round(float(np.abs(mc - ref).max()), 6),
                "mean_path_corr": round(float(np.corrcoef(mp, ref)[0, 1]), 5),
                "pr_auc_stored": round(float(average_precision_score(y, ref)), 4) if both else None,
                "pr_auc_live_mc": round(float(average_precision_score(y, mc)), 4) if both else None,
                "pr_auc_live_mean_path": round(float(average_precision_score(y, mp)), 4) if both else None,
            })

        # check 3: prefix invariance (the compromise days). D-038 criterion 1 gates preprocessing and
        # the threshold. The forecast's own prefix difference is reported beside it: CausalContext
        # stretches its positional embedding to the input length, so a window's score depends on how
        # many windows follow it (E27 finding; pre-existing, every model).
        if day in ("thursday", "friday"):
            cut = len(frame) // 2
            prefix = [m["scaler"].transform(frame[names].iloc[:cut]) for m in members]
            scale_ok = all(np.array_equal(p, x[:cut]) for p, x in zip(prefix, xs))
            part = np.mean([_forecast(m, p, int(ens["horizon_k"]), 1, True)["p_max"] for m, p in zip(members, prefix)], axis=0)
            full = np.mean(mean_paths, axis=0)
            diff = np.abs(part - full[:cut])
            thr_ok = bool(np.array_equal(causal_threshold(full[:cut], 0.9), causal_threshold(full, 0.9)[:cut], equal_nan=True))
            # how much the length dependence moves the alarms: the prefix's own causal alarms vs the
            # full day's alarms on the same windows
            alarm_part = part >= causal_threshold(part, 0.9)
            alarm_full = full[:cut] >= causal_threshold(full, 0.9)[:cut]
            ok = scale_ok and thr_ok
            no_lookahead &= ok
            rows.append({"day": day, "check": "no_lookahead", "ok": ok, "prefix_windows": cut,
                         "scaler_prefix_equal": scale_ok, "threshold_prefix_equal": thr_ok,
                         "forecast_max_score_diff": round(float(diff.max()), 6),
                         "forecast_mean_score_diff": round(float(diff.mean()), 6),
                         "forecast_score_corr": round(float(np.corrcoef(part, full[:cut])[0, 1]), 5),
                         "alarm_windows_differing": int((alarm_part != alarm_full).sum()),
                         "alarm_windows_full": int(alarm_full.sum())})

    live = None
    if args.pcap:
        # check 4: the upload path's state against the training matrix
        names = load_checkpoint(fold_paths(args.day)[0], cpu)["feature_names"]
        spec = WindowSpec(ds.meta["config"]["window"]["length_s"], ds.stride_s)
        served, _, t0, n = state_matrix(pcap_to_flows(args.pcap), names, spec, pcap_path=args.pcap)
        day_t0 = pd.Timestamp(next(m["t0"] for m in ds.meta["splits"] if m["split"] == args.day))
        offset = (pd.Timestamp(t0) - day_t0).total_seconds() / ds.stride_s
        if offset != int(offset):
            raise SystemExit(f"slice grid {t0} is not on the day's {ds.stride_s:.0f} s grid from {day_t0}")
        offset = int(offset)
        keep = np.arange(EDGE, n - EDGE)
        train = ds.frame(args.day)[names].iloc[keep + offset].reset_index(drop=True)
        got = served[names].iloc[keep].reset_index(drop=True)
        per_feature = []
        for col in names:
            a, b = got[col].to_numpy(float), train[col].to_numpy(float)
            rel = np.abs(a - b) / np.maximum(1.0, np.abs(b))
            per_feature.append({"feature": col, "block": "pcap" if col.startswith("pcap_") else "pkt" if col.startswith("pkt_") else "flow",
                                "max_rel_diff": round(float(rel.max()), 6), "mean_rel_diff": round(float(rel.mean()), 6),
                                "corr": round(float(np.corrcoef(a, b)[0, 1]), 5) if a.std() > 0 and b.std() > 0 else None})
        pf = pd.DataFrame(per_feature)
        pf.to_csv(TABLES / "e27_parity_live_pcap.csv", index=False)
        live = {"pcap": str(args.pcap), "day": args.day, "slice_t0": str(t0), "day_window_offset": offset,
                "windows_compared": int(len(keep)),
                "exact_features": int((pf["max_rel_diff"] <= 1e-6).sum()), "features": len(names),
                "by_block": pf.groupby("block")["max_rel_diff"].agg(["count", "median", "max"]).round(6).to_dict("index")}

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "e27_parity.csv", index=False)
    verdict = {"one_method": bool(one_method), "no_lookahead": bool(no_lookahead),
               "passed": bool(one_method and no_lookahead)}
    save_run("e27-parity", {"verdict": verdict, "rows": rows, "live_pcap": live},
             config={**vars(args), "decision": "D-038", "command": " ".join(sys.argv)})
    pd.set_option("display.width", 250)
    print(table.to_string(index=False))
    if live:
        print(json.dumps(live, indent=1))
    print("verdict:", verdict)
    raise SystemExit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
