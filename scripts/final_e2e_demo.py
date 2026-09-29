"""F8: the final end-to-end demo test - the frozen code, the served checkpoints and the demo data, through
the API exactly as the dashboard calls it, with every outbound connection refused.

    python scripts/final_e2e_demo.py

Checks, and exits non-zero if any fails:

- ``/api/health`` is ok with a model loaded and ``offline``; ``/api/model``'s route metrics equal D-041's
  gate rows for held-out Thursday (``results/tables/n8_fix_eval.csv``);
- the served weights are the frozen ones: every fold's SHA-256 equals its run's ``checkpoints_manifest.json``;
- the Thursday demo (held out) is served live (``mock`` false) by r2w seed 42 on the causal expanding 10 %
  budget (D-034), and the same slice uploaded as a CSV gives the same scores and alarms;
- the demo PCAP uploaded is served by the mean of the three E20rw seeds on all 105 inputs, on the same
  policy, never by the CSV model.

The slice figures it records (alarmed windows, alarms on attack windows, early warnings) describe one demo
slice under its own causal budget; they are not an evaluation. The PCAP route's are not quoted as the
model's (N-9: live-PCAP state parity is open). Writes ``results/runs/f8-final-e2e/``.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from netwm.utils import TABLES, git_sha, save_run  # noqa: E402

RUN = "f8-final-e2e"
DEMO_CSV = ROOT / "data" / "demo" / "thursday_infiltration.csv"
DEMO_PCAP = ROOT / "data" / "demo" / "thursday_demo.pcap"
CARD_KEYS = ("f1", "precision", "recall", "fpr", "pr_auc")


def refuse_remote_connections() -> None:
    """The offline claim: any connection to a non-loopback address raises (as backend/tests/test_offline.py)."""
    original = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ConnectionRefusedError(f"outbound connection attempted during the offline demo: {address}")
        return original(self, address)

    socket.socket.connect = connect


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def summary(payload: dict) -> dict:
    tl = payload["timeline"]
    alarmed = [w for w in tl if w["alarm"]]
    labelled = any(w.get("observed_stage") is not None for w in tl)
    lead = payload.get("lead_time_summary") or {}
    inf = payload["inference"]
    return {
        "mock": payload["mock"], "threshold_policy": payload["threshold_policy"],
        "alarm_statistic": payload["alarm_statistic"], "input_modality": inf["input_modality"],
        "model_mode": inf["model_mode"], "aggregation": inf.get("aggregation"), "feature_count": inf.get("feature_count"),
        "checkpoints": [Path(c).parent.name + "/" + Path(c).name for c in inf["checkpoints"]],
        "flows": payload["source"]["flows"], "windows": len(tl), "warmup_windows": payload["threshold_warmup_windows"],
        "threshold_at_end": round(float(payload["threshold"]), 4), "alarmed_windows": len(alarmed),
        "alarmed_on_attack_windows": sum(1 for w in alarmed if w.get("observed_stage")) if labelled else None,
        "alarm_runs": len(payload.get("alarms") or []),
        "early_warning": ({k: lead.get(k) for k in ("episodes", "warned_early", "p_value")} if lead else None),
        "in_sample": payload.get("in_sample"),
    }


def main() -> None:
    refuse_remote_connections()
    from fastapi.testclient import TestClient

    from backend import inference
    from backend.server import app

    client = TestClient(app)
    checks: dict[str, bool] = {}

    def wait(job_id: str, timeout_s: float = 900.0) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = client.get(f"/api/jobs/{job_id}").json()
            if status["state"] in {"done", "error"}:
                if status["state"] != "done":
                    raise SystemExit(f"job {job_id} failed: {status}")
                return client.get(f"/api/jobs/{job_id}/result").json()
            time.sleep(0.5)
        raise SystemExit(f"job {job_id} did not finish in {timeout_s} s")

    def upload(path: Path, mime: str) -> dict:
        with open(path, "rb") as f:
            resp = client.post("/api/analyze", files={"file": (path.name, f, mime)})
        return wait(resp.json()["job_id"])

    health = client.get("/api/health").json()
    checks["health ok, model loaded, offline"] = (health["status"] == "ok" and health["model_loaded"]
                                                  and health.get("offline") is True)

    card = client.get("/api/model").json()
    gate = pd.read_csv(TABLES / "n8_fix_eval.csv")
    thu = gate[gate["day"] == "thursday"].set_index("run")
    for route, run in (("csv", inference.CSV_ROUTE_RUN), ("pcap", "n8-e20rw-mean")):
        served = card["routes"][route]["metrics"]
        checks[f"model card {route} route = D-041 gate row {run}"] = all(
            abs(served[k] - round(float(thu.loc[run, k]), 3)) < 1e-9 for k in CARD_KEYS)

    frozen = {}
    for run in (inference.CSV_ROUTE_RUN, *inference.PCAP_ENSEMBLE_RUNS):
        man = json.loads((ROOT / "results" / "runs" / run / "checkpoints_manifest.json").read_text(encoding="utf-8"))
        for c in man["checkpoints"]:
            pt = ROOT / "models" / run / Path(c["file"]).name
            frozen[f"{run}/{pt.name}"] = pt.exists() and sha256(pt) == c["sha256"]
    checks["served weights = frozen checkpoint hashes"] = all(frozen.values())

    demo = wait(client.post("/api/analyze/demo/thursday_infiltration").json()["job_id"])
    csv_up = upload(DEMO_CSV, "text/csv")
    pcap_up = upload(DEMO_PCAP, "application/vnd.tcpdump.pcap")
    s_demo, s_csv, s_pcap = summary(demo), summary(csv_up), summary(pcap_up)

    csv_ckpt = [f"{inference.CSV_ROUTE_RUN}/thursday.pt"]
    pcap_ckpts = [f"{r}/thursday.pt" for r in inference.PCAP_ENSEMBLE_RUNS]
    checks["demo: live, r2w seed 42, causal 10 % budget, held out"] = (
        s_demo["mock"] is False and s_demo["checkpoints"] == csv_ckpt
        and s_demo["threshold_policy"] == "expanding-10pct" and s_demo["in_sample"] is False)
    checks["CSV upload = the demo (scores and alarms)"] = (
        s_csv["checkpoints"] == csv_ckpt and s_csv["threshold_policy"] == "expanding-10pct"
        and [w["p_max"] for w in csv_up["timeline"]] == [w["p_max"] for w in demo["timeline"]]
        and [w["alarm"] for w in csv_up["timeline"]] == [w["alarm"] for w in demo["timeline"]])
    checks["PCAP upload: live mean of the three E20rw seeds, 105 inputs, causal 10 % budget"] = (
        s_pcap["mock"] is False and s_pcap["checkpoints"] == pcap_ckpts and s_pcap["feature_count"] == 105
        and s_pcap["input_modality"] == "pcap" and s_pcap["threshold_policy"] == "expanding-10pct")

    save_run(RUN, {"checks": checks, "passed": all(checks.values()), "health": health,
                   "model_card_routes": card["routes"], "frozen_checkpoints": frozen,
                   "thursday_demo": s_demo, "thursday_csv_upload": s_csv, "thursday_pcap_upload": s_pcap},
             config={"git_sha_at_start": git_sha(), "demo_csv": DEMO_CSV.name, "demo_csv_sha256": sha256(DEMO_CSV),
                     "demo_pcap": DEMO_PCAP.name, "demo_pcap_sha256": sha256(DEMO_PCAP),
                     "note": "slice figures describe one demo slice under its own causal budget - not an evaluation; "
                             "PCAP-route scores are not quoted as the model's (N-9)"})
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    for label, s in (("Thursday demo", s_demo), ("CSV upload", s_csv), ("PCAP upload", s_pcap)):
        print(f"{label}: {s['windows']} windows, {s['alarmed_windows']} alarmed "
              f"({s['alarmed_on_attack_windows']} on attack windows), {s['alarm_runs']} alarm runs, "
              f"early warning {s['early_warning']}, threshold at end {s['threshold_at_end']}")
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
