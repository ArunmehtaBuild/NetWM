/**
 * NetWM Kill-Chain Ribbon & Current Stage Card (H-3)
 *
 * Implements:
 * 1. Kill-chain ribbon canvas: one segment per window colored by pred_stage
 * 2. Secondary ground-truth strip for observed_stage (when present)
 * 3. Dynamic stage chips legend generated from payload.stages[]
 * 4. Current-stage assessment card:
 *    - Stage label & stage ID
 *    - ATT&CK tactic ID (e.g. TA0008)
 *    - Ground truth comparison & calibration confidence
 *    - Full stage probability distribution bar list
 * 5. Interactive clicking/scrubbing to select windows
 * 6. Graceful handling of missing ground truth or stages
 *
 * See frontend/PLAN.md
 */

import { store } from "../store.js";
import { formatPercent, formatFloat, formatIsoTime, hexToRgba } from "../format.js";

export class RibbonPanel {
  constructor(ribbonContainerId, stageCardContainerId) {
    this.ribbonContainer = document.getElementById(ribbonContainerId);
    this.stageCardContainer = document.getElementById(stageCardContainerId);

    this.canvas = null;
    this.isDragging = false;
    this.lastRenderedPayload = null;

    this._setupDOM();
  }

  _setupDOM() {
    if (this.ribbonContainer) {
      this.ribbonContainer.innerHTML = `
        <div class="ribbon-wrapper">
          <div class="ribbon-legend" id="ribbonLegend"></div>
          <div class="ribbon-canvas-box">
            <div class="ribbon-axis-labels">
              <span class="ribbon-axis-label">PREDICTED STAGE</span>
              <span class="ribbon-axis-label ribbon-axis-obs" id="obsAxisLabel">GROUND TRUTH</span>
            </div>
            <div class="ribbon-canvas-wrapper">
              <canvas id="ribbonCanvas" height="32"></canvas>
              <div class="ribbon-tooltip hidden" id="ribbonTooltip"></div>
            </div>
          </div>
          <div class="ribbon-footer-meta">
            <span>Window t=0</span>
            <span id="ribbonWindowRange">972 windows</span>
            <span id="ribbonEndWindow">Window t=--</span>
          </div>
        </div>
      `;

      this.canvas = document.getElementById("ribbonCanvas");
      this.tooltip = document.getElementById("ribbonTooltip");
      this.legendEl = document.getElementById("ribbonLegend");
      this.obsLabelEl = document.getElementById("obsAxisLabel");

      if (this.canvas) {
        this._bindCanvasEvents();
      }
    }
  }

  _bindCanvasEvents() {
    const handleMouse = (e) => {
      const state = store.getState();
      const payload = state.payload;
      if (!payload || !payload.timeline || !payload.timeline.length) return;

      const rect = this.canvas.getBoundingClientRect();
      const mouseX = Math.max(0, Math.min(rect.width - 1, e.clientX - rect.left));
      const t = Math.floor((mouseX / rect.width) * payload.timeline.length);

      // Tooltip positioning
      if (this.tooltip) {
        const w = payload.timeline[t];
        const stages = payload.stages || [];
        const predStage = stages.find((s) => s.id === w.pred_stage);
        const obsStage = stages.find((s) => s.id === w.observed_stage);

        const obsText = w.observed_stage !== undefined
          ? `<br><span style="color:var(--text-dim)">Observed:</span> ${obsStage ? obsStage.label : "Stage " + w.observed_stage}`
          : "";

        this.tooltip.innerHTML = `
          <strong>Window t=${w.t}</strong> (${formatIsoTime(w.ts)})<br>
          <span style="color:var(--text-dim)">Predicted:</span> <span style="color:${predStage?.color || 'var(--text)'}; font-weight:600;">${predStage?.label || "Unknown"}</span>${obsText}
        `;

        this.tooltip.classList.remove("hidden");
        const tooltipX = Math.max(10, Math.min(rect.width - 150, mouseX - 70));
        this.tooltip.style.left = `${tooltipX}px`;
      }

      if (this.isDragging || e.type === "click") {
        store.set({ selectedWindow: t });
      }
    };

    this.canvas.addEventListener("mousedown", (e) => {
      this.isDragging = true;
      handleMouse(e);
    });

    window.addEventListener("mouseup", () => {
      this.isDragging = false;
    });

    this.canvas.addEventListener("mousemove", (e) => {
      handleMouse(e);
    });

    this.canvas.addEventListener("mouseleave", () => {
      if (this.tooltip) this.tooltip.classList.add("hidden");
    });

    this.canvas.addEventListener("click", (e) => {
      handleMouse(e);
    });
  }

