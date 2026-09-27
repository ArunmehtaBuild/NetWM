"""Task R-4: Offline Guarantee Verification.

Proves that NetWM operates 100% offline with zero external network or cloud calls.
Intercepts socket connections to ensure no outbound connection to non-loopback hosts
or external web ports (e.g. 80, 443) is attempted during health check, model loading,
demo execution, result retrieval, or SSE streaming.
"""

from __future__ import annotations

import io
from pathlib import Path
import socket
import time
from fastapi.testclient import TestClient
import pytest

from backend.server import app


def test_zero_network_calls_guarantee(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no outbound socket connections are made across all backend flows."""

    original_connect = socket.socket.connect

    def non_local_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) else address
        port = address[1] if isinstance(address, (tuple, list)) and len(address) > 1 else None

        # Allow internal Windows asyncio loopback self-pipe on 127.0.0.1 / localhost
        # but forbid any external hosts or standard cloud / web service ports
        if host not in {"127.0.0.1", "localhost", "::1"} or port in {80, 443, 8000, 8080}:
            raise RuntimeError(
                f"CRITICAL: Outbound network call to {host}:{port} attempted in offline mode!"
            )
        return original_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", non_local_connect)

    client = TestClient(app)

    # 1. Health check
    h_resp = client.get("/api/health")
    assert h_resp.status_code == 200
    assert h_resp.json()["offline"] is True

    # 2. Model information & card retrieval
    m_resp = client.get("/api/model")
    assert m_resp.status_code == 200

    # 3. Demos catalog
    d_resp = client.get("/api/demos")
    assert d_resp.status_code == 200

    # 4. Upload CSV analysis
    sample_csv = (
        "Timestamp,Src IP,Dst IP,Dst Port,fwd_pkts,bwd_pkts\n"
        "2017-07-06 12:00:00,192.168.10.14,192.168.10.50,80,5,5\n"
        "2017-07-06 12:01:00,192.168.10.14,192.168.10.50,80,6,6\n"
    )
    upload_resp = client.post(
        "/api/analyze",
        files={"file": ("offline_sample.csv", io.BytesIO(sample_csv.encode("utf-8")), "text/csv")},
    )
    assert upload_resp.status_code == 202
    upload_job_id = upload_resp.json()["job_id"]


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "data" / "demo" / "thursday_infiltration.csv").exists(),
    reason="Demo slice thursday_infiltration.csv missing (clean checkout without generated data)",
)
def test_demo_execution_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure demo execution and streaming make no outbound network calls."""
    original_connect = socket.socket.connect

    def non_local_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) else address
        port = address[1] if isinstance(address, (tuple, list)) and len(address) > 1 else None
        if host not in {"127.0.0.1", "localhost", "::1"} or port in {80, 443, 8000, 8080}:
            raise RuntimeError(
                f"CRITICAL: Outbound network call to {host}:{port} attempted in offline mode!"
            )
        return original_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", non_local_connect)
    client = TestClient(app)

    # Demo execution lifecycle
    demo_resp = client.post("/api/analyze/demo/thursday_infiltration")
    assert demo_resp.status_code == 202
    demo_job_id = demo_resp.json()["job_id"]

    # Wait for completion - the demo now runs real inference, not a fixture load
    for _ in range(1500):
        time.sleep(0.2)
        st = client.get(f"/api/jobs/{demo_job_id}").json()["state"]
        if st in {"done", "error"}:
            break
    assert st == "done"

    # Retrieve result payload
    res_resp = client.get(f"/api/jobs/{demo_job_id}/result")
    assert res_resp.status_code == 200

    # SSE Streaming replay
    with client.stream("GET", f"/api/jobs/{demo_job_id}/stream?speed=50") as stream_resp:
        assert stream_resp.status_code == 200
        count = 0
        for line in stream_resp.iter_lines():
            if line:
                count += 1
            if count >= 6:
                break
        assert count >= 6


def test_socket_lockdown_catches_remote_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that an attempt to connect to an external server actually raises an error."""
    original_connect = socket.socket.connect

    def non_local_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, (tuple, list)) else address
        port = address[1] if isinstance(address, (tuple, list)) and len(address) > 1 else None
        if host not in {"127.0.0.1", "localhost", "::1"} or port in {80, 443}:
            raise RuntimeError(
                f"CRITICAL: Outbound network call to {host}:{port} attempted in offline mode!"
            )
        return original_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", non_local_connect)

    s = socket.socket()
    with pytest.raises(RuntimeError, match="CRITICAL: Outbound network call"):
        s.connect(("8.8.8.8", 53))
