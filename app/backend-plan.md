# Backend plan - NetWM API

Owner: **Arun** (R-1..R-4 on [teamtasks.md](../teamtasks.md)) · Serves
[api_contract.md](api_contract.md) v1.1 · Wraps `netwm.engine.predict.analyze_file`.

## Constraints

- **Offline, always.** No outbound request from any code path. This is a graded PS requirement, not
  a preference.
- **Never undemoable.** With no checkpoint present the server still serves `app/mock/*.json`, marked
  `"mock": true`. A missing model degrades the demo, it does not break it.
- Single machine, single user, Flask dev server is fine. No auth, bind `127.0.0.1` only.
- One inference at a time (torch + a 4 GB GPU); requests queue rather than fight for memory.

## Layout

```
app/
  server.py     Flask app + routes only - thin, no ML logic
  jobs.py       Job model, in-memory store, worker thread, cleanup
  inference.py  model registry, checkpoint loading, calls analyze_file, mock fallback
  config.py     paths, limits, defaults (window caps, upload caps, worker count)
  errors.py     error codes -> HTTP status, one JSON error shape
  run_demo.bat  one-command start for the evaluators
```

## Request lifecycle

```
POST /api/analyze (multipart)
  ├─ validate: extension in {.csv,.pcap,.pcapng}, size under cap, non-empty
  ├─ save to data/uploads/<job_id>/<secure_filename>   (never join user text into a path)
  ├─ create Job(id, state="queued", progress=0.0)      -> return {"job_id": ...} 202
  └─ worker thread:
        inference.run(job)            progress callback -> job.progress / job.stage_text
          ├─ load flows  (CSV adapter, or PCAP -> flow_aggregator once A-3 lands)
          ├─ build features + scaler
          ├─ model forward + K-step rollout
          ├─ explanations for alarm windows + every 8th (D-018)
          └─ write data/jobs/<job_id>.json            job.state = "done"
GET /api/jobs/<id>          -> {state, progress, stage_text, error?}
GET /api/jobs/<id>/result   -> streams the cached JSON straight from disk (do not re-serialise)
```

`analyze_file` already takes a `progress=lambda p, msg: ...` callback - wire it to the Job, do not
re-implement the pipeline.

## Job store

```python
@dataclass
class Job:
    id: str; kind: str; filename: str
    state: str  # queued | running | done | error
    progress: float; stage_text: str
    result_path: Path | None; error: dict | None
    created_at: float
```

Dict + `threading.Lock`, single worker thread pulling a `queue.Queue`. Jobs and their uploads are
deleted after 2 hours or when more than 20 exist (oldest first). Results live on disk so a large
payload is never held in memory twice - Thursday's payload is ~1.9 MB and 972 windows.

## Model registry (`inference.py`)

`models/registry.json`: `{"default": "e4e7-worldmodel-r2/thursday.pt", "friday": "..."}`. Load lazily
on first request, keep one model in memory, log which checkpoint answered a request and echo it in
`/api/model`. If the file is missing: serve mocks and set `"mock": true` - never a 500.

## Threshold policy (D-020)

The engine computes a **per-capture** threshold (top 10 % of that capture's own scores) because
train-tuned thresholds are ~100x too high on a held-out day (E14). The API passes
`threshold_policy` through untouched and accepts `?policy=self-budget-10pct|self-budget-5pct|fixed&threshold=`
so the UI can offer the trade-off. It must never silently substitute a fixed threshold.

## Errors

| code | status | when |
|---|---|---|
| `bad_file` | 400 | unreadable, empty, or wrong columns |
| `unsupported_format` | 415 | extension not allowed |
| `too_large` | 413 | over the cap (200 MB CSV / 2 GB PCAP) |
| `no_model` | 503 | checkpoint missing *and* mocks unavailable |
| `job_not_found` | 404 | unknown or expired job id |
| `internal` | 500 | anything else - log the traceback, return the job id, never the stack |

One shape: `{"error": {"code": "...", "message": "..."}}`. The message is for a human on screen.

## SSE replay (R-3)

`GET /api/jobs/<id>/stream?speed=4` yields `event: window` + one timeline entry as JSON, paced at
`speed` windows/second, a `: heartbeat` comment every 15 s, then `event: end`. Read the cached result
from disk and stream it - do not re-run inference. Client disconnect must stop the generator.

## Safety and offline guarantee (R-4)

- `werkzeug.utils.secure_filename`, uploads under `data/uploads/<job_id>/` only, extension allowlist,
  `MAX_CONTENT_LENGTH` set in `config.py`.
- A pytest that monkeypatches `socket.socket` to raise, then exercises upload -> result -> stream:
  if anything reaches the network, the test fails. This is the evidence for the PS's offline claim.
- No `debug=True` in the shipped command; `run_demo.bat` starts on `127.0.0.1:5000` and opens the page.

## Tests (pytest, `tests/test_api.py`)

1. Every endpoint against the committed mocks, no model loaded.
2. Upload a 200-row CSV slice -> job completes -> payload validates against the documented v1.1 keys
   (reuse the validator so contract drift fails CI, not the demo).
3. Error paths: wrong extension, empty file, unknown job id.
4. The offline test above.

## Definition of done per milestone

| id | done when |
|---|---|
| R-1 | upload a real day CSV -> real payload; mocks served when no checkpoint exists |
| R-2 | contract, mocks and engine agree, enforced by a test |
| R-3 | SSE replay drives the dashboard smoothly at speed 4 |
| R-4 | clean Windows machine: `run_demo.bat`, WiFi off, works from the README alone |
