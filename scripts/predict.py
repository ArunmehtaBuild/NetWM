"""Run the world model over a flow CSV (or PCAP) and write the API-shaped analysis JSON.

    python scripts/predict.py --model models/e4e7-worldmodel/thursday.pt \
        --input data/raw/cicids2017_improved/thursday.csv --out fixtures/api/thursday.json

Used three ways: as the CLI deliverable, as the backend's inference call (``analyze_file``), and to
generate the mock payloads the frontend develops against before a model exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.engine.predict import analyze_file, load_checkpoint
from netwm.utils import set_seed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True, help="checkpoint from scripts/train.py")
    ap.add_argument("--input", required=True, help=".csv flow records (or .pcap once supported)")
    ap.add_argument("--out", default=None, help="write JSON here (default: print a summary)")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--max-windows", type=int, default=None, help="truncate the timeline (mocks)")
    ap.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="override the alarm threshold (fixtures only - marks the payload dev_only)",
    )
    ap.add_argument("--note", default=None, help="why this payload was produced with an override")
    ap.add_argument(
        "--sampled-score",
        action="store_true",
        help="score alarms from sampled rollouts instead of the deterministic mean path",
    )
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    set_seed(args.seed)
    ckpt = load_checkpoint(args.model)
    if args.threshold is not None and not args.note:
        ap.error("--threshold requires --note: a fixture with a hand-picked threshold must say why")
    payload = analyze_file(
        args.input, ckpt, n_samples=args.samples,
        threshold_override=args.threshold, override_note=args.note,
        mean_path_score=not args.sampled_score,
        progress=lambda p, msg: print(f"  [{p:5.0%}] {msg}"),
    )
    if args.max_windows:
        payload["timeline"] = payload["timeline"][: args.max_windows]

    alarms = payload["alarms"]
    early = [a for a in alarms if a.get("lead_windows")]
    summary = payload.get("lead_time_summary")
    if summary:
        print("")
        print(f"  lead time: {summary['warned_early']} of {summary['episodes']} episodes warned "
              f"early (mean {summary['mean_lead_seconds']:.0f} s)")
    print(
        f"\n{payload['source']['filename']}: {payload['source']['flows']:,} flows, "
        f"{payload['source']['windows']:,} windows, {len(alarms)} alarm runs, "
        f"{len(early)} with a known onset ahead of them"
    )
    for a in early[:5]:
        print(f"  alarm at t={a['t']} ({a['ts']}) -> onset t={a['onset_t']}, "
              f"lead {a['lead_windows']} windows ({a['lead_seconds']:.0f} s)")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
