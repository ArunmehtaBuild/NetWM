"""E27 Step 8 follow-up (descriptive, D-038 / D-040 / D-043): why the two routes' risk scores barely correlate.

    CUDA_VISIBLE_DEVICES="" python scripts/step8_decompose.py --pcap data/cic-2017-pcap/thursday_1640_1850.pcap --tag d043
    CUDA_VISIBLE_DEVICES="" python scripts/step8_decompose.py --pcap ... --flow-aggregator <old flow_aggregator.py> --tag pre-d043

Step 8 served one real Thursday window (16:40-18:50 UTC) through both routes: a CSV to the CSV route,
the capture to the PCAP route. Their per-window risk scores correlated at 0.035 (E27, r2 and the E20r
mean). Three things differ between those two scores, and this separates them by scoring the same 260
windows six ways (mean-path ``p_max``, the statistic the payload alarms on; deterministic):

- **as served**: the CSV route on the CSV slice, the PCAP route on the PCAP slice;
- **training state, same length**: each model on its own training matrix's rows for those windows,
  fed as a 260-window input - removes the live-state difference (the PCAP converter, N-9);
- **training state, whole day**: each model on the whole 972-window day, cut to those windows; the
  difference from the row above is the length effect (N-8).

``--routes served`` (default) scores the checkpoints the backend serves now (``backend.inference``);
``--routes e27`` the ones E27 served (r2, the E20r mean) and reproduces 77e5b10's run.
``--flow-aggregator`` loads ``pcap_to_flows`` from another file, so the same models can be scored
with the converter before a change. Nothing is tuned and no detection number is computed. Writes
results/tables/e27_step8_decompose[_tag].csv (per-window scores) and results/runs/e27-step8-decompose[-tag]/.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import _forecast, analyze_file, load_checkpoint, load_ensemble
from netwm.features import flow_aggregator
from netwm.metrics import causal_threshold
from netwm.utils import TABLES, ensure_dirs, save_run

CSV_DATA = "data/processed/cicids2017"
PACKET_DATA = "data/processed/cicids2017_m1v2p"
E27_ROUTES = {"csv": "e4e7-worldmodel-r2", "pcap": ("m1v2-e20r-s42", "m1v2-e20r-s43", "m1v2-e20r-s44")}


def served_routes() -> dict:
    from backend.inference import CSV_ROUTE_RUN, PCAP_ENSEMBLE_RUNS
    return {"csv": CSV_ROUTE_RUN, "pcap": tuple(PCAP_ENSEMBLE_RUNS)}


def matrix_scores(ckpt: dict, frame: pd.DataFrame) -> np.ndarray:
    """Mean-path p_max of a checkpoint (or ensemble mean) on a slice of its training matrix."""
    members = ckpt.get("members") or [ckpt]
    names, horizon = list(ckpt["feature_names"]), int(ckpt["horizon_k"])
    return np.mean([_forecast(m, m["scaler"].transform(frame[names]), horizon, 1, True)["p_max"] for m in members], axis=0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap", required=True, help="the real Thursday 16:40-18:50 UTC slice Step 8 used")
    ap.add_argument("--csv", default="data/demo/thursday_infiltration.csv")
    ap.add_argument("--routes", choices=("served", "e27"), default="served")
    ap.add_argument("--flow-aggregator", default=None, help="a flow_aggregator.py to take pcap_to_flows from (a baseline)")
    ap.add_argument("--tag", default="", help="suffix for the run folder and table")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    ensure_dirs()
    cpu = torch.device("cpu")
    suffix = f"_{args.tag}" if args.tag else ""

    if args.flow_aggregator:  # analyze_file imports pcap_to_flows from the module at call time
        spec = importlib.util.spec_from_file_location("baseline_flow_aggregator", args.flow_aggregator)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        flow_aggregator.pcap_to_flows = baseline.pcap_to_flows

    routes = served_routes() if args.routes == "served" else E27_ROUTES
    csv_ckpt = load_checkpoint(ROOT / "models" / routes["csv"] / "thursday.pt", cpu)
    pcap_ckpt = load_ensemble([ROOT / "models" / run / "thursday.pt" for run in routes["pcap"]], cpu)

    live = {}
    for key, path, ckpt in (("csv_route", ROOT / args.csv, csv_ckpt), ("pcap_route", ROOT / args.pcap, pcap_ckpt)):
        payload = analyze_file(path, ckpt, explain_limit=0)
        live[key] = pd.Series([e["p_max"] for e in payload["timeline"]],
                              index=pd.to_datetime([e["ts"] for e in payload["timeline"]], utc=True).tz_convert(None))
    ts = live["csv_route"].index
    if not ts.equals(live["pcap_route"].index):
        raise SystemExit("the two routes' window grids differ")

    series = {"csv_route_as_served": live["csv_route"].to_numpy(), "pcap_route_as_served": live["pcap_route"].to_numpy()}
    for key, ckpt, data in (("csv_route", csv_ckpt, CSV_DATA), ("pcap_route", pcap_ckpt, PACKET_DATA)):
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
    table.to_csv(TABLES / f"e27_step8_decompose{suffix}.csv")
    corr = lambda a, b: round(float(np.corrcoef(table[a], table[b])[0, 1]), 4)  # noqa: E731
    alarms = {c: int((table[c].to_numpy() >= causal_threshold(table[c].to_numpy(), 0.9)).sum()) for c in table}
    pairs = {
        "routes_as_served (Step 8)": corr("csv_route_as_served", "pcap_route_as_served"),
        "routes_on_training_state_same_length": corr("csv_route_training_state_same_length", "pcap_route_training_state_same_length"),
        "routes_on_training_state_whole_day": corr("csv_route_training_state_whole_day", "pcap_route_training_state_whole_day"),
        "pcap_route_live_vs_training_state (live-state effect)": corr("pcap_route_as_served", "pcap_route_training_state_same_length"),
        "csv_route_live_vs_training_state (CSV parity)": corr("csv_route_as_served", "csv_route_training_state_same_length"),
        "pcap_route_same_length_vs_whole_day (length effect)": corr("pcap_route_training_state_same_length", "pcap_route_training_state_whole_day"),
        "csv_route_same_length_vs_whole_day (length effect)": corr("csv_route_training_state_same_length", "csv_route_training_state_whole_day"),
    }
    result = {"windows": int(len(table)), "t0": str(ts[0]), "routes": {"csv": routes["csv"], "pcap": list(routes["pcap"])},
              "flow_aggregator": args.flow_aggregator or "netwm.features.flow_aggregator (working tree)",
              "score_corr": pairs, "causal_q90_alarm_windows": alarms,
              "mean_score": {c: round(float(table[c].mean()), 4) for c in table}}
    save_run("e27-step8-decompose" + suffix.replace("_", "-"), result,
             config={**vars(args), "decision": "D-038", "command": " ".join(sys.argv)})
    for k, v in pairs.items():
        print(f"{v:8.4f}  {k}")
    print(alarms)
    print(result["mean_score"])


if __name__ == "__main__":
    main()
