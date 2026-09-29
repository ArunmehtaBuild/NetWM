"""The demo video's figures for the served CSV model (r2w seed 42, D-041), measured through the backend's
own demo path - the payload the dashboard draws - on the causal expanding 10 % budget it serves.

    python scripts/demo_figures.py

Every number the demo video quotes about a demo slice comes from here, so the script can be checked
against the screen. Per slice: windows, alarmed windows (on attack windows and on benign ones), each alarm
run's start and end, onsets warned early against the circular-shift null, surprise on benign windows, at the
17:00 scan and over the sweep, and the stage and top features at the sweep's strongest alarm. The whole
held-out Thursday is also run through the upload path, for the alarm rate and the early-warning test the
dashboard runs live; the evaluation's own alarm rate is recomputed from the stored scores beside it.

These describe single captures under their own causal budget; they are not an evaluation (the evaluation
is D-041's, ``results/tables/n8_fix_eval.csv``). Writes ``results/runs/demo-r2w-figures/`` and
``results/tables/demo_r2w_alarm_runs.csv``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from netwm.metrics import causal_threshold  # noqa: E402
from netwm.utils import RUNS, TABLES, git_sha, save_run  # noqa: E402

RUN = "demo-r2w-figures"
FULL_THURSDAY = ROOT / "data" / "raw" / "cicids2017_improved" / "thursday.csv"
# Thursday's story, UTC as the dashboard shows it (S-8 for the scan's own seconds)
SCAN = ("2017-07-06T16:59:30Z", "2017-07-06T17:00:00Z")   # windows overlapping 17:00:31-17:00:45
COMPROMISE = "2017-07-06T17:18:30Z"
SWEEP = ("2017-07-06T18:04:00Z", "2017-07-06T18:45:00Z")   # the sweeping host is the top talker


def _payload(kind: str, name: str, path: Path | None = None) -> dict:
    from backend import inference
    from backend.jobs import Job

    job = Job(id=f"j_demo_figures_{name}", kind=kind, filename=name, file_path=path, state="running",
              progress=0.0, stage_text="")
    return json.loads(inference.run_job_inference(job, lambda pct, msg: None).read_text(encoding="utf-8"))


def _runs(payload: dict, slice_id: str) -> list[dict]:
    ts = [w["ts"] for w in payload["timeline"]]
    return [{"slice": slice_id, "start": a["ts"], "last_window": ts[a["until_t"]], "windows": a["windows"],
             "peak_p": a["p"]} for a in payload.get("alarms") or []]


def _common(payload: dict) -> dict:
    tl = payload["timeline"]
    attack = np.array([bool(w.get("observed_stage")) for w in tl])
    alarm = np.array([w["alarm"] for w in tl])
    surprise = np.array([w["surprise"] for w in tl], float)
    lead = payload.get("lead_time_summary") or {}
    return {
        "checkpoint": [Path(c).parent.name + "/" + Path(c).name for c in payload["inference"]["checkpoints"]],
        "threshold_policy": payload["threshold_policy"], "mock": payload["mock"], "in_sample": payload.get("in_sample"),
        "flows": payload["source"]["flows"], "windows": len(tl), "attack_windows": int(attack.sum()),
        "alarmed_windows": int(alarm.sum()), "alarmed_share": round(float(alarm.mean()), 3),
        "alarmed_on_attack_windows": int((alarm & attack).sum()), "alarmed_on_benign_windows": int((alarm & ~attack).sum()),
        "attack_windows_alarmed_share": round(float(alarm[attack].mean()), 3) if attack.any() else None,
        "alarm_runs": len(payload.get("alarms") or []),
        "surprise_benign_median": round(float(np.median(surprise[~attack])), 2) if (~attack).any() else None,
        "p_max_median": round(float(np.median([w["p_max"] for w in tl])), 4),
        "p_max_max": round(float(max(w["p_max"] for w in tl)), 4),
        "early_warning": {k: lead.get(k) for k in ("episodes", "warned_early", "p_value")} if lead else None,
        "onsets": [o["ts"] for o in (payload.get("ground_truth") or {}).get("onsets", [])],
    }


def _between(tl: list[dict], lo: str, hi: str) -> list[dict]:
    return [w for w in tl if lo <= w["ts"] <= hi]


def thursday_story(payload: dict, runs: list[dict]) -> dict:
    tl = payload["timeline"]
    scan = _between(tl, *SCAN)
    sweep = _between(tl, *SWEEP)
    sweep_alarms = [w for w in sweep if w["alarm"]]
    peak = max(sweep_alarms, key=lambda w: w["p_max"]) if sweep_alarms else None
    stages = pd.Series([w["pred_stage"] for w in sweep]).value_counts()
    names = {s["id"]: s["label"] for s in payload["stages"]}
    before = [w for w in tl if w["ts"] < SCAN[0]]
    return {
        "surprise_quiet_median_before_scan": round(float(np.median([w["surprise"] for w in before])), 2),
        "scan_windows": [{"ts": w["ts"], "surprise": round(w["surprise"], 2), "p_max": w["p_max"], "alarm": w["alarm"],
                          "threshold": w["threshold"]} for w in scan],
        "runs_scan_to_compromise": [r for r in runs if SCAN[1] < r["start"] < COMPROMISE],
        "runs_compromise_to_sweep": [r for r in runs if COMPROMISE <= r["start"] < SWEEP[0]],
        "runs_in_sweep": [r for r in runs if SWEEP[0] <= r["last_window"] and r["start"] <= SWEEP[1]],
        "surprise_sweep": {"min": round(float(min(w["surprise"] for w in sweep)), 1),
                           "median": round(float(np.median([w["surprise"] for w in sweep])), 1),
                           "max": round(float(max(w["surprise"] for w in sweep)), 1)},
        "sweep_windows": len(sweep), "sweep_alarmed": len(sweep_alarms),
        "sweep_predicted_stage": {names[int(k)]: int(v) for k, v in stages.items()},
        "sweep_peak_alarm": None if peak is None else {
            "ts": peak["ts"], "p_max": peak["p_max"], "surprise": round(peak["surprise"], 1),
            "pred_stage": names[peak["pred_stage"]], "top_talker": (peak.get("top_talkers") or [{}])[0],
            "top_features": [(f["name"], f["direction"]) for f in (peak.get("top_features") or [])[:5]]},
    }


def friday_c2_story(payload: dict, runs: list[dict]) -> dict:
    onset = payload["ground_truth"]["onsets"][0]["ts"] if payload["ground_truth"].get("onsets") else None
    after = [r for r in runs if onset and r["last_window"] >= onset]
    first = after[0]["start"] if after else None
    late_min = None if first is None else round((pd.Timestamp(first) - pd.Timestamp(onset)).total_seconds() / 60, 1)
    names = {s["id"]: s["label"] for s in payload["stages"]}
    at = [w for w in payload["timeline"] if onset and onset <= w["ts"] and w.get("observed_stage")]
    return {"c2_onset": onset, "first_alarm_at_or_after_onset": first, "minutes_after_onset": late_min,
            "alarms_before_onset": [r for r in runs if onset and r["last_window"] < onset],
            "predicted_stage_on_c2_windows": {k: int(v) for k, v in
                                              pd.Series([names[w["pred_stage"]] for w in at]).value_counts().items()}}


def stored_alarm_rate(run: str = "n8-r2w-s42", day: str = "thursday") -> dict:
    """The evaluation's own view: the stored held-out scores under the same causal budget (D-034)."""
    m = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))
    s = np.asarray(m["metrics"]["per_day"][day]["scores"], float)
    alarm = s >= causal_threshold(s, 0.90)
    return {"run": run, "day": day, "windows": int(s.size), "alarmed_windows": int(alarm.sum()),
            "alarmed_share": round(float(alarm.mean()), 3)}


