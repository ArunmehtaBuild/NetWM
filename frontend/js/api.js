/**
 * NetWM API Client
 * Manages HTTP communication with the FastAPI backend, with graceful offline fallback
 * to frontend/mock/*.json.
 * See frontend/PLAN.md & docs/api_contract.md
 */

import { API_BASE, USE_MOCK } from "./config.js";

export class ApiClient {
  constructor() {
    this.apiBase = API_BASE;
    this.useMock = USE_MOCK;
  }

  /**
   * Load analysis payload for a scenario.
   * Priority:
   * 1. If USE_MOCK is true -> load ./mock/{scenario}.json
   * 2. Otherwise try GET {API_BASE}/api/jobs/{scenario}/result (or /api/demos)
   * 3. On network error / unreachable -> fall back to ./mock/{scenario}.json
   */
  async loadAnalysis(scenario = "thursday") {
    // If mock is explicitly requested via query string ?mock
    if (this.useMock) {
      return this._loadMock(scenario);
    }

    // Attempt live backend fetch
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500); // Fast timeout for offline check

      const res = await fetch(`${this.apiBase}/api/demos`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        // Backend is up; fetch the demo scenario result
        const demoRes = await fetch(`${this.apiBase}/api/analyze/demo/${scenario}`, {
          method: "POST",
        });
        if (demoRes.ok) {
          const job = await demoRes.json();
          const resultRes = await fetch(`${this.apiBase}/api/jobs/${job.job_id}/result`);
          if (resultRes.ok) {
            const data = await resultRes.json();
            return { payload: data, isMock: false };
          }
        }
      }
    } catch {
      // Backend not running / unreachable: fallback to mock fixture
    }

    return this._loadMock(scenario);
  }

  /**
   * Load fixture from local mock folder
   */
  async _loadMock(scenario = "thursday") {
    const filename = scenario.endsWith(".json") ? scenario : `${scenario}.json`;
    const mockUrl = `./mock/${filename}`;
    
    const res = await fetch(mockUrl);
    if (!res.ok) {
      throw new Error(`Failed to load mock fixture at ${mockUrl} (${res.status} ${res.statusText})`);
    }

    const payload = await res.json();
    return { payload, isMock: true };
  }

  /**
   * Fetch flagged flows for a window
   * Endpoint: GET /api/jobs/<job_id>/flows?window=<t>&limit=50
   * Falls back gracefully to deterministic contract-compliant mock flows when offline
   */
  async getFlows(jobId, windowIndex, payload = null) {
    if (!this.useMock && jobId) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);
        const res = await fetch(`${this.apiBase}/api/jobs/${jobId}/flows?window=${windowIndex}&limit=50`, {
          signal: controller.signal,
        });
        clearTimeout(timeoutId);
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.flows)) {
            return data;
          }
        }
      } catch {
        // Backend unavailable: fall through to mock-development generator
      }
    }

    return this._generateMockFlows(windowIndex, payload);
  }

  /**
   * Deterministic mock flow generator matching docs/api_contract.md schema
   */
  _generateMockFlows(windowIndex, payload = null) {
    if (!payload || !payload.timeline || windowIndex < 0 || windowIndex >= payload.timeline.length) {
      return { window: windowIndex, total: 0, flows: [] };
    }

    const w = payload.timeline[windowIndex];
    if (!w) {
      return { window: windowIndex, total: 0, flows: [] };
    }

    const talkers = w.top_talkers || [];
    const totalFlowCount = w.flow_count || (talkers.reduce((acc, t) => acc + (t.flows || 0), 0) || 24);
    const numRows = Math.min(35, totalFlowCount);
    const flows = [];

    const baseTs = w.ts ? new Date(w.ts).getTime() : Date.now();
    const ports = [445, 80, 443, 22, 53, 8080, 3389, 21, 139, 88];
    const flagsList = ["S", "PA", "A", "FA", "R", "SA"];
    const dstIps = ["192.168.10.50", "192.168.10.3", "192.168.10.14", "205.174.165.73", "172.16.0.1"];

    const stageHint = w.pred_stage !== undefined ? w.pred_stage : 0;
    const baseScore = Number(w.p_max) || 0.01;

    for (let i = 0; i < numRows; i++) {
      // Deterministic pseudo-randomness based on window and row index
      const seed = (windowIndex * 37 + i * 17) % 1000;
      const secOffset = (seed % 30);
      const flowTs = new Date(baseTs + secOffset * 1000).toISOString();

      let srcIp = "192.168.10.8";
      if (talkers.length > 0) {
        srcIp = talkers[i % talkers.length].ip || srcIp;
      } else {
        srcIp = `192.168.10.${10 + (seed % 15)}`;
      }

      const dstIp = dstIps[(seed + i) % dstIps.length];
      const dstPort = ports[(seed * 3 + i) % ports.length];
      const srcPort = 49152 + ((seed * 7 + i * 13) % 16000);
      const proto = dstPort === 53 ? 17 : 6;
      const flags = proto === 6 ? flagsList[(seed + i) % flagsList.length] : "";
      const pkts = 1 + ((seed + i * 3) % 40);
      const bytes = pkts * (40 + ((seed * 5 + i * 11) % 1400));
      const durMs = 1 + ((seed * 2 + i * 7) % 1800);

      // Score: some elevated flows if window has high risk or alarm
      let flowScore = 0.01 + ((seed % 100) / 1000);
      if (baseScore > 0.05 || w.alarm) {
        if (i < 8) {
          flowScore = Math.min(0.99, Math.max(0.65, baseScore + ((seed % 30) / 100)));
        } else if (i < 18) {
          flowScore = Math.min(0.85, Math.max(0.25, baseScore * 0.7 + ((seed % 20) / 100)));
        }
      }

      flows.push({
        ts: flowTs,
        src_ip: srcIp,
        src_port: srcPort,
        dst_ip: dstIp,
        dst_port: dstPort,
        protocol: proto,
        flags: flags,
        pkts: pkts,
        bytes: bytes,
        duration_ms: durMs,
        score: Math.round(flowScore * 10000) / 10000,
        stage_hint: stageHint,
      });
    }

    // Sort descending by score
    flows.sort((a, b) => b.score - a.score);

    return {
      window: windowIndex,
      total: totalFlowCount,
      flows: flows,
    };
  }

  /**
   * Connect to SSE stream GET /api/jobs/<job_id>/stream?speed=<windows_per_second>
   * with fallback to deterministic local fixture playback
   */
  createReplayStream({
    jobId,
    speed = 4,
    fromWindow = 0,
    onWindow,
    onEnd,
    onError,
    payload = null,
  }) {
    let es = null;
    let timerId = null;
    let stopped = false;
    let currentSpeed = Math.max(1, speed);
    let currentT = fromWindow;

    const stop = () => {
      stopped = true;
      if (es) {
        try {
          es.close();
        } catch {
          // ignore
        }
        es = null;
      }
      if (timerId) {
        clearInterval(timerId);
        timerId = null;
      }
    };

    const runLocalMock = (startT = currentT) => {
      if (stopped) return;
      if (timerId) {
        clearInterval(timerId);
        timerId = null;
      }

      const timeline = payload?.timeline || [];
      const total = timeline.length;
      if (total === 0) {
        onEnd?.();
        return;
      }

      currentT = Math.max(0, Math.min(total, startT));
      const intervalMs = Math.max(15, Math.round(1000 / currentSpeed));

      timerId = setInterval(() => {
        if (stopped) {
          clearInterval(timerId);
          return;
        }

        if (currentT >= total) {
          clearInterval(timerId);
          timerId = null;
          onEnd?.();
          return;
        }

        const winData = timeline[currentT];
        onWindow?.(winData);
        currentT++;
      }, intervalMs);
    };

    // Attempt live SSE connection if not in mock mode and jobId is present
    if (!this.useMock && jobId) {
      try {
        const streamUrl = `${this.apiBase}/api/jobs/${jobId}/stream?speed=${currentSpeed}&from=${currentT}`;
        es = new EventSource(streamUrl);

        es.addEventListener("window", (e) => {
          if (stopped) return;
          try {
            const winData = JSON.parse(e.data);
            currentT = winData.t;
            onWindow?.(winData);
          } catch (err) {
            console.error("Error parsing SSE window event:", err);
          }
        });

        es.addEventListener("end", () => {
          stop();
          onEnd?.();
        });

        es.onerror = (err) => {
          if (es) {
            try {
              es.close();
            } catch {
              // ignore
            }
            es = null;
          }
          onError?.(err);
          // Fall back gracefully to deterministic local fixture playback
          runLocalMock(currentT);
        };
      } catch (err) {
        onError?.(err);
        runLocalMock(currentT);
      }
    } else {
      // Mock / Offline deterministic playback
      runLocalMock(currentT);
    }

    return {
      stop,
      setSpeed(newSpeed) {
        currentSpeed = Math.max(1, newSpeed);
        if (timerId) {
          runLocalMock(currentT);
        }
      },
      getCurrentT() {
        return currentT;
      },
    };
  }
}

export const api = new ApiClient();
