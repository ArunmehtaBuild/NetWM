/**
 * NetWM Upload & Capture Ingestion Panel
 * Handles drag-drop file upload, format validation, demo scenario selection,
 * and live / simulated job progress tracking.
 * See frontend/PLAN.md (lines 30, 78-81) & docs/api_contract.md
 */

import { api } from "../api.js";
import { store } from "../store.js";
import { formatBytes } from "../format.js";

export class UploadPanel {
  constructor(modalId = "uploadModal") {
    this.modal = document.getElementById(modalId);
    this.isProcessing = false;

    // Cache elements
    this.dropzone = document.getElementById("uploadDropzone");
    this.fileInput = document.getElementById("captureFileInput");
    this.btnBrowse = document.getElementById("btnBrowseFiles");
    this.btnClose = document.getElementById("btnCloseUploadModal");
    this.btnCancel = document.getElementById("btnCancelUpload");
    this.btnTrigger = document.getElementById("btnUploadCapture");

    // Progress elements
    this.progressContainer = document.getElementById("uploadProgressContainer");
    this.progressBarFill = document.getElementById("uploadProgressBarFill");
    this.percentText = document.getElementById("uploadPercentText");
    this.stageText = document.getElementById("uploadStageText");
    this.fileInfoCard = document.getElementById("uploadFileInfoCard");
    this.fileNameText = document.getElementById("uploadFileNameText");
    this.fileSizeText = document.getElementById("uploadFileSizeText");

    // Error & Demo elements
    this.errorBanner = document.getElementById("uploadErrorBanner");
    this.errorMessageText = document.getElementById("uploadErrorMessageText");
    this.btnRetryUpload = document.getElementById("btnRetryUpload");
    this.demoChips = document.querySelectorAll(".demo-preset-chip");

    this._initEvents();
  }

