"""D-042: the CTU-13 window matrix plus E21's six host-relative features, computed over whole captures.

    python scripts/build_ctu13_hostrel.py --config configs/ctu13_hostrel.yaml

The host-relative block compares each internal host with its own past, so unlike every other S_t
column it cannot be computed in the time chunks ``build_ctu13.py`` uses. This reads each scenario's
raw flows once, puts them on the existing matrix's window grid, computes the block with the E21
definition unchanged (``flow_features.host_relative_block``) and appends it to a copy of the existing
frame. Checks, per scenario (the build stops if one fails): the same window anchor and count as the
base matrix, and the same per-window flow count, so the new columns sit on the same windows.

Writes ``data/processed/ctu13_hostrel/<split>.parquet`` and ``meta.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.ctu13 import CTU13Adapter
from netwm.data.processed import ProcessedDataset
from netwm.features.flow_features import HOST_RELATIVE_FEATURES, host_relative_block
from netwm.features.windowing import WindowSpec, expand_to_windows
from netwm.utils import git_sha, set_seed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/ctu13_hostrel.yaml")
    ap.add_argument("--seed", type=int, default=42, help="nothing here samples; kept for the repo contract")
    ap.add_argument("--splits", nargs="*", default=None, help="default: every split of the base matrix")
    args = ap.parse_args()
    set_seed(args.seed)
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    spec = WindowSpec(cfg["window"]["length_s"], cfg["window"]["stride_s"])
    internal = tuple(cfg["internal_prefixes"])
    base = ProcessedDataset(cfg["base_dir"])
    out_dir = Path(cfg["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter = CTU13Adapter(cfg["raw_dir"])
    assert not set(HOST_RELATIVE_FEATURES) & set(base.feature_names), "base matrix already has the block"

    splits_meta = []
    for split in args.splits or base.splits:
        t_start = time.time()
        frame = base.frame(split)
        meta = next(m for m in base.meta["splits"] if m["split"] == split)
        raw = adapter.load(split)
        src, dst = raw["src_ip"].astype(str), raw["dst_ip"].astype(str)
        flows = pd.DataFrame({
            "ts": raw["ts"],
            "src_ip": src.astype("category").cat.codes.astype(np.int32),
            "dst_ip": dst.astype("category").cat.codes.astype(np.int32),
            "dst_port": raw["dst_port"].to_numpy(),
            "src_internal": src.str.startswith(internal).to_numpy(),
            "dst_internal": dst.str.startswith(internal).to_numpy(),
        })
        del raw, src, dst
        t0 = flows["ts"].min().floor("min")
        n = spec.n_windows((flows["ts"].max() - t0).total_seconds())
        if n != len(frame) or str(t0) != str(pd.Timestamp(meta["t0"])):
            raise SystemExit(f"{split}: grid {t0} x {n} != base {meta['t0']} x {len(frame)} - stop")
        exp, _ = expand_to_windows(flows, spec, t0)
        counts = np.bincount(exp["w"].to_numpy(), minlength=n)[:n]
        if not np.array_equal(counts, frame["n_flows"].to_numpy().astype(np.int64)):
            raise SystemExit(f"{split}: per-window flow counts differ from the base matrix - stop")
        block = host_relative_block(exp, n, internal).astype(np.float32)
        del exp, flows
        out = frame.copy()
        for c in HOST_RELATIVE_FEATURES:
            out[c] = block[c].to_numpy()
        out.to_parquet(out_dir / f"{split}.parquet", index=False)
        splits_meta.append({**meta, "hostrel_build_s": round(time.time() - t_start, 1)})
        print(f"{split}: {n} windows, block built in {time.time() - t_start:.0f}s; "
              f"max per column: " + ", ".join(f"{c}={block[c].max():.1f}" for c in HOST_RELATIVE_FEATURES), flush=True)

    new_meta = {**base.meta, "feature_names": [*base.feature_names, *HOST_RELATIVE_FEATURES],
                "n_features": len(base.feature_names) + len(HOST_RELATIVE_FEATURES),
                "config": {**base.meta["config"], "use_host_relative": True},
                "base_dir": cfg["base_dir"], "base_git_sha": base.meta.get("git_sha"), "git_sha": git_sha(),
                "splits": splits_meta}
    (out_dir / "meta.json").write_text(json.dumps(new_meta, indent=2, default=str), encoding="utf-8")
    print(f"wrote {out_dir}/ ({len(splits_meta)} splits)")


if __name__ == "__main__":
    main()
