"""Evidence freezes: content hashes for everything a conclusion rests on.

A git tag pins every tracked file, but not the weights (``models/`` is untracked), the processed
matrices or the raw data. A freeze therefore records their SHA-256 beside the tag, and checks that every
artefact results.md quotes actually exists - a number quoted from a missing file is not reproducible.
"""

from __future__ import annotations

import hashlib
import itertools
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

#: results.md quotes artefacts as paths under results/; ``{a,b}`` lists alternatives.
_REF = re.compile(r"results/(?:tables|runs|figures)/(?:\{[^{}\s]*\}|[^\s`'\"()|,;{}])+")


def sha256_file(path: Path | str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def brace_expand(s: str) -> list[str]:
    """``a{1,2}b{x,y}`` -> the four combinations (no nesting, which results.md never uses)."""
    parts = re.split(r"(\{[^{}]*\})", s)
    options = [p[1:-1].split(",") if p.startswith("{") and p.endswith("}") else [p] for p in parts]
    return ["".join(c) for c in itertools.product(*options)]


_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")


def range_expand(s: str) -> list[str]:
    """results.md's shorthand ``scorecard_e19..e23.csv`` and ``e1_monday..friday_timeline.png``."""
    m = re.search(r"([a-z]*)(\d+)\.\.\1(\d+)", s)
    if m:
        return [s[:m.start()] + f"{m.group(1)}{i}" + s[m.end():] for i in range(int(m.group(2)), int(m.group(3)) + 1)]
    m = re.search(r"(" + "|".join(_DAYS) + r")\.\.(" + "|".join(_DAYS) + r")", s)
    if m:
        a, b = _DAYS.index(m.group(1)), _DAYS.index(m.group(2))
        return [s[:m.start()] + d + s[m.end():] for d in _DAYS[a:b + 1]]
    return [s]


def quoted_paths(markdown: str) -> list[str]:
    """Every concrete results/ path a markdown document quotes, braces and ``a..b`` ranges expanded,
    trailing punctuation dropped. Placeholders (``<run>``) and wildcards (``*``) are returned as-is for
    the caller to skip."""
    out: list[str] = []
    for m in _REF.findall(markdown):
        m = re.sub(r"[.:]+$", "", m)
        for b in brace_expand(m):
            for p in range_expand(b):
                if p not in out:
                    out.append(p)
    return out


def check_references(markdown: str, root: Path) -> list[dict]:
    rows = []
    for p in quoted_paths(markdown):
        if "<" in p or "*" in p:
            rows.append({"path": p, "status": "pattern (not checked)"})
            continue
        target = root / p
        if target.is_file():
            rows.append({"path": p, "status": "file", "sha256": sha256_file(target)})
        elif target.is_dir():
            files = sorted(q for q in target.rglob("*") if q.is_file())
            rows.append({"path": p, "status": "folder", "files": len(files),
                         "sha256": sha256_text("\n".join(f"{q.relative_to(root).as_posix()} {sha256_file(q)}" for q in files))})
        else:
            rows.append({"path": p, "status": "MISSING"})
    return rows


def checkpoint_record(path: Path) -> dict:
    """What identifies one checkpoint: bytes, SHA-256, and what it says about itself."""
    import torch

    rec = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    try:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        mc = ck.get("model_config", {})
        rec |= {"git_sha": ck.get("git_sha"), "pos_mode": mc.get("pos_mode", "interp"), "hazard": mc.get("hazard", "direct"),
                "n_features": len(ck.get("feature_names", [])),
                "feature_schema_sha256": sha256_text("\n".join(ck.get("feature_names", []))),
                "train_days": ck.get("train_days"), "test_days": ck.get("test_days") or [ck.get("test_day")],
                "stored_threshold": ck.get("threshold"),
                "params": int(sum(t.numel() for t in ck["model_state"].values()))}
    except Exception as exc:  # the hash stands on its own; say why the metadata is missing
        rec["load_error"] = repr(exc)
    return rec


def machine_info() -> dict:
    info = {"machine": platform.node(), "python": sys.version.split()[0],
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        import torch

        info["torch"] = torch.__version__
        info["device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:
        pass
    return info
