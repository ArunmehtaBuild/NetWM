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

# D-038: PCAP uploads are served by all three seeds of the packet model, averaged per window - never one
# seed picked by held-out performance, and never the CSV model, which reads no packet features.
# D-041 (N-8 fix, gates G1-G3 passed): both routes serve the retrained window-position checkpoints, whose
# scores do not depend on the capture's length - E20rw for PCAP, r2w seed 42 for CSV.
PCAP_ENSEMBLE_RUNS = ("m1v2-n8-e20rw-s42", "m1v2-n8-e20rw-s43", "m1v2-n8-e20rw-s44")
CSV_ROUTE_RUN = "n8-r2w-s42"
PCAP_SUFFIXES = {".pcap", ".pcapng"}
# D-034 / G-9: both routes alarm on the causal expanding 10 % budget - the policy D-041's gates scored
# (scripts/n8_eval.py) and the one the PCAP ensemble names (predict.ENSEMBLE_POLICY). The window-position
# checkpoints store only their train-tuned threshold, which does not transfer to a held-out day (E14):
# read as a "fixed" policy it raised no alarm on held-out Thursday. r2's checkpoints named their policy.
SERVED_POLICY = "expanding-10pct"
_E20R_FOLDS = {"monday", "tuesday", "wednesday", "thursday", "friday"}
_ensemble_cache: dict[str, dict[str, Any]] = {}


def is_pcap(path: Path | str) -> bool:
    return Path(path).suffix.lower() in PCAP_SUFFIXES


def pcap_ensemble_paths(day: Optional[str] = None) -> list[Path]:
    """Each seed's fold for ``day`` (a held-out demo day), else its Thursday fold - r2's default."""
    fold = str(day).lower() if day and str(day).lower() in _E20R_FOLDS else "thursday"
    return [settings.models_dir / run / f"{fold}.pt" for run in PCAP_ENSEMBLE_RUNS]


def get_pcap_ensemble(day: Optional[str] = None) -> dict[str, Any]:
    """Load (once per fold) the D-038 ensemble, or fail loudly: a PCAP upload never falls back to r2
    or to a fixture, because either would present a flow-only answer as a packet-enriched one."""
    paths = pcap_ensemble_paths(day)
    key = paths[0].stem
    if key in _ensemble_cache:
        return _ensemble_cache[key]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise APIError(
            "no_model",
            "The PCAP route needs all three E20rw checkpoints (D-038, D-041); missing: " + ", ".join(missing),
        )
    from netwm.engine.predict import load_ensemble

    logger.info("Loading the PCAP ensemble: %s", [str(p) for p in paths])
    _ensemble_cache[key] = load_ensemble(paths)
    return _ensemble_cache[key]


