"""N-9 (D-040 follow-up): trace check 4's residual flow-feature differences to individual flows.

    python scripts/check4_flow_match.py --pcap data/cic-2017-pcap/tuesday_1300_1400.pcap --day tuesday

Check 4 compares window aggregates, which cannot say *why* a feature differs. This pairs every flow
``pcap_to_flows`` builds from a real slice with the corrected CSV's row for the same flow (same
5-tuple, same first-packet time), then reports:

- **Which flows exist on one side only** - by protocol and packet count - and whether the other side
  has the same 5-tuple reversed (a direction disagreement) or starting at another time (a split or
  merge disagreement).
- **For the flows both sides have, how often each column agrees**, and for the columns that do not,
  the typical disagreement.

Descriptive: nothing in the converter changes. Flows starting within ``--edge-s`` of the slice's ends
are left out, because the slice cuts them. Writes results/tables/check4_flow_match_{columns,unmatched}.csv,
check4_flow_match_pairs.csv.gz
and results/runs/check4-flow-match/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.cicids2017 import CICIDS2017Adapter
from netwm.features.flow_aggregator import pcap_to_flows
from netwm.utils import TABLES, ensure_dirs, save_run

KEY = ["src_ip", "dst_ip", "src_port", "dst_port", "protocol"]
#: timing columns are in microseconds; the two extractions may round a timestamp differently
TIME_COLS = {"duration_us", "flow_iat_mean", "flow_iat_std", "flow_iat_max", "flow_iat_min",
             "active_mean", "idle_mean", "fwd_iat_std", "bwd_iat_std"}
REVERSE = {"src_ip": "dst_ip", "dst_ip": "src_ip", "src_port": "dst_port", "dst_port": "src_port"}


def pair_flows(ours: pd.DataFrame, csv: pd.DataFrame, tol: pd.Timedelta) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Exact (5-tuple, ts) pairs first, then the same 5-tuple within ``tol``; returns pairs and both leftovers."""
    ours = ours.assign(_o=np.arange(len(ours)))
    csv = csv.assign(_c=np.arange(len(csv)))
    exact = ours.merge(csv, on=KEY + ["ts"], suffixes=("_pcap", "_csv"))
    exact = exact.drop_duplicates("_o").drop_duplicates("_c").assign(match="exact")
    o_left = ours[~ours["_o"].isin(exact["_o"])].sort_values("ts")
    c_left = csv[~csv["_c"].isin(exact["_c"])].sort_values("ts")
    near = pd.merge_asof(o_left, c_left, on="ts", by=KEY, tolerance=tol, direction="nearest",
                         suffixes=("_pcap", "_csv"))
    near = near[near["_c"].notna()].drop_duplicates("_c").assign(match="near")
    near["_c"] = near["_c"].astype(int)
    pairs = pd.concat([exact, near], ignore_index=True)
    return pairs, ours[~ours["_o"].isin(pairs["_o"])], csv[~csv["_c"].isin(pairs["_c"])]


