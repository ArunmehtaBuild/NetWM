# NetWM API contract v1

Frozen on day 1 so frontend, backend and ML can work in parallel. **Any change is a PR that updates
this file, `fixtures/api/*.json` and the frontend in one commit.** The mock fixtures are the source of
truth for the UI until the real model lands - the frontend must never need a trained model to run.

Base URL: `http://127.0.0.1:5000`. Everything is offline; no external calls, ever.

## Endpoints

| method | path | purpose |
|---|---|---|
| GET | `/api/health` | liveness + whether a model is loaded |
| GET | `/api/model` | model card: architecture, training config, headline metrics, stage list |
| GET | `/api/demos` | preloaded demo scenarios (no upload needed - used in the demo video) |
| POST | `/api/analyze` | multipart upload of a `.csv` or `.pcap`; returns a `job_id` |
| POST | `/api/analyze/demo/<demo_id>` | run a preloaded scenario; returns a `job_id` |
| GET | `/api/jobs/<job_id>` | status: `queued` / `running` / `done` / `error`, `progress` 0-1, `stage_text` |
| GET | `/api/jobs/<job_id>/result` | the full analysis payload (below) |
| GET | `/api/jobs/<job_id>/stream` | SSE: one `window` event per time window, for live replay |
| GET | `/api/jobs/<job_id>/flows?window=<t>&limit=50` | flagged flows for one window (paged) |

Errors: HTTP status + `{"error": {"code": "...", "message": "..."}}`. Codes: `bad_file`,
`unsupported_format`, `too_large`, `no_model`, `job_not_found`, `internal`.

## `GET /api/model`

```json
{
  "name": "netwm-rssm-v1", "trained_on": "CIC-IDS2017 (corrected), Mon-Wed + Fri",
  "window_s": 60, "stride_s": 30, "horizon_k": 10, "params": 1840000, "git_sha": "abc1234",
  "stages": [
    {"id": 0, "key": "BENIGN", "label": "Benign", "tactic": "", "color": "#9aa7b1"},
    {"id": 1, "key": "RECONNAISSANCE", "label": "Reconnaissance", "tactic": "TA0043", "color": "#4c9be8"},
    {"id": 2, "key": "INITIAL_ACCESS", "label": "Initial Access", "tactic": "TA0001", "color": "#f2a541"},
    {"id": 3, "key": "LATERAL_MOVEMENT", "label": "Lateral Movement", "tactic": "TA0008", "color": "#e2574c"},
    {"id": 4, "key": "COMMAND_AND_CONTROL", "label": "Command & Control", "tactic": "TA0011", "color": "#8e5bd9"},
    {"id": 5, "key": "EXFILTRATION", "label": "Exfiltration", "tactic": "TA0010", "color": "#2fa87a"},
    {"id": 6, "key": "IMPACT", "label": "Impact", "tactic": "TA0040", "color": "#6b6b6b"}
  ],
  "metrics": {"f1": 0.0, "precision": 0.0, "recall": 0.0, "fpr": 0.0, "pr_auc": 0.0,
              "mean_lead_time_windows": 0.0, "baseline_f1": 0.0},
  "feature_count": 84
}
```

## `GET /api/jobs/<job_id>/result`

`timeline[]` is one entry per window and drives every chart. `forecast` is the K-step rollout *from
that window*: `p_cum[k-1]` = P(compromise within k windows), with `p_lo` / `p_hi` the Monte-Carlo
5th/95th percentile band. `alarm` is `p_cum[K-1] > threshold`.

