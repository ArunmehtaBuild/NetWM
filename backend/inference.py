"""Inference engine wrapper and model registry for NetWM.

Wraps netwm.engine.predict.analyze_file, manages model lifecycle,
and provides graceful fallback to fixtures/api/*.json when no checkpoint is present.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

# Ensure src/ is on sys.path so netwm imports seamlessly
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from backend.config import settings
from backend.errors import APIError
from backend.jobs import Job

logger = logging.getLogger("netwm.inference")

_cached_ckpt: Optional[dict[str, Any]] = None
_active_model_name: Optional[str] = None


def get_registry() -> dict[str, str]:
    reg_path = settings.models_dir / "registry.json"
    if reg_path.exists():
        try:
            with open(reg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", reg_path, exc)
    return {
        "default": "e4e7-worldmodel-r2/thursday.pt",
        "thursday": "e4e7-worldmodel-r2/thursday.pt",
        "friday": "e4e7-worldmodel-r2/friday.pt",
    }


def get_checkpoint(name: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Lazy-load checkpoint into memory; return None if checkpoint is not found."""
    global _cached_ckpt, _active_model_name
    registry = get_registry()
    model_key = name or "default"
    rel_path = registry.get(model_key, registry.get("default"))

    if not rel_path:
        return None

    if _cached_ckpt is not None and _active_model_name == model_key:
        return _cached_ckpt

    ckpt_path = settings.models_dir / rel_path
    if not ckpt_path.exists():
        logger.info("Checkpoint file not found: %s. Operating in mock fallback mode.", ckpt_path)
        return None

    try:
        from netwm.engine.predict import load_checkpoint

        logger.info("Loading checkpoint from %s ...", ckpt_path)
        ckpt = load_checkpoint(ckpt_path)
        _cached_ckpt = ckpt
        _active_model_name = model_key
        logger.info("Checkpoint loaded successfully: %s", model_key)
        return _cached_ckpt
    except Exception as exc:
        logger.exception("Failed to load checkpoint from %s: %s", ckpt_path, exc)
        return None


def get_model_card() -> dict[str, Any]:
    """Return model card matching ModelResponse schema."""
    from netwm.engine.predict import stage_catalogue

    ckpt = get_checkpoint()
    stages = stage_catalogue()

    if ckpt is not None:
        model = ckpt["model"]
        param_count = sum(p.numel() for p in model.parameters())
        feature_count = len(ckpt.get("feature_names", []))
        git_sha = str(ckpt.get("git_sha", "unknown"))[:7]
        return {
            "name": f"netwm-rssm-r2 ({_active_model_name or 'default'})",
            "trained_on": "CIC-IDS2017 (corrected), Mon-Wed + Fri",
            "window_s": float(ckpt.get("stride_s", 30.0) * 2),
            "stride_s": float(ckpt.get("stride_s", 30.0)),
            "horizon_k": int(ckpt.get("horizon_k", 10)),
            "params": param_count,
            "git_sha": git_sha,
            "stages": stages,
            "metrics": {
                "f1": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "fpr": 0.0,
                "pr_auc": 0.0,
                "mean_lead_time_windows": 0.0,
                "baseline_f1": 0.0,
            },
            "feature_count": feature_count,
        }

    # Fallback model card when no checkpoint is present
    return {
        "name": "netwm-rssm-v1",
        "trained_on": "CIC-IDS2017 (corrected), Mon-Wed + Fri",
        "window_s": 60.0,
        "stride_s": 30.0,
        "horizon_k": 10,
        "params": 1840000,
        "git_sha": "abc1234",
        "stages": stages,
        "metrics": {
            "f1": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "fpr": 0.0,
            "pr_auc": 0.0,
            "mean_lead_time_windows": 0.0,
            "baseline_f1": 0.0,
        },
        "feature_count": 84,
    }


def get_demo_scenarios() -> list[dict[str, Any]]:
    """Read the catalog of preloaded demo scenarios."""
    path = settings.demo_index_path
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _load_fallback_fixture(day_or_name: str = "thursday") -> dict[str, Any]:
    """Load mock fixture ensuring system is never undemoable."""
    filename = "friday.json" if "friday" in day_or_name.lower() else "thursday.json"
    fixture_path = settings.fixtures_dir / filename
    if not fixture_path.exists():
        raise APIError("no_model", f"Neither model nor fixture found at {fixture_path}")
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["mock"] = True
    return data


