/**
 * NetWM Forecast Timeline Panel (H-2)
 *
 * Implements:
 * 1. Historical risk line using timeline[].p_max (the alarm statistic)
 * 2. Threshold line labelled with policy and human-readable explanation
 * 3. K-step forecast cone (p_cum, p_lo, p_hi) anchored at selectedWindow
 * 4. Ground-truth attack spans shaded with dynamic colors from payload.stages[]
 * 5. Alarm markers for timeline[].alarm
 * 6. Interactive window selection (store.selectedWindow single source of truth)
 * 7. Fast in-place chart updates (chart.update('none'))
 * 8. Optional secondary series (p_cum_attack, p_cum_escalate)
 *
 * See frontend/PLAN.md
 */

import { store } from "../store.js";
import { computeForecastCone } from "../charts/cone.js";
import {
  formatPercent,
  formatFloat,
  formatIsoTime,
  hexToRgba,
  explainThresholdPolicy,
} from "../format.js";

// Accent colour comes from the --accent token in theme.css so the timeline follows the theme
// instead of carrying its own copy of the palette (H-7).
function accentColor() {
  const v = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  return v || "#4c9be8";
}

// Custom Chart.js Plugin for Ground-Truth Attack Spans and Selected Window Hairline
const netwmTimelineOverlayPlugin = {
  id: "netwmTimelineOverlay",
  beforeDatasetsDraw(chart, args, pluginOptions) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales.x) return;
    const { top, bottom, left, right } = chartArea;
    const x = scales.x;

    const { spans, stages, selectedWindow } = pluginOptions;

    ctx.save();

    // 1. Draw Ground-Truth Attack Spans Shading
    if (spans && spans.length && stages) {
      const colorMap = new Map();
      stages.forEach((s) => colorMap.set(s.id, s.color));

      for (const span of spans) {
        const xStart = Math.max(left, x.getPixelForValue(span.start_t));
        const xEnd = Math.min(right, x.getPixelForValue(span.end_t));
        const width = Math.max(2, xEnd - xStart);

        const stageColor = colorMap.get(span.stage) || "#e2574c";

        // Vertical background shading band
        ctx.fillStyle = hexToRgba(stageColor, 0.16);
        ctx.fillRect(xStart, top, width, bottom - top);

        // Top accent stripe
        ctx.fillStyle = hexToRgba(stageColor, 0.7);
        ctx.fillRect(xStart, top, width, 2);

        // Render text label if span is wide enough
        if (width > 36) {
          ctx.font = "10px ui-monospace, Consolas, monospace";
          ctx.fillStyle = hexToRgba(stageColor, 0.95);
          ctx.fillText(span.label || "Attack", xStart + 4, top + 13);
        }
      }
    }

    // 2. Draw Selected Window Vertical Hairline Cursor
    if (selectedWindow !== null && selectedWindow !== undefined) {
      const xPos = x.getPixelForValue(selectedWindow);
      if (xPos >= left && xPos <= right) {
        ctx.strokeStyle = hexToRgba(accentColor(), 0.8);
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(xPos, top);
        ctx.lineTo(xPos, bottom);
        ctx.stroke();

        // Accent top notch
        ctx.fillStyle = accentColor();
        ctx.fillRect(xPos - 3, top, 6, 4);
      }
    }

    ctx.restore();
  },
};

export class TimelinePanel {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.chart = null;
    this.lastRenderedPayload = null;
    this.lastSelectedWindow = null;
    this.lastFilters = null;

