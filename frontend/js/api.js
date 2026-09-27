/**
 * NetWM API Client
 * Manages HTTP communication with the FastAPI backend, with graceful offline fallback
 * to frontend/mock/*.json.
 * See frontend/PLAN.md & docs/api_contract.md
 */

import { API_BASE, USE_MOCK } from "./config.js";
import { formatBytes } from "./format.js";

export class ApiClient {
  constructor() {
    this.apiBase = API_BASE;
    this.useMock = USE_MOCK;
    this._activeUploadXhr = null;
    this._activePollController = null;
    this._mockAbortController = null;
  }

  /**
   * Load analysis payload for a scenario.
   * Priority:
   * 1. If USE_MOCK is true -> load ./mock/{scenario}.json
   * 2. Otherwise resolve the scenario to a backend demo id via GET /api/demos, then
   *    POST /api/analyze/demo/<id> and poll the job to its result
   * 3. Backend unreachable, or no live demo for this scenario -> ./mock/{scenario}.json
   *
   * The selector speaks in fixture names ("thursday"); the backend speaks in demo ids
   * ("thursday_infiltration"). Posting the fixture name 400s and silently degrades a
   * healthy backend to Mock Fixture (H-9), so the id always comes from /api/demos.
   */
  async loadAnalysis(scenario = "thursday", onProgress = null) {
    if (this.useMock) {
      return this._loadMock(scenario);
    }

    const demos = await this.listDemos();
    const demoId = this.resolveDemoId(scenario, demos);
    if (demoId) {
      try {
        return await this._startDemoJob(demoId, onProgress);
      } catch (err) {
        console.warn(`Live demo '${demoId}' failed, falling back to fixture:`, err);
      }
    }

    return this._loadMock(scenario);
  }

