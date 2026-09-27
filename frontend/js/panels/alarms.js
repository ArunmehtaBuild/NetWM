/**
 * NetWM Alarm Log & Lead-Time Panel (H-4)
 *
 * Implements:
 * 1. Honest episode-level lead-time summary:
 *    - Total episodes, warned early count, mean lead time
 *    - Per-episode breakdown table (onset time, first alarm, lead time, verdict)
 * 2. Alarm runs table (alarms[]) with the three required deliberate states:
 *    - STATE 1: lead_windows > 0 -> "Fired N windows (M s) before onset"
 *    - STATE 2: onset_t is known, lead_windows <= 0 -> "Fired at onset — detection, not forecast"
 *    - STATE 3: no onset ahead -> "No compromise followed within the horizon"
 * 3. dev_only fixture detection (prominent development badge)
 * 4. Interactive row selection linked to store.selectedWindow
 * 5. Robust handling of unlabelled captures
 *
 * See frontend/PLAN.md & docs/api_contract.md v1.1
 */

import { store } from "../store.js";
import {
  formatPercent,
  formatFloat,
  formatIsoTime,
  formatDuration,
  explainThresholdPolicy,
} from "../format.js";

export class AlarmsPanel {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.lastPayload = null;
    this.rendered = false;
  }

  /**
   * Render alarms panel given store state
   */
  render(state) {
    if (!this.container) return;

    const { payload, selectedWindow } = state;
    if (!payload) {
      this.container.innerHTML = `
        <div class="panel-placeholder">
          <div class="placeholder-title">No analysis payload loaded</div>
        </div>
      `;
      this.lastPayload = null;
      this.rendered = false;
      return;
    }

    // Optimization for H-6 replay: If payload has not changed, update active row highlighting in-place
    if (this.lastPayload === payload && this.rendered) {
      this._updateActiveRow(selectedWindow);
      return;
    }
    this.lastPayload = payload;
    this.rendered = true;

    const alarms = payload.alarms || [];
    const leadSummary = payload.lead_time_summary;
    const stages = payload.stages || [];
    const threshold = Number(payload.threshold) || 0;
    const policy = payload.threshold_policy || "";
    const isDevOnly = Boolean(payload.dev_only);

    // 1. Lead-Time Summary Banner & Verdict
    let verdictBannerHtml = "";
    let summaryStatsHtml = "";
    let episodesTableHtml = "";
    const horizonK = payload.horizon_k || 10;
    const windowSec = payload.window_seconds || 30;
    const horizonDurationStr = formatDuration(horizonK * windowSec);

    if (leadSummary) {
      const episodes = leadSummary.episodes || 0;
      const warnedEarly = leadSummary.warned_early || 0;
      const meanSeconds = leadSummary.mean_lead_seconds || 0;

      if (isDevOnly) {
        verdictBannerHtml = `
          <div class="verdict-banner verdict-dev">
            <span class="status-dot dot-dev"></span>
            <div>
              <strong>UI DEVELOPMENT FIXTURE ONLY:</strong> Hand-picked threshold (${formatFloat(threshold, 4)}) — 
              ${warnedEarly} of ${episodes} episodes warned early. This fixture exists only for visual verification of early-warning UI states and is <em>not</em> a model result (D-021).
            </div>
          </div>
        `;
      } else if (warnedEarly === 0) {
        verdictBannerHtml = `
          <div class="verdict-banner verdict-honest">
            <span class="status-dot dot-warn"></span>
            <div>
              <strong>HONEST CURRENT OUTCOME:</strong> 0 of ${episodes} episodes warned early at the deployable threshold
              (${explainThresholdPolicy(threshold, policy)}). System operating in detection mode (E18).
            </div>
          </div>
        `;
      } else if (leadSummary.beats_null === false) {
        // D-022: an early-warning count that an unaligned alarm series of the same shape matches is
        // chance, not a result - say so instead of "verified".
        verdictBannerHtml = `
          <div class="verdict-banner verdict-honest">
            <span class="status-dot dot-warn"></span>
            <div>
              <strong>NOT DISTINGUISHABLE FROM CHANCE:</strong> ${warnedEarly} of ${episodes} episodes had an alarm before onset,
              but the same alarms shifted to random times do this often (chance level ${leadSummary.null_mean} of ${episodes}, p = ${leadSummary.p_value}).
              Detection, not early warning (D-022, E18).
            </div>
          </div>
        `;
      } else {
        verdictBannerHtml = `
          <div class="verdict-banner verdict-early">
            <span class="status-dot dot-success"></span>
            <div>
              <strong>EARLY WARNING VERIFIED:</strong> ${warnedEarly} of ${episodes} episodes warned early 
              (Mean lead: ${formatDuration(meanSeconds)} before compromise onset).
            </div>
          </div>
        `;
      }

      // Metric Counter Grid with clear contextual labels
      summaryStatsHtml = `
        <div class="alarm-stat-grid">
          <div class="alarm-stat-card">
            <div class="alarm-stat-num">${episodes}</div>
            <div class="alarm-stat-label">Total Episodes</div>
          </div>
          <div class="alarm-stat-card">
            <div class="alarm-stat-num" style="color:${warnedEarly > 0 ? 'var(--accent)' : 'var(--warning)'}">
              ${warnedEarly} / ${episodes}
            </div>
            <div class="alarm-stat-label">Warned Early</div>
          </div>
          <div class="alarm-stat-card">
            <div class="alarm-stat-num font-mono">${formatDuration(meanSeconds)}</div>
            <div class="alarm-stat-label">Mean Lead Time</div>
          </div>
          <div class="alarm-stat-card">
            <div class="alarm-stat-num">${alarms.length}</div>
            <div class="alarm-stat-label">Alarm Runs (${formatFloat(threshold, 4)})</div>
          </div>
        </div>
      `;

      // Episode-level Breakdown Table with full context
      const episodeRows = (leadSummary.per_episode || [])
        .map((ep, idx) => {
          let statusBadge = "";
          let leadStr = "--";

          if (ep.detected_early) {
            statusBadge = `<span class="alarm-badge badge-early">WARNED EARLY (+${ep.lead_windows}w)</span>`;
            leadStr = `<strong>${ep.lead_windows} windows</strong> (${Math.round(ep.lead_seconds)}s)`;
          } else if (ep.first_alarm !== null && ep.first_alarm !== undefined) {
            statusBadge = `<span class="alarm-badge badge-onset">ONSET DETECTION</span>`;
            leadStr = "0s (At onset)";
          } else {
            statusBadge = `<span class="alarm-badge badge-noop">NO EARLY ALARM</span>`;
            leadStr = "0s (Missed lead)";
          }

          const onsetTimeStr = ep.onset_ts ? formatIsoTime(ep.onset_ts) : `t=${ep.onset}`;
          const firstAlarmStr = ep.first_alarm_ts
            ? `${formatIsoTime(ep.first_alarm_ts)} (t=${ep.first_alarm})`
            : "<span style='color:var(--text-dim)'>None</span>";

          const scoreOnsetVal = ep.score_at_onset !== undefined ? Number(ep.score_at_onset) : null;
          // the causal threshold in force at the onset window (D-034), else the payload scalar
          const onsetEntry = (payload.timeline || [])[ep.onset];
          const onsetThr = onsetEntry && onsetEntry.threshold !== undefined
            ? (onsetEntry.threshold === null ? Infinity : Number(onsetEntry.threshold))
            : threshold;
          const scoreOnsetStr = scoreOnsetVal !== null
            ? `${formatFloat(scoreOnsetVal, 4)} ${scoreOnsetVal >= onsetThr ? '▲' : '< thr'}`
            : "--";

          return `
            <tr>
              <td class="font-mono">#${idx + 1}</td>
              <td class="font-mono">t=${ep.onset} (${onsetTimeStr})</td>
              <td class="font-mono" title="Threshold at onset: ${Number.isFinite(onsetThr) ? formatFloat(onsetThr, 4) : "warming up"}">${scoreOnsetStr}</td>
              <td class="font-mono">${firstAlarmStr}</td>
              <td class="font-mono">${leadStr}</td>
              <td>${statusBadge}</td>
            </tr>
          `;
        })
        .join("");

      episodesTableHtml = `
        <div class="alarm-section">
          <div class="alarm-sub-title">
            <span>Ground-Truth Compromise Episodes Evaluation</span>
            <span style="font-size:10px; color:var(--text-dim); text-transform:none;">Horizon K=${horizonK} windows (${horizonDurationStr})</span>
          </div>
          <div class="alarm-table-wrapper" style="max-height: 130px;">
            <table class="alarm-table">
              <thead>
                <tr>
                  <th>Ep</th>
                  <th>Onset Time</th>
                  <th>Score at Onset vs Threshold then</th>
                  <th>First Alarm</th>
                  <th>Lead Time</th>
                  <th>Per-Episode Outcome</th>
                </tr>
              </thead>
              <tbody>
                ${episodeRows || "<tr><td colspan='6' style='text-align:center;'>No episodes recorded</td></tr>"}
              </tbody>
            </table>
          </div>
        </div>
      `;
    } else {
      verdictBannerHtml = `
        <div class="verdict-banner verdict-honest">
          <span class="status-dot dot-warn"></span>
          <div>
            <strong>UNLABELLED CAPTURE:</strong> Ground-truth compromise annotations are not present. 
            Alarms evaluate strictly against threshold (${formatFloat(threshold, 4)} · ${explainThresholdPolicy(threshold, policy)}).
          </div>
        </div>
      `;
    }

    // 2. Alarm Runs Table (alarms[])
    const alarmRowsHtml = alarms
      .map((a, idx) => {
        const isSelected = selectedWindow >= a.t && selectedWindow <= a.until_t;
        const activeClass = isSelected ? "alarm-row-active" : "";

        // Predicted stage lookup
        const w = payload.timeline?.[a.t];
        const predStage = w ? stages.find((s) => s.id === w.pred_stage) : null;
        const predStageLabel = predStage ? predStage.label : "Stage " + (w ? w.pred_stage : "--");
        const predStageColor = predStage?.color || "var(--text)";

        // State 1, State 2, or State 3 determination as strictly specified
        let stateVerdictHtml = "";
        if (a.lead_windows !== null && a.lead_windows !== undefined && a.lead_windows > 0) {
          // STATE 1: lead_windows is present and > 0
          const leadSec = a.lead_seconds != null ? Math.round(a.lead_seconds) : a.lead_windows * windowSec;
          stateVerdictHtml = `
            <span class="alarm-badge badge-early" title="Fired before ground-truth onset t=${a.onset_t}">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
              Fired ${a.lead_windows} windows (${leadSec} seconds) before onset
            </span>
          `;
        } else if (a.onset_t !== null && a.onset_t !== undefined) {
          // STATE 2: onset_t is known but lead_windows is null or 0
          stateVerdictHtml = `
            <span class="alarm-badge badge-onset" title="Alarm fired at onset window t=${a.onset_t}">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="8" x2="12" y2="12"></line>
              </svg>
              Fired at onset - detection, not forecast
            </span>
          `;
        } else {
          // STATE 3: no future onset associated with the alarm
          stateVerdictHtml = `
            <span class="alarm-badge badge-noop" title="No compromise onset followed within K=${horizonK} windows">
              <span class="status-dot" style="background:var(--text-dim)"></span>
              No compromise followed within the horizon
            </span>
          `;
        }

        const windowRangeStr = a.t === a.until_t ? `t=${a.t}` : `t=${a.t}..${a.until_t}`;
        const timeStr = a.ts ? formatIsoTime(a.ts) : "--";
        // the causal threshold moves, so compare against the one in force when the run began
        const runThreshold = a.threshold !== undefined && a.threshold !== null ? Number(a.threshold) : threshold;
        const deltaThreshold = a.p - runThreshold;
        const deltaStr = deltaThreshold >= 0 ? `+${formatFloat(deltaThreshold, 4)}` : formatFloat(deltaThreshold, 4);
        const peakPStr = `${formatFloat(a.p, 4)} (${formatPercent(a.p, 1)})`;

        return `
          <tr class="alarm-row ${activeClass}" data-window="${a.t}" data-until="${a.until_t}" title="Click to inspect window t=${a.t} on timeline">
            <td class="font-mono">#${idx + 1}</td>
            <td class="font-mono">${windowRangeStr} (${timeStr})</td>
            <td class="font-mono" style="color:var(--danger); font-weight:600;" title="Threshold: ${formatFloat(runThreshold, 4)} (Delta: ${deltaStr})">
              ${peakPStr} <span style="font-size:9px; color:var(--text-dim); font-weight:normal;">[${deltaStr}]</span>
            </td>
            <td>
              <span class="stage-chip-dot" style="background:${predStageColor}; display:inline-block; vertical-align:middle; margin-right:4px;"></span>
              <span style="color:${predStageColor}">${predStageLabel}</span>
            </td>
            <td>${stateVerdictHtml}</td>
          </tr>
        `;
      })
      .join("");

    this.container.innerHTML = `
      <div class="alarm-panel-content">
        ${verdictBannerHtml}
        ${summaryStatsHtml}
        ${episodesTableHtml}

        <div class="alarm-section">
          <div class="alarm-sub-title">
            <span>Detected Alarm Runs (Threshold: ${formatFloat(threshold, 4)} · ${explainThresholdPolicy(threshold, policy)})</span>
            <span style="font-size:10px; color:var(--text-dim); text-transform:none;">Click row to inspect window</span>
          </div>
          <div class="alarm-table-wrapper" style="max-height: 160px;">
            <table class="alarm-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Window (Time)</th>
                  <th title="Ranked against this capture's alert budget, not a calibrated probability (E17)">Peak Risk (p_max) vs Thr</th>
                  <th>Predicted Stage</th>
                  <th>Forecast Lead-Time Verdict</th>
                </tr>
              </thead>
              <tbody>
                ${alarmRowsHtml || "<tr><td colspan='5' style='text-align:center; padding:16px; color:var(--text-dim);'>No alarms fired at current threshold</td></tr>"}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;

    // Bind row click handlers to update selectedWindow
    const rows = this.container.querySelectorAll(".alarm-row");
    rows.forEach((row) => {
      row.addEventListener("click", () => {
        const wIdx = parseInt(row.getAttribute("data-window"), 10);
        if (!isNaN(wIdx)) {
          store.set({ selectedWindow: wIdx });
        }
      });
    });

    // Auto-scroll active row into view if present
    const activeRow = this.container.querySelector(".alarm-row-active");
    if (activeRow) {
      activeRow.scrollIntoView({ block: "nearest" });
    }
  }

  /**
   * Fast in-place row update without rebuilding DOM
   */
  _updateActiveRow(selectedWindow) {
    if (!this.container) return;
    const rows = this.container.querySelectorAll(".alarm-row");
    let activeRow = null;
    rows.forEach((row) => {
      const startT = parseInt(row.getAttribute("data-window"), 10);
      const untilT = parseInt(row.getAttribute("data-until") || row.getAttribute("data-window"), 10);
      if (selectedWindow >= startT && selectedWindow <= untilT) {
        row.classList.add("alarm-row-active");
        activeRow = row;
      } else {
        row.classList.remove("alarm-row-active");
      }
    });

    if (activeRow) {
      activeRow.scrollIntoView({ block: "nearest" });
    }
  }
}
