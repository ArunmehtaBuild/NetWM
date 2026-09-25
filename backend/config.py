"""Configuration for the NetWM FastAPI backend.

Centralises paths, size limits, CORS allowlist, and defaults.
Values can be overridden via environment variables.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _repo_root() -> Path:
    # backend/ is one level down from the repository root
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    repo_root: Path = field(default_factory=_repo_root)

    # Server binding
    host: str = field(default_factory=lambda: os.getenv("NETWM_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("NETWM_PORT", "5000")))

    # CORS allowlist - never use '*' for a locally-bound service accepting uploads
    cors_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv(
                "NETWM_CORS_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080"
            ).split(",")
            if origin.strip()
        ]
    )

    # Upload size limits
    max_csv_bytes: int = 200 * 1024 * 1024  # 200 MB
    max_pcap_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GB

    # Paths
    @property
    def uploads_dir(self) -> Path:
        p = self.repo_root / "data" / "uploads"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def jobs_dir(self) -> Path:
        p = self.repo_root / "data" / "jobs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def fixtures_dir(self) -> Path:
        return self.repo_root / "fixtures" / "api"

    @property
    def models_dir(self) -> Path:
        return self.repo_root / "models"

    @property
    def demo_index_path(self) -> Path:
        return self.repo_root / "data" / "demo" / "index.json"

    # Job management limits
    max_active_jobs: int = 20
    job_retention_seconds: int = 2 * 3600  # 2 hours

    # Response limits
    max_timeline_entries: int = 5000


settings = Settings()