  _initEvents() {
    // Open modal on trigger click
    if (this.btnTrigger) {
      this.btnTrigger.disabled = false;
      this.btnTrigger.removeAttribute("style");
      this.btnTrigger.title = "Upload capture (.csv, .pcap) or run demo analysis";
      this.btnTrigger.addEventListener("click", () => this.open());
    }

    // Close modal on close / cancel click
    if (this.btnClose) {
      this.btnClose.addEventListener("click", () => this.close());
    }
    if (this.btnCancel) {
      this.btnCancel.addEventListener("click", () => this.close());
    }

    // Close on backdrop click (if not processing)
    if (this.modal) {
      this.modal.addEventListener("click", (e) => {
        if (e.target === this.modal && !this.isProcessing) {
          this.close();
        }
      });
    }

    // Escape key closes modal
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.isOpen() && !this.isProcessing) {
        this.close();
      }
    });

    // File input trigger
    if (this.btnBrowse && this.fileInput) {
      this.btnBrowse.addEventListener("click", (e) => {
        e.stopPropagation();
        this.fileInput.click();
      });
    }

    if (this.dropzone && this.fileInput) {
      this.dropzone.addEventListener("click", () => {
        if (!this.isProcessing) {
          this.fileInput.click();
        }
      });
    }

    // File input change
    if (this.fileInput) {
      this.fileInput.addEventListener("change", (e) => {
        const file = e.target.files?.[0];
        if (file) {
          this.processFile(file);
        }
      });
    }

    // Drag and Drop handling
    if (this.dropzone) {
      ["dragenter", "dragover"].forEach((eventName) => {
        this.dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (!this.isProcessing) {
            this.dropzone.classList.add("drag-over");
          }
        });
      });

      ["dragleave", "drop"].forEach((eventName) => {
        this.dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          e.stopPropagation();
          this.dropzone.classList.remove("drag-over");
        });
      });

      this.dropzone.addEventListener("drop", (e) => {
        if (this.isProcessing) return;
        const dt = e.dataTransfer;
        const file = dt?.files?.[0];
        if (file) {
          this.processFile(file);
        }
      });
    }

    // Retry button on error
    if (this.btnRetryUpload) {
      this.btnRetryUpload.addEventListener("click", () => {
        this.resetState();
      });
    }

    // Demo preset chips
    if (this.demoChips) {
      this.demoChips.forEach((chip) => {
        chip.addEventListener("click", () => {
          if (this.isProcessing) return;
          const demoId = chip.getAttribute("data-demo");
          if (demoId) {
            this.processDemo(demoId, chip.getAttribute("data-name") || demoId);
          }
        });
      });
    }
  }

  isOpen() {
    return this.modal && !this.modal.classList.contains("hidden");
  }

  open() {
    if (!this.modal) return;
    this.resetState();
    this.modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  close() {
    if (this.isProcessing || !this.modal) return;
    this.modal.classList.add("hidden");
    document.body.style.overflow = "";
    this.resetState();
  }

  resetState() {
    this.isProcessing = false;
    if (this.fileInput) this.fileInput.value = "";

    // Show dropzone & demo choices
    if (this.dropzone) this.dropzone.classList.remove("hidden");
    const demoPresets = document.getElementById("uploadDemoPresets");
    if (demoPresets) demoPresets.classList.remove("hidden");

    // Hide progress and error
    if (this.progressContainer) this.progressContainer.classList.add("hidden");
    if (this.errorBanner) this.errorBanner.classList.add("hidden");
    if (this.fileInfoCard) this.fileInfoCard.classList.add("hidden");

    // Reset progress bar
    if (this.progressBarFill) {
      this.progressBarFill.style.width = "0%";
      this.progressBarFill.classList.remove("progress-fill-error", "progress-fill-done");
    }
    if (this.percentText) this.percentText.textContent = "0%";
    if (this.stageText) this.stageText.textContent = "Ready";

    // Enable buttons
    if (this.btnClose) this.btnClose.disabled = false;
    if (this.btnCancel) this.btnCancel.disabled = false;
  }

  showProcessing(fileName, fileSize) {
    this.isProcessing = true;

    // Hide dropzone and presets
    if (this.dropzone) this.dropzone.classList.add("hidden");
    const demoPresets = document.getElementById("uploadDemoPresets");
    if (demoPresets) demoPresets.classList.add("hidden");

    // Show progress and file card
    if (this.errorBanner) this.errorBanner.classList.add("hidden");
    if (this.progressContainer) this.progressContainer.classList.remove("hidden");
    if (this.fileInfoCard) this.fileInfoCard.classList.remove("hidden");

    if (this.fileNameText) this.fileNameText.textContent = fileName;
    if (this.fileSizeText) this.fileSizeText.textContent = formatBytes(fileSize);

    if (this.btnClose) this.btnClose.disabled = true;
    if (this.btnCancel) this.btnCancel.disabled = true;
  }

  updateProgress({ state, progress, stage_text }) {
    const pct = Math.max(0, Math.min(100, Math.round((progress || 0) * 100)));

    if (this.progressBarFill) {
      this.progressBarFill.style.width = `${pct}%`;
    }
    if (this.percentText) {
      this.percentText.textContent = `${pct}%`;
    }
    if (this.stageText) {
      this.stageText.textContent = stage_text || (state === "uploading" ? "Uploading capture..." : "Analyzing...");
    }

    const statusPill = document.getElementById("uploadStatusPill");
    if (statusPill) {
      statusPill.className = `status-pill pill-${state}`;
      statusPill.textContent = (state || "RUNNING").toUpperCase();
    }
  }

  showError(err) {
    this.isProcessing = false;
    if (this.btnClose) this.btnClose.disabled = false;
    if (this.btnCancel) this.btnCancel.disabled = false;

    if (this.progressContainer) this.progressContainer.classList.add("hidden");
    if (this.errorBanner) this.errorBanner.classList.remove("hidden");

    const errCodeEl = document.getElementById("uploadErrorCode");
    if (errCodeEl) {
      errCodeEl.textContent = (err.code || "analysis_error").toUpperCase();
    }
    if (this.errorMessageText) {
      this.errorMessageText.textContent = err.message || "Capture analysis encountered an unexpected error.";
    }
  }

  async processFile(file) {
    // Validate first
    const val = api.validateCaptureFile(file);
    if (!val.valid) {
      this.showError(val);
      return;
    }

    this.showProcessing(file.name, file.size);

    try {
      const result = await api.uploadCapture(file, (prog) => {
        this.updateProgress(prog);
      });

      this._handleSuccess(result, file.name);
    } catch (err) {
      this.showError(err);
    }
  }

  async processDemo(demoId, demoName) {
    this.showProcessing(`${demoName} (.csv)`, 42800000);

    try {
      const result = await api.runDemoAnalysis(demoId, (prog) => {
        this.updateProgress(prog);
      });

      this._handleSuccess(result, `${demoId}.csv`);
    } catch (err) {
      this.showError(err);
    }
  }

  _handleSuccess(result, captureName) {
    const { payload, isMock } = result;

    if (this.progressBarFill) {
      this.progressBarFill.style.width = "100%";
      this.progressBarFill.classList.add("progress-fill-done");
    }
    if (this.percentText) this.percentText.textContent = "100%";
    if (this.stageText) {
      this.stageText.textContent = `Analysis complete. Ingested ${payload.timeline?.length || 0} windows.`;
    }

    const statusPill = document.getElementById("uploadStatusPill");
    if (statusPill) {
      statusPill.className = "status-pill pill-done";
      statusPill.textContent = "COMPLETE";
    }

    // Synchronize with store
    setTimeout(() => {
      this.isProcessing = false;
      this.close();

      // Update scenario selector dropdown value if it matches known demo
      const demoSelector = document.getElementById("demoSelector");
      if (demoSelector) {
        if (captureName.toLowerCase().includes("friday")) {
          demoSelector.value = "friday";
        } else if (captureName.toLowerCase().includes("oracle")) {
          demoSelector.value = "thursday_oracle";
        } else if (captureName.toLowerCase().includes("thursday")) {
          demoSelector.value = "thursday";
        }
      }

      store.set({
        payload,
        isMock,
        demoName: captureName,
        selectedWindow: 0,
        jobStatus: "done",
        replay: {
          playing: false,
          t: 0,
        },
      });
    }, 700);
  }

  render(state) {
    // Can optionally reflect jobStatus in store
    if (state.jobStatus === "running" && !this.isProcessing) {
      // background progress if needed
    }
  }
}
