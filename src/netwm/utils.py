"""Small shared helpers: reproducibility, run folders, artefact paths (every run writes its seed, config and git SHA)."""

from __future__ import annotations

import json
import os
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS = REPO_ROOT / "results"
FIGURES = RESULTS / "figures"
TABLES = RESULTS / "tables"
RUNS = RESULTS / "runs"


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # pragma: no cover - git missing or not a repo
        return "unknown"


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:  # pragma: no cover
        pass
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    except ImportError:  # pragma: no cover
        pass


def run_dir(run_id: str) -> Path:
    """Folder for one experiment's metrics/config, created on demand."""
    path = RUNS / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_env() -> dict[str, Any]:
    """Interpreter, torch build and GPU. The seeds of one experiment can be trained on different
    machines (E25: seed 42 on a GTX 1650, seeds 43/44 on an RTX 4060); the run folder must say which."""
    import platform

    env: dict[str, Any] = {"python": platform.python_version()}
    try:
        import torch

        env["torch"] = torch.__version__
        env["cuda"] = torch.version.cuda
        env["device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:  # pragma: no cover - torch absent (backend-only install)
        pass
    return env


def save_run(run_id: str, metrics: dict[str, Any], config: dict[str, Any] | None = None) -> Path:
    """Write metrics + provenance so every number in results.md is traceable."""
    path = run_dir(run_id)
    payload = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "env": run_env(),
        "config": config or {},
        "metrics": metrics,
    }
    (path / "metrics.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def ensure_dirs() -> None:
    for d in (FIGURES, TABLES, RUNS):
        d.mkdir(parents=True, exist_ok=True)
