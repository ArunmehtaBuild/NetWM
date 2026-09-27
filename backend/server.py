"""FastAPI server for NetWM attack forecasting API.

Serves docs/api_contract.md v1.1. Thin routing layer; delegates ML logic
to backend.inference and async queueing to backend.jobs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from backend.config import settings
from backend.errors import APIError, register_error_handlers
from backend.inference import (
    get_checkpoint,
    get_demo_scenarios,
    get_flows_for_window,
    get_model_card,
    resolve_demo,
    run_job_inference,
)
from backend.jobs import job_store
from backend.schemas import (
    DemoItem,
    FlowsResponse,
    HealthResponse,
    JobCreatedResponse,
    JobStatusResponse,
    ModelResponse,
)

logger = logging.getLogger("netwm.server")

# Connect the inference runner to the background job queue
job_store.set_runner(run_job_inference)

app = FastAPI(
    title="NetWM API",
    description="Network Attack Forecasting Engine - SIH 2026",
    version="1.1.0",
    docs_url="/docs",
    redoc_url=None,
)

# Register custom exception handlers for uniform {"error": {"code": "...", "message": "..."}} responses
register_error_handlers(app)

# Explicit CORS allowlist - wildcard '*' is strictly forbidden
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _sanitize_filename(name: str) -> str:
    """Sanitize uploaded filename to avoid path traversal."""
    cleaned = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", cleaned)
    return cleaned or "upload.csv"


@app.get("/api/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness check and model availability status."""
    ckpt = get_checkpoint()
    return HealthResponse(
        status="ok",
        model_loaded=(ckpt is not None),
        active_checkpoint=str(ckpt.get("test_day", "default")) if ckpt else None,
        offline=True,
    )


@app.get("/api/model", response_model=ModelResponse)
async def model_info() -> ModelResponse:
    """Return model card and MITRE ATT&CK stage catalogue."""
    data = get_model_card()
    return ModelResponse.model_validate(data)


@app.get("/api/demos", response_model=list[DemoItem])
async def list_demos() -> list[DemoItem]:
    """Return preloaded demo scenarios."""
    scenarios = get_demo_scenarios()
    return [DemoItem.model_validate(s) for s in scenarios]


@app.post("/api/analyze", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreatedResponse)
async def analyze_file(
    request: Request,
    file: UploadFile = File(...),
    policy: Optional[str] = Query(None),
    threshold: Optional[float] = Query(None),
) -> JobCreatedResponse:
    """Upload a CSV or PCAP network capture for forecasting analysis."""
    if not file.filename:
        raise APIError("bad_file", "Upload filename cannot be empty")

    ext = Path(file.filename).suffix.lower()
    allowed_exts = {".csv", ".pcap", ".pcapng"}
    if ext not in allowed_exts:
        raise APIError(
            "unsupported_format",
            f"File format '{ext}' is not supported. Allowed formats: {sorted(allowed_exts)}",
        )

    # Check Content-Length header if provided
    content_length = request.headers.get("content-length")
    max_bytes = settings.max_pcap_bytes if "pcap" in ext else settings.max_csv_bytes
    if content_length and int(content_length) > max_bytes:
        raise APIError(
            "too_large",
            f"File size exceeds maximum limit of {max_bytes // (1024 * 1024)} MB",
        )

    # Register the job but do not enqueue it until the file is fully on disk,
    # otherwise the worker races the upload and sees file_path=None (R-5).
    clean_name = _sanitize_filename(file.filename)
    job = job_store.create_job(
        kind=ext.lstrip("."),
        filename=clean_name,
        policy=policy,
        threshold=threshold,
        enqueue=False,
    )

    upload_dir = settings.uploads_dir / job.id
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = (upload_dir / clean_name).resolve()

    total_bytes = 0
    chunk_size = 1024 * 1024  # 1 MB chunks
    try:
        with open(destination, "wb") as f_out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise APIError(
                        "too_large",
                        f"File size exceeds limit of {max_bytes // (1024 * 1024)} MB",
                    )
                f_out.write(chunk)
        if total_bytes == 0:
            raise APIError("bad_file", "Uploaded file is empty (0 bytes)")
    except BaseException:
        job.file_path = destination
        job_store.discard(job.id)
        raise
    finally:
        await file.close()

    job_store.update_job(job.id, file_path=destination)
    logger.info("Upload for job %s written: %s (%d bytes)", job.id, destination, total_bytes)
    job_store.submit(job.id)
    return JobCreatedResponse(job_id=job.id, state="queued")


