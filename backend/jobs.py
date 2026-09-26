"""In-memory job store and single-worker background queue for NetWM analysis.

PyTorch model inference is compute-heavy and blocking. A dedicated worker thread
pulls jobs sequentially from a FIFO queue, ensuring single-tenant GPU safety.
Results and uploads are written to disk and pruned automatically.
"""

from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from backend.config import settings
from backend.errors import APIError

logger = logging.getLogger("netwm.jobs")


@dataclass
class Job:
    id: str
    kind: str  # csv | pcap | demo
    filename: str
    file_path: Optional[Path]
    state: str  # queued | running | done | error
    progress: float  # 0.0 to 1.0
    stage_text: str
    result_path: Optional[Path] = None
    error: Optional[dict[str, str]] = None
    created_at: float = 0.0
    policy: Optional[str] = None
    threshold: Optional[float] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._runner: Optional[Callable[[Job, Callable[[float, str], None]], Path]] = None
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def set_runner(
        self, runner: Callable[[Job, Callable[[float, str], None]], Path]
    ) -> None:
        """Register the callable that runs inference for a job."""
        self._runner = runner

    def _ensure_worker(self) -> None:
        if not self._worker_thread.is_alive():
            logger.warning("Worker thread died, restarting worker...")
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()

    def create_job(
        self,
        kind: str,
        filename: str,
        file_path: Optional[Path] = None,
        policy: Optional[str] = None,
        threshold: Optional[float] = None,
        enqueue: bool = True,
    ) -> Job:
        """Register a job; enqueue it now unless its input is still being written.

        Uploads pass ``enqueue=False`` and call :meth:`submit` once the file is on disk -
        enqueueing first let the worker pick the job up with ``file_path=None`` (R-5).
        """
        self._ensure_worker()
        with self._lock:
            self._cleanup_locked()
            job_id = f"j_{uuid.uuid4().hex[:8]}"
            job = Job(
                id=job_id,
                kind=kind,
                filename=filename,
                file_path=file_path,
                state="queued",
                progress=0.0,
                stage_text="queued",
                created_at=time.time(),
                policy=policy,
                threshold=threshold,
            )
            self._jobs[job_id] = job
            if enqueue:
                self._queue.put(job_id)
            logger.info("Job created: id=%s kind=%s file=%s", job_id, kind, filename)
            return job

    def submit(self, job_id: str) -> None:
        """Hand a job registered with ``enqueue=False`` to the worker."""
        self._ensure_worker()
        self._queue.put(job_id)

    def discard(self, job_id: str) -> None:
        """Forget a job whose input never arrived (rejected or failed upload)."""
        with self._lock:
            self._delete_job_files(self._jobs.pop(job_id, None))

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)

    def _cleanup_locked(self) -> None:
        """Prune jobs older than 2 hours or when count > max_active_jobs (oldest first)."""
        now = time.time()
        # 1. Prune expired jobs
        expired_ids = [
            jid
            for jid, j in self._jobs.items()
            if j.state in {"done", "error"}
            and (now - j.created_at) > settings.job_retention_seconds
        ]
        for jid in expired_ids:
            self._delete_job_files(self._jobs.pop(jid, None))

        # 2. Prune if count exceeds limit (prune oldest done/error jobs first)
        if len(self._jobs) >= settings.max_active_jobs:
            completed = sorted(
                [j for j in self._jobs.values() if j.state in {"done", "error"}],
                key=lambda j: j.created_at,
            )
            to_remove = len(self._jobs) - settings.max_active_jobs + 1
            for j in completed[:to_remove]:
                self._jobs.pop(j.id, None)
                self._delete_job_files(j)

    def _delete_job_files(self, job: Optional[Job]) -> None:
        if not job:
            return
        try:
            if job.result_path and job.result_path.exists():
                job.result_path.unlink()
            if job.file_path and job.file_path.exists():
                # If upload directory contains only this file or is job upload dir, clean up
                parent = job.file_path.parent
                if parent != settings.uploads_dir and parent.name == job.id:
                    shutil.rmtree(parent, ignore_errors=True)
                else:
                    job.file_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Failed cleaning up files for job %s: %s", job.id, exc)

    def _worker_loop(self) -> None:
        """Sequential single-worker queue loop."""
        while True:
            try:
                job_id = self._queue.get()
                job = self.get_job(job_id)
                if not job:
                    self._queue.task_done()
                    continue

                self.update_job(job_id, state="running", progress=0.05, stage_text="starting")
                logger.info("Starting processing job %s", job_id)

                if self._runner is None:
                    self.update_job(
                        job_id,
                        state="error",
                        error={"code": "internal", "message": "Inference runner not initialized"},
                    )
                    self._queue.task_done()
                    continue

                def progress_cb(pct: float, text: str) -> None:
                    self.update_job(job_id, progress=min(1.0, max(0.0, pct)), stage_text=text)

                try:
                    result_path = self._runner(job, progress_cb)
                    self.update_job(
                        job_id,
                        state="done",
                        progress=1.0,
                        stage_text="done",
                        result_path=result_path,
                    )
                    logger.info("Job %s completed successfully", job_id)
                except Exception as exc:
                    logger.exception("Job %s execution failed: %s", job_id, exc)
                    self.update_job(
                        job_id,
                        state="error",
                        progress=1.0,
                        stage_text="failed",
                        error={"code": _error_code(exc), "message": str(exc)},
                    )
                finally:
                    self._queue.task_done()
            except Exception as exc:
                logger.critical("Unexpected error in job queue worker: %s", exc)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, APIError):
        return exc.code
    return "bad_file" if isinstance(exc, ValueError) else "internal"


job_store = JobStore()