def rollout_vs_persistence(run: str = "n8-r2w-s42") -> dict:
    """The cone beat: next-state error of the open-loop rollout against repeating the current state, from
    the run's stored held-out rollout (the E5 measurement, per step k)."""
    m = json.loads((RUNS / run / "metrics.json").read_text(encoding="utf-8"))
    out = {}
    for day, d in m["metrics"]["per_day"].items():
        r = d["rollout"]
        wm, pe = np.asarray(r["world_model_mse"]), np.asarray(r["persistence_mse"])
        out[day] = {"k1_world_model": round(float(wm[0]), 3), "k1_persistence": round(float(pe[0]), 3),
                    "k2_10_world_model": round(float(wm[1:].mean()), 3), "k2_10_persistence": round(float(pe[1:].mean()), 3),
                    "steps_2_10_better": int((wm[1:] < pe[1:]).sum())}
    return out


def main() -> None:
    out, all_runs = {}, []
    for slice_id in ("thursday_infiltration", "friday_botnet_c2", "friday_scan_to_ddos"):
        p = _payload("demo", slice_id)
        runs = _runs(p, slice_id)
        all_runs += runs
        out[slice_id] = _common(p)
        if slice_id == "thursday_infiltration":
            out[slice_id]["story"] = thursday_story(p, runs)
        if slice_id == "friday_botnet_c2":
            out[slice_id]["story"] = friday_c2_story(p, runs)
    full = _payload("csv", "thursday.csv", FULL_THURSDAY)
    out["full_thursday_upload"] = _common(full)
    out["full_thursday_stored_scores"] = stored_alarm_rate()
    out["rollout_vs_persistence"] = rollout_vs_persistence()

    pd.DataFrame(all_runs).to_csv(TABLES / "demo_r2w_alarm_runs.csv", index=False)
    save_run(RUN, out, config={"git_sha_at_start": git_sha(), "served_via": "backend.inference.run_job_inference",
                               "scan_windows": SCAN, "compromise": COMPROMISE, "sweep": SWEEP,
                               "note": "description of single captures under their own causal budget, not an evaluation"})
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
