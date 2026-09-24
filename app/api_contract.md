# NetWM API contract v1

Frozen on day 1 so frontend, backend and ML can work in parallel. **Any change is a PR that updates
this file, `app/mock/*.json` and the frontend in one commit.** The mock fixtures are the source of
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
- When no trained model is present the backend still serves `/api/demos` from `app/mock/` so the UI
  is always demo-able (`"mock": true` in the payload).