def compare_columns(pairs: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    rows = []
    for col in cols:
        a, b = pairs[f"{col}_pcap"].to_numpy(float), pairs[f"{col}_csv"].to_numpy(float)
        ok = np.isfinite(a) & np.isfinite(b)
        a, b = a[ok], b[ok]
        tol = 2.0 if col in TIME_COLS else 1e-6
        equal = np.abs(a - b) <= np.maximum(tol, 1e-9 * np.abs(b))
        within1 = np.abs(a - b) <= np.maximum(tol, 0.01 * np.abs(b))
        nz = ~equal & (b != 0)
        rows.append({
            "column": col, "pairs": int(ok.sum()), "equal": round(float(equal.mean()), 4),
            "within_1pct": round(float(within1.mean()), 4),
            "pcap_zero_csv_nonzero": int((~equal & (a == 0) & (b != 0)).sum()),
            "pcap_nonzero_csv_zero": int((~equal & (a != 0) & (b == 0)).sum()),
            "median_ratio_when_different": round(float(np.median(a[nz] / b[nz])), 4) if nz.any() else None,
            "mean_pcap": round(float(a.mean()), 3), "mean_csv": round(float(b.mean()), 3),
        })
    return pd.DataFrame(rows).sort_values("equal").reset_index(drop=True)


def describe_unmatched(flows: pd.DataFrame, other: pd.DataFrame, side: str) -> pd.DataFrame:
    """One side's unmatched flows, and whether the other side has the tuple reversed or at another time."""
    tuples = set(map(tuple, other[KEY].to_numpy()))
    rev_tuples = set(map(tuple, other.rename(columns=REVERSE)[KEY].to_numpy()))
    keys = list(map(tuple, flows[KEY].to_numpy()))
    return flows.assign(
        side=side,
        other_has_tuple_reversed=[k in rev_tuples for k in keys],
        other_has_tuple_other_time=[k in tuples for k in keys],
        pkts=flows["fwd_pkts"] + flows["bwd_pkts"],
    )


def side_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"flows": 0}
    return {"flows": int(len(df)),
            "by_protocol": {int(k): int(v) for k, v in df["protocol"].value_counts().items()},
            "pkts_distribution": {str(k): int(v) for k, v in df["pkts"].clip(upper=10).value_counts().sort_index().items()},
            "other_side_has_tuple_reversed": int(df["other_has_tuple_reversed"].sum()),
            "other_side_has_tuple_at_other_time": int(df["other_has_tuple_other_time"].sum()),
            "top_dst_ports": {int(k): int(v) for k, v in df["dst_port"].value_counts().head(8).items()},
            "top_src_ips": {str(k): int(v) for k, v in df["src_ip"].value_counts().head(8).items()}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcap", required=True)
    ap.add_argument("--day", required=True)
    ap.add_argument("--raw", default="data/raw/cicids2017_improved")
    ap.add_argument("--edge-s", type=float, default=150.0, help="leave out flows starting this close to the slice's ends")
    ap.add_argument("--tolerance-ms", type=float, default=5.0, help="second-pass start-time tolerance for pairing")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    np.random.seed(args.seed)
    ensure_dirs()

    ours = pcap_to_flows(args.pcap)
    lo = ours["ts"].min() + pd.Timedelta(seconds=args.edge_s)
    hi = ours["ts"].max() - pd.Timedelta(seconds=args.edge_s)
    ours = ours[(ours["ts"] >= lo) & (ours["ts"] < hi)].reset_index(drop=True)
    csv = CICIDS2017Adapter(Path(args.raw)).load(args.day)
    csv = csv[(csv["ts"] >= lo) & (csv["ts"] < hi)].reset_index(drop=True)
    csv_tcpudp = csv[csv["protocol"].isin([6, 17])].reset_index(drop=True)

    pairs, o_only, c_only = pair_flows(ours, csv_tcpudp, pd.Timedelta(milliseconds=args.tolerance_ms))
    shared = [c for c in ours.columns if c not in KEY + ["ts"] and f"{c}_csv" in pairs.columns
              and pd.api.types.is_numeric_dtype(ours[c])]
    columns = compare_columns(pairs, shared)
    columns.to_csv(TABLES / "check4_flow_match_columns.csv", index=False)
    # every paired flow with both sides' values: what the per-column rules are read from
    pair_cols = ["match", "ts", *KEY] + [f"{c}_{s}" for c in shared for s in ("pcap", "csv")]
    pairs[pair_cols].to_csv(TABLES / "check4_flow_match_pairs.csv.gz", index=False)  # ~20 MB as plain CSV

    unmatched = pd.concat([describe_unmatched(o_only, csv_tcpudp, "pcap_only"),
                           describe_unmatched(c_only, ours, "csv_only")], ignore_index=True)
    keep = ["side", "ts", *KEY, "fwd_pkts", "bwd_pkts", "syn_cnt", "fin_cnt", "rst_cnt", "duration_us",
            "other_has_tuple_reversed", "other_has_tuple_other_time"]
    unmatched[keep].to_csv(TABLES / "check4_flow_match_unmatched.csv", index=False)

    summary = {
        "pcap": args.pcap, "day": args.day, "range": [str(lo), str(hi)],
        "flows_pcap": int(len(ours)), "flows_csv_all_protocols": int(len(csv)),
        "flows_csv_tcp_udp": int(len(csv_tcpudp)),
        "csv_other_protocols": {int(k): int(v) for k, v in csv.loc[~csv["protocol"].isin([6, 17]), "protocol"].value_counts().items()},
        "paired_exact": int((pairs["match"] == "exact").sum()), "paired_near": int((pairs["match"] == "near").sum()),
        "pcap_only": side_summary(unmatched[unmatched["side"] == "pcap_only"]),
        "csv_only": side_summary(unmatched[unmatched["side"] == "csv_only"]),
        "columns_equal_on_pairs": dict(zip(columns["column"], columns["equal"])),
    }
    save_run("check4-flow-match", summary, config={**vars(args), "decision": "D-040", "command": " ".join(sys.argv)})
    pd.set_option("display.width", 220)
    print(columns.to_string())
    for k, v in summary.items():
        if k != "columns_equal_on_pairs":
            print(k, v)


if __name__ == "__main__":
    main()