```json
{
  "job_id": "j_7f3a", "source": {"filename": "thursday_slice.csv", "kind": "csv",
    "flows": 362076, "windows": 972, "t0": "2017-07-06T11:59:00Z", "window_s": 60, "stride_s": 30},
  "threshold": 0.5, "horizon_k": 10,
  "timeline": [
    {
      "t": 417, "ts": "2017-07-06T17:17:30Z",
      "observed_stage": 0, "observed_stage_conf": 0.97,
      "pred_stage": 3, "stage_probs": [0.11, 0.02, 0.07, 0.68, 0.09, 0.02, 0.01],
      "forecast": {
        "p_cum":  [0.08, 0.17, 0.29, 0.44, 0.58, 0.67, 0.73, 0.77, 0.80, 0.82],
        "p_lo":   [0.03, 0.09, 0.16, 0.27, 0.38, 0.47, 0.54, 0.59, 0.62, 0.64],
        "p_hi":   [0.15, 0.28, 0.44, 0.61, 0.74, 0.82, 0.87, 0.90, 0.92, 0.93]
      },
      "alarm": true, "surprise": 2.41,
      "top_features": [
        {"name": "syn_without_ack_ratio", "value": 0.83, "attribution": 0.31, "direction": "up"},
        {"name": "unique_dst_ports", "value": 217.0, "attribution": 0.22, "direction": "up"},
        {"name": "dst_port_entropy", "value": 6.9, "attribution": 0.14, "direction": "up"}
      ],
      "attention": [0.02, 0.03, 0.05, 0.09, 0.14, 0.21, 0.46],
      "flow_count": 812, "top_talkers": [{"ip": "192.168.10.8", "flows": 640, "bytes_out": 91233}]
    }
  ],
  "ground_truth": {
    "available": true,
    "spans": [{"start_t": 420, "end_t": 512, "stage": 3, "label": "Infiltration"}],
    "onsets": [{"t": 420, "ts": "2017-07-06T17:18:30Z", "label": "Infiltration"}]
  },
  "alarms": [
    {"t": 414, "ts": "2017-07-06T17:16:00Z", "p": 0.62, "pred_stage": 3,
     "onset_t": 420, "lead_windows": 6, "lead_seconds": 180}
  ],
  "explanation_global": {
    "feature_names": ["syn_without_ack_ratio", "unique_dst_ports", "..."],
    "mean_abs_attribution": [0.21, 0.18]
  }
}
```

## `GET /api/jobs/<job_id>/flows?window=417`

```json
{"window": 417, "total": 812, "flows": [
  {"ts": "2017-07-06T17:17:33Z", "src_ip": "192.168.10.8", "src_port": 54112,
   "dst_ip": "192.168.10.50", "dst_port": 445, "protocol": 6, "flags": "S",
   "pkts": 2, "bytes": 120, "duration_ms": 3, "score": 0.91, "stage_hint": 3}
]}
```

## SSE `GET /api/jobs/<job_id>/stream`

`event: window` with one `timeline[]` entry as `data:`, emitted in order at a replay rate set by
`?speed=` (windows per second, default 4). Terminates with `event: end`. Used by the dashboard's
play/pause replay so the demo video shows the forecast rising *before* the attack.

## Rules

- Every numeric field is JSON-safe (no `NaN`/`Infinity`); the backend replaces them with `null`.
- `timeline` is capped at 5 000 entries per response; longer captures paginate with `?from=&to=`.
- Uploads capped at 200 MB CSV / 2 GB PCAP; oversize returns `too_large`.
- Stage ids and colours come from `/api/model`, never hard-coded in the frontend.
- When no trained model is present the backend still serves `/api/demos` from `fixtures/api/` so the UI
  is always demo-able (`"mock": true` in the payload).

---

## v1.1 (2026-09-25) - additive

Every v1.0 field is unchanged; v1.1 only adds. Payloads carry `"payload_version": "1.1"`.
Reference payloads: `fixtures/api/thursday.json`, `fixtures/api/friday.json` (2.0 MB each, real model output
from `models/e4e7-worldmodel-r2/`, not hand-written).

**Top level**

