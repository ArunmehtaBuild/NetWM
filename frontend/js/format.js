/**
 * NetWM Formatting Helpers
 * Tabular numerals and consistent time, percent, and metric formatting.
 */

/**
 * Format ISO timestamp string (e.g. 2017-07-06T17:18:30Z) to readable HH:MM:SS UTC
 */
export function formatIsoTime(isoString) {
  if (!isoString) return "--:--:--";
  try {
    // UTC, matching the payload and docs/demo_script.md - toTimeString() rendered the viewer's
    // local zone (22:10 IST for a 16:40 UTC window), so the screen disagreed with the script.
    const d = new Date(isoString);
    return d.toISOString().substring(11, 19);
  } catch {
    return isoString;
  }
}

/**
 * Format full ISO timestamp to YYYY-MM-DD HH:MM:SS
 */
export function formatIsoDateTime(isoString) {
  if (!isoString) return "--";
  try {
    const d = new Date(isoString);
    return d.toISOString().replace("T", " ").replace("Z", " UTC");
  } catch {
    return isoString;
  }
}

/**
 * Format float to percent string (e.g. 0.0439 -> "4.4%")
 */
export function formatPercent(value, decimals = 1) {
  if (value === null || value === undefined || isNaN(value)) return "--%";
  return `${(value * 100).toFixed(decimals)}%`;
}

/**
 * Format integer with commas (e.g. 362076 -> "362,076")
 */
export function formatInt(value) {
  if (value === null || value === undefined || isNaN(value)) return "--";
  return Number(value).toLocaleString();
}

/**
 * Format float with fixed precision
 */
export function formatFloat(value, decimals = 4) {
  if (value === null || value === undefined || isNaN(value)) return "--";
  return Number(value).toFixed(decimals);
}

/**
 * Format seconds into a human-readable duration (e.g. 150 -> "2m 30s")
 */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || isNaN(seconds)) return "--";
  const s = Math.round(Number(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
}

/**
 * Format lead time string from windows and seconds
 */
export function formatLeadTime(leadWindows, leadSeconds) {
  if (leadWindows === null || leadWindows === undefined) {
    return "No early lead";
  }
  return `${leadWindows} windows (${formatDuration(leadSeconds)})`;
}

/**
 * Format bytes to KB, MB, GB
 */
export function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || isNaN(bytes)) return "-- B";
  const b = Number(bytes);
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`;
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/**
 * Convert hex color string to rgba format
 */
export function hexToRgba(hex, alpha = 1) {
  if (!hex || typeof hex !== "string") return `rgba(255, 255, 255, ${alpha})`;
  let c = hex.replace("#", "");
  if (c.length === 3) c = c.split("").map((x) => x + x).join("");
  const num = parseInt(c, 16);
  if (isNaN(num)) return `rgba(255, 255, 255, ${alpha})`;
  return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
}

/**
 * Human-readable explanation of threshold policy (e.g. self-budget-10pct -> "Top 10% of this capture")
 */
export function explainThresholdPolicy(threshold, policy = "") {
  if (!policy) return "Reference threshold";
  if (policy.startsWith("self-budget-")) {
    const pct = policy.replace("self-budget-", "").replace("pct", "");
    return `Top ${pct}% of this capture (self-budget)`;
  }
  if (policy === "fixed-override") {
    return "Hand-picked threshold (UI test only)";
  }
  if (policy === "fixed") {
    return "Fixed reference threshold";
  }
  if (policy.startsWith("train-tuned")) {
    return "Train-tuned F1-optimal threshold";
  }
  if (policy.startsWith("train-quantile")) {
    return "Training 95th percentile budget";
  }
  return policy;
}

