"""N-6(b) (D-039): does the bot host separate on per-host features where network-global ones fail? Descriptive.

    python scripts/ctu_perhost_diagnostic.py        # needs data/raw/ctu13/scenarioNN.binetflow

D-039 reopens a per-host state only if, "in the inverted scenarios (s08, s07, s11), the bot host's
windows separate from background hosts on per-host features but not on the network-global ones".
This measures that and nothing else; it trains nothing.

Everything below was fixed before any per-host number was looked at.

* **Scenarios.** The three D-039 names (Murlo s08, Sogou s07, Rbot s11) decide. Neris s02 and Virut
  s13 (the other deciding inversions) and NSIS s12 (transfers; the N-6a control) are reported beside
  them and decide nothing.
* **Windows and labels.** The flows are read with ``CTU13Adapter`` and put on the processed matrix's
  own grid (``expand_to_windows``, 60 s windows at a 30 s stride, anchored where ``build_ctu13.py``
  anchors it). The window count and the global flow count must match ``data/processed/ctu13`` exactly,
  or the script stops. Target: ``y_within_K`` from the processed matrix.
* **Five statistics**, each computed three ways per window. The direction is fixed in advance: a
  higher value is scored as more bot-like (a bot adds flows, ports, destinations, bytes and
  unanswered connection attempts), so no ROC-AUC is flipped after the fact.
  - ``flows`` (count), ``dst_ports`` and ``dst_ips`` (distinct), ``bytes`` (both directions),
    ``syn_unanswered`` (TCP flows with a SYN and no reply). A count, not a rate: a rate's maximum over
    hosts is 1.0 for any host with a single unanswered SYN.
  - **(i) global**: over every flow in the window, as a network-global state sees it.
  - **(ii) per-host max**: the maximum over internal source hosts (``147.32.``) of that host's own
    value. Label-free: a per-host state could compute it.
  - **(iii) oracle**: the bot host's own value (the source addresses of the scenario's ``From-Botnet``
    flows, taken together; 0 when silent). Uses the labels to pick the host: an upper bound, not a
    deployable score.
* **References for (i).** E25b's stored ROC-AUC of the world model (seeds 42/43/44) and LR on the 56
  global features, from ``results/tables/e25b_ctu13_scenarios.csv``.
* **Host-level view (iv)**, D-039's literal wording. Over all (window, internal source host) pairs with
  at least one flow, the ROC-AUC of "this host is the bot" on each statistic: does the bot host
  outrank the other internal hosts in the same traffic?
* **Rule for "meets D-039's reopen condition", fixed here.** On each of s08, s07 and s11, at least one
  statistic's per-host max (ii) reaches ROC-AUC >= 0.70 (D-037's transfer threshold) while that
  statistic's global value (i) and the world model on all three seeds stay below 0.70. Five statistics
  are tried per scenario, so a hit on one statistic is reported with that caveat. If the rule is met,
  the result says so and stops: a per-host-state run needs its own pre-registration.

Writes ``results/tables/n6b_ctu13_perhost.csv`` (one row per scenario, statistic and view),
``results/tables/n6b_ctu13_perhost_hostlevel.csv`` and ``results/runs/n6b-ctu13-perhost/``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from netwm.data.ctu13 import CTU13Adapter
from netwm.data.processed import ProcessedDataset
from netwm.features.windowing import WindowSpec, expand_to_windows
from netwm.utils import TABLES, ensure_dirs, git_sha, save_run, set_seed

DECIDING = ("s08", "s07", "s11")
REPORTED = ("s02", "s13", "s12")
STATS = ("flows", "dst_ports", "dst_ips", "bytes", "syn_unanswered")
BAR = 0.70


def _per_group(exp: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    g = exp.groupby(keys, observed=True, sort=False)
    return pd.DataFrame({"flows": g.size(), "dst_ports": g["dst_port"].nunique(), "dst_ips": g["dst"].nunique(),
                         "bytes": g["bytes"].sum(), "syn_unanswered": g["syn_unanswered"].sum()})


def window_stats(flows: pd.DataFrame, spec: WindowSpec, n: int, t0: pd.Timestamp, chunk: int = 400):
    """(global, per-host max, bot-host, host-level pairs) per window, in time chunks for memory."""
    offs = (flows["ts"] - t0).dt.total_seconds().to_numpy()
    glob = np.zeros((n, len(STATS)))
    hmax = np.zeros((n, len(STATS)))
    bot = np.zeros((n, len(STATS)))
    pairs = []
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        sel = (offs >= a * spec.stride_s) & (offs < (b - 1) * spec.stride_s + spec.length_s)
        exp, _ = expand_to_windows(flows.loc[sel], spec, t0)
        exp = exp[(exp["w"] >= a) & (exp["w"] < b)]
        g = _per_group(exp, ["w"])
        glob[g.index.to_numpy()] = g[list(STATS)].to_numpy()
        internal = exp[exp["internal_src"]]
        h = _per_group(internal, ["w", "src"])
        hm = h.groupby(level="w").max()
        hmax[hm.index.to_numpy()] = hm[list(STATS)].to_numpy()
        bb = _per_group(exp[exp["bot_src"]], ["w"])
        bot[bb.index.to_numpy()] = bb[list(STATS)].to_numpy()
        hl = h.reset_index()
        hl["is_bot"] = hl["src"].isin(flows.attrs["bot_codes"])
        pairs.append(hl)
    return glob, hmax, bot, pd.concat(pairs, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="configs/ctu13.yaml")
    ap.add_argument("--data", default="data/processed/ctu13")
    ap.add_argument("--seed", type=int, default=42, help="nothing here samples; kept for the repo contract")
    args = ap.parse_args()
    set_seed(args.seed)
    ensure_dirs()
    start_sha = git_sha()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    spec = WindowSpec(cfg["window"]["length_s"], cfg["window"]["stride_s"])
    internal = tuple(cfg["internal_prefixes"])
    ds = ProcessedDataset(args.data)
    adapter = CTU13Adapter(cfg["raw_dir"])
    e25b = pd.read_csv(TABLES / "e25b_ctu13_scenarios.csv")

    rows, host_rows, checks = [], [], {}
    for scen in (*DECIDING, *REPORTED):
        frame = ds.frame(scen)
        y = frame["y_within_K"].to_numpy().astype(int)
        raw = adapter.load(scen)
        src = raw["src_ip"].astype(str)
        bot_ips = sorted(src[raw["label"].astype(str).str.contains("From-Botnet")].unique())
        flows = pd.DataFrame({
            "ts": raw["ts"],
            "src": src.astype("category"),
            "dst": raw["dst_ip"].astype(str).astype("category").cat.codes,
            "dst_port": raw["dst_port"].to_numpy(),
            "bytes": (raw["fwd_bytes"] + raw["bwd_bytes"]).to_numpy(),
            "syn_unanswered": ((raw["protocol"] == 6) & (raw["syn_cnt"] > 0) & (raw["bwd_pkts"] == 0)).to_numpy(),
            "internal_src": src.str.startswith(internal).to_numpy(),
            "bot_src": src.isin(bot_ips).to_numpy(),
        })
        del raw, src
        cats = flows["src"].cat.categories
        flows["src"] = flows["src"].cat.codes
        flows.attrs["bot_codes"] = [int(np.flatnonzero(cats == ip)[0]) for ip in bot_ips]

        t0 = flows["ts"].min().floor("min")
        n = spec.n_windows((flows["ts"].max() - t0).total_seconds())
        if n != len(frame):
            raise SystemExit(f"{scen}: {n} windows from the raw flows, {len(frame)} in the processed matrix - stop")
        glob, hmax, bot, pairs = window_stats(flows, spec, n, t0)
        if not np.allclose(glob[:, 0], frame["n_flows"].to_numpy()):
            raise SystemExit(f"{scen}: global flow counts differ from the processed matrix - stop")
        checks[scen] = {"windows": n, "flows": len(flows), "bot_hosts": bot_ips,
                        "internal_hosts": int(flows.loc[flows["internal_src"], "src"].nunique())}
        del flows

        ref = e25b[e25b["scenario"] == scen]
        wm = ref[ref["model"] == "world model"]["roc_auc"].to_numpy()
        lr = float(ref[ref["model"] == "logistic regression"]["roc_auc"].iloc[0])
        for j, stat in enumerate(STATS):
            rec = {"scenario": scen, "family": next(m for m in ds.meta["splits"] if m["split"] == scen)["family"],
                   "decides": scen in DECIDING, "windows": n, "background": int((y == 0).sum()),
                   "statistic": stat}
            for view, arr in (("global", glob), ("perhost_max", hmax), ("oracle_bot", bot)):
                rec[f"roc_{view}"] = round(float(roc_auc_score(y, arr[:, j])), 4)
            hl = pairs[stat].to_numpy()
            rec["roc_hostlevel_bot_vs_other_hosts"] = (round(float(roc_auc_score(pairs["is_bot"], hl)), 4)
                                                       if 0 < pairs["is_bot"].sum() < len(pairs) else None)
            rec["wm_roc_e25b_s42_s43_s44"] = " / ".join(f"{v:.3f}" for v in wm)
            rec["lr_roc_e25b"] = round(lr, 4)
            rec["meets_rule"] = bool(rec["roc_perhost_max"] >= BAR and rec["roc_global"] < BAR and (wm < BAR).all())
            rows.append(rec)
            print(f"{scen} {stat:15s} global={rec['roc_global']:.3f} perhost_max={rec['roc_perhost_max']:.3f} "
                  f"oracle={rec['roc_oracle_bot']:.3f} hostlevel={rec['roc_hostlevel_bot_vs_other_hosts']} "
                  f"WM={rec['wm_roc_e25b_s42_s43_s44']} LR={lr:.3f} meets={rec['meets_rule']}")
        share = pairs.groupby("w").apply(lambda d: bool(d.loc[d["flows"].idxmax(), "is_bot"]) if len(d) else False)
        busiest = np.zeros(n, bool)
        busiest[share.index.to_numpy()] = share.to_numpy()
        host_rows.append({"scenario": scen, "host_windows": len(pairs), "bot_host_windows": int(pairs["is_bot"].sum()),
                          "bot_is_busiest_internal_host_pos": round(float(busiest[y == 1].mean()), 4),
                          "bot_is_busiest_internal_host_neg": round(float(busiest[y == 0].mean()), 4)
                          if (y == 0).any() else None})
        print(f"{scen} bot hosts {bot_ips}; bot is busiest internal host in {host_rows[-1]['bot_is_busiest_internal_host_pos']:.2f} "
              f"of positive windows, {host_rows[-1]['bot_is_busiest_internal_host_neg']} of background")

    table = pd.DataFrame(rows)
    per_scen = table[table["decides"]].groupby("scenario")["meets_rule"].any()
    met = bool(per_scen.reindex(list(DECIDING)).fillna(False).all())
    table.to_csv(TABLES / "n6b_ctu13_perhost.csv", index=False)
    pd.DataFrame(host_rows).to_csv(TABLES / "n6b_ctu13_perhost_hostlevel.csv", index=False)
    save_run("n6b-ctu13-perhost", {"rows": rows, "host_level": host_rows, "checks": checks,
                                   "meets_rule_per_deciding_scenario": per_scen.to_dict(), "reopen_condition_met": met},
             config={**vars(args), "deciding": DECIDING, "reported": REPORTED, "stats": STATS, "bar": BAR,
                     "internal_prefixes": internal, "git_sha_at_start": start_sha})
    print(f"per deciding scenario: {per_scen.to_dict()}  -> D-039 reopen condition met: {met}")
    print("wrote results/tables/n6b_ctu13_perhost{,_hostlevel}.csv and results/runs/n6b-ctu13-perhost/")


if __name__ == "__main__":
    main()
