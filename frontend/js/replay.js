/**
 * NetWM Chronological Replay Controller (H-6)
 *
 * Implements:
 * 1. Play / Pause / Reset / Speed selection controls
 * 2. Synchronized timeline scrubber
 * 3. Store-driven replay state: store.replay { playing, t, speed }
 * 4. Progressive timeline & panel updates on every window event
 * 5. SSE stream integration via api.createReplayStream() with offline mock fallback
 * 6. Clean completion state at end of capture
 *
 * See frontend/PLAN.md & docs/api_contract.md
 */

import { api } from "./api.js";
import { store } from "./store.js";
import { formatIsoTime } from "./format.js";

export class ReplayController {
  constructor() {
    this.btnPlayPause = document.getElementById("btnPlayPause");
    this.btnReset = document.getElementById("btnReset");
    this.speedSelect = document.getElementById("replaySpeedSelect");
    this.scrubber = document.getElementById("replayScrubber");
    this.statusBadge = document.getElementById("replayStatusBadge");
    this.timeText = document.getElementById("replayTimeText");
    this.playPauseText = document.getElementById("playPauseText");
    this.iconPlay = document.querySelector(".icon-play");
    this.iconPause = document.querySelector(".icon-pause");

    this.activeStream = null;
    this.lastPlaying = false;
    this.lastT = -1;
    this.lastSpeed = 4;
    this.isUserScrubbing = false;

    this._bindUiEvents();
  }

  /**
   * Bind user button and slider events
   */
  _bindUiEvents() {
    if (this.btnPlayPause) {
      this.btnPlayPause.addEventListener("click", () => {
        const state = store.getState();
        const replay = state.replay || { playing: false, t: 0, speed: 4 };
        const timeline = state.payload?.timeline || [];
        const maxT = Math.max(0, timeline.length - 1);

        if (replay.playing) {
          // Pause
          store.set({ replay: { playing: false } });
        } else {
          // If at the end, restart from 0
          if (replay.t >= maxT) {
            store.set({
              replay: { playing: true, t: 0 },
              selectedWindow: 0,
            });
          } else {
            store.set({ replay: { playing: true } });
          }
        }
      });
    }

    if (this.btnReset) {
      this.btnReset.addEventListener("click", () => {
        if (this.activeStream) {
          this.activeStream.stop();
          this.activeStream = null;
        }
        store.set({
          replay: { playing: false, t: 0 },
          selectedWindow: 0,
        });
      });
    }

    if (this.speedSelect) {
      this.speedSelect.addEventListener("change", (e) => {
        const newSpeed = parseInt(e.target.value, 10) || 4;
        store.set({ replay: { speed: newSpeed } });
        if (this.activeStream) {
          this.activeStream.setSpeed(newSpeed);
        }
      });
    }

    if (this.scrubber) {
      this.scrubber.addEventListener("input", (e) => {
        this.isUserScrubbing = true;
        // Pause active stream while actively dragging
        if (this.activeStream) {
          this.activeStream.stop();
          this.activeStream = null;
        }
        const targetT = parseInt(e.target.value, 10);
        store.set({
          replay: { t: targetT },
          selectedWindow: targetT,
        });
      });

      this.scrubber.addEventListener("change", (e) => {
        this.isUserScrubbing = false;
        const targetT = parseInt(e.target.value, 10);
        const state = store.getState();
        if (state.replay.playing) {
          // Resume stream from scrubbed window
          this._startStream(targetT, state.replay.speed, state.payload);
        }
      });
    }
  }

  /**
   * Handle store updates
   */
  update(state) {
    const { payload, replay, selectedWindow } = state;
    if (!payload || !payload.timeline || !payload.timeline.length) return;

    const timeline = payload.timeline;
    const maxT = timeline.length - 1;
    const currentT = replay.t !== undefined ? replay.t : selectedWindow;
    const isPlaying = Boolean(replay.playing);
    const speed = replay.speed || 4;

    // 1. Update Scrubber limits & value
    if (this.scrubber) {
      this.scrubber.max = maxT;
      if (!this.isUserScrubbing) {
        this.scrubber.value = currentT;
      }
    }

    // 2. Synchronize Speed dropdown
    if (this.speedSelect && this.speedSelect.value !== String(speed)) {
      this.speedSelect.value = String(speed);
    }

    if (this.lastSpeed !== speed && this.activeStream) {
      this.activeStream.setSpeed(speed);
    }

    // 3. Update Play/Pause button UI
    if (this.btnPlayPause) {
      if (isPlaying) {
        this.btnPlayPause.classList.add("btn-playing");
        if (this.playPauseText) this.playPauseText.textContent = "Pause";
        if (this.iconPlay) this.iconPlay.classList.add("hidden");
        if (this.iconPause) this.iconPause.classList.remove("hidden");
      } else {
        this.btnPlayPause.classList.remove("btn-playing");
        if (this.playPauseText) {
          this.playPauseText.textContent = currentT >= maxT ? "Replay Again" : "Play Replay";
        }
        if (this.iconPlay) this.iconPlay.classList.remove("hidden");
        if (this.iconPause) this.iconPause.classList.add("hidden");
      }
    }

    // 4. Update Status Badge & Time Text
    if (this.statusBadge) {
      if (isPlaying) {
        this.statusBadge.className = "replay-status-badge badge-playing";
        this.statusBadge.textContent = `PLAYING (${speed} w/s)`;
      } else if (currentT >= maxT) {
        this.statusBadge.className = "replay-status-badge badge-completed";
        this.statusBadge.textContent = "COMPLETED";
      } else {
        this.statusBadge.className = "replay-status-badge badge-paused";
        this.statusBadge.textContent = "PAUSED";
      }
    }

    if (this.timeText && timeline[currentT]) {
      const w = timeline[currentT];
      const timeStr = w.ts ? formatIsoTime(w.ts) : "--:--:--";
      this.timeText.textContent = `t=${currentT} / ${maxT} · ${timeStr}`;
    }

    // 5. Manage Stream Lifecycle
    if (isPlaying && (!this.activeStream || this.lastPlaying !== isPlaying)) {
      this._startStream(currentT, speed, payload);
    } else if (!isPlaying && this.activeStream) {
      this.activeStream.stop();
      this.activeStream = null;
    }

    this.lastPlaying = isPlaying;
    this.lastT = currentT;
    this.lastSpeed = speed;
  }

  /**
   * Start stream from specific window
   */
  _startStream(fromT, speed, payload) {
    if (this.activeStream) {
      this.activeStream.stop();
      this.activeStream = null;
    }

    const jobId = payload.job_id || "demo";
    const maxT = payload.timeline.length - 1;

    this.activeStream = api.createReplayStream({
      jobId,
      speed,
      fromWindow: fromT,
      payload,
      onWindow: (winData) => {
        store.set({
          replay: { t: winData.t, playing: true },
          selectedWindow: winData.t,
        });
      },
      onEnd: () => {
        this.activeStream = null;
        store.set({
          replay: { playing: false, t: maxT },
          selectedWindow: maxT,
        });
      },
      onError: (err) => {
        console.warn("Replay stream fallback to local mock playback:", err);
      },
    });
  }
}
