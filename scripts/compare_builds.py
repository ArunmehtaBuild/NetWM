"""D-044 amendment: two builds of the same processed dataset must be identical (a transient read error
during either build would show up as a difference).

    python scripts/compare_builds.py data/processed/cicids2018 data/processed/cicids2018_verify
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


def main() -> None:
    a, b = Path(sys.argv[1]), Path(sys.argv[2])
    ma, mb = (json.loads((d / "meta.json").read_text(encoding="utf-8")) for d in (a, b))
    ok = ma["feature_names"] == mb["feature_names"]
    fa, fb = ({m["split"]: m["flows"] for m in x["splits"]} for x in (ma, mb))
    ok &= fa == fb
    for split in fa:
        x, y = pd.read_parquet(a / f"{split}.parquet"), pd.read_parquet(b / f"{split}.parquet")
        same = x.shape == y.shape and x.equals(y)
        ok &= same
        print(f"{split}: {x.shape[0]} windows, flows {fa[split]:,} / {fb.get(split, 0):,} -> {'identical' if same else 'DIFFERENT'}")
    print(f"builds identical: {ok}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