@app.post("/api/analyze/demo/{demo_id}", status_code=status.HTTP_202_ACCEPTED, response_model=JobCreatedResponse)
async def analyze_demo(
    demo_id: str,
    policy: Optional[str] = Query(None),
    threshold: Optional[float] = Query(None),
) -> JobCreatedResponse:
    """Launch analysis for a preloaded demo scenario."""
    resolve_demo(demo_id)  # 400/503 now, not a job that fails later

    job = job_store.create_job(
        kind="demo",
        filename=demo_id,
        policy=policy,
        threshold=threshold,
    )
    return JobCreatedResponse(job_id=job.id, state="queued")


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Poll job status, progress, and stage text."""
    job = job_store.get_job(job_id)
    if not job:
        raise APIError("job_not_found", f"Job '{job_id}' not found or has expired")
    return JobStatusResponse(
        id=job.id,
        state=job.state,
        progress=round(job.progress, 3),
        stage_text=job.stage_text,
        error=job.error,
    )


@app.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str) -> FileResponse:
    """Return the cached JSON analysis payload without re-serialization."""
    job = job_store.get_job(job_id)
    if not job:
        raise APIError("job_not_found", f"Job '{job_id}' not found or has expired")
    if job.state == "error":
        msg = (job.error or {}).get("message", "Inference failed")
        code = (job.error or {}).get("code", "internal")
        raise APIError(code, f"Job failed: {msg}")
    if job.state != "done" or not job.result_path or not job.result_path.exists():
        raise APIError("job_not_found", f"Job '{job_id}' results are not ready yet")

    return FileResponse(
        path=job.result_path,
        media_type="application/json",
        filename=f"{job_id}_result.json",
    )


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_replay(
    request: Request,
    job_id: str,
    speed: float = Query(4.0, ge=0.1, le=100.0, description="Replay rate in windows/second"),
    from_window: int = Query(0, ge=0, alias="from", description="Starting window index t"),
) -> StreamingResponse:
    """SSE replay stream for the dashboard play/pause scrubber.
    
    Streams timeline entries window-by-window at the requested speed starting from `from_window`.
    """
    job = job_store.get_job(job_id)
    if not job:
        raise APIError("job_not_found", f"Job '{job_id}' not found or has expired")
    if job.state != "done" or not job.result_path or not job.result_path.exists():
        raise APIError("job_not_found", f"Results for job '{job_id}' are not ready yet")

    try:
        with open(job.result_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        raise APIError("internal", f"Failed reading job result cache: {exc}")

    timeline = payload.get("timeline", [])
    if from_window > 0:
        timeline = [entry for entry in timeline if entry.get("t", 0) >= from_window]
    delay_s = 1.0 / speed

    async def event_generator() -> AsyncGenerator[str, None]:
        last_heartbeat = time.time()
        for entry in timeline:
            if await request.is_disconnected():
                logger.info("Client disconnected from SSE replay of job %s", job_id)
                break

            now = time.time()
            if now - last_heartbeat > 15.0:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            entry_json = json.dumps(entry)
            yield f"event: window\ndata: {entry_json}\n\n"
            await asyncio.sleep(delay_s)

        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs/{job_id}/flows", response_model=FlowsResponse)
async def inspect_flows(
    job_id: str,
    window: int = Query(..., ge=0, description="Window index t"),
    limit: int = Query(50, ge=1, le=500, description="Max flows to return"),
) -> FlowsResponse:
    """Retrieve flows flagged for a specific window index."""
    job = job_store.get_job(job_id)
    if not job:
        raise APIError("job_not_found", f"Job '{job_id}' not found or has expired")
    data = get_flows_for_window(job, window, limit)
    return FlowsResponse.model_validate(data)
