"""Block until the API answers /api/health, so run_demo.bat never opens the dashboard onto a dead API.

    python backend/wait_ready.py [--url http://127.0.0.1:5000/api/health] [--timeout 45]

Exits 0 once the API is up, 1 on timeout. Importing torch and the model code makes a cold start take
several seconds; opening the browser before that would show the dashboard's mock fallback instead
of the live API, which is the symptom this exists to prevent.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request


def wait(url: str, timeout: float, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass  # not listening yet
        time.sleep(interval)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5000/api/health")
    ap.add_argument("--timeout", type=float, default=45.0)
    args = ap.parse_args()
    start = time.monotonic()
    if wait(args.url, args.timeout):
        print(f"API ready after {time.monotonic() - start:.1f} s")
        return
    print(f"API did not answer {args.url} within {args.timeout:.0f} s - check the backend window", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
