/**
 * NetWM SOC Dashboard Main Entry Point
 * Orchestrates store, API client, and panel components.
 * See frontend/PLAN.md
 */

import { api } from "./api.js";
import { store } from "./store.js";
import { DEFAULT_DEMO } from "./config.js";
import { TimelinePanel } from "./panels/timeline.js";
import { RibbonPanel } from "./panels/ribbon.js";
import { AlarmsPanel } from "./panels/alarms.js";
import { WhyPanel } from "./panels/why.js";
import { FlowsPanel } from "./panels/flows.js";
import { UploadPanel } from "./panels/upload.js";
import { ReplayController } from "./replay.js";
import {
  formatInt,
  formatPercent,
  formatFloat,
  formatIsoTime,
  explainThresholdPolicy,
} from "./format.js";

// Initialize panel instances
const timelinePanel = new TimelinePanel("timelineChart");
let ribbonPanel = null;
let alarmsPanel = null;
let whyPanel = null;
let flowsPanel = null;
let uploadPanel = null;
let replayController = null;

/**
 * Update global UI elements on state changes
 */
function renderGlobal(state) {
  const { payload, selectedWindow, isMock } = state;
  if (!payload) return;

  // Header Status Pills
  const mockPill = document.getElementById("mockPill");
  if (mockPill) {
    mockPill.className = isMock ? "pill pill-mock" : "pill pill-live";
    mockPill.innerHTML = `<span class="status-dot"></span>${isMock ? "Mock Fixture" : "Live API"}`;
  }

  const thresholdPill = document.getElementById("thresholdPill");
  if (thresholdPill) {
    const policyDesc = explainThresholdPolicy(payload.threshold, payload.threshold_policy);
    thresholdPill.textContent = `Threshold: ${formatFloat(payload.threshold, 4)} (${policyDesc})`;
    thresholdPill.title = `Alarm statistic: ${payload.alarm_statistic || "p_max"} >= ${payload.threshold} · Policy: ${payload.threshold_policy}`;
  }

  const horizonPill = document.getElementById("horizonPill");
  if (horizonPill) {
    horizonPill.textContent = `Horizon K=${payload.horizon_k} (5m lookahead)`;
  }

  // Capture Source Info
  const sourceFilename = document.getElementById("sourceFilename");
  if (sourceFilename && payload.source) {
    sourceFilename.textContent = payload.source.filename || "capture.csv";
  }

  const sourceStats = document.getElementById("sourceStats");
  if (sourceStats && payload.source) {
    sourceStats.textContent = `${formatInt(payload.source.flows)} flows · ${formatInt(payload.source.windows)} windows`;
  }

  // Dev Notice Banner (e.g. for thursday_oracle fixture)
  const devBanner = document.getElementById("devBanner");
  const devNote = document.getElementById("devNote");
  if (devBanner && devNote) {
    if (payload.dev_only) {
      devBanner.classList.remove("hidden");
      devNote.textContent = payload.note || "UI DEVELOPMENT ONLY: Hand-picked threshold fixture.";
    } else {
      devBanner.classList.add("hidden");
    }
  }

  // Selected Window Quick Info
  const selectedWindowEl = document.getElementById("selectedWindowText");
  if (selectedWindowEl && payload.timeline && payload.timeline[selectedWindow]) {
    const w = payload.timeline[selectedWindow];
    const alarmBadge = w.alarm ? `<span style="color:var(--danger); font-weight:600;">[ALARM ACTIVE]</span>` : "";
    selectedWindowEl.innerHTML = `Selected: <strong>t=${w.t}</strong> (${formatIsoTime(w.ts)}) · Risk: <strong>${formatPercent(w.p_max)}</strong> ${alarmBadge}`;
  }
}

/**
 * Load scenario data into store
 */
async function loadScenario(scenarioName, targetWindow = null) {
  const loadingOverlay = document.getElementById("loadingOverlay");
  if (loadingOverlay) loadingOverlay.classList.remove("hidden");

  try {
    const { payload, isMock } = await api.loadAnalysis(scenarioName);
    
    // Choose appropriate default selected window (e.g. 417 for Thursday to showcase forecast cone, or 0)
    let defaultWindow = 0;
    if (targetWindow !== null && targetWindow >= 0 && targetWindow < payload.timeline.length) {
      defaultWindow = targetWindow;
    } else if (scenarioName.startsWith("thursday") && payload.timeline.length > 417) {
      defaultWindow = 417; // Infiltration approach window
    }

    store.set({
      payload,
      isMock,
      demoName: scenarioName,
      selectedWindow: defaultWindow,
      replay: {
        playing: false,
        t: defaultWindow,
      },
    });

    if (loadingOverlay) loadingOverlay.classList.add("hidden");
  } catch (err) {
    console.error("Failed to load scenario:", err);
    if (loadingOverlay) {
      loadingOverlay.innerHTML = `
        <div style="color:var(--danger); font-weight:600; font-size:14px;">Error Loading Analysis</div>
        <div style="color:var(--text-muted); font-size:12px; max-width:400px; text-align:center;">
          ${err.message || "Could not retrieve scenario fixture."}
        </div>
        <button class="btn" style="margin-top:10px;" onclick="location.reload()">Retry</button>
      `;
    }
  }
}

// Bind Store Subscriptions
store.subscribe((state) => {
  renderGlobal(state);
  timelinePanel.render(state);
  if (ribbonPanel) ribbonPanel.render(state);
  if (alarmsPanel) alarmsPanel.render(state);
  if (whyPanel) whyPanel.render(state);
  if (flowsPanel) flowsPanel.render(state);
  if (uploadPanel) uploadPanel.render(state);
  if (replayController) replayController.update(state);
});

// DOM Ready initialization
window.addEventListener("DOMContentLoaded", () => {
  // Initialize panels
  ribbonPanel = new RibbonPanel("ribbonPanelBody", "stageCardBody");
  alarmsPanel = new AlarmsPanel("alarmPanelBody");
  whyPanel = new WhyPanel("whyPanelBody");
  flowsPanel = new FlowsPanel("flowsPanelBody");
  uploadPanel = new UploadPanel("uploadModal");
  replayController = new ReplayController();

  const params = new URLSearchParams(window.location.search);
  const initialWindow = params.has("window") ? parseInt(params.get("window"), 10) : null;

  // Wire Demo Selector dropdown
  const demoSelector = document.getElementById("demoSelector");
  if (demoSelector) {
    demoSelector.value = DEFAULT_DEMO;
    demoSelector.addEventListener("change", (e) => {
      loadScenario(e.target.value);
    });
  }

  // Wire Secondary Series Toggles
  const toggleAttack = document.getElementById("toggleAttackSeries");
  if (toggleAttack) {
    if (params.has("attack")) {
      toggleAttack.checked = true;
      store.set({ filters: { showAttack: true } });
    }
    toggleAttack.addEventListener("change", (e) => {
      store.set({ filters: { showAttack: e.target.checked } });
    });
  }

  const toggleEscalate = document.getElementById("toggleEscalateSeries");
  if (toggleEscalate) {
    if (params.has("escalate")) {
      toggleEscalate.checked = true;
      store.set({ filters: { showEscalate: true } });
    }
    toggleEscalate.addEventListener("change", (e) => {
      store.set({ filters: { showEscalate: e.target.checked } });
    });
  }

  // Initial Scenario Load
  loadScenario(DEFAULT_DEMO, initialWindow).then(() => {
    if (params.has("play")) {
      const speed = params.has("speed") ? parseInt(params.get("speed"), 10) : 4;
      store.set({ replay: { playing: true, speed } });
    }
  });
});