  /**
   * GET /api/demos, or null when the backend is unreachable. Short timeout so an
   * offline dashboard falls through to fixtures without a visible stall.
   */
  async listDemos() {
    if (this.useMock) return null;
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      const res = await fetch(`${this.apiBase}/api/demos`, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) return null;
      const demos = await res.json();
      return Array.isArray(demos) ? demos : null;
    } catch {
      return null;
    }
  }

  /**
   * Map a UI scenario name to a backend demo id: an exact id match wins, otherwise the
   * first demo for that day. Returns null when there is no live equivalent (e.g. the
   * dev-only thursday_oracle fixture), so the caller shows the fixture and says so.
   */
  resolveDemoId(scenario, demos) {
    if (!Array.isArray(demos) || !scenario) return null;
    const exact = demos.find((d) => d.id === scenario);
    if (exact) return exact.id;
    const byDay = demos.find((d) => d.day === scenario);
    return byDay ? byDay.id : null;
  }

  /** POST /api/analyze/demo/<id> and poll that job to its result. Throws on failure. */
  async _startDemoJob(demoId, onProgress = null) {
    onProgress?.({ state: "running", progress: 0.05, stage_text: `Dispatching demo ${demoId}...` });
    const res = await fetch(`${this.apiBase}/api/analyze/demo/${encodeURIComponent(demoId)}`, {
      method: "POST",
    });
    if (!res.ok) {
      let errData = null;
      try {
        errData = await res.json();
      } catch {
        errData = null;
      }
      const err = new Error(errData?.error?.message || `POST /api/analyze/demo/${demoId} returned ${res.status}`);
      err.code = errData?.error?.code || "bad_file";
      throw err;
    }
    const { job_id } = await res.json();
    return this._pollJob(job_id, onProgress);
  }

  /**
   * Load fixture from local mock folder
   */
  async _loadMock(scenario = "thursday") {
    const rawName = (scenario || "thursday").replace(".json", "");
    const baseFilename = `${rawName}.json`;

    // Resolve against this module, not the page, so frontend/dev/ harnesses find fixtures too.
    const mockUrl = new URL(`../mock/${baseFilename}`, import.meta.url).href;

    // Node unit-testing environment support (Node fetch does not support file:// scheme)
    if (mockUrl.startsWith("file:") && typeof process !== "undefined" && process.versions?.node) {
      try {
        const fs = await import("node:fs/promises");
        const { fileURLToPath } = await import("node:url");
        try {
          const content = await fs.readFile(fileURLToPath(mockUrl), "utf-8");
          return { payload: JSON.parse(content), isMock: true };
        } catch {
          const fallbackPath = fileURLToPath(new URL("../mock/thursday.json", import.meta.url).href);
          const content = await fs.readFile(fallbackPath, "utf-8");
          return { payload: JSON.parse(content), isMock: true };
        }
      } catch {
        // Fall through to browser fetch
      }
    }
    
    let res;
    try {
      res = await fetch(mockUrl);
    } catch {
      // Fallback to thursday.json if scenario fixture file does not exist locally
      res = await fetch(new URL("../mock/thursday.json", import.meta.url).href);
    }

    if (!res || !res.ok) {
      res = await fetch(new URL("../mock/thursday.json", import.meta.url).href);
      if (!res.ok) {
        throw new Error(`Failed to load mock fixture at ${mockUrl} (${res.status} ${res.statusText})`);
      }
    }

    const payload = await res.json();
    return { payload, isMock: true };
  }

  /**
   * Validate capture file extension and size caps
   * Supported: .csv (max 200MB), .pcap/.pcapng (max 2GB)
   */
  validateCaptureFile(file) {
    if (!file) {
      return { valid: false, code: "bad_file", message: "No file selected." };
    }
    const name = file.name || "";
    const lowerName = name.toLowerCase();
    const isCsv = lowerName.endsWith(".csv");
    const isPcap = lowerName.endsWith(".pcap") || lowerName.endsWith(".pcapng");

    if (!isCsv && !isPcap) {
      return {
        valid: false,
        code: "unsupported_format",
        message: "Unsupported file extension. Only .csv, .pcap, and .pcapng files are supported.",
      };
    }

    if (file.size === 0) {
      return {
        valid: false,
        code: "bad_file",
        message: "The selected capture file is empty (0 bytes).",
      };
    }

    const maxCsv = 200 * 1024 * 1024; // 200 MB
    const maxPcap = 2 * 1024 * 1024 * 1024; // 2 GB

    if (isCsv && file.size > maxCsv) {
      return {
        valid: false,
        code: "too_large",
        message: `CSV file exceeds the 200 MB limit (${formatBytes(file.size)}).`,
      };
    }

    if (isPcap && file.size > maxPcap) {
      return {
        valid: false,
        code: "too_large",
        message: `PCAP file exceeds the 2 GB limit (${formatBytes(file.size)}).`,
      };
    }

    return { valid: true };
  }

  /**
   * Cancel in-flight upload request or stop waiting for backend analysis polling.
   */
  cancelUpload() {
    let handled = false;
    if (this._activeUploadXhr) {
      try {
        this._activeUploadXhr.abort();
      } catch (e) {
        console.warn("Error aborting XHR:", e);
      }
      this._activeUploadXhr = null;
      handled = true;
    }

    if (this._activePollController) {
      try {
        this._activePollController.abort();
      } catch (e) {
        console.warn("Error aborting poll controller:", e);
      }
      this._activePollController = null;
      handled = true;
    }

    if (this._mockAbortController) {
      this._mockAbortController.aborted = true;
      handled = true;
    }

    return handled;
  }

  /**
   * Upload and analyze capture file (.csv or .pcap)
   * Real backend: POST /api/analyze (via XMLHttpRequest with real upload byte progress)
   *               -> poll GET /api/jobs/<id> (with polling abort support)
   *               -> GET /api/jobs/<id>/result
   * Offline/Mock: Realistic simulated progress pipeline and fixture synthesis
   */
  async uploadCapture(file, onProgress = null) {
    const val = this.validateCaptureFile(file);
    if (!val.valid) {
      const err = new Error(val.message);
      err.code = val.code;
      throw err;
    }

    // Try live API if not forced mock
    if (!this.useMock) {
      return await this._uploadCaptureLive(file, onProgress);
    }

    // Deterministic mock analysis simulation
    return await this._simulateMockAnalysis(file, onProgress);
  }

  /**
   * Live upload using XMLHttpRequest for real byte-level progress reporting
   * followed by backend job polling.
   */
  async _uploadCaptureLive(file, onProgress = null) {
    // Phase 1: Uploading file over network via XMLHttpRequest
    let jobId;
    try {
      jobId = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        this._activeUploadXhr = xhr;

        // Byte-level progress callback (mapped to 0.0 -> 0.45 total progress)
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable && e.total > 0) {
            const bytePct = e.loaded / e.total;
            const progress = bytePct * 0.45;
            onProgress?.({
              state: "uploading",
              progress,
              stage_text: `Uploading ${file.name} (${formatBytes(e.loaded)} / ${formatBytes(e.total)} · ${Math.round(bytePct * 100)}%)...`,
              bytesLoaded: e.loaded,
              bytesTotal: e.total,
            });
          } else {
            onProgress?.({
              state: "uploading",
              progress: 0.15,
              stage_text: `Uploading ${file.name} (${formatBytes(file.size)})...`,
            });
          }
        };

        xhr.onload = () => {
          this._activeUploadXhr = null;
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const data = JSON.parse(xhr.responseText);
              if (data && data.job_id) {
                resolve(data.job_id);
              } else {
                const err = new Error("Invalid response format from server: missing job_id");
                err.code = "internal";
                reject(err);
              }
            } catch (pErr) {
              const err = new Error("Failed to parse server response: " + pErr.message);
              err.code = "internal";
              reject(err);
            }
          } else {
            // Structured error response from backend register_error_handlers
            let errData = null;
            try {
              errData = JSON.parse(xhr.responseText);
            } catch {
              errData = null;
            }

            const code =
              errData?.error?.code ||
              (xhr.status === 413
                ? "too_large"
                : xhr.status === 415
                ? "unsupported_format"
                : xhr.status === 400
                ? "bad_file"
                : xhr.status === 503
                ? "no_model"
                : "internal");
            const msg =
              errData?.error?.message ||
              `Server rejected upload (${xhr.status} ${xhr.statusText || ""})`.trim();
            const err = new Error(msg);
            err.code = code;
            err.status = xhr.status;
            reject(err);
          }
        };

        xhr.onerror = () => {
          this._activeUploadXhr = null;
          const err = new Error(
            `Failed to connect to backend server at ${this.apiBase}. Verify the backend server is running.`
          );
          err.code = "network";
          reject(err);
        };

        xhr.onabort = () => {
          this._activeUploadXhr = null;
          const err = new Error("Upload cancelled by user.");
          err.code = "cancelled";
          err.wasUploading = true;
          reject(err);
        };

        // Initial 0% progress notification
        onProgress?.({
          state: "uploading",
          progress: 0.0,
          stage_text: `Uploading ${file.name} (${formatBytes(file.size)})...`,
          bytesLoaded: 0,
          bytesTotal: file.size,
        });

        const formData = new FormData();
        formData.append("file", file);

        xhr.open("POST", `${this.apiBase}/api/analyze`);
        xhr.send(formData);
      });
    } catch (uploadErr) {
      this._activeUploadXhr = null;
      throw uploadErr;
    }

    // Phase 2: Analyzing / Server Job Polling (0.45 -> 1.0 total progress)
    onProgress?.({
      state: "queued",
      progress: 0.45,
      stage_text: "Upload received. Queued for RSSM analysis on backend...",
      jobId,
    });

    return await this._pollJob(jobId, (pollState) => {
      // Map server job progress (0.0 -> 1.0) into overall UI progress (0.45 -> 1.0)
      const mappedProgress = 0.45 + (pollState.progress || 0) * 0.55;
      onProgress?.({
        state: pollState.state === "running" ? "analyzing" : pollState.state,
        progress: mappedProgress,
        stage_text: pollState.stage_text ? `Analyzing: ${pollState.stage_text}` : "Analyzing capture telemetry...",
        jobId,
      });
    });
  }

  /**
   * Trigger demo scenario analysis from the upload modal's preset chips. Chips carry
   * fixture names, so they go through the same /api/demos resolution as the selector.
   */
  async runDemoAnalysis(demoId, onProgress = null) {
    if (!this.useMock) {
      const liveId = this.resolveDemoId(demoId, await this.listDemos());
      if (liveId) {
        try {
          return await this._startDemoJob(liveId, onProgress);
        } catch (err) {
          if (err.code === "cancelled" || err.code === "stopped_waiting") {
            throw err;
          }
          console.warn(`Live demo '${liveId}' failed, falling back to fixture:`, err);
        }
      }
    }

    const mockFile = {
      name: `${demoId}_demo_capture.csv`,
      size: 42800000,
    };
    return await this._simulateMockAnalysis(mockFile, onProgress, demoId);
  }

  /**
   * The job id to use for /flows and /stream, or null for fixture data. A fixture has no
   * backend job, so asking the API about it only produces 404s (H-9: literal "demo").
   */
  liveJobId(state) {
    if (!state || state.isMock) return null;
    return state.payload?.job_id ?? null;
  }

  /**
   * Poll backend job until done or error
   * Spec: Poll GET /api/jobs/<id> every 750 ms (frontend/PLAN.md)
   */
  async _pollJob(jobId, onProgress = null) {
    const pollInterval = 750;
    this._activePollController = new AbortController();
    const signal = this._activePollController.signal;

    try {
      while (true) {
        if (signal.aborted) {
          const err = new Error(
            "Stopped waiting for server analysis job. (The server had already accepted the upload; client stopped waiting.)"
          );
          err.code = "stopped_waiting";
          err.wasAnalyzing = true;
          err.jobId = jobId;
          throw err;
        }

        let res;
        try {
          res = await fetch(`${this.apiBase}/api/jobs/${jobId}`, { signal });
        } catch (fetchErr) {
          if (signal.aborted) {
            const err = new Error(
              "Stopped waiting for server analysis job. (The server had already accepted the upload; client stopped waiting.)"
            );
            err.code = "stopped_waiting";
            err.wasAnalyzing = true;
            err.jobId = jobId;
            throw err;
          }
          const err = new Error(`Failed to poll job status: ${fetchErr.message}`);
          err.code = "network";
          throw err;
        }

        if (!res.ok) {
          let errData = null;
          try {
            errData = await res.json();
          } catch {
            errData = null;
          }
          const err = new Error(errData?.error?.message || `Job poll failed with status ${res.status}`);
          err.code = errData?.error?.code || (res.status === 404 ? "job_not_found" : "internal");
          throw err;
        }

        const job = await res.json();
        onProgress?.({
          state: job.state,
          progress: job.progress || 0,
          stage_text: job.stage_text || "",
          jobId,
        });

        if (job.state === "done") {
          const resultRes = await fetch(`${this.apiBase}/api/jobs/${jobId}/result`, { signal });
          if (!resultRes.ok) {
            let resErrData = null;
            try {
              resErrData = await resultRes.json();
            } catch {
              resErrData = null;
            }
            const err = new Error(resErrData?.error?.message || `Failed to retrieve job results (${resultRes.status})`);
            err.code = resErrData?.error?.code || "internal";
            throw err;
          }
          const payload = await resultRes.json();
          payload.job_id = payload.job_id || jobId;
          return { payload, isMock: false };
        } else if (job.state === "error") {
          const err = new Error(job.error?.message || "Job analysis failed");
          err.code = job.error?.code || "internal";
          throw err;
        }

        await new Promise((resolve, reject) => {
          const timeoutId = setTimeout(resolve, pollInterval);
          signal.addEventListener(
            "abort",
            () => {
              clearTimeout(timeoutId);
              const err = new Error(
                "Stopped waiting for server analysis job. (The server had already accepted the upload; client stopped waiting.)"
              );
              err.code = "stopped_waiting";
              err.wasAnalyzing = true;
              err.jobId = jobId;
              reject(err);
            },
            { once: true }
          );
        });
      }
    } finally {
      this._activePollController = null;
    }
  }

  /**
   * High-fidelity offline simulation of the NetWM ML ingestion pipeline
   */
  async _simulateMockAnalysis(file, onProgress = null, explicitFixture = null) {
    const mockAbort = { aborted: false };
    this._mockAbortController = mockAbort;

    const stages = [
      { progress: 0.12, state: "uploading", text: `Uploading ${file.name} (${formatBytes(file.size)})...` },
      { progress: 0.28, state: "uploading", text: "Validating capture format and network flow timestamps..." },
      { progress: 0.48, state: "analyzing", text: "Extracting 70-dimensional flow features across 60s windows..." },
      { progress: 0.72, state: "analyzing", text: "Rolling out RSSM world model forward dynamics (K=10 horizon)..." },
      { progress: 0.88, state: "analyzing", text: "Evaluating risk heads (p_max, p_cum) and computing attribution..." },
      { progress: 1.00, state: "analyzing", text: "Finalizing detection and forecasting payload..." },
    ];

    try {
      for (const step of stages) {
        if (mockAbort.aborted) {
          const err = new Error("Analysis cancelled by user.");
          err.code = "cancelled";
          err.wasUploading = true;
          throw err;
        }
        onProgress?.({ state: step.state, progress: step.progress, stage_text: step.text });
        await new Promise((r) => setTimeout(r, 420));
      }

      if (mockAbort.aborted) {
        const err = new Error("Analysis cancelled by user.");
        err.code = "cancelled";
        err.wasUploading = true;
        throw err;
      }

      const lower = (file.name || "").toLowerCase();
      let baseScenario = explicitFixture;
      if (!baseScenario) {
        if (lower.includes("friday") || lower.includes("botnet") || lower.includes("ddos") || lower.includes("portscan")) {
          baseScenario = "friday";
        } else if (lower.includes("oracle")) {
          baseScenario = "thursday_oracle";
        } else {
          baseScenario = "thursday";
        }
      }

      const { payload } = await this._loadMock(baseScenario);
      const cloned = JSON.parse(JSON.stringify(payload));

      const isPcap = lower.endsWith(".pcap") || lower.endsWith(".pcapng");
      cloned.source = {
        filename: file.name,
        kind: isPcap ? "pcap" : "csv",
        flows: cloned.source?.flows || 362076,
        windows: cloned.timeline ? cloned.timeline.length : 972,
        t0: cloned.source?.t0 || "2017-07-06T11:59:00Z",
        window_s: 60,
        stride_s: 30,
        size_bytes: file.size,
      };
      cloned.job_id = `job_${Math.random().toString(36).substring(2, 8)}`;

      onProgress?.({ state: "done", progress: 1.0, stage_text: "Fixture shown, your file was not analysed" });
      return { payload: cloned, isMock: true };
    } finally {
      this._mockAbortController = null;
    }
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
    let currentSpeed = Math.max(0.1, Number(speed) || 4);
    let currentT = Math.max(0, parseInt(fromWindow, 10) || 0);

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

    const startLiveSse = (startT = currentT, s = currentSpeed) => {
      if (stopped) return;
      if (es) {
        try {
          es.close();
        } catch {}
        es = null;
      }

      currentT = startT;
      currentSpeed = s;

      try {
        const streamUrl = `${this.apiBase}/api/jobs/${encodeURIComponent(jobId)}/stream?speed=${currentSpeed}&from=${currentT}`;
        es = new EventSource(streamUrl);

        es.addEventListener("window", (e) => {
          if (stopped) return;
          try {
            const winData = JSON.parse(e.data);
            if (winData.t < startT) {
              // Discard past frames if backend stream started before scrub position
              return;
            }
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
          if (stopped) return;
          stop();
          // Real error signaling without silent mock fallback
          onError?.(err || new Error("Live SSE stream disconnected"));
        };
      } catch (err) {
        stop();
        onError?.(err);
      }
    };

    // Attempt live SSE connection if not in mock mode and jobId is present
    if (!this.useMock && jobId) {
      startLiveSse(currentT, currentSpeed);
    } else {
      // Mock / Offline deterministic playback
      runLocalMock(currentT);
    }

    return {
      stop,
      setSpeed(newSpeed) {
        const s = Math.max(0.1, Number(newSpeed) || 4);
        currentSpeed = s;
        if (!stopped) {
          if (!this.useMock && jobId && es) {
            startLiveSse(currentT, currentSpeed);
          } else if (timerId) {
            runLocalMock(currentT);
          }
        }
      },
      getCurrentT() {
        return currentT;
      },
      isLive() {
        return Boolean(!this.useMock && jobId);
      },
    };
  }
}

export const api = new ApiClient();
