/**
 * NetWM Forecast Cone Helper
 * Prepares the K-step forward simulation datasets for Chart.js
 */

/**
 * Compute the K-step forecast cone series anchored at selectedWindow.
 * 
 * @param {Array} timeline - Array of timeline window objects
 * @param {number} selectedWindow - Index t of currently selected window
 * @param {number} horizonK - Number of lookahead steps K (from payload.horizon_k)
 * @param {Object} options - Optional toggles { showAttack, showEscalate }
 * @returns {Object} { upper, lower, cum, attack, escalate }
 */
export function computeForecastCone(timeline, selectedWindow, horizonK = 10, options = {}) {
  const N = timeline ? timeline.length : 0;
  const upper = new Array(N).fill(null);
  const lower = new Array(N).fill(null);
  const cum = new Array(N).fill(null);
  const attack = new Array(N).fill(null);
  const escalate = new Array(N).fill(null);

  if (!timeline || selectedWindow < 0 || selectedWindow >= N) {
    return { upper, lower, cum, attack, escalate };
  }

  const cur = timeline[selectedWindow];
  if (!cur || !cur.forecast) {
    return { upper, lower, cum, attack, escalate };
  }

  const pMaxNow = cur.p_max !== undefined ? Number(cur.p_max) : 0;
  const K = Math.min(Number(horizonK) || 10, cur.forecast.p_cum?.length || 0);

  // Visually anchor the forecast cone at the selected historical point
  upper[selectedWindow] = pMaxNow;
  lower[selectedWindow] = pMaxNow;
  cum[selectedWindow] = pMaxNow;
  if (options.showAttack) attack[selectedWindow] = pMaxNow;
  if (options.showEscalate) escalate[selectedWindow] = pMaxNow;

  for (let k = 1; k <= K; k++) {
    const targetIdx = selectedWindow + k;
    if (targetIdx < N) {
      const stepIdx = k - 1;
      upper[targetIdx] = cur.forecast.p_hi?.[stepIdx] ?? null;
      lower[targetIdx] = cur.forecast.p_lo?.[stepIdx] ?? null;
      cum[targetIdx] = cur.forecast.p_cum?.[stepIdx] ?? null;

      if (options.showAttack) {
        attack[targetIdx] = cur.forecast.p_cum_attack?.[stepIdx] ?? null;
      }
      if (options.showEscalate) {
        escalate[targetIdx] = cur.forecast.p_cum_escalate?.[stepIdx] ?? null;
      }
    }
  }

  return { upper, lower, cum, attack, escalate };
}
