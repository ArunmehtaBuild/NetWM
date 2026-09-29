/**
 * NetWM Why Panel — Explainability & Attention (H-5)
 *
 * Implements:
 * 1. PART 1: Why This Forecast (Local Attribution)
 *    - timeline[].top_features for selectedWindow
 *    - Signed horizontal attribution bars, values, directions (up/down)
 *    - Explicit empty state when top_features is empty (D-018: ~15% coverage)
 * 2. PART 2: Temporal Attention Heatmap
 *    - timeline[].attention lookback weights over past L context windows
 *    - Relative offsets (t-15..t), intensity styling, and hover/click inspection
 * 3. PART 3: Global Explanation ("What drives this capture overall")
 *    - explanation_global: feature_names and mean_abs_attribution
 *
 * See docs/api_contract.md
 */

import { store } from "../store.js";
import { formatFloat, formatPercent, formatIsoTime, formatDuration } from "../format.js";

export class WhyPanel {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.hoveredAttentionIndex = null;
  }

  /**
   * Render Why Panel given store state
   */
  render(state) {
    if (!this.container) return;

    const { payload, selectedWindow } = state;
    if (!payload || !payload.timeline || !payload.timeline[selectedWindow]) {
      this.container.innerHTML = `
        <div class="panel-placeholder">
          <div class="placeholder-title">No window selected</div>
        </div>
      `;
      return;
    }

    const w = payload.timeline[selectedWindow];
    const threshold = Number(payload.threshold) || 0.05;
    const windowSec = payload.window_seconds || 30;

    // 1. PART 1: Local Feature Attribution (top_features)
    const localAttrHtml = this._renderLocalAttribution(w, threshold);

    // 2. PART 2: Temporal Attention Heatmap (attention)
    const attentionHtml = this._renderAttentionHeatmap(w, payload, selectedWindow, windowSec);

    // 3. PART 3: Global Explanation (explanation_global)
    const globalAttrHtml = this._renderGlobalExplanation(payload);

    this.container.innerHTML = `
      <div class="why-panel-content">
        <!-- Part 1: Local Attribution -->
        <div class="why-section">
          <div class="why-section-header">
            <div>
              <span class="why-section-title" title="Integrated Gradients of the compromise score. On held-out attacks these match the attack's known signature on only 1 of 6 episodes (E11), so read them as what moved this score, not as a diagnosis">Features Pushing the Compromise Score · Window t=${w.t}</span>
              <span class="why-section-sub" title="Ranked against this capture's alert budget, not a calibrated probability (E17)">(${formatIsoTime(w.ts)} · Risk p_max: ${formatPercent(w.p_max)})</span>
            </div>
            <span class="why-section-badge">Local Integrated Gradients</span>
          </div>
          ${localAttrHtml}
        </div>

        <!-- Part 2: Temporal Attention Heatmap -->
        <div class="why-section">
          <div class="why-section-header">
            <div>
              <span class="why-section-title">Temporal Attention Lookback</span>
              <span class="why-section-sub">Which earlier moments the model paid attention to</span>
            </div>
            <span class="why-section-badge">RSSM Attention Weights</span>
          </div>
          ${attentionHtml}
        </div>

        <!-- Part 3: Global Explanation -->
        <div class="why-section">
          <div class="why-section-header">
            <div>
              <span class="why-section-title">What Drives This Capture Overall</span>
              <span class="why-section-sub">Mean absolute attribution across all ${payload.timeline.length} windows</span>
            </div>
            <span class="why-section-badge">Capture Global</span>
          </div>
          ${globalAttrHtml}
        </div>
      </div>
    `;

    // Bind interactive handlers (e.g. clicking past attention window)
    this._bindEvents();
  }

  /**
   * Part 1: Render Local Attribution bars or empty state
   */
  _renderLocalAttribution(w, threshold) {
    const features = w.top_features;

    // Check if window has no explanations (D-018: intentionally computed for ~15% of checkpoint windows)
    if (!features || !Array.isArray(features) || features.length === 0) {
      return `
        <div class="why-empty-card">
          <div class="why-empty-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <div class="why-empty-body">
            <div class="why-empty-title">No attribution computed for this window</div>
            <div class="why-empty-desc">
              Integrated Gradients attribution is computed at key checkpoint windows (~15% of capture, D-018) to preserve real-time inference throughput. Select a checkpoint window (e.g. t=0, 8, 16, 24, 32...) to view driving feature attributions.
            </div>
          </div>
        </div>
      `;
    }

    // Find maximum absolute attribution for scaling bars
    const maxAtt = Math.max(...features.map((f) => Math.abs(Number(f.attribution) || 0)), 0.001);

    const featureRows = features
      .map((f) => {
        const name = f.name || "unknown_feature";
        const val = Number(f.value) || 0;
        const att = Number(f.attribution) || 0;
        const dir = (f.direction || (att >= 0 ? "up" : "down")).toLowerCase();
        const isPos = att >= 0 || dir === "up";

        const barPct = Math.min(100, Math.max(4, (Math.abs(att) / maxAtt) * 100));
        const signStr = att >= 0 ? "+" : "";
        const attFormatted = `${signStr}${formatFloat(att, 4)}`;

        const dirBadge = isPos
          ? `<span class="dir-badge dir-up" title="Pushes risk higher (hostile contribution)">▲ Risk Up</span>`
          : `<span class="dir-badge dir-down" title="Pushes risk lower (benign contribution)">▼ Risk Down</span>`;

        return `
          <div class="attr-row">
            <div class="attr-header">
              <div class="attr-name-box">
                <span class="attr-name font-mono">${name}</span>
                <span class="attr-val font-mono">val: ${formatFloat(val, 2)}</span>
              </div>
              <div class="attr-meta">
                ${dirBadge}
                <span class="attr-signed font-mono ${isPos ? 'attr-pos-text' : 'attr-neg-text'}">${attFormatted}</span>
              </div>
            </div>
            <div class="attr-bar-container">
              <div class="attr-bar-track">
                <div class="attr-bar-fill ${isPos ? 'attr-bar-pos' : 'attr-bar-neg'}" style="width: ${barPct}%;"></div>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    return `
      <div class="attr-list">
        ${featureRows}
      </div>
    `;
  }

  /**
   * Part 2: Render Temporal Attention Heatmap
   */
  _renderAttentionHeatmap(w, payload, selectedWindow, windowSec) {
    const attention = w.attention;

    if (!attention || !Array.isArray(attention) || attention.length === 0) {
      return `
        <div class="why-empty-card">
          <div class="why-empty-body">
            <div class="why-empty-title">No attention weights recorded for this window</div>
          </div>
        </div>
      `;
    }

    const L = attention.length;
    const maxWeight = Math.max(...attention, 0.001);

    // Generate cells from past to present
    const cellsHtml = attention
      .map((weight, idx) => {
        const offset = L - 1 - idx;
        const pastWindow = Math.max(0, selectedWindow - offset);
        const isCurrent = offset === 0;
        const normWeight = Math.min(1, Math.max(0, weight / maxWeight));
        const pctFormatted = formatPercent(weight, 1);
        const weightFormatted = formatFloat(weight, 4);

        // Color interpolation based on attention strength
        // Low: dark surface -> Mid: accent cyan/blue -> High: intense amber/bright
        let cellBg = "var(--surface-2)";
        let barColor = "var(--accent)";
        if (weight > 0.3) {
          barColor = "var(--warning)";
        }
        if (weight > 0.6) {
          barColor = "var(--danger)";
        }

        const heightPct = Math.max(8, normWeight * 100);

        const offsetLabel = isCurrent ? "t" : `t-${offset}`;
        const timeAgo = isCurrent ? "Current" : `-${formatDuration(offset * windowSec)}`;

        return `
          <div class="att-cell ${isCurrent ? 'att-cell-current' : ''}" 
               data-window="${pastWindow}" 
               data-offset="${offset}"
               data-weight="${weightFormatted}"
               data-pct="${pctFormatted}"
               data-timeago="${timeAgo}"
               title="Window t=${pastWindow} (${timeAgo}) · Attention: ${weightFormatted} (${pctFormatted}) · Click to select">
            <div class="att-cell-bar" style="height: ${heightPct}%; background: ${barColor};"></div>
            <div class="att-cell-label font-mono">${offsetLabel}</div>
          </div>
        `;
      })
      .join("");

    const contextDuration = formatDuration((L - 1) * windowSec);

    return `
      <div class="att-heatmap-wrapper">
        <div class="att-cells-box">
          ${cellsHtml}
        </div>
        <div class="att-axis-meta">
          <span>Past Context (t-${L - 1} · -${contextDuration})</span>
          <span id="attHoverDetail" style="color:var(--accent); font-family:var(--font-mono); font-size:10.5px;">Hover cells to inspect attention weight</span>
          <span style="font-weight:600; color:var(--text);">Current Window (t=${selectedWindow})</span>
        </div>
      </div>
    `;
  }

  /**
   * Part 3: Render Global Capture Attribution
   */
  _renderGlobalExplanation(payload) {
    const globalExp = payload.explanation_global;

    if (!globalExp || !Array.isArray(globalExp.feature_names) || !Array.isArray(globalExp.mean_abs_attribution)) {
      return `
        <div class="why-empty-card">
          <div class="why-empty-body">
            <div class="why-empty-title">Global explanation not available for this capture</div>
          </div>
        </div>
      `;
    }

    const names = globalExp.feature_names;
    const vals = globalExp.mean_abs_attribution;

    const pairs = names.map((name, i) => ({
      name,
      val: Number(vals[i]) || 0,
    }));

    // Sort descending by mean absolute attribution
    pairs.sort((a, b) => b.val - a.val);

    // Display top 6 features
    const topPairs = pairs.slice(0, 6);
    const maxVal = topPairs[0]?.val || 0.001;

    const globalRows = topPairs
      .map((p, idx) => {
        const barPct = Math.min(100, Math.max(4, (p.val / maxVal) * 100));
        return `
          <div class="global-exp-row">
            <div class="global-exp-header">
              <div class="global-exp-info">
                <span class="global-exp-rank font-mono">#${idx + 1}</span>
                <span class="global-exp-name font-mono">${p.name}</span>
              </div>
              <span class="global-exp-val font-mono">${formatFloat(p.val, 4)}</span>
            </div>
            <div class="global-exp-track">
              <div class="global-exp-fill" style="width: ${barPct}%;"></div>
            </div>
          </div>
        `;
      })
      .join("");

    return `
      <div class="global-exp-list">
        ${globalRows}
      </div>
    `;
  }

  /**
   * Bind event listeners for attention hover and clicks
   */
  _bindEvents() {
    const cells = this.container.querySelectorAll(".att-cell");
    const detailEl = this.container.querySelector("#attHoverDetail");

    cells.forEach((cell) => {
      cell.addEventListener("mouseenter", () => {
        const wIdx = cell.getAttribute("data-window");
        const offset = cell.getAttribute("data-offset");
        const weight = cell.getAttribute("data-weight");
        const pct = cell.getAttribute("data-pct");
        const timeAgo = cell.getAttribute("data-timeago");

        if (detailEl) {
          detailEl.textContent = `Window t=${wIdx} (${timeAgo}) · Weight: ${weight} (${pct})`;
        }
      });

      cell.addEventListener("mouseleave", () => {
        if (detailEl) {
          detailEl.textContent = "Hover cells to inspect attention weight";
        }
      });

      cell.addEventListener("click", () => {
        const wIdx = parseInt(cell.getAttribute("data-window"), 10);
        if (!isNaN(wIdx)) {
          store.set({ selectedWindow: wIdx });
        }
      });
    });
  }
}