  /**
   * Main render function called on store updates
   */
  render(state) {
    const { payload, selectedWindow } = state;
    if (!payload || !payload.timeline) return;

    this._renderRibbonCanvas(payload, selectedWindow);
    if (this.lastPayload !== payload) {
      this._renderLegend(payload.stages);
      this.lastPayload = payload;
    }
    this._renderStageCard(payload, selectedWindow);
  }

  /**
   * Render the dual-strip Canvas (Predicted Stage + Observed Stage)
   */
  _renderRibbonCanvas(payload, selectedWindow) {
    if (!this.canvas) return;

    const timeline = payload.timeline;
    const stages = payload.stages || [];
    const N = timeline.length;
    if (N === 0) return;

    // Build stage color map dynamically from payload.stages
    const colorMap = new Map();
    stages.forEach((s) => colorMap.set(s.id, s.color));

    // Handle high DPI
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    if (rect.width === 0) return;

    this.canvas.width = rect.width * dpr;
    this.canvas.height = 32 * dpr;

    const ctx = this.canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    const hasObserved = timeline.some((w) => w.observed_stage !== undefined);
    if (this.obsLabelEl) {
      this.obsLabelEl.style.display = hasObserved ? "block" : "none";
    }

    const predHeight = hasObserved ? 20 : 28;
    const obsHeight = hasObserved ? 8 : 0;
    const obsY = 22;

    // Draw window segments
    for (let t = 0; t < N; t++) {
      const w = timeline[t];
      const x = (t / N) * rect.width;
      const cellWidth = Math.max(1, ((t + 1) / N) * rect.width - x);

      // 1. Predicted Stage Cell (Top Strip)
      const predColor = colorMap.get(w.pred_stage) || "#9aa7b1";
      ctx.fillStyle = predColor;
      ctx.fillRect(x, 0, cellWidth, predHeight);

      // 2. Observed Stage Cell (Bottom Strip)
      if (hasObserved && w.observed_stage !== undefined) {
        const obsColor = colorMap.get(w.observed_stage) || "#9aa7b1";
        ctx.fillStyle = obsColor;
        ctx.fillRect(x, obsY, cellWidth, obsHeight);
      }
    }

    // Divider line between predicted and observed
    if (hasObserved) {
      ctx.fillStyle = "#0f1216";
      ctx.fillRect(0, predHeight, rect.width, 2);
    }

    // Active Cursor Highlight for selectedWindow
    if (selectedWindow >= 0 && selectedWindow < N) {
      const xSel = (selectedWindow / N) * rect.width;
      const wSel = Math.max(4, rect.width / N + 2);

      ctx.save();
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.strokeRect(xSel - 1, 0, wSel, hasObserved ? 30 : 28);

      // Top indicator arrow / marker
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.moveTo(xSel + wSel / 2 - 3, 0);
      ctx.lineTo(xSel + wSel / 2 + 3, 0);
      ctx.lineTo(xSel + wSel / 2, 4);
      ctx.fill();
      ctx.restore();
    }

    // Update range labels
    const rangeEl = document.getElementById("ribbonWindowRange");
    if (rangeEl) rangeEl.textContent = `${N} continuous windows`;
    const endEl = document.getElementById("ribbonEndWindow");
    if (endEl) endEl.textContent = `Window t=${N - 1}`;
  }

  /**
   * Render the stage chips legend dynamically from payload.stages
   */
  _renderLegend(stages) {
    if (!this.legendEl || !stages) return;

    this.legendEl.innerHTML = stages
      .map((s) => {
        const tacticBadge = s.tactic ? `<span class="tactic-mini">${s.tactic}</span>` : "";
        return `
          <div class="stage-chip" title="Stage ${s.id}: ${s.label} (${s.tactic || 'Benign'})">
            <span class="stage-chip-dot" style="background:${s.color}"></span>
            <span class="stage-chip-label">${s.label}</span>
            ${tacticBadge}
          </div>
        `;
      })
      .join("");
  }

