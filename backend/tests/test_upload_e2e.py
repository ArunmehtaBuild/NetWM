"""End-to-end: the product's main interaction - upload a CSV, get a real forecast back.

test_api.py only checked the 202 and the job record, which let R-5 (worker raced the upload and
never saw the file) reach the board as done. These tests must reach ``state == "done"``.
"""

from __future__ import annotations

import io
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.inference import get_checkpoint, pcap_ensemble_paths, resolve_demo
from backend.errors import APIError
from backend.server import app
from netwm.data.cicids2017 import COLUMN_MAP

client = TestClient(app)

needs_model = pytest.mark.skipif(get_checkpoint() is None, reason="no checkpoint in models/")

try:
    from netwm.features.flow_aggregator import pcap_to_flows
    has_pcap_aggregator = True
except Exception:
    has_pcap_aggregator = False

needs_pcap = pytest.mark.skipif(
    not has_pcap_aggregator,
    reason="PCAP flow aggregator not importable (scapy or flow_aggregator missing)",
)

# D-038: a PCAP upload is served by the three E20r seeds, never by r2 (models/ is not tracked)
needs_pcap_ensemble = pytest.mark.skipif(
    not all(p.exists() for p in pcap_ensemble_paths()),
    reason="E20r checkpoints (the PCAP route, D-038) not in models/",
)


def _synthetic_flow_csv(minutes: int = 20, flows_per_min: int = 40, seed: int = 42) -> bytes:
    """A small CIC-schema flow CSV, so the test needs no gitignored data."""
    rng = np.random.default_rng(seed)
    n = minutes * flows_per_min
    start = pd.Timestamp("2017-07-06 12:00:00")
    df = pd.DataFrame({col: rng.integers(0, 1000, n) for col in COLUMN_MAP})
    df["Timestamp"] = (start + pd.to_timedelta(np.sort(rng.uniform(0, minutes * 60, n)), unit="s")
                       ).strftime("%Y-%m-%d %H:%M:%S.%f")
    df["Src IP"] = [f"192.168.10.{i}" for i in rng.integers(2, 60, n)]
    df["Dst IP"] = [f"205.174.165.{i}" for i in rng.integers(2, 90, n)]
    df["Protocol"] = 6
    df["Label"] = "BENIGN"
    return df.to_csv(index=False).encode()


def _wait(job_id: str, timeout_s: float = 300.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["state"] in {"done", "error"}:
            return status
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish in {timeout_s}s")


@needs_model
def test_upload_csv_runs_real_inference() -> None:
    resp = client.post(
        "/api/analyze",
        files={"file": ("upload_test.csv", io.BytesIO(_synthetic_flow_csv()), "text/csv")},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status = _wait(job_id)
    assert status["state"] == "done", status

    payload = client.get(f"/api/jobs/{job_id}/result").json()
    assert payload["mock"] is False
    assert len(payload["timeline"]) > 0
    assert payload["source"]["filename"] == "upload_test.csv"
    # D-038: a CSV is served by the flow-only r2, and says packet features were unavailable
    assert payload["inference"]["telemetry"] == "flow"
    assert payload["inference"]["packet_features"] == "unavailable (flow input)"


def _synthetic_pcap_bytes(packet_count: int = 50, step_seconds: float = 20.0) -> bytes:
    """A small synthetic PCAP of answered TCP handshakes across ~15-20 minutes (a flow of one packet
    is not emitted, D-043)."""
    from scapy.all import Ether, IP, TCP, wrpcap
    from tempfile import NamedTemporaryFile

    base_time = 1499342400.0  # 2017-07-06 12:00:00 UTC
    packets = []
    for i in range(packet_count):
        pkt = Ether() / IP(src="192.168.10.14", dst="205.174.165.80") / TCP(sport=1024 + i, dport=80, flags="S")
        pkt.time = base_time + i * step_seconds
        reply = Ether() / IP(src="205.174.165.80", dst="192.168.10.14") / TCP(sport=80, dport=1024 + i, flags="SA")
        reply.time = base_time + i * step_seconds + 0.05
        packets += [pkt, reply]

    with NamedTemporaryFile(suffix=".pcap", delete=False) as tmp:
        tmp_name = tmp.name
    try:
        wrpcap(tmp_name, packets)
        data = Path(tmp_name).read_bytes()
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    return data


@needs_pcap_ensemble
@needs_pcap
def test_upload_pcap_runs_real_inference() -> None:
    """Task R-11: PCAP end-to-end upload test matching the CSV upload coverage; since D-038 the
    capture is served by the packet-enriched E20r ensemble."""
    resp = client.post(
        "/api/analyze",
        files={"file": ("upload_test.pcap", io.BytesIO(_synthetic_pcap_bytes()), "application/vnd.tcpdump.pcap")},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    status = _wait(job_id)
    assert status["state"] == "done", status

    payload = client.get(f"/api/jobs/{job_id}/result").json()
    assert payload["mock"] is False
    assert len(payload["timeline"]) > 0
    assert payload["source"]["filename"] == "upload_test.pcap"
    assert payload["source"]["kind"] == "pcap"
    # a capture carries no labels: the payload must not claim all-benign ground truth
    assert payload["ground_truth"]["available"] is False
    assert payload["inference"]["telemetry"] == "flow + packet"
    assert payload["inference"]["model_mode"] == "packet-enriched ensemble of 3"
    assert payload["inference"]["packet_features"] == "measured from the capture"


@needs_model
def test_demo_runs_real_inference_on_its_slice() -> None:
    try:
        resolve_demo("thursday_infiltration")
    except APIError:
        pytest.skip("data/demo/ not generated (python scripts/make_demo_samples.py)")

    resp = client.post("/api/analyze/demo/thursday_infiltration")
    assert resp.status_code == 202
    status = _wait(resp.json()["job_id"])
    assert status["state"] == "done", status

    payload = client.get(f"/api/jobs/{resp.json()['job_id']}/result").json()
    assert payload["mock"] is False
    # 16:40-18:50 is 130 min -> ~259 windows, not the 972 of a full-day fixture
    assert 200 < len(payload["timeline"]) < 300


def test_model_card_metrics_come_from_results() -> None:
    card = client.get("/api/model").json()
    metrics = card["metrics"]
    # The CSV route's model (r2w seed 42, D-041) at the causal budget the dashboard applies (D-034,
    # G-9), as D-041's gate evaluation scored it (results/runs/n8-fix-eval/)
    assert metrics["f1"] == pytest.approx(0.591, abs=1e-3)
    assert metrics["fpr"] == pytest.approx(0.093, abs=1e-3)
    assert metrics["pr_auc"] == pytest.approx(0.677, abs=1e-3)
    pcap = card["routes"]["pcap"]["metrics"]
    assert pcap["pr_auc"] == pytest.approx(0.514, abs=1e-3) and pcap["f1"] == pytest.approx(0.583, abs=1e-3)
    # LR at the same causal threshold (benchmark-final, G-6); E3's 0.011 used LR's own threshold
    assert metrics["baseline_f1"] == pytest.approx(0.112, abs=1e-3)
    assert metrics["mean_lead_time_windows"] == 0.0
