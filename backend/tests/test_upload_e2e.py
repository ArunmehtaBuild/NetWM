"""End-to-end: the product's main interaction - upload a CSV, get a real forecast back.

test_api.py only checked the 202 and the job record, which let R-5 (worker raced the upload and
never saw the file) reach the board as done. These tests must reach ``state == "done"``.
"""

from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.inference import get_checkpoint, resolve_demo
from backend.errors import APIError
from backend.server import app
from netwm.data.cicids2017 import COLUMN_MAP

client = TestClient(app)

needs_model = pytest.mark.skipif(get_checkpoint() is None, reason="no checkpoint in models/")


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
    metrics = client.get("/api/model").json()["metrics"]
    assert metrics["f1"] == pytest.approx(0.576, abs=1e-3)
    assert metrics["fpr"] == pytest.approx(0.027, abs=1e-3)
    assert metrics["baseline_f1"] == pytest.approx(0.011, abs=1e-3)
    assert metrics["mean_lead_time_windows"] == 0.0
