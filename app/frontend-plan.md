# Frontend plan - NetWM dashboard

Owner: **Harshit** (H-1..H-6 on [teamtasks.md](../teamtasks.md)) · Data contract:
[api_contract.md](api_contract.md) v1.1 · Build against `app/mock/*.json` - **never wait for a model.**

## Constraints

- **No build step.** Plain ES modules, no npm, no bundler. Open `index.html` through Flask and it works.
- **Fully offline.** Every asset is vendored in `app/static/vendor/`. A single CDN `<script>` tag
  fails the PS requirement on an air-gapped evaluation machine.
- **The payload is the API.** Colours, stage names, horizon, threshold and the alarm statistic all come
  from the JSON. Nothing about MITRE stages is hard-coded in JS.
- Target: one screen, 1366x768 and up, dark theme. Mobile is not a requirement.

## Layout

```
app/
  templates/index.html         single page, panel containers only, no logic
  static/
    css/theme.css              design tokens (colours, spacing, type scale)
    css/app.css                layout + panel styles
    js/api.js                  fetch wrappers, mock fallback, SSE client
    js/store.js                one state object + subscribe/notify, no framework
    js/format.js               time, percent, byte and lead-time formatting
    js/main.js                 wiring: load payload -> store -> render panels
    js/panels/upload.js        file picker, demo selector, job progress
    js/panels/timeline.js      risk timeline + forecast cone (the main chart)
    js/panels/ribbon.js        kill-chain stage ribbon + current-stage card
    js/panels/alarms.js        alarm log with lead time  <- H-4, the demo money shot
    js/panels/why.js           attribution bars + attention heatmap
    js/panels/flows.js         flagged flows table + top talkers
    js/charts/cone.js          cone rendering helper for Chart.js
    js/charts/heatmap.js       canvas attention heatmap (Chart.js has no heatmap)
    vendor/chart.umd.min.js    pinned Chart.js, vendored (see below)
```

## Data flow

```
main.js ──► api.loadAnalysis()  ──► store.set({payload})
               │  (POST /api/analyze  or  GET /api/demos  or  fetch('/static/../mock/thursday.json'))
               ▼
          store.subscribe(panel.render)   every panel is a pure render(state) function
               ▲
          store.set({selectedWindow})     clicking the timeline updates one key; panels re-render
```

`store.js` holds exactly: `payload`, `selectedWindow` (int), `replay` (`{playing, t, speed}`),
`filters` (`{stage, minScore}`), `jobStatus`. No other global state; no framework.

## Panels

### Upload / demo bar
Drag-drop or pick a `.csv` / `.pcap`, or choose a demo from `GET /api/demos`. Shows job progress
(`GET /api/jobs/<id>` every 750 ms) with the backend's `stage_text`. States: idle, uploading,
running (progress bar), done, error (show `error.code` in plain words).

### Timeline (H-2) - the main chart
Chart.js line chart over `timeline[]`:
- **Risk line**: `p_max` per window (this is what `alarm` thresholds - D-019/D-020).
- **Forecast cone**: on the selected window, plot `forecast.p_cum` for k = 1..K continuing forward
  from `t`, shaded between `p_lo` and `p_hi`.
- **Threshold line**: `payload.threshold`, labelled with `threshold_policy` - say
  *"top 10 % of this capture"*, not a bare number.
- **Ground-truth spans**: shade `ground_truth.spans[]` by stage colour when `available`.
- **Alarm markers**: points where `alarm` is true.
- Optional toggles: `p_cum_attack`, `p_cum_escalate` as secondary lines (they answer different
  questions - "anything hostile" and "attacker advancing").
- Click a point -> `store.set({selectedWindow: t})`; every other panel follows.
- **Performance**: 972 windows x several series. Enable Chart.js decimation, `animation: false`,
  `pointRadius: 0` except alarms, and redraw with `chart.update('none')`.

### Kill-chain ribbon (H-3)
A strip of one cell per window coloured by `pred_stage`, with `observed_stage` as a thinner strip
underneath when ground truth exists. Current-stage card shows the stage label, its ATT&CK tactic id
from `payload.stages[]`, and `stage_probs` as a small bar row.

### Alarm log with lead time (H-4)
One row per entry in `alarms[]`: time, peak `p`, predicted stage, and the lead-time verdict.
**Three states, all of which must look deliberate:**
1. `lead_windows` present -> *"fired 6 windows (180 s) before onset"* in the accent colour.
2. `onset_t` present, `lead_windows` null/0 -> *"fired at onset - detection, not forecast"*.
3. no onset ahead -> *"no compromise followed within the horizon"* (a false positive, shown plainly).

