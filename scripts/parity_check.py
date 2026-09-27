"""D-037: the state the API builds for an upload equals the state the model was trained on.

    python scripts/parity_check.py --day thursday --pcap D:/CIC-2017-PCAP/Thursday-WorkingHours.pcap

Builds the state for one full real day through the inference path - ``read_flow_csv`` (what a CSV
upload goes through) and ``engine.predict.state_matrix`` with the capture (what a PCAP upload's packet
block goes through) - and compares it, window by window, with the training matrix in
``data/processed/cicids2017_m1v2p``. Checks both input forms of the E26 feature set:

  pcap mode  every one of the 106 inputs, packets measured from the capture
  csv mode   the same with the packet block absent (pcap_ = 0, has_pcap = 0), against the training
             matrix masked by the same function training dropout uses

Writes ``results/runs/parity-<day>/metrics.json``. Exit status 1 on any mismatch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from netwm.data.processed import ProcessedDataset
from netwm.engine.predict import read_flow_csv, state_matrix
from netwm.features.packet_windows import mask_packets
from netwm.features.windowing import WindowSpec
from netwm.utils import save_run
from train import select_features

import yaml


def compare(a, b, names) -> dict:
    diff = np.abs(a[names].to_numpy(float) - b[names].to_numpy(float))
    tol = 1e-6 * np.maximum(1.0, np.abs(b[names].to_numpy(float)))
    bad = diff > tol
    worst = {names[j]: float(diff[:, j].max()) for j in np.flatnonzero(bad.any(axis=0))}
    return {"windows": int(len(a)), "inputs": len(names), "mismatched_cells": int(bad.sum()),
            "mismatched_inputs": worst}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", default="thursday")
    ap.add_argument("--pcap", required=True)
    ap.add_argument("--data", default="data/processed/cicids2017_m1v2p")
    ap.add_argument("--raw", default="data/raw/cicids2017_improved")
    ap.add_argument("--model-config", default="configs/m1v2/e26_combined.yaml")
    args = ap.parse_args()

    ds = ProcessedDataset(args.data)
    cfg = yaml.safe_load(Path(args.model_config).read_text(encoding="utf-8"))
    names = select_features(ds.feature_names, cfg.get("features"))
    train = ds.frame(args.day)
    spec = WindowSpec(ds.meta["config"]["window"]["length_s"], ds.stride_s)

    flows = read_flow_csv(Path(args.raw) / f"{args.day}.csv")
    served, _, t0, n = state_matrix(flows, names, spec, pcap_path=args.pcap)
    served_csv, _, _, _ = state_matrix(flows, names, spec, pcap_path=None)
    assert str(t0) == next(m["t0"] for m in ds.meta["splits"] if m["split"] == args.day), "window grid differs"
    assert n == len(train), f"{n} windows served vs {len(train)} trained"

    result = {
        "day": args.day,
        "t0": str(t0),
        "pcap_mode": compare(served.reset_index(drop=True), train.reset_index(drop=True), names),
        "csv_mode": compare(served_csv.reset_index(drop=True), mask_packets(train[names]).reset_index(drop=True), names),
    }
    ok = result["pcap_mode"]["mismatched_cells"] == 0 and result["csv_mode"]["mismatched_cells"] == 0
    result["identical"] = ok
    save_run(f"parity-{args.day}", result, config=vars(args))
    print(result)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
