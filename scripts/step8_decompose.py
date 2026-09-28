"""E27 Step 8 follow-up (descriptive, D-038 / D-040): why the two routes' risk scores barely correlate.

    CUDA_VISIBLE_DEVICES="" python scripts/step8_decompose.py --pcap data/cic-2017-pcap/thursday_1640_1850.pcap

Step 8 served one real Thursday window (16:40-18:50 UTC) through both routes: CSV to r2, PCAP to the
E20r mean. Their per-window risk scores correlated at 0.035. Three things differ between those two
scores, and this separates them by scoring the same 260 windows six ways (mean-path ``p_max``, the
statistic the payload alarms on; deterministic):

- **as served**: r2 on the CSV slice, the E20r mean on the PCAP slice (the Step 8 payloads' numbers);
- **training state, same length**: each model on its own training matrix's rows for those windows,
  fed as a 260-window input - removes the live-state difference (D-040's residual flow block);
- **training state, whole day**: each model on the whole 972-window day, cut to those windows -
  what the stored E27 scores describe; the difference from the row above is the length effect (N-8).

Nothing is tuned and no detection number is computed. Writes results/tables/e27_step8_decompose.csv
(per-window scores) and results/runs/e27-step8-decompose/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import _forecast, analyze_file, load_checkpoint, load_ensemble
from netwm.metrics import causal_threshold
from netwm.utils import TABLES, ensure_dirs, save_run

SEEDS = (42, 43, 44)
R2 = "models/e4e7-worldmodel-r2/thursday.pt"
R2_DATA = "data/processed/cicids2017"
PACKET_DATA = "data/processed/cicids2017_m1v2p"


def matrix_scores(ckpt: dict, frame: pd.DataFrame) -> np.ndarray:
    """Mean-path p_max of a checkpoint (or ensemble mean) on a slice of its training matrix."""
    members = ckpt.get("members") or [ckpt]
    names, horizon = list(ckpt["feature_names"]), int(ckpt["horizon_k"])
    return np.mean([_forecast(m, m["scaler"].transform(frame[names]), horizon, 1, True)["p_max"] for m in members], axis=0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap", required=True, help="the real Thursday 16:40-18:50 UTC slice Step 8 used")
    ap.add_argument("--csv", default="data/demo/thursday_infiltration.csv")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    ensure_dirs()
    cpu = torch.device("cpu")

    r2 = load_checkpoint(ROOT / R2, cpu)
    ens = load_ensemble([ROOT / "models" / f"m1v2-e20r-s{s}" / "thursday.pt" for s in SEEDS], cpu)

    live = {}
    for key, path, ckpt in (("r2", ROOT / args.csv, r2), ("e20r_mean", ROOT / args.pcap, ens)):
        payload = analyze_file(path, ckpt, explain_limit=0)
        live[key] = pd.Series([e["p_max"] for e in payload["timeline"]],
                              index=pd.to_datetime([e["ts"] for e in payload["timeline"]], utc=True).tz_convert(None))
    ts = live["r2"].index
    if not ts.equals(live["e20r_mean"].index):
        raise SystemExit("the two routes' window grids differ")

    series = {"r2_as_served": live["r2"].to_numpy(), "e20r_mean_as_served": live["e20r_mean"].to_numpy()}
    for key, ckpt, data in (("r2", r2, R2_DATA), ("e20r_mean", ens, PACKET_DATA)):
        ds = ProcessedDataset(data)
        day_t0 = pd.Timestamp(next(m["t0"] for m in ds.meta["splits"] if m["split"] == "thursday"))
        offset = (ts[0] - day_t0).total_seconds() / ds.stride_s
        if offset != int(offset):
            raise SystemExit(f"{data}: the slice grid is not on the day's grid")
        rows = np.arange(int(offset), int(offset) + len(ts))
        frame = ds.frame("thursday")
        series[f"{key}_training_state_same_length"] = matrix_scores(ckpt, frame.iloc[rows].reset_index(drop=True))
        series[f"{key}_training_state_whole_day"] = matrix_scores(ckpt, frame)[rows]

    table = pd.DataFrame(series, index=ts.rename("ts"))
    table.to_csv(TABLES / "e27_step8_decompose.csv")
    corr = lambda a, b: round(float(np.corrcoef(table[a], table[b])[0, 1]), 4)  # noqa: E731
    alarms = {c: int((table[c].to_numpy() >= causal_threshold(table[c].to_numpy(), 0.9)).sum()) for c in table}
    pairs = {
        "routes_as_served (Step 8)": corr("r2_as_served", "e20r_mean_as_served"),
        "routes_on_training_state_same_length": corr("r2_training_state_same_length", "e20r_mean_training_state_same_length"),
        "routes_on_training_state_whole_day": corr("r2_training_state_whole_day", "e20r_mean_training_state_whole_day"),
        "e20r_mean_live_vs_training_state (live-state effect)": corr("e20r_mean_as_served", "e20r_mean_training_state_same_length"),
        "r2_live_vs_training_state (CSV parity)": corr("r2_as_served", "r2_training_state_same_length"),
        "e20r_mean_same_length_vs_whole_day (length effect)": corr("e20r_mean_training_state_same_length", "e20r_mean_training_state_whole_day"),
        "r2_same_length_vs_whole_day (length effect)": corr("r2_training_state_same_length", "r2_training_state_whole_day"),
    }
    result = {"windows": int(len(table)), "t0": str(ts[0]), "score_corr": pairs, "causal_q90_alarm_windows": alarms,
              "mean_score": {c: round(float(table[c].mean()), 4) for c in table}}
    save_run("e27-step8-decompose", result, config={**vars(args), "decision": "D-038", "command": " ".join(sys.argv)})
    for k, v in pairs.items():
        print(f"{v:8.4f}  {k}")
    print(alarms)


if __name__ == "__main__":
    main()
