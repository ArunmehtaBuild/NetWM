# Backend plan - NetWM API

Owner: **Arun** (R-1..R-4 on [../teamtasks.md](../teamtasks.md)) · Serves
[../docs/api_contract.md](../docs/api_contract.md) v1.1 · Wraps `netwm.engine.predict.analyze_file`.

**Deployed separately from the frontend.** This is a JSON API and nothing else - it renders no HTML,
serves no CSS, and has no opinion about how the dashboard is hosted.

## Why FastAPI rather than Flask

The PS names "Streamlit, Flask web app, or CLI" as examples and says explicitly that the listed
approaches "are provided only as examples and are not mandatory". Flask was the original pick purely
because the PS names it. Three things changed that:

1. **Pydantic response models make the contract executable.** We have already shipped payload drift
   twice - `p_cum_attack`/`p_cum_escalate` were computed and then silently dropped, and
   `observed_stage_conf` was documented for a day without existing. A typed response model turns
   that class of bug into a startup/validation error instead of something the frontend discovers.
2. **Separate deployment needs first-class CORS**, which is one middleware line here.
3. **OpenAPI comes free** at `/docs`, so the frontend has a browsable, always-current spec next to
   the hand-written contract.

The costs are real but small: one more dependency, and the team knows Flask better. Async buys us
little - torch inference is blocking and runs on one worker by design.

## Constraints

- **Offline, always.** No outbound request from any code path. Graded PS requirement.
- **Never undemoable.** With no checkpoint present the API still serves `fixtures/api/*.json`, marked
  `"mock": true`. A missing model degrades the demo, it does not break it.
- Local single-user tool: bind `127.0.0.1`, no auth, one inference at a time (4 GB GPU).

## Layout

```
backend/
  server.py      FastAPI app, routes, CORS - thin, no ML logic
  schemas.py     Pydantic models mirroring docs/api_contract.md  <- the executable contract
  jobs.py        Job model, in-memory store, single worker thread, cleanup
  inference.py   model registry, checkpoint loading, calls analyze_file, mock fallback
  config.py      paths, limits, CORS origins, defaults (pydantic-settings or plain dataclass)
  errors.py      error codes -> HTTP status, one JSON error shape
  run_demo.bat   starts uvicorn, then the frontend static server
  tests/         test_api.py, test_contract.py, test_offline.py
```

Run: `uvicorn backend.server:app --host 127.0.0.1 --port 5000`

## Request lifecycle

```
POST /api/analyze (multipart)
  ├─ validate: extension in {.csv,.pcap,.pcapng}, size under cap, non-empty
  ├─ save to data/uploads/<job_id>/<secure name>   (never join user text into a path)
  ├─ create Job(id, state="queued") -> 202 {"job_id": ...}
  └─ worker thread (not async - torch blocks):
        inference.run(job)          progress callback -> job.progress / job.stage_text
          ├─ load flows (CSV adapter; PCAP via flow_aggregator once A-3 lands)
          ├─ features + scaler -> model forward -> K-step rollout
          ├─ explanations for alarm windows + every 8th (D-018)
          └─ write data/jobs/<job_id>.json         job.state = "done"
GET /api/jobs/<id>          -> {state, progress, stage_text, error?}
GET /api/jobs/<id>/result   -> FileResponse of the cached JSON (do not re-serialise 2 MB)
```

`analyze_file` already accepts `progress=lambda p, msg: ...` - wire it to the Job, do not
re-implement the pipeline.

## Job store

```python
@dataclass
class Job:
    id: str; kind: str; filename: str
    state: str          # queued | running | done | error
    progress: float; stage_text: str
    result_path: Path | None; error: dict | None
    created_at: float
```

Dict + `threading.Lock`, one worker thread pulling a `queue.Queue`. Jobs and uploads are deleted
after 2 hours or when more than 20 exist (oldest first). Results live on disk so a 2 MB payload is
never held twice.

