"""Download and extract the corrected CIC-IDS2017 flow dataset (D-001).

    python scripts/get_data.py            # download + extract, skips work already done
    python scripts/get_data.py --check    # verify what is on disk, download nothing
    python scripts/get_data.py --force    # re-download even if the archive is present

Why this release and not the CIC original: the original CSVs mis-terminate TCP flows and mislabel
attack onsets, and onset time is the quantity we predict. See decisions.md D-001 and
research/cicids2017.md.

The archive is ~328 MB and expands to ~1.1 GB of per-day CSVs in data/raw/cicids2017_improved/
(gitignored). Nothing else in the repo needs network access.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ARCHIVE = RAW / "CICIDS2017_improved.zip"
EXTRACT_DIR = RAW / "cicids2017_improved"

URL = "https://intrusion-detection.distrinet-research.be/CNS2022/Datasets/CICIDS2017_improved.zip"
SHA256 = "97fdb91d339e2d8cf5627f981b831e5e7e400b981c58181c451a38fd03c48883"
SIZE_BYTES = 343_549_013
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def extracted_ok() -> bool:
    return all((EXTRACT_DIR / f"{d}.csv").exists() for d in DAYS)


def report() -> None:
    print(f"archive : {ARCHIVE}  {'present' if ARCHIVE.exists() else 'MISSING'}")
    if ARCHIVE.exists():
        print(f"          {ARCHIVE.stat().st_size / 1e6:.1f} MB")
    for day in DAYS:
        csv = EXTRACT_DIR / f"{day}.csv"
        state = f"{csv.stat().st_size / 1e6:>7.1f} MB" if csv.exists() else "  MISSING"
        print(f"  {day:<10}{state}")


def download(force: bool = False) -> None:
    import requests  # imported here so --check works without the dependency

    if ARCHIVE.exists() and not force:
        print(f"archive already present ({ARCHIVE.stat().st_size / 1e6:.1f} MB), skipping download")
        return

    RAW.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVE.with_suffix(".zip.part")
    print(f"downloading {URL}\n  -> {ARCHIVE}  (~{SIZE_BYTES / 1e6:.0f} MB, a few minutes)")

    with requests.get(URL, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", SIZE_BYTES))
        done = 0
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                done += len(chunk)
                pct = 100 * done / total if total else 0
                print(f"\r  {done / 1e6:7.1f} / {total / 1e6:.0f} MB  {pct:5.1f}%", end="", flush=True)
    print()
    tmp.replace(ARCHIVE)


def verify() -> bool:
    """Checksum the archive. A mismatch means a truncated download or a changed upstream file."""
    print("verifying sha256 (takes a few seconds)...")
    actual = sha256_of(ARCHIVE)
    if actual == SHA256:
        print(f"  ok  {actual}")
        return True
    print(f"  MISMATCH\n    expected {SHA256}\n    actual   {actual}", file=sys.stderr)
    print(
        "  Delete data/raw/CICIDS2017_improved.zip and re-run. If it still mismatches, upstream\n"
        "  changed the file - tell the team before using it, every published number assumes this one.",
        file=sys.stderr,
    )
    return False


def extract() -> None:
    if extracted_ok():
        print(f"already extracted in {EXTRACT_DIR}")
        return
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"extracting -> {EXTRACT_DIR} (~1.1 GB)")
    with zipfile.ZipFile(ARCHIVE) as zf:
        for info in zf.infolist():
            print(f"  {info.filename:<16}{info.file_size / 1e6:>8.1f} MB")
            zf.extract(info, EXTRACT_DIR)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report what is on disk, download nothing")
    ap.add_argument("--force", action="store_true", help="re-download even if the archive exists")
    ap.add_argument("--skip-verify", action="store_true", help="skip the checksum (not recommended)")
    args = ap.parse_args()

    if args.check:
        report()
        return 0 if extracted_ok() else 1

    download(force=args.force)
    if not args.skip_verify and not verify():
        return 1
    extract()

    if not extracted_ok():
        print("extraction incomplete - see above", file=sys.stderr)
        return 1
    print("\nready. next:\n  python scripts/build_features.py --config configs/cicids2017.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
