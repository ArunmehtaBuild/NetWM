"""Copy the canonical API fixtures into the frontend so it can run standalone.

`fixtures/api/*.json` is the single source of truth - produced by `scripts/predict.py`, shared by the
backend's mock fallback and by the API contract tests. The frontend needs its own copy because it
deploys separately (static hosting, no backend), so run this after regenerating a fixture:

    python scripts/sync_fixtures.py

`frontend/mock/` is gitignored - it is a build artefact, never edited by hand.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "fixtures" / "api"
DST = ROOT / "frontend" / "mock"


def main() -> int:
    if not SRC.exists():
        print(f"no fixtures at {SRC}", file=sys.stderr)
        return 1
    DST.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC.glob("*.json")):
        shutil.copy2(src, DST / src.name)
        print(f"  {src.name}  {src.stat().st_size/1e6:.2f} MB")
    print(f"synced {len(list(SRC.glob('*.json')))} fixtures -> {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