Today's real payloads produce **only state 2/3** (see `results.md` E14). State 1 is built against
`app/mock/thursday_oracle.json` (task T-07), which is a **UI development fixture only** - no number
from it ever reaches a slide.

### Why panel (H-5)
- Horizontal bars of `top_features[]` for the selected window: name, value, signed `attribution`.
  Only ~15 % of windows carry explanations (D-018) - when the selected one does not, say
  *"no attribution computed for this window"* instead of rendering an empty chart.
- Attention heatmap: `attention[]` is the weight over the last L windows. Canvas, one row, hover
  shows which past window and its timestamp.
- `explanation_global` drives a "what drives this capture overall" bar list.

### Flows + talkers (H-5)
`GET /api/jobs/<id>/flows?window=<t>` paged table: ts, src, dst, port, protocol, flags, pkts, bytes,
score. Sortable, filter by stage. `top_talkers[]` from the selected window as a compact list.

### Replay (H-6)
Play / pause / scrub driven by `GET /api/jobs/<id>/stream?speed=`. On each `window` event, advance
`replay.t` and let the timeline draw progressively - the point of the demo video is that the risk
curve moves *before* the attack spans appear.

## Design tokens (`css/theme.css`)

Define once as CSS custom properties, never inline:

| token | value | use |
|---|---|---|
| `--bg` / `--surface` / `--surface-2` | `#0f1216` / `#161b22` / `#1c2230` | page, panels, raised rows |
| `--text` / `--muted` | `#e6edf3` / `#8b98a5` | copy, secondary copy |
| `--accent` | `#4c9be8` | selection, focus, the lead-time callout |
| `--danger` | `#e2574c` | alarms, compromise |
| `--grid` | `#2a3038` | chart gridlines |
| stage colours | from `payload.stages[].color` | ribbon, spans, stage chips |

Type: system stack, 13/14 px body, tabular numerals for every metric (`font-variant-numeric:
tabular-nums`) so columns do not jitter during replay.

## Vendoring Chart.js (do this before H-1)

Pin the version, download once, commit the file, and record the SHA-256 in this file:

**Done** - `app/static/vendor/chart.umd.min.js` is committed:

| | |
|---|---|
| version | Chart.js v4.4.1 (UMD build) |
| source | `https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js` |
| size | 205 399 bytes |
| sha256 | `d2af8974e95271638772e9e9524db5b9a6f58d6ec2d5d781400447b4a31c681e` |
| licence | MIT |

Load it with `<script src="/static/vendor/chart.umd.min.js"></script>` - no `integrity` attribute is
needed or wanted, the file is local. To re-vendor or upgrade:

```bash
curl -sL -o app/static/vendor/chart.umd.min.js https://cdn.jsdelivr.net/npm/chart.js@<version>/dist/chart.umd.min.js
sha256sum app/static/vendor/chart.umd.min.js   # then update the table above
```

Nothing else gets vendored without a line here saying what and why. No fonts from Google, no icon
CDN - use inline SVG for the handful of icons.

## Empty, loading and error states (write these first, not last)

Every panel needs all four: **no payload yet**, **loading**, **loaded but nothing to show**
(no alarms, no explanation for this window, no ground truth), **error**. A demo that hits an empty
state and shows a blank rectangle reads as broken; one that says *"no compromise followed within the
horizon"* reads as honest.

## Definition of done per milestone

| id | done when |
|---|---|
| H-1 | page loads from `python -m flask --app app.server run`, offline, renders the Thursday mock |
| H-2 | timeline with risk line, cone on the selected window, threshold line labelled by policy, ground-truth spans |
| H-3 | ribbon + current-stage card, colours sourced from the payload |
| H-4 | all three alarm states render; verified against `thursday.json` (state 2/3) *and* `thursday_oracle.json` (state 1) |
| H-5 | attribution bars, attention heatmap, flows table, talkers - all reacting to `selectedWindow` |
| H-6 | replay plays a day end-to-end without stutter; 2-minute video recorded |

## Rules

1. Read every number from the payload. If something you need is missing, that is a **contract**
   change: raise it here and it becomes a v1.2 entry - do not compute it in JS.
2. Never display a probability without its context: the threshold policy and the horizon
   (*"within the next 5 minutes"*) belong next to it.
3. Do not invent an "attack detected!" narrative the model did not produce. The honest states are the
   product (see `results.md` E14 and the demo-framing note in `teamtasks.md`).