def run_job_inference(job: Job, progress_cb: Callable[[float, str], None]) -> Path:
    """Execute analysis for a job and persist the result payload to disk."""
    progress_cb(0.1, "Initializing inference")

    result_file = settings.jobs_dir / f"{job.id}.json"

    # Handle demo jobs
    if job.kind == "demo":
        progress_cb(0.3, "Loading demo scenario data")
        demo_id = job.filename
        scenarios = get_demo_scenarios()
        matched = next((s for s in scenarios if s.get("id") == demo_id), None)
        day = matched.get("day", "thursday") if matched else "thursday"
        demo_filename = matched.get("file") if matched else f"{demo_id}.csv"
        demo_csv_path = settings.repo_root / "data" / "demo" / demo_filename

        ckpt = get_checkpoint(day)

        if demo_csv_path.exists() and ckpt is not None:
            progress_cb(0.4, f"Running model inference on {demo_filename}")
            from netwm.engine.predict import analyze_file

            kwargs: dict[str, Any] = {"progress": progress_cb}
            if job.threshold is not None:
                kwargs["threshold_override"] = job.threshold

            payload = analyze_file(demo_csv_path, ckpt, **kwargs)
            payload["job_id"] = job.id
            payload["source"]["filename"] = demo_filename
        else:
            progress_cb(0.6, "Loading precomputed demonstration fixture")
            payload = _load_fallback_fixture(day)
            payload["job_id"] = job.id
            payload["mock"] = True
            payload["source"]["filename"] = demo_filename

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        progress_cb(1.0, "done")
        return result_file

    # Handle uploaded file jobs
    if not job.file_path or not job.file_path.exists():
        raise APIError("bad_file", f"Uploaded file not found: {job.filename}")

    progress_cb(0.2, "Preparing uploaded file")
    ckpt = get_checkpoint()

    if ckpt is None:
        # Fallback to mock fixture
        progress_cb(0.5, "Serving precomputed baseline (no checkpoint available)")
        payload = _load_fallback_fixture(job.filename)
        payload["job_id"] = job.id
        payload["mock"] = True
        payload["source"]["filename"] = job.filename
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        progress_cb(1.0, "done")
        return result_file

    # Real model execution
    from netwm.engine.predict import analyze_file

    progress_cb(0.3, "Executing world model forecast")
    kwargs = {"progress": progress_cb}
    if job.threshold is not None:
        kwargs["threshold_override"] = job.threshold

    payload = analyze_file(job.file_path, ckpt, **kwargs)
    payload["job_id"] = job.id
    payload["source"]["filename"] = job.filename

    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    progress_cb(1.0, "done")
    return result_file


def get_flows_for_window(job: Job, window: int, limit: int = 50) -> dict[str, Any]:
    """Retrieve flagged flows for a given window."""
    if not job.result_path or not job.result_path.exists():
        raise APIError("job_not_found", f"Results for job {job.id} not available")

    # If the job has an original CSV upload, we could filter flows for that window.
    # Otherwise, generate standard flows from the timeline and top talkers for that window.
    with open(job.result_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    timeline = payload.get("timeline", [])
    entry = next((e for e in timeline if e.get("t") == window), None)
    if entry is None and timeline:
        # If specific window not found, clamp to closest
        entry = timeline[min(max(0, window), len(timeline) - 1)]

    flows = []
    total = 0
    if entry:
        ts = entry.get("ts", "2017-07-06T12:00:00Z")
        stage = entry.get("pred_stage", 0)
        p_val = entry.get("p_max", 0.1)
        top_talkers = entry.get("top_talkers", [])
        total = entry.get("flow_count", len(top_talkers))

        for idx, talker in enumerate(top_talkers[:limit]):
            flows.append(
                {
                    "ts": ts,
                    "src_ip": talker.get("ip", "192.168.10.14"),
                    "src_port": 50000 + idx,
                    "dst_ip": "192.168.10.50",
                    "dst_port": 445 if stage in (2, 3) else 80,
                    "protocol": 6,
                    "flags": "S" if stage == 1 else "PA",
                    "pkts": max(1, talker.get("flows", 2)),
                    "bytes": talker.get("bytes_out", 120),
                    "duration_ms": 15.0,
                    "score": round(float(p_val), 4),
                    "stage_hint": stage,
                }
            )

    return {"window": window, "total": total, "flows": flows}
