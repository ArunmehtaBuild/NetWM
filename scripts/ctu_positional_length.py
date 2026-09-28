"""N-8 x E25b: does the positional-length defect move the CTU-13 detection numbers? Descriptive, not a bar.

    python scripts/ctu_positional_length.py            # seed 42's fold checkpoints (all 7 on this machine)

``CausalContext`` interpolates its 16 learned positional vectors to the input length T
(research/positional-length.md), so a window's score depends on how long the capture is. CTU-13's
held-out scenarios run from 34 to 8,019 windows, training sequences are 96 windows (or a whole capture
when it is shorter), and two of E25b's deciding inversions are the two shortest captures (s11, 34;
s07, 44). This asks whether E25b's per-scenario ROC-AUC moves when only the capture's length changes.
It does **not** re-read E25b's verdicts: D-037 fixed the rule and the stored scores.

Everything below was fixed before any output was looked at.

* **Models.** The world model's fold checkpoints ``models/e25-ctu13-s<seed>/<family>.pt`` for every
  seed given (default 42; seeds 43/44 are on the other machine), each scored on the scenarios of its
  own held-out family. Deterministic mean path (``forecast(sample=False)``), score ``p_max``, as in
  N-6a. The native condition is checked against E25b's stored ROC-AUC (Monte-Carlo ``comp``) and
  reported beside it; N-6a saw agreement within 0.011.
* **Scenarios.** All 13, on ``y_within_K``.
* **Conditions.**
  1. ``native`` - the whole capture in one pass, as E25b scored it (positional stretch T/16).
  2. ``prefix_of_96`` / ``prefix_of_8019`` - the same single pass, but the positional vectors are
     interpolated to length T' and the first T are used. Attention is causal and the latent state is
     recurrent, so this is exactly the score the capture's windows would get if T' - T further windows
     were appended: the capture as the start of a 96-window (training ``seq_len``) or an 8,019-window
     (the longest CTU-13 capture, s03) recording. Only where T <= T'. Nothing else changes, so this
     isolates the positional effect.
  3. ``slices_34`` / ``slices_96`` - the capture cut into consecutive slices of L windows (34, the
     shortest capture; 96, training ``seq_len``), each scored alone from a fresh latent state; the last
     slice is the capture's final L windows and contributes only windows not already scored. Every
     window is then scored at the same positional stretch whatever the capture's length, but the
     recurrent state also restarts every L windows, so this mixes the positional effect with lost
     history. Only where T > L (otherwise it equals ``native``).
* **Read-out.** Per scenario and condition: ROC-AUC, the change from ``native``, the Spearman
  correlation of the scores with ``native``, and whether the ROC-AUC sits on the other side of 0.50
  or 0.70 (D-037's thresholds) from ``native``. Descriptive; no verdict is recomputed.

Writes ``results/tables/n8_ctu13_positional_length.csv`` and ``results/runs/n8-ctu13-positional-length/``.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import yaml
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.processed import ProcessedDataset
from netwm.models.world_model import WorldModelConfig, build_model
from netwm.utils import RUNS, TABLES, ensure_dirs, git_sha, save_run, set_seed

PREFIX_OF = (96, 8019)
SLICES = (34, 96)
THRESHOLDS = (0.50, 0.70)


def _context_forward_at(self, embeds: torch.Tensor, pos_len: int | None):
    """CausalContext.forward with the positional vectors interpolated to ``pos_len`` instead of T."""
    b, t, _ = embeds.shape
    n = t if pos_len is None else pos_len
    assert n >= t
    pos = self.pos[:, :n] if n <= self.cfg.context_len else F.interpolate(
        self.pos.transpose(1, 2), size=n, mode="linear", align_corners=False).transpose(1, 2)
    x = self.norm1(embeds + pos[:, :t])
    idx = torch.arange(t, device=embeds.device)
    distance = idx[:, None] - idx[None, :]
    mask = (distance < 0) | (distance >= self.cfg.context_len)
    attended, weights = self.attn(x, x, x, attn_mask=mask, need_weights=True, average_attn_weights=True)
    h = embeds + attended
    return h + self.ff(self.norm2(h)), weights


@torch.no_grad()
def score(model, x: np.ndarray, horizon: int, device: torch.device, pos_len: int | None = None) -> np.ndarray:
    ctx = model.context
    ctx.forward = types.MethodType(lambda self, e: _context_forward_at(self, e, pos_len), ctx)
    try:
        t = torch.from_numpy(np.asarray(x, dtype=np.float32)).unsqueeze(0).to(device)
        return model.forecast(t, horizon=horizon, sample=False)["p_max"].cpu().numpy()
    finally:
        del ctx.forward


def sliced(model, x: np.ndarray, horizon: int, device: torch.device, length: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    starts = list(range(0, len(x) - length + 1, length))
    if starts[-1] + length < len(x):
        starts.append(len(x) - length)
    for s in starts:
        sc = score(model, x[s:s + length], horizon, device)
        new = np.isnan(out[s:s + length])
        out[s:s + length][new] = sc[new]
    assert not np.isnan(out).any()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data/processed/ctu13")
    ap.add_argument("--group-folds", default="configs/ctu13_folds.yaml")
    ap.add_argument("--seed", type=int, default=42, help="nothing here samples; kept for the repo contract")
    ap.add_argument("--seeds", type=int, nargs="+", default=[42], help="world-model seeds to score")
    args = ap.parse_args()
    set_seed(args.seed)
    ensure_dirs()
    start_sha = git_sha()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    ds = ProcessedDataset(args.data)
    folds = yaml.safe_load(Path(args.group_folds).read_text(encoding="utf-8"))
    rows, skipped = [], []
    for seed in args.seeds:
        run = f"e25-ctu13-s{seed}"
        stored = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]["per_day"]
        for fold, scens in folds.items():
            path = Path("models") / run / f"{fold}.pt"
            if not path.exists():
                skipped.append(str(path))
                continue
            ck = torch.load(path, map_location=device, weights_only=False)
            wm = build_model(WorldModelConfig(**ck["model_config"])).to(device)
            wm.load_state_dict(ck["model_state"])
            wm.eval()
            h = ck["horizon_k"]
            for scen in scens:
                frame = ds.frame(scen)
                y = frame["y_within_K"].to_numpy().astype(int)
                x = np.asarray(ck["scaler"].transform(frame[ck["feature_names"]]), dtype=np.float32)
                t = len(x)
                conds = {"native": score(wm, x, h, device)}
                for n in PREFIX_OF:
                    if t <= n:
                        conds[f"prefix_of_{n}"] = score(wm, x, h, device, pos_len=n)
                for n in SLICES:
                    if t > n:
                        conds[f"slices_{n}"] = sliced(wm, x, h, device, n)
                native = conds["native"]
                roc_native = roc_auc_score(y, native)
                roc_stored = roc_auc_score(y, np.asarray(stored[scen]["scores"], float))
                for cond, sc in conds.items():
                    roc = roc_auc_score(y, sc)
                    crosses = [thr for thr in THRESHOLDS if (roc >= thr) != (roc_native >= thr)]
                    rows.append({
                        "seed": seed, "family": fold, "scenario": scen, "windows": t,
                        "background": int((y == 0).sum()), "condition": cond,
                        "roc_auc": round(float(roc), 4), "delta_vs_native": round(float(roc - roc_native), 4),
                        "spearman_vs_native": round(float(spearmanr(sc, native).correlation), 4),
                        "max_abs_score_change": round(float(np.max(np.abs(sc - native))), 4),
                        "crosses_thresholds": " ".join(f"{c:.2f}" for c in crosses),
                        "roc_auc_stored_e25b": round(float(roc_stored), 4),
                    })
                    print(f"s{seed} {scen} T={t:5d} {cond:15s} roc={roc:.3f} (native {roc_native:.3f}, "
                          f"stored {roc_stored:.3f})  d={roc - roc_native:+.3f}  "
                          f"rho={rows[-1]['spearman_vs_native']:.3f}  crosses={rows[-1]['crosses_thresholds']}")

    table = pd.DataFrame(rows)
    table.to_csv(TABLES / "n8_ctu13_positional_length.csv", index=False)
    save_run("n8-ctu13-positional-length", {"rows": table.to_dict("records"), "skipped_checkpoints": skipped},
             config={**vars(args), "prefix_of": PREFIX_OF, "slices": SLICES, "thresholds": THRESHOLDS,
                     "device": str(device), "git_sha_at_start": start_sha})
    print("wrote results/tables/n8_ctu13_positional_length.csv and results/runs/n8-ctu13-positional-length/")


if __name__ == "__main__":
    main()
