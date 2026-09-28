"""D-038 Step 8 (E27): the same traffic through both routes - CSV to r2, PCAP to the E20r mean.

    CUDA_VISIBLE_DEVICES="" python scripts/pcap_route_same_traffic.py --pcap data/demo/thursday_1640_1850.pcap

Runs the backend's own routing (``run_job_inference``) on the ``thursday_infiltration`` CSV slice and
on a real-capture PCAP of the same 16:40-18:50 window. The point is not equal scores - the PCAP route
is a different model reading 35 more inputs - but that both telemetry forms are served cleanly, by the
model D-038 names, in the one public payload format. Recorded: each payload's route metadata, schema
validation, window grid, alarm count and packet-feature status, and the per-window correlation of the
two risk scores on the windows both cover.

Writes results/runs/e27-same-traffic/metrics.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from backend.inference import run_job_inference
from backend.jobs import Job
from backend.schemas import AnalysisResultPayload
from netwm.utils import save_run


def serve(path: Path, kind: str) -> dict:
    job = Job(id=f"j_e27_{kind}", kind=kind, filename=path.name, file_path=path, state="running",
              progress=0.0, stage_text="")
    payload = json.loads(run_job_inference(job, lambda pct, msg: None).read_text(encoding="utf-8"))
    AnalysisResultPayload.model_validate(payload)  # the one public format, both routes
    return payload


def summary(p: dict) -> dict:
    return {
        "inference": p["inference"],
        "source_packet_features": p["source"].get("packet_features"),
        "windows": len(p["timeline"]),
        "t0": p["source"]["t0"],
        "threshold_policy": p["threshold_policy"],
        "alarm_statistic": p["alarm_statistic"],
        "alarm_windows": int(sum(e["alarm"] for e in p["timeline"])),
        "ground_truth_available": p["ground_truth"]["available"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="data/demo/thursday_infiltration.csv")
    ap.add_argument("--pcap", required=True, help="a real-capture slice of the same window, not the synthesised demo PCAP")
    args = ap.parse_args()

    csv_payload = serve(ROOT / args.csv, "csv")
    pcap_payload = serve(ROOT / args.pcap, "pcap")
    a, b = (pd.DataFrame([{"ts": e["ts"], "p_max": e["p_max"]} for e in p["timeline"]]) for p in (csv_payload, pcap_payload))
    both = a.merge(b, on="ts", suffixes=("_csv_r2", "_pcap_e20r"))
    result = {
        "csv_route": summary(csv_payload),
        "pcap_route": summary(pcap_payload),
        "shared_windows": int(len(both)),
        "risk_score_corr": round(float(np.corrcoef(both["p_max_csv_r2"], both["p_max_pcap_e20r"])[0, 1]), 4) if len(both) > 2 else None,
        "routes_as_d038": (csv_payload["inference"]["telemetry"] == "flow"
                           and pcap_payload["inference"]["telemetry"] == "flow + packet"
                           and len(pcap_payload["inference"]["checkpoints"]) == 3),
    }
    save_run("e27-same-traffic", result, config={**vars(args), "decision": "D-038", "command": " ".join(sys.argv)})
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