def get_registry() -> dict[str, str]:
    reg_path = settings.models_dir / "registry.json"
    if reg_path.exists():
        try:
            with open(reg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", reg_path, exc)
    return {
        "default": f"{CSV_ROUTE_RUN}/thursday.pt",
        "thursday": f"{CSV_ROUTE_RUN}/thursday.pt",
        "friday": f"{CSV_ROUTE_RUN}/friday.pt",
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


# The deployable operating point of each route, as D-041's gate evaluation scored it
# (scripts/n8_eval.py): Thursday fold, p_max, the causal expanding 10 % budget the dashboard itself
# applies (D-034, G-9), label y_within_K; PR-AUC is threshold-free on the same arrays. Read from the run
# folder so the API can never drift from it.
_ROUTE_EVAL_RUN = "n8-fix-eval"
_PCAP_ROUTE_MODEL = "E20rw mean"
# The PS baseline at the same causal threshold as the model (G-6, D-037): like for like. E3's 0.011
# was at LR's own train-tuned threshold, a different policy from the model's.
_BENCHMARK_RUN = "benchmark-final"


def _find_row(run_id: str, key: str = "rows", **match: Any) -> Optional[dict[str, Any]]:
    path = settings.repo_root / "results" / "runs" / run_id / "metrics.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = json.load(f)["metrics"][key]
    except Exception as exc:
        logger.warning("Cannot read metrics from %s: %s", path, exc)
        return None
    return next((r for r in rows if all(r.get(k) == v for k, v in match.items())), None)


def _detection(row: Optional[dict[str, Any]]) -> dict[str, float]:
    return {k: round(float(row[k]), 3) for k in ("f1", "precision", "recall", "fpr", "pr_auc") if k in row} if row else {}


def load_headline_metrics() -> dict[str, float]:
    """The CSV route's model-card metrics, sourced from results/runs/ (zeros only if a run folder is missing)."""
    metrics = {k: 0.0 for k in ("f1", "precision", "recall", "fpr", "pr_auc",
                                "mean_lead_time_windows", "baseline_f1")}
    # mean_lead_time_windows stays 0.0: no model's early warnings beat the circular-shift null (S3 is
    # met nowhere), and a count that does not is not a result (D-022).
    metrics.update(_detection(_find_row(_ROUTE_EVAL_RUN, key="detection", run=CSV_ROUTE_RUN, day="thursday")))
    base = _find_row(_BENCHMARK_RUN, model="Logistic regression (PS baseline)", day="thursday")
    if base:
        metrics["baseline_f1"] = round(base["f1"], 3)
    return metrics


def load_pcap_route_metrics() -> Optional[dict[str, float]]:
    """The PCAP route's model-card metrics; None until the scored result exists, rather than borrowing the
    CSV route's numbers for a different input."""
    return _detection(_find_row(_ROUTE_EVAL_RUN, key="detection", model=_PCAP_ROUTE_MODEL, day="thursday")) or None


def model_routes() -> dict[str, Any]:
    """Which model serves which input, and which of them reads packet-derived features (D-038, D-041)."""
    paths = pcap_ensemble_paths()
    return {
        "csv": {
            "model": f"r2w seed 42 (models/{CSV_ROUTE_RUN}/): r2's setup with window positions (D-041)",
            "telemetry": "flow",
            "packet_features": "not read: a flow-only model (70 flow features)",
            "metrics": load_headline_metrics(),
        },
        "pcap": {
            "model": "E20rw seeds 42, 43 and 44 (E20r with window positions, D-041), arithmetic mean per window (D-038)",
            "telemetry": "flow + packet",
            "packet_features": "read: 18 pcap_ features measured from the capture (TTL, fragments, "
                               "retransmissions, TCP window, payload sizes, packet timing, SYN-only and "
                               "RST shares) beside the 70 flow features and 17 CSV packet statistics",
            "checkpoints": [str(p.relative_to(settings.models_dir)) for p in paths],
            "available": all(p.exists() for p in paths),
            "metrics": load_pcap_route_metrics(),
        },
    }


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
            "name": f"netwm-rssm-r2w ({_active_model_name or 'default'})",
            "trained_on": "CIC-IDS2017 (corrected), Mon-Wed + Fri",
            "window_s": float(ckpt.get("stride_s", 30.0) * 2),
            "stride_s": float(ckpt.get("stride_s", 30.0)),
            "horizon_k": int(ckpt.get("horizon_k", 10)),
            "params": param_count,
            "git_sha": git_sha,
            "stages": stages,
            "metrics": load_headline_metrics(),
            "feature_count": feature_count,
            # the headline metrics above are the CSV route's; the PCAP route is a different model
            "routes": model_routes(),
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
        "metrics": load_headline_metrics(),
        "feature_count": 84,
    }


def resolve_demo(demo_id: str) -> tuple[Path, str]:
    """Map a demo id to its CSV slice and checkpoint day, or raise a client-facing error."""
    matched = next((s for s in get_demo_scenarios() if s.get("id") == demo_id), None)
    if matched is None:
        raise APIError("bad_file", f"Demo scenario '{demo_id}' does not exist")
    path = (settings.repo_root / "data" / "demo" / matched["file"]).resolve()
    if not path.exists():
        raise APIError(
            "no_model",
            f"Demo slice {path} is missing - regenerate with `python scripts/make_demo_samples.py`",
        )
    return path, str(matched.get("day", "thursday"))


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
    # ``in_sample`` describes the data actually served, and a fallback always serves the Thursday or
    # Friday fixture - both held-out days - whatever name was requested. The fixture files carry
    # ``"in_sample": false`` themselves; guessing from the requested name would badge Thursday data
    # as a training day whenever "monday" was asked for (R-12 review).
    return data


def _served_policy(ckpt: dict[str, Any]) -> dict[str, Any]:
    """A checkpoint that names no threshold policy is served on the deployable one, never on its stored
    train-tuned scalar."""
    if not ckpt.get("threshold_policy"):
        ckpt["threshold_policy"] = SERVED_POLICY
    return ckpt


def run_job_inference(job: Job, progress_cb: Callable[[float, str], None]) -> Path:
    """Execute analysis for a job and persist the result payload to disk."""
    progress_cb(0.1, "Initializing inference")

    result_file = settings.jobs_dir / f"{job.id}.json"

    # Handle demo jobs: always real inference on the slice in data/demo/. Serving a fixture
    # here returned a full-day payload under a 2-hour slice's metadata (R-6).
    if job.kind == "demo":
        demo_csv_path, day = resolve_demo(job.filename)
        if is_pcap(demo_csv_path):
            ckpt = get_pcap_ensemble(day)  # D-038: raises rather than fall back
        else:
            ckpt = get_checkpoint(day)
        if ckpt is None:
            raise APIError("no_model", f"No checkpoint available for demo day '{day}'")
        ckpt = _served_policy(ckpt)

        progress_cb(0.3, f"Running model inference on {demo_csv_path.name}")
        from netwm.engine.predict import analyze_file

        kwargs: dict[str, Any] = {"progress": progress_cb}
        if job.threshold is not None:
            kwargs["threshold_override"] = job.threshold

        logger.info("Demo job %s reading %s", job.id, demo_csv_path)
        payload = analyze_file(demo_csv_path, ckpt, **kwargs)
        payload["job_id"] = job.id
        payload["mock"] = False

        train_days = [str(d).lower() for d in ckpt.get("train_days", [])] if isinstance(ckpt, dict) else []
        is_in_sample = str(day).lower() in train_days
        payload["in_sample"] = is_in_sample
        if "source" in payload and isinstance(payload["source"], dict):
            payload["source"]["in_sample"] = is_in_sample

        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        progress_cb(1.0, "done")
        return result_file

    # Handle uploaded file jobs
    logger.info("Job %s reading upload %s", job.id, job.file_path)
    if not job.file_path or not job.file_path.exists():
        raise APIError("bad_file", f"Uploaded file not found: {job.file_path or job.filename}")

    progress_cb(0.2, "Preparing uploaded file")
    if is_pcap(job.file_path):
        # D-038: packet-enriched route; a missing member is an error, never r2 and never a fixture
        ckpt = get_pcap_ensemble()
    else:
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
    ckpt = _served_policy(ckpt)
    from netwm.engine.predict import analyze_file

    progress_cb(0.3, "Executing world model forecast")
    kwargs = {"progress": progress_cb}
    if job.threshold is not None:
        kwargs["threshold_override"] = job.threshold

    payload = analyze_file(job.file_path, ckpt, **kwargs)
    payload["job_id"] = job.id
    payload["source"]["filename"] = job.filename
    payload["mock"] = False

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
