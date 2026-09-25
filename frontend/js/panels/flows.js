/**
 * NetWM Telemetry Flows & Top Talkers Panel (H-5)
 *
 * Implements:
 * 1. PART 4: Top Talkers for selected window (IP, flows, bytes_out)
 * 2. PART 5: Flagged Telemetry Flows table:
 *    - Integrated behind api.getFlows()
 *    - Stage and minScore filtering driven strictly by store.state.filters
 *    - Performant capped rendering (max 50 rows)
 *    - Handled states: loading, empty (filtered or no flows), error with retry
 *
 * See frontend/PLAN.md & docs/api_contract.md
 */

import { api } from "../api.js";
import { store } from "../store.js";
import {
  formatInt,
  formatFloat,
  formatBytes,
  formatIsoTime,
} from "../format.js";

export class FlowsPanel {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.currentWindow = null;
    this.cachedFlows = null;
    this.currentPayload = null;
    this.isLoading = false;
    this.error = null;
  }

  /**
   * Render Flows & Talkers panel given store state
   */
  async render(state) {
    if (!this.container) return;

    const { payload, selectedWindow, filters } = state;
    if (!payload || !payload.timeline || !payload.timeline[selectedWindow]) {
      this.container.innerHTML = `
        <div class="panel-placeholder">
          <div class="placeholder-title">No window selected</div>
        </div>
      `;
      return;
    }

    const w = payload.timeline[selectedWindow];
    const stages = payload.stages || [];
    const threshold = Number(payload.threshold) || 0.05;

    // Check if we need to fetch flows for a newly selected window
    // Key the cache on the payload too: switching scenario at the same window index must
    // refetch, or the new capture shows the previous capture's flows.
    if (this.currentWindow !== selectedWindow || this.currentPayload !== payload || !this.cachedFlows) {
      this.currentWindow = selectedWindow;
      this.currentPayload = payload;
      this.isLoading = true;
      this.error = null;

      // Render top talkers immediately, and loading state for table
      this._renderSkeleton(w, stages, filters, threshold);

      try {
        const fetchWindow = selectedWindow;
        const jobId = api.liveJobId(state);
        const flowData = await api.getFlows(jobId, selectedWindow, payload);
        if (this.currentWindow !== fetchWindow || this.currentPayload !== payload) return; // Stale fetch
        this.cachedFlows = flowData?.flows || [];
        this.isLoading = false;
      } catch (err) {
        if (this.currentWindow !== selectedWindow) return;
        console.error("Error fetching flows:", err);
        this.error = err.message || "Failed to load telemetry flows";
        this.isLoading = false;
      }
    }

    // Render full content with loaded flows
    this._renderFull(w, stages, filters, threshold);
  }

  /**
   * Render skeleton while flows are in flight
   */
  _renderSkeleton(w, stages, filters, threshold) {
    const talkersHtml = this._renderTopTalkers(w);
    const filterBarHtml = this._renderFilterBar(stages, filters);

    this.container.innerHTML = `
      <div class="flows-panel-content">
        <!-- Part 4: Top Talkers -->
        ${talkersHtml}

        <!-- Part 5: Flagged Flows Section -->
        <div class="flows-section">
          ${filterBarHtml}
          <div class="flow-loading-box">
            <div class="spinner-sm"></div>
            <span>Fetching telemetry NetFlows for window t=${w.t}...</span>
          </div>
        </div>
      </div>
    `;
    this._bindFilterEvents();
  }

  /**
   * Render complete panel once flows are available
   */
  _renderFull(w, stages, filters, threshold) {
    const talkersHtml = this._renderTopTalkers(w);
    const filterBarHtml = this._renderFilterBar(stages, filters);
    const tableHtml = this._renderFlowsTable(stages, filters, threshold, w);

    this.container.innerHTML = `
      <div class="flows-panel-content">
        <!-- Part 4: Top Talkers -->
        ${talkersHtml}

        <!-- Part 5: Flagged Flows Section -->
        <div class="flows-section">
          ${filterBarHtml}
          ${tableHtml}
        </div>
      </div>
    `;

    this._bindFilterEvents();
  }

  /**
   * Part 4: Top Talkers
   */
  _renderTopTalkers(w) {
    const talkers = w.top_talkers;
    const totalFlows = w.flow_count || 0;

    let talkersCardsHtml = "";
    if (!talkers || !Array.isArray(talkers) || talkers.length === 0) {
      talkersCardsHtml = `
        <div class="talkers-empty">No top talkers recorded for window t=${w.t}</div>
      `;
    } else {
      talkersCardsHtml = talkers
        .map((talker, idx) => {
          const flowCount = Number(talker.flows) || 0;
          const bytesOut = Number(talker.bytes_out) || 0;
          const pct = totalFlows > 0 ? Math.round((flowCount / totalFlows) * 100) : 0;

          return `
            <div class="talker-card">
              <div class="talker-card-header">
                <span class="talker-rank font-mono">#${idx + 1}</span>
                <span class="talker-ip font-mono" title="Source IP">${talker.ip || "unknown"}</span>
              </div>
              <div class="talker-stats">
                <div class="talker-stat-item">
                  <span class="talker-stat-num font-mono">${formatInt(flowCount)}</span>
                  <span class="talker-stat-lbl">Flows (${pct}%)</span>
                </div>
                <div class="talker-stat-item">
                  <span class="talker-stat-num font-mono">${formatBytes(bytesOut)}</span>
                  <span class="talker-stat-lbl">Bytes Out</span>
                </div>
              </div>
            </div>
          `;
        })
        .join("");
    }

    return `
      <div class="talkers-container">
        <div class="talkers-header">
          <span class="section-subtitle">Top Talkers (Window t=${w.t})</span>
          <span class="talkers-total-pill font-mono">${formatInt(totalFlows)} Total Window Flows</span>
        </div>
        <div class="talkers-grid">
          ${talkersCardsHtml}
        </div>
      </div>
    `;
  }

  /**
   * Part 5: Filter controls bar
   */
  _renderFilterBar(stages, filters) {
    const currentStage = filters.stage !== undefined && filters.stage !== null ? String(filters.stage) : "";
    const currentMinScore = filters.minScore !== undefined ? String(filters.minScore) : "0";

    const stageOptions = stages
      .map((s) => {
        const selected = currentStage === String(s.id) ? "selected" : "";
        const tacticStr = s.tactic ? ` (${s.tactic})` : "";
        return `<option value="${s.id}" ${selected}>${s.label}${tacticStr}</option>`;
      })
      .join("");

    return `
      <div class="flow-filter-bar">
        <div class="flow-filter-group">
          <label for="flowStageSelect">Stage Filter:</label>
          <select id="flowStageSelect" class="filter-select">
            <option value="" ${currentStage === "" ? "selected" : ""}>All Stages</option>
            ${stageOptions}
          </select>
        </div>

        <div class="flow-filter-group">
          <label for="flowMinScoreSelect">Min Anomaly Score:</label>
          <select id="flowMinScoreSelect" class="filter-select">
            <option value="0" ${currentMinScore === "0" ? "selected" : ""}>All Scores (&ge; 0.0)</option>
            <option value="0.2" ${currentMinScore === "0.2" ? "selected" : ""}>Score &ge; 0.20</option>
            <option value="0.5" ${currentMinScore === "0.5" ? "selected" : ""}>Score &ge; 0.50 (Elevated)</option>
            <option value="0.8" ${currentMinScore === "0.8" ? "selected" : ""}>Score &ge; 0.80 (Critical)</option>
          </select>
        </div>

        <div class="flow-filter-summary font-mono" id="flowCountSummary">
          Filtering active
        </div>
      </div>
    `;
  }

  /**
   * Part 5: Render flows table or empty / error state
   */
  _renderFlowsTable(stages, filters, threshold, w) {
    if (this.error) {
      return `
        <div class="flows-error-box">
          <div style="color:var(--danger); font-weight:600;">Error Loading Flows</div>
          <div style="font-size:11.5px; color:var(--text-muted);">${this.error}</div>
          <button class="btn btn-sm" id="retryFlowsBtn" style="margin-top:6px;">Retry Fetch</button>
        </div>
      `;
    }

    const allFlows = this.cachedFlows || [];
    if (allFlows.length === 0) {
      return `
        <div class="flows-empty-box">
          No telemetry NetFlows recorded for window t=${w.t}.
        </div>
      `;
    }

    // Apply store filters
    const filterStage = filters.stage !== undefined && filters.stage !== null && filters.stage !== ""
      ? parseInt(filters.stage, 10)
      : null;
    const filterMinScore = Number(filters.minScore) || 0;

    const filteredFlows = allFlows.filter((f) => {
      if (filterStage !== null && f.stage_hint !== filterStage) {
        return false;
      }
      if (filterMinScore > 0 && (f.score || 0) < filterMinScore) {
        return false;
      }
      return true;
    });

    if (filteredFlows.length === 0) {
      return `
        <div class="flows-empty-box">
          No flows match the active filter criteria (Stage: ${filterStage !== null ? filterStage : "All"}, Min Score: ${filterMinScore}).
        </div>
      `;
    }

    // Performance optimization: cap rendered rows to 50
    const maxRows = 50;
    const displayFlows = filteredFlows.slice(0, maxRows);

    const rowsHtml = displayFlows
      .map((f, idx) => {
        const timeStr = f.ts ? formatIsoTime(f.ts) : "--";
        const protoStr = f.protocol === 6 ? "TCP" : f.protocol === 17 ? "UDP" : f.protocol === 1 ? "ICMP" : String(f.protocol);

        // Stage hint lookup
        const stageObj = stages.find((s) => s.id === f.stage_hint);
        const stageLabel = stageObj ? stageObj.label : `Stage ${f.stage_hint}`;
        const stageColor = stageObj?.color || "var(--text-dim)";

        // Score coloring
        const scoreVal = Number(f.score) || 0;
        let scoreClass = "score-low";
        if (scoreVal >= threshold || scoreVal >= 0.8) {
          scoreClass = "score-high";
        } else if (scoreVal >= 0.3) {
          scoreClass = "score-mid";
        }

        const flagsBadge = f.flags ? `<span class="flags-badge font-mono">${f.flags}</span>` : `<span style="color:var(--text-dim)">-</span>`;

        return `
          <tr>
            <td class="font-mono" style="color:var(--text-dim);">${idx + 1}</td>
            <td class="font-mono">${timeStr}</td>
            <td class="font-mono" title="${f.src_ip}:${f.src_port}">${f.src_ip}:${f.src_port}</td>
            <td class="font-mono" title="${f.dst_ip}:${f.dst_port}">${f.dst_ip}:${f.dst_port}</td>
            <td class="font-mono">${protoStr}</td>
            <td>${flagsBadge}</td>
            <td class="font-mono">${formatInt(f.pkts)}</td>
            <td class="font-mono">${formatBytes(f.bytes)}</td>
            <td class="font-mono ${scoreClass}" style="font-weight:600;">${formatFloat(scoreVal, 3)}</td>
            <td>
              <span class="stage-chip-dot" style="background:${stageColor}; display:inline-block; vertical-align:middle; margin-right:4px;"></span>
              <span style="color:${stageColor}">${stageLabel}</span>
            </td>
          </tr>
        `;
      })
      .join("");

    return `
      <div class="flows-table-wrapper">
        <table class="flows-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Time</th>
              <th>Source IP:Port</th>
              <th>Dest IP:Port</th>
              <th>Proto</th>
              <th>Flags</th>
              <th>Pkts</th>
              <th>Bytes</th>
              <th>Score</th>
              <th>Stage Hint</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
      <div class="flows-table-footer">
        <span>Showing ${displayFlows.length} of ${filteredFlows.length} matching flows (${allFlows.length} in window t=${w.t})</span>
        <span style="color:var(--text-dim)">Capped at ${maxRows} rows for DOM performance</span>
      </div>
    `;
  }

  /**
   * Bind filter dropdown changes to store
   */
  _bindFilterEvents() {
    const stageSelect = this.container.querySelector("#flowStageSelect");
    if (stageSelect) {
      stageSelect.addEventListener("change", (e) => {
        const val = e.target.value === "" ? null : parseInt(e.target.value, 10);
        store.set({ filters: { stage: val } });
      });
    }

    const minScoreSelect = this.container.querySelector("#flowMinScoreSelect");
    if (minScoreSelect) {
      minScoreSelect.addEventListener("change", (e) => {
        const val = parseFloat(e.target.value) || 0;
        store.set({ filters: { minScore: val } });
      });
    }

    const retryBtn = this.container.querySelector("#retryFlowsBtn");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        this.cachedFlows = null;
        this.render(store.getState());
      });
    }
  }
}