  /**
   * Render the Current Stage Assessment Card
   */
  _renderStageCard(payload, selectedWindow) {
    if (!this.stageCardContainer) return;

    const timeline = payload.timeline;
    const stages = payload.stages || [];
    const w = timeline[selectedWindow] || timeline[0];
    if (!w) return;

    const curStage = stages.find((s) => s.id === w.pred_stage) || {
      id: w.pred_stage,
      label: `Stage ${w.pred_stage}`,
      color: "#9aa7b1",
      tactic: "",
    };

    const hasObserved = w.observed_stage !== undefined;
    const obsStage = hasObserved ? stages.find((s) => s.id === w.observed_stage) : null;
    const isMatch = hasObserved && w.pred_stage === w.observed_stage;

    // Ground Truth status pill
    let groundTruthHtml = "";
    if (hasObserved) {
      const matchBadge = isMatch
        ? `<span class="badge-match">MATCH</span>`
        : `<span class="badge-mismatch">MISMATCH (Observed: ${obsStage ? obsStage.label : w.observed_stage})</span>`;
      
      const confStr = w.observed_stage_conf !== undefined
        ? ` · Calibration Conf: <strong>${formatPercent(w.observed_stage_conf, 1)}</strong>`
        : "";

      groundTruthHtml = `
        <div class="stage-obs-row">
          <span class="meta-label">Ground Truth:</span>
          <span style="color:${obsStage?.color || 'var(--text)'}; font-weight:600;">
            ${obsStage ? obsStage.label : "Stage " + w.observed_stage}
          </span>
          ${matchBadge}
          ${confStr}
        </div>
      `;
    } else {
      groundTruthHtml = `
        <div class="stage-obs-row">
          <span class="meta-label">Ground Truth:</span>
          <span style="color:var(--text-dim)">Unlabelled traffic capture (live stream)</span>
        </div>
      `;
    }

    // Stage Probabilities List
    const probs = w.stage_probs || [];
    const probRowsHtml = stages
      .map((s) => {
        const prob = probs[s.id] !== undefined ? Number(probs[s.id]) : 0;
        const isPredicted = s.id === w.pred_stage;
        const isObserved = hasObserved && s.id === w.observed_stage;

        let rowHighlight = isPredicted ? "stage-prob-row-selected" : "";
        let tags = "";
        if (isPredicted) tags += `<span class="tag-pred">PREDICTED</span>`;
        if (isObserved) tags += `<span class="tag-obs">ACTUAL</span>`;

        return `
          <div class="stage-prob-row ${rowHighlight}">
            <div class="stage-prob-info">
              <span class="stage-chip-dot" style="background:${s.color}"></span>
              <span class="stage-prob-name">${s.label}</span>
              ${s.tactic ? `<span class="tactic-mini">${s.tactic}</span>` : ""}
              ${tags}
            </div>
            <div class="stage-prob-bar-container">
              <div class="stage-prob-bar-fill" style="width: ${Math.max(1, prob * 100)}%; background: ${s.color};"></div>
            </div>
            <div class="stage-prob-val font-mono">${formatPercent(prob, 1)}</div>
          </div>
        `;
      })
      .join("");

    this.stageCardContainer.innerHTML = `
      <div class="stage-card">
        <div class="stage-card-header">
          <div class="stage-main-badge" style="border-color:${curStage.color}; background:${hexToRgba(curStage.color, 0.12)}">
            <span class="stage-chip-dot" style="background:${curStage.color}; width:10px; height:10px;"></span>
            <span class="stage-name-lg" style="color:${curStage.color}">${curStage.label}</span>
            <span class="stage-id-pill">Stage ${curStage.id}</span>
            ${curStage.tactic ? `<span class="tactic-badge" title="MITRE ATT&CK Tactic">${curStage.tactic}</span>` : ""}
          </div>
          <div class="stage-window-coord font-mono">
            Window <strong>t=${w.t}</strong> (${formatIsoTime(w.ts)})
          </div>
        </div>

        ${groundTruthHtml}

        <div class="stage-probs-section" title="Ranked against this capture's alert budget, not a calibrated probability (E17)">
          <div class="section-subtitle">MITRE ATT&CK Stage Score Distribution</div>
          <div class="stage-probs-list">
            ${probRowsHtml}
          </div>
        </div>

        <div class="stage-card-footer font-mono">
          <span>Surprise Score: <strong>${formatFloat(w.surprise, 2)}</strong></span>
          <span>Window Flows: <strong>${w.flow_count ? Number(w.flow_count).toLocaleString() : '--'}</strong></span>
        </div>
      </div>
    `;
  }
}