## CORS and separate deployment

The frontend is static files on a different origin (`http://127.0.0.1:8080` in dev, anything in
deployment). `config.py` holds an explicit allowlist - default
`["http://127.0.0.1:8080", "http://localhost:8080"]`, overridable with `NETWM_CORS_ORIGINS`:

```python
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["GET", "POST"], allow_headers=["*"])
```

Do **not** ship `allow_origins=["*"]`: this API takes file uploads, and a wildcard on a
locally-bound service is the kind of thing a security-themed jury asks about. An allowlist costs one
environment variable.

## Model registry (`inference.py`)

`models/registry.json`: `{"default": "e4e7-worldmodel-r2/thursday.pt", "friday": "..."}`. Load lazily
on first request, keep one model in memory, echo which checkpoint answered in `/api/model`. Missing
file -> serve fixtures with `"mock": true`, never a 500.

## Threshold policy (D-020)

The engine computes a **per-capture** threshold (top 10 % of that capture's own scores); train-tuned
thresholds are ~100x too high on a held-out day and fire zero alarms (E14). The API passes
`threshold_policy` through untouched and accepts
`?policy=self-budget-10pct|self-budget-5pct|fixed&threshold=` so the UI can offer the trade-off.
It must never silently substitute a fixed threshold.

## Errors

| code | status | when |
|---|---|---|
| `bad_file` | 400 | unreadable, empty, or wrong columns |
| `unsupported_format` | 415 | extension not allowed |
| `too_large` | 413 | over the cap (200 MB CSV / 2 GB PCAP) |
| `no_model` | 503 | checkpoint missing *and* fixtures unavailable |
| `job_not_found` | 404 | unknown or expired job id |
| `internal` | 500 | anything else - log the traceback, return the job id, never the stack |

One shape everywhere: `{"error": {"code": "...", "message": "..."}}`, with the message written for a
human reading it on screen. Register an exception handler so FastAPI's default `{"detail": ...}`
never leaks through.

## SSE replay (R-3)

`GET /api/jobs/<id>/stream?speed=4` returns a `StreamingResponse` with media type
`text/event-stream`: `event: window` + one timeline entry per message, paced at `speed`
windows/second, a `: heartbeat` comment every 15 s, then `event: end`. Stream from the cached result
on disk - never re-run inference. Stop the generator when the client disconnects
(`await request.is_disconnected()`).

## Safety and the offline guarantee (R-4)

- Filename sanitising, uploads only under `data/uploads/<job_id>/`, extension allowlist, request size
  cap enforced in middleware (FastAPI has no `MAX_CONTENT_LENGTH` equivalent - check
  `content-length` and stream-count bytes).
- **`tests/test_offline.py`**: monkeypatch `socket.socket` to raise, then exercise
  upload -> result -> stream. If anything touches the network, the test fails. This test *is* our
  evidence for the PS's offline requirement.
- No `--reload` in the shipped command. `run_demo.bat` starts uvicorn on 127.0.0.1:5000 and the
  frontend's static server on 8080, then opens the browser.

## Tests

| file | covers |
|---|---|
| `test_api.py` | every endpoint against the fixtures with no model loaded; error paths (wrong extension, empty file, unknown job id) |
| `test_contract.py` | **R-2**: every key documented in `docs/api_contract.md` exists in `fixtures/api/*.json` and in a freshly produced payload - drift fails a test, not the demo |
| `test_offline.py` | the socket test above |

## Definition of done

| id | done when |
|---|---|
| R-1 | `POST /api/analyze` with a real day CSV returns a real payload; fixtures served when no checkpoint |
| R-2 | contract, fixtures and engine agree, enforced by `test_contract.py` |
| R-3 | SSE replay drives the dashboard smoothly at speed 4 |
| R-4 | clean Windows machine: `run_demo.bat`, WiFi off, works from the README alone |