| field | type | meaning |
|---|---|---|
| `payload_version` | string | `"1.1"` |
| `alarm_statistic` | string | `"p_max"` - the statistic `alarm` and `threshold` refer to |
| `threshold_policy` | string | `"self-budget-10pct"` (threshold = 90th percentile of this capture's own scores) or `"fixed"` |
| `stages` | array | the stage catalogue, same shape as `GET /api/model.stages` - so a result is renderable on its own |

**Per timeline entry**

| field | type | meaning |
|---|---|---|
| `p_max` | float | `max_k P(compromised at t+k)` - **this is what `alarm` thresholds** (D-019) |
| `forecast.p_step` | float[K] | per-step P(compromised at t+k), before any union formula |
| `forecast.p_cum_attack` | float[K] | P(anything hostile within k) |
| `forecast.p_cum_escalate` | float[K] | P(the attacker advances a stage within k) |
| `top_talkers` | array | `[{ip, flows, bytes_out}]`, the 3 busiest sources in the window |
| `observed_stage` | int | ground-truth stage, present only when the upload carries labels |

**`ground_truth.spans`**

```json
{"start_t": 639, "end_t": 657, "start_ts": "2017-07-06T17:18:30Z", "end_ts": "2017-07-06T17:27:30Z",
 "stage": 3, "label": "Infiltration"}
```

Contiguous runs of one ground-truth stage, named after the attack that dominates them (attempted-only
traffic never names a span - D-009). Use these for the shaded bands behind the timeline.

**Note on `alarm`/`threshold`.** `threshold` is now computed per capture when `threshold_policy` is a
self-budget policy, so it differs between uploads - read it from the payload, never hard-code it.
Absolute probabilities do not transfer between days (E14: a threshold tuned on training days sits
~100x too high on a held-out day).

### v1.1 addendum (2026-09-25) - fields that closed contract drift

| field | where | meaning |
|---|---|---|
| `observed_stage_conf` | timeline entry | documented in v1.0 but never emitted until now. It is the probability the model assigned to the stage that was *actually* happening (`stage_probs[observed_stage]`), so it is a calibration read-out, not a ground-truth confidence. Present only with labelled input, alongside `observed_stage`. |
| `lead_time_summary` | top level | `{episodes, warned_early, mean_lead_windows, mean_lead_seconds, per_episode[]}`; `null` when the upload has no labels. Each `per_episode` row carries `onset`, `onset_ts`, `first_alarm`, `first_alarm_ts`, `lead_windows`, `lead_seconds`, `detected_early`. |
| `dev_only`, `note` | top level | present **only** on hand-thresholded fixtures. If `dev_only` is true the payload is not a real result - see below. |

**The alarm panel (H-4) must render both states.** With the shipped model and a deployable threshold
the honest answer today is *"0 of 4 episodes warned early"* - that is what `fixtures/api/thursday.json`
contains, and the panel has to show it as a first-class outcome (episodes listed, each marked "no
early warning", with the onset time and the score at onset) rather than an empty list.

**Fixtures**

| file | threshold | use |
|---|---|---|
| `fixtures/api/thursday.json` | self-budget 10 % (0.044) | the real payload: 8 alarm runs, **0 of 4** episodes warned early |
| `fixtures/api/friday.json` | self-budget 10 % | the real payload: 13 alarm runs, **0 of 1** warned early |
| `fixtures/api/thursday_oracle.json` | **0.010, hand-picked from the labels** | **UI development only.** `dev_only: true`. 2 of 4 episodes warned early (leads of 5 and 10 windows, 150 s and 300 s) and 2 missed, so H-4 can be built and verified against both branches in one payload. Never quote its numbers as a result - the honest ones are in results.md E14. |


## Deployment (the two halves ship separately)

The API and the dashboard are separate deployables. The dashboard is static files that may sit on any
origin; the API is JSON only and renders nothing.

| | dev default | notes |
|---|---|---|
| API | `http://127.0.0.1:5000` (`uvicorn backend.server:app`) | binds loopback; OpenAPI at `/docs` |
| dashboard | `http://127.0.0.1:8080` (`python -m http.server 8080` in `frontend/`) | overrides the API host with `?api=` or `window.NETWM_API_BASE` |

- **CORS:** the API allowlists the dashboard origins explicitly (`NETWM_CORS_ORIGINS`), never `*` -
  it accepts file uploads.
- **Fixtures:** `fixtures/api/*.json` is the single source of truth. The API serves them when no
  checkpoint is loaded (`"mock": true`); the dashboard keeps a generated copy in `frontend/mock/`
  (`python scripts/sync_fixtures.py`) so it runs with no backend at all.
- **No cookies, no auth, no state on the server** beyond the job store, so the dashboard can be
  hosted anywhere without changing the API.

### v1.1 addendum (2026-09-25, T-11) - reproducible alarm scores

`alarm_statistic` now reads **`"p_max (mean path)"`**. The curves and their Monte-Carlo band are
unchanged - still sampled rollouts - but the scalar that `alarm` and `threshold` compare against is
read off the deterministic mean path, so the same checkpoint on the same file gives the same
lead-time count every time (E14 saw 1 of 4 and then 2 of 4 at one threshold). Both fixtures and the
API are reproducible end to end: `scripts/predict.py` seeds torch, so even the sampled band is
byte-identical between runs.

| field | where | meaning |
|---|---|---|
| `p_max_mc` | timeline entry | the same statistic from the sampled rollouts, for comparison; `null` when mean-path scoring is off (`--sampled-score`) |
| `windows`, `sustained` | alarm row | run length in windows, and whether it met the persistence rule |
| `persistence_windows` | `lead_time_summary` | how many consecutive windows above the threshold count as a warning (2) |

**One rule change worth reading.** An alarm run shorter than `persistence_windows` is still reported -
the operator saw it - but it no longer carries `lead_windows`/`onset_t`, because a single spike is not
a warning. Before this, `alarms[]` and `lead_time_summary` could disagree about how many episodes were
warned (the oracle fixture said 2 in one place and 1 in the other). They now share one rule.

**Budget thresholds always fire.** `fixtures/api/` has no all-benign payload on purpose, but running
the engine over `data/demo/monday_benign.csv` - a capture with no attack in it - still produces 24
alarms, because a top-10 % budget flags the top 10 % of *something*. The UI must show the score and
the threshold, not a bare alarm count (D-020).