    // Register plugin if Chart.js is present
    if (window.Chart && !window.Chart.registry.plugins.get("netwmTimelineOverlay")) {
      window.Chart.register(netwmTimelineOverlayPlugin);
    }
  }

  /**
   * Render or update timeline given store state
   */
  render(state) {
    const { payload, selectedWindow, filters } = state;
    if (!payload || !payload.timeline || !this.canvas) return;

    const showAttack = Boolean(filters?.showAttack);
    const showEscalate = Boolean(filters?.showEscalate);

    // Full rebuild on new payload or first load
    if (!this.chart || this.lastRenderedPayload !== payload) {
      this._buildChart(payload, selectedWindow, { showAttack, showEscalate });
      this.lastRenderedPayload = payload;
      this.lastSelectedWindow = selectedWindow;
      this.lastFilters = { showAttack, showEscalate };
    } else if (
      this.lastSelectedWindow !== selectedWindow ||
      this.lastFilters?.showAttack !== showAttack ||
      this.lastFilters?.showEscalate !== showEscalate
    ) {
      // In-place lightweight update
      this._updateForecastCone(payload, selectedWindow, { showAttack, showEscalate });
      this.lastSelectedWindow = selectedWindow;
      this.lastFilters = { showAttack, showEscalate };
    }
  }

  _buildChart(payload, selectedWindow, options) {
    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }

    if (!window.Chart) {
      console.error("Vendored Chart.js is not loaded.");
      return;
    }

    const timeline = payload.timeline;
    const labels = timeline.map((w) => w.t);
    const pMaxData = timeline.map((w) => w.p_max);
    const thresholdValue = Number(payload.threshold);
    const thresholdData = new Array(timeline.length).fill(thresholdValue);

    // Compute initial forecast cone
    const cone = computeForecastCone(timeline, selectedWindow, payload.horizon_k, options);

    const thresholdExplanation = explainThresholdPolicy(
      thresholdValue,
      payload.threshold_policy
    );

    const ctx = this.canvas.getContext("2d");

    this.chart = new window.Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          // 0: Historical Risk Line (p_max is the alarm statistic)
          {
            label: "Risk p_max (Historical)",
            data: pMaxData,
            borderColor: accentColor(),
            borderWidth: 1.5,
            fill: false,
            tension: 0.05,
            pointRadius: timeline.map((w) => (w.alarm ? 3.5 : 0)),
            pointBackgroundColor: timeline.map((w) => (w.alarm ? "#e2574c" : "transparent")),
            pointBorderColor: timeline.map((w) => (w.alarm ? "#ffffff" : "transparent")),
            pointBorderWidth: timeline.map((w) => (w.alarm ? 1.2 : 0)),
            pointHoverRadius: 5,
            pointHoverBackgroundColor: accentColor(),
            pointHoverBorderColor: "#ffffff",
            order: 2,
          },
          // 1: Threshold Line
          {
            label: `Threshold: ${formatFloat(thresholdValue, 4)} (${thresholdExplanation})`,
            data: thresholdData,
            borderColor: "rgba(226, 87, 76, 0.8)",
            borderWidth: 1.5,
            borderDash: [5, 4],
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 0,
            order: 3,
          },
          // 2: Forecast Upper Bound (95% CI)
          {
            label: "Forecast Upper (95% CI)",
            data: cone.upper,
            borderColor: hexToRgba(accentColor(), 0.4),
            borderWidth: 1,
            borderDash: [3, 3],
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 0,
            spanGaps: false,
            order: 1,
          },
          // 3: Forecast Lower Bound (5% CI) with Shaded Fill to Upper Bound
          {
            label: "Forecast Lower (5% CI)",
            data: cone.lower,
            borderColor: hexToRgba(accentColor(), 0.4),
            borderWidth: 1,
            borderDash: [3, 3],
            fill: "-1", // Fill area between lower and upper
            backgroundColor: hexToRgba(accentColor(), 0.18),
            pointRadius: 0,
            pointHoverRadius: 0,
            spanGaps: false,
            order: 1,
          },
          // 4: Forecast Forward Trajectory (p_cum)
          {
            label: `K-step Forecast (p_cum · K=${payload.horizon_k || 10})`,
            data: cone.cum,
            borderColor: accentColor(),
            borderWidth: 2.5,
            fill: false,
            spanGaps: false,
            pointRadius: (ctx) => {
              const val = ctx.parsed?.y;
              if (val === null || val === undefined) return 0;
              const idx = ctx.dataIndex;
              const sel = this.lastSelectedWindow ?? selectedWindow;
              if (idx === sel) return 4; // Anchor bead at t
              const K = Math.min(Number(payload.horizon_k) || 10, timeline[sel]?.forecast?.p_cum?.length || 0);
              if (idx === sel + K) return 4.5; // Final forecast bead at t+K
              return 2.5; // Intermediate steps
            },
            pointBackgroundColor: accentColor(),
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1,
            pointHoverRadius: 5,
            order: 0,
          },
          // 5: Optional Secondary Series: Attack Progression
          {
            label: "Attack Progression (p_cum_attack)",
            data: cone.attack,
            borderColor: "#f2a541",
            borderWidth: 1.5,
            borderDash: [4, 3],
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 3,
            spanGaps: false,
            hidden: !options.showAttack,
            order: 1,
          },
          // 6: Optional Secondary Series: Escalation
          {
            label: "Stage Escalation (p_cum_escalate)",
            data: cone.escalate,
            borderColor: "#8e5bd9",
            borderWidth: 1.5,
            borderDash: [4, 3],
            fill: false,
            pointRadius: 0,
            pointHoverRadius: 3,
            spanGaps: false,
            hidden: !options.showEscalate,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        scales: {
          x: {
            grid: {
              color: "#212836",
            },
            ticks: {
              color: "#8b98a5",
              maxTicksLimit: 16,
              font: {
                family: "ui-monospace, Consolas, monospace",
                size: 10,
              },
            },
            title: {
              display: true,
              text: `Timeline Windows (t = 0..${timeline.length - 1} · ${payload.source?.window_s || 60}s window / ${payload.source?.stride_s || 30}s stride)`,
              color: "#65707d",
              font: { size: 11 },
            },
          },
          y: {
            min: 0,
            max: 1.0,
            grid: {
              color: "#212836",
            },
            ticks: {
              color: "#8b98a5",
              font: {
                family: "ui-monospace, Consolas, monospace",
                size: 10,
              },
              callback: (val) => formatPercent(val, 0),
            },
            title: {
              display: true,
              text: "Forecasted Risk / Probability",
              color: "#65707d",
              font: { size: 11 },
            },
          },
        },
        plugins: {
          netwmTimelineOverlay: {
            spans: payload.ground_truth?.available ? payload.ground_truth.spans : [],
            stages: payload.stages || [],
            selectedWindow,
          },
          legend: {
            position: "top",
            align: "end",
            labels: {
              color: "#e6edf3",
              boxWidth: 14,
              boxHeight: 2,
              font: { size: 11 },
              // Filter out upper/lower CI bounds and inactive secondary series from legend
              filter: (legendItem, chartData) => {
                if (legendItem.text.includes("(95% CI)") || legendItem.text.includes("(5% CI)")) {
                  return false;
                }
                const ds = chartData.datasets[legendItem.datasetIndex];
                if (ds && ds.hidden) {
                  return false;
                }
                return true;
              },
            },
          },
          tooltip: {
            backgroundColor: "#161b22",
            borderColor: "#2a3038",
            borderWidth: 1,
            titleColor: "#e6edf3",
            bodyColor: "#8b98a5",
            padding: 10,
            callbacks: {
              title: (items) => {
                if (!items.length) return "";
                const idx = items[0].dataIndex;
                const w = timeline[idx];
                return `Window t=${w.t} · ${formatIsoTime(w.ts)}`;
              },
              label: (context) => {
                const idx = context.dataIndex;
                const w = timeline[idx];
                const dIdx = context.datasetIndex;

                if (dIdx === 0) {
                  const alarmText = w.alarm ? "  ⚠️ [ALARM ACTIVE]" : "";
                  return `Historical p_max: ${formatFloat(w.p_max, 4)} (${formatPercent(w.p_max, 1)})${alarmText}`;
                }
                if (dIdx === 1) {
                  return `Threshold: ${formatFloat(thresholdValue, 4)} (${thresholdExplanation})`;
                }
                if (dIdx === 4 && context.parsed.y !== null) {
                  const lo = cone.lower[idx];
                  const hi = cone.upper[idx];
                  const loStr = lo !== null ? formatPercent(lo, 1) : "--";
                  const hiStr = hi !== null ? formatPercent(hi, 1) : "--";
                  return `K-step Forecast (p_cum): ${formatFloat(context.parsed.y, 4)} [90% CI: ${loStr} - ${hiStr}]`;
                }
                if (dIdx === 5 && context.parsed.y !== null) {
                  return `Attack Progression: ${formatFloat(context.parsed.y, 4)} (${formatPercent(context.parsed.y, 1)})`;
                }
                if (dIdx === 6 && context.parsed.y !== null) {
                  return `Stage Escalation: ${formatFloat(context.parsed.y, 4)} (${formatPercent(context.parsed.y, 1)})`;
                }
                return null;
              },
              afterBody: (items) => {
                if (!items.length) return [];
                const idx = items[0].dataIndex;
                const lines = [];

                if (payload.ground_truth?.available && payload.ground_truth.spans) {
                  const activeSpan = payload.ground_truth.spans.find(
                    (s) => idx >= s.start_t && idx <= s.end_t
                  );
                  if (activeSpan) {
                    const st = (payload.stages || []).find((s) => s.id === activeSpan.stage);
                    lines.push(`Attack Span: ${activeSpan.label} [${st ? st.label : "Stage " + activeSpan.stage}]`);
                  }
                }
                return lines;
              },
            },
          },
        },
        onClick: (event, elements, chart) => {
          if (!window.Chart || !chart) return;
          const canvasPos = window.Chart.helpers.getRelativePosition(event, chart);
          const dataX = chart.scales.x.getValueForPixel(canvasPos.x);
          if (dataX !== undefined) {
            const clampedIndex = Math.max(
              0,
              Math.min(payload.timeline.length - 1, Math.round(dataX))
            );
            store.set({ selectedWindow: clampedIndex });
          }
        },
      },
    });
  }

  _updateForecastCone(payload, selectedWindow, options) {
    if (!this.chart) return;

    this.lastSelectedWindow = selectedWindow;
    const timeline = payload.timeline;
    const cone = computeForecastCone(
      timeline,
      selectedWindow,
      payload.horizon_k,
      options
    );

    // Update forecast datasets
    this.chart.data.datasets[2].data = cone.upper;
    this.chart.data.datasets[3].data = cone.lower;
    this.chart.data.datasets[4].data = cone.cum;
    this.chart.data.datasets[5].data = cone.attack;
    this.chart.data.datasets[5].hidden = !options.showAttack;
    this.chart.data.datasets[6].data = cone.escalate;
    this.chart.data.datasets[6].hidden = !options.showEscalate;

    // Update overlay cursor window
    if (this.chart.options.plugins?.netwmTimelineOverlay) {
      this.chart.options.plugins.netwmTimelineOverlay.selectedWindow = selectedWindow;
    }

    // Fast in-place redraw
    this.chart.update("none");
  }
}
