"""Functional tests for NetWM API endpoints and error paths."""

from __future__ import annotations

import io
import json
import time
from fastapi.testclient import TestClient
import pytest

from backend.server import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["offline"] is True
    assert "model_loaded" in data


def test_model_endpoint() -> None:
    response = client.get("/api/model")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "stages" in data
    assert len(data["stages"]) == 7
    # Check that BENIGN is id 0
    assert data["stages"][0]["key"] == "BENIGN"
    assert data["stages"][0]["color"] == "#9aa7b1"
    assert "metrics" in data
    assert "feature_count" in data


def test_demos_endpoint() -> None:
    response = client.get("/api/demos")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "id" in first
    assert "flows" in first
    assert "file" in first


def test_error_unsupported_format() -> None:
    file_bytes = b"fake binary data"
    response = client.post(
        "/api/analyze",
        files={"file": ("malicious.exe", io.BytesIO(file_bytes), "application/octet-stream")},
    )
    assert response.status_code == 415
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "unsupported_format"


def test_error_empty_file() -> None:
    response = client.post(
        "/api/analyze",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "bad_file"


def test_error_job_not_found() -> None:
    response = client.get("/api/jobs/j_nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "job_not_found"


def test_demo_job_lifecycle_and_results() -> None:
    # 1. Trigger demo job
    create_resp = client.post("/api/analyze/demo/thursday_infiltration")
    assert create_resp.status_code == 202
    job_id = create_resp.json()["job_id"]

    # 2. Poll until done (or timeout)
    for _ in range(50):
        time.sleep(0.1)
        status_resp = client.get(f"/api/jobs/{job_id}")
        assert status_resp.status_code == 200
        state = status_resp.json()["state"]
        if state in {"done", "error"}:
            break

    assert state == "done"

    # 3. Retrieve result payload
    result_resp = client.get(f"/api/jobs/{job_id}/result")
    assert result_resp.status_code == 200
    payload = result_resp.json()
    assert payload["payload_version"] == "1.1"
    assert "timeline" in payload
    assert len(payload["timeline"]) > 0

    # 4. Inspect flows for window 417
    flows_resp = client.get(f"/api/jobs/{job_id}/flows?window=417")
    assert flows_resp.status_code == 200
    flows_data = flows_resp.json()
    assert flows_data["window"] == 417
    assert "flows" in flows_data
    assert isinstance(flows_data["flows"], list)

    # 5. Check SSE stream starts and emits window events
    with client.stream("GET", f"/api/jobs/{job_id}/stream?speed=50") as stream_resp:
        assert stream_resp.status_code == 200
        lines = []
        for line in stream_resp.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 6:
                break
        assert any("event: window" in l for l in lines)
