/* Acoustic Eye — frontend controller (vanilla JS, no build step). */
(function () {
  "use strict";

  const API = ""; // same origin as the FastAPI server

  const els = {
    navLinks: document.querySelectorAll(".nav-link"),
    views: {
      home: document.getElementById("view-home"),
      how: document.getElementById("view-how"),
      about: document.getElementById("view-about"),
    },
    themeToggle: document.getElementById("theme-toggle"),
    healthBanner: document.getElementById("health-banner"),
    maxMb: document.getElementById("max-mb"),
    heroCta: document.getElementById("hero-cta"),
    heroHow: document.getElementById("hero-how"),

    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("file-input"),
    browseBtn: document.getElementById("browse-btn"),
    uploadProgress: document.getElementById("upload-progress"),
    uploadError: document.getElementById("upload-error"),

    localIngest: document.getElementById("local-ingest"),
    pCaptureFps: document.getElementById("p-capture-fps"),
    pMains: document.getElementById("p-mains"),
    pLowpass: document.getElementById("p-lowpass"),
    localPath: document.getElementById("local-path"),
    localStart: document.getElementById("local-start"),
    localDuration: document.getElementById("local-duration"),
    localBtn: document.getElementById("local-btn"),
    localHint: document.getElementById("local-hint"),
    localError: document.getElementById("local-error"),

    stepPreview: document.getElementById("step-preview"),
    previewPlayer: document.getElementById("preview-player"),
    previewUnavailable: document.getElementById("preview-unavailable"),
    metaList: document.getElementById("meta-list"),
    frameNote: document.getElementById("frame-note"),

    stepProcess: document.getElementById("step-process"),
    pDownsample: document.getElementById("p-downsample"),
    pScales: document.getElementById("p-scales"),
    pOrientations: document.getElementById("p-orientations"),
    pHighpass: document.getElementById("p-highpass"),
    pSpecsub: document.getElementById("p-specsub"),
    pTranscribe: document.getElementById("p-transcribe"),
    pTranscribeWrap: document.getElementById("p-transcribe-wrap"),
    startBtn: document.getElementById("start-btn"),
    stageList: document.getElementById("stage-list"),
    procProgress: document.getElementById("proc-progress"),
    procBar: document.getElementById("proc-bar"),
    procLabel: document.getElementById("proc-label"),
    processError: document.getElementById("process-error"),

    stepResults: document.getElementById("step-results"),
    resultAudio: document.getElementById("result-audio"),
    downloadWav: document.getElementById("download-wav"),
    wavProps: document.getElementById("wav-props"),
    denoisedBlock: document.getElementById("denoised-block"),
    denoisedAudio: document.getElementById("denoised-audio"),
    downloadDenoised: document.getElementById("download-denoised"),
    imgWaveform: document.getElementById("img-waveform"),
    imgSpectrogram: document.getElementById("img-spectrogram"),
    nyquistNote: document.getElementById("nyquist-note"),
    analysisSummary: document.getElementById("analysis-summary"),
    analysisGrid: document.getElementById("analysis-grid"),
    bandEnergy: document.getElementById("band-energy"),
    burstList: document.getElementById("burst-list"),
    copyAnalysis: document.getElementById("copy-analysis"),
    transcriptBlock: document.getElementById("transcript-block"),
    transcriptText: document.getElementById("transcript-text"),
    transcriptNote: document.getElementById("transcript-note"),
    notesBlock: document.getElementById("notes-block"),
    notesList: document.getElementById("notes-list"),
    restartBtn: document.getElementById("restart-btn"),
  };

  const STAGE_LABELS = {
    validate: "Validating video",
    read_frames: "Reading & preprocessing frames",
    extract_phase: "Extracting local phase (steerable pyramid)",
    reconstruct: "Reconstructing & aligning band signals",
    filter: "Filtering & normalising",
    generate_audio: "Generating WAV audio",
    visualize: "Rendering waveform & spectrogram",
    analyze: "Analysing signal & writing text",
  };

  let state = { jobId: null, objectUrl: null, polling: null, localMode: false };

  /* ---------------- Navigation & theme ---------------- */
  function showView(view) {
    els.navLinks.forEach((b) => b.classList.toggle("active", b.dataset.view === view));
    Object.entries(els.views).forEach(([k, node]) =>
      node.classList.toggle("active", k === view)
    );
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  els.navLinks.forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.view) showView(btn.dataset.view);
    });
  });
  if (els.heroHow) els.heroHow.addEventListener("click", () => showView("how"));
  if (els.heroCta) {
    els.heroCta.addEventListener("click", () => {
      const target = document.getElementById("step-upload");
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("ae-theme", theme); } catch (e) {}
  }
  els.themeToggle.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "light";
    applyTheme(cur === "light" ? "dark" : "light");
  });
  (function initTheme() {
    let saved = "light";
    try { saved = localStorage.getItem("ae-theme") || saved; } catch (e) {}
    if (!localStorage.getItem("ae-theme") && window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches) {
      saved = "dark";
    }
    applyTheme(saved);
  })();

  /* ---------------- Helpers ---------------- */
  function show(node) { node.classList.remove("hidden"); }
  function hide(node) { node.classList.add("hidden"); }
  function fmtBytes(n) {
    if (!n && n !== 0) return "—";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
  }
  function setMeta(key, value) {
    const dd = els.metaList.querySelector(`dd[data-k="${key}"]`);
    if (dd) dd.textContent = value;
  }
  async function readError(res) {
    try {
      const data = await res.json();
      if (data && data.detail) {
        return typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail);
      }
    } catch (e) {}
    return `Request failed (HTTP ${res.status}).`;
  }

  /* ---------------- Health check ---------------- */
  (async function health() {
    try {
      const res = await fetch(`${API}/health`);
      if (!res.ok) return;
      const h = await res.json();
      if (els.maxMb && h.max_upload_mb) els.maxMb.textContent = h.max_upload_mb;
      if (h.default_processing) {
        const d = h.default_processing;
        els.pDownsample.value = d.downsample;
        els.pScales.value = d.scales;
        els.pOrientations.value = d.orientations;
        els.pHighpass.value = d.high_pass_frequency;
        els.pSpecsub.checked = !!d.spectral_subtraction;
      }
      if (!h.pyrtools_available) {
        els.healthBanner.textContent =
          "Server notice: pyrtools is not installed, so acoustic reconstruction " +
          "cannot run yet. Install it with `pip install pyrtools` and restart the " +
          "server. Upload & validation still work.";
        show(els.healthBanner);
      }

      if (h.transcription_available && els.pTranscribeWrap) {
        els.pTranscribeWrap.hidden = false;
      }

      const li = h.local_ingest || {};
      if (li.enabled) {
        if (li.segment_default_seconds) els.localDuration.value = li.segment_default_seconds;
        if (li.segment_max_seconds) els.localDuration.max = li.segment_max_seconds;
        const roots = (li.allowed_roots || []).join("  ·  ");
        els.localHint.textContent = roots
          ? `Allowed folders: ${roots}  (max segment ${li.segment_max_seconds || 30}s).`
          : `Max segment ${li.segment_max_seconds || 30}s.`;
        show(els.localIngest);
      } else {
        hide(els.localIngest);
      }
    } catch (e) {
      /* server may still be starting; ignore */
    }
  })();

  /* ---------------- Upload ---------------- */
  els.browseBtn.addEventListener("click", () => els.fileInput.click());
  els.dropzone.addEventListener("click", (e) => {
    if (e.target === els.browseBtn) return;
    els.fileInput.click();
  });
  els.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); }
  });
  ["dragenter", "dragover"].forEach((ev) =>
    els.dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      els.dropzone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    els.dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      els.dropzone.classList.remove("dragover");
    })
  );
  els.dropzone.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) uploadFile(f);
  });
  els.fileInput.addEventListener("change", () => {
    const f = els.fileInput.files && els.fileInput.files[0];
    if (f) uploadFile(f);
  });

  const ALLOWED_EXT = [".mp4", ".avi", ".mov", ".mkv", ".webm"];

  async function uploadFile(file) {
    hide(els.uploadError);
    hide(els.stepPreview);
    hide(els.stepProcess);
    hide(els.stepResults);
    stopPolling();

    const lower = file.name.toLowerCase();
    if (!ALLOWED_EXT.some((x) => lower.endsWith(x))) {
      return fail(els.uploadError,
        `Unsupported file type. Please choose one of: ${ALLOWED_EXT.join(", ")}.`);
    }
    if (file.type && file.type.startsWith("audio/")) {
      return fail(els.uploadError, "Audio-only files are not supported. Upload a video.");
    }

    show(els.uploadProgress);
    const fd = new FormData();
    fd.append("file", file, file.name);

    let res;
    try {
      res = await fetch(`${API}/upload`, { method: "POST", body: fd });
    } catch (e) {
      hide(els.uploadProgress);
      return fail(els.uploadError,
        "Could not reach the server. Is the backend running (uvicorn backend.main:app)?");
    }
    hide(els.uploadProgress);

    if (!res.ok) {
      return fail(els.uploadError, await readError(res));
    }

    const data = await res.json();
    state.jobId = data.job_id;
    state.localMode = false;
    populatePreview(file, data.video);
  }

  function fail(node, msg) {
    node.textContent = msg;
    show(node);
  }

  function fillMeta(video, sizeBytes) {
    setMeta("filename", video.filename || "—");
    setMeta("filesize", sizeBytes != null ? fmtBytes(sizeBytes) : "— (local file)");
    setMeta("resolution", `${video.width} × ${video.height}`);
    setMeta("fps", String(video.fps));
    setMeta("duration", `${Number(video.duration_seconds).toFixed(2)} s`);
    setMeta("frames", String(video.frames_read));
    setMeta("frames_meta", String(video.frame_count_metadata));
    setMeta("fourcc", video.fourcc || "—");

    let note = "";
    const mismatch = video.frame_count_metadata &&
      Math.abs(video.frame_count_metadata - video.frames_read) > 2;
    if (video.segment_start_seconds > 0) {
      note = `Analysing a ${video.frames_read}-frame segment starting at ` +
        `${Number(video.segment_start_seconds).toFixed(1)} s of a ` +
        `~${Number(video.source_duration_seconds).toFixed(0)} s source video.`;
    } else if (mismatch) {
      note = `Note: the container reports ${video.frame_count_metadata} frames but ` +
        `only ${video.frames_read} were actually decodable. Acoustic Eye uses the ` +
        `real count (${video.frames_read}).`;
    }
    els.frameNote.textContent = note;

    const nyq = (video.fps / 2).toFixed(1);
    els.nyquistNote.textContent =
      `Output sample rate = frame rate = ${Math.round(video.fps)} Hz. ` +
      `Highest representable frequency (Nyquist) ≈ ${nyq} Hz.`;

    show(els.stepPreview);
    show(els.stepProcess);
    els.stepPreview.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function populatePreview(file, video) {
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = URL.createObjectURL(file);
    els.previewPlayer.src = state.objectUrl;
    show(els.previewPlayer);
    hide(els.previewUnavailable);
    show(els.startBtn);
    els.startBtn.disabled = false;
    fillMeta(video, file.size);
  }

  function populatePreviewLocal(video) {
    els.previewPlayer.removeAttribute("src");
    els.previewPlayer.load && els.previewPlayer.load();
    hide(els.previewPlayer);
    show(els.previewUnavailable);
    fillMeta(video, null);
  }

  /* ---------------- Local-file processing ---------------- */
  els.localBtn.addEventListener("click", processLocal);

  async function processLocal() {
    hide(els.localError);
    hide(els.stepPreview);
    hide(els.stepProcess);
    hide(els.stepResults);
    stopPolling();

    const path = (els.localPath.value || "").trim();
    if (!path) return fail(els.localError, "Enter the full path to a video file.");

    const start = Math.max(0, parseFloat(els.localStart.value) || 0);
    const duration = Math.max(1, parseFloat(els.localDuration.value) || 10);

    els.localBtn.disabled = true;
    els.localBtn.textContent = "Validating…";

    const options = {
      capture_fps: parseFloat(els.pCaptureFps.value) || undefined,
      mains_notch_hz: parseFloat(els.pMains.value) || undefined,
      low_pass_hz: parseFloat(els.pLowpass.value) || undefined,
      downsample: parseFloat(els.pDownsample.value) || undefined,
      scales: parseInt(els.pScales.value, 10) || undefined,
      orientations: parseInt(els.pOrientations.value, 10) || undefined,
      high_pass_frequency: parseFloat(els.pHighpass.value) || undefined,
      spectral_subtraction: !!els.pSpecsub.checked,
      enable_transcription: !!(els.pTranscribe && els.pTranscribe.checked),
    };

    let res;
    try {
      res = await fetch(`${API}/process-local`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: path,
          start_seconds: start,
          duration_seconds: duration,
          options: options,
        }),
      });
    } catch (e) {
      els.localBtn.disabled = false;
      els.localBtn.textContent = "Process local file segment";
      return fail(els.localError, "Could not reach the server.");
    }

    els.localBtn.disabled = false;
    els.localBtn.textContent = "Process local file segment";

    if (!res.ok) return fail(els.localError, await readError(res));

    const data = await res.json();
    state.jobId = data.job_id;
    state.localMode = true;
    populatePreviewLocal(data.video);

    // The backend already started the job; go straight to polling.
    hide(els.processError);
    hide(els.startBtn); // no separate "start" step in local mode
    enterProcessingUI();
    pollStatus();
  }

  /* ---------------- Processing ---------------- */
  els.startBtn.addEventListener("click", startProcessing);

  function enterProcessingUI() {
    buildStageRows();
    show(els.procProgress);
    els.procProgress.querySelector(".progress-bar").classList.add("indeterminate");
    els.procBar.style.width = "";
    els.procLabel.textContent = "Working…";
  }

  function buildStageRows() {
    els.stageList.innerHTML = "";
    Object.keys(STAGE_LABELS).forEach((key) => {
      const row = document.createElement("div");
      row.className = "stage-row pending";
      row.dataset.key = key;
      row.innerHTML = `<span class="stage-ico">○</span><span class="stage-text">${STAGE_LABELS[key]}</span>`;
      els.stageList.appendChild(row);
    });
    show(els.stageList);
  }

  function renderStages(stages) {
    stages.forEach((s) => {
      const row = els.stageList.querySelector(`.stage-row[data-key="${s.key}"]`);
      if (!row) return;
      row.className = `stage-row ${s.state}`;
      const ico = row.querySelector(".stage-ico");
      const txt = row.querySelector(".stage-text");
      if (s.state === "done") ico.textContent = "✓";
      else if (s.state === "running") { ico.innerHTML = '<span class="spin">⟳</span>'; }
      else if (s.state === "error") ico.textContent = "✕";
      else ico.textContent = "○";

      let label = STAGE_LABELS[s.key];
      if (s.state === "running" && typeof s.fraction === "number") {
        label += ` — ${Math.round(s.fraction * 100)}%`;
      }
      txt.textContent = label;
    });
  }

  async function startProcessing() {
    if (!state.jobId || state.localMode) return;
    hide(els.processError);
    hide(els.stepResults);
    els.startBtn.disabled = true;
    enterProcessingUI();
    els.procLabel.textContent = "Starting…";

    const options = {
      capture_fps: parseFloat(els.pCaptureFps.value) || undefined,
      mains_notch_hz: parseFloat(els.pMains.value) || undefined,
      low_pass_hz: parseFloat(els.pLowpass.value) || undefined,
      downsample: parseFloat(els.pDownsample.value) || undefined,
      scales: parseInt(els.pScales.value, 10) || undefined,
      orientations: parseInt(els.pOrientations.value, 10) || undefined,
      high_pass_frequency: parseFloat(els.pHighpass.value) || undefined,
      spectral_subtraction: !!els.pSpecsub.checked,
      enable_transcription: !!(els.pTranscribe && els.pTranscribe.checked),
    };

    let res;
    try {
      res = await fetch(`${API}/process`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: state.jobId, options }),
      });
    } catch (e) {
      els.startBtn.disabled = false;
      hide(els.procProgress);
      return fail(els.processError, "Could not reach the server to start processing.");
    }

    if (!res.ok) {
      els.startBtn.disabled = false;
      hide(els.procProgress);
      return fail(els.processError, await readError(res));
    }

    pollStatus();
  }

  function stopPolling() {
    if (state.polling) { clearTimeout(state.polling); state.polling = null; }
  }

  async function pollStatus() {
    let res;
    try {
      res = await fetch(`${API}/status/${state.jobId}`);
    } catch (e) {
      state.polling = setTimeout(pollStatus, 1500);
      return;
    }
    if (!res.ok) {
      els.startBtn.disabled = false;
      hide(els.procProgress);
      return fail(els.processError, await readError(res));
    }
    const data = await res.json();
    renderStages(data.stages || []);

    // Drive the top progress bar from the phase-extraction fraction when known.
    const phase = (data.stages || []).find((s) => s.key === "extract_phase");
    const bar = els.procProgress.querySelector(".progress-bar");
    if (phase && phase.state === "running" && typeof phase.fraction === "number") {
      bar.classList.remove("indeterminate");
      bar.style.width = `${Math.max(3, phase.fraction * 100)}%`;
      els.procLabel.textContent =
        `Extracting phase information — ${Math.round(phase.fraction * 100)}%`;
    } else {
      bar.classList.add("indeterminate");
      const running = (data.stages || []).find((s) => s.state === "running");
      els.procLabel.textContent = running
        ? STAGE_LABELS[running.key] + "…"
        : "Working…";
    }

    if (data.status === "done" && data.result) {
      stopPolling();
      hide(els.procProgress);
      els.startBtn.disabled = false;
      showResults(data.result);
    } else if (data.status === "error") {
      stopPolling();
      hide(els.procProgress);
      els.startBtn.disabled = false;
      fail(els.processError, data.error || "Processing failed.");
    } else {
      state.polling = setTimeout(pollStatus, 1200);
    }
  }

  /* ---------------- Results ---------------- */
  function resultUrl(name) { return `${API}/result/${encodeURIComponent(name)}`; }

  function showResults(r) {
    const wav = resultUrl(r.wav_filename);
    els.resultAudio.src = wav;
    els.downloadWav.href = wav;
    els.downloadWav.setAttribute("download", r.wav_filename);

    const p = r.wav_properties || {};
    els.wavProps.textContent =
      `WAV: ${p.samplerate || r.sample_rate} Hz · ${p.subtype || "PCM_16"} · ` +
      `${p.channels || 1} ch · ${Number(p.duration || 0).toFixed(2)} s · ` +
      `${r.frames_processed} frames processed.`;

    if (r.denoised_wav_filename) {
      const dw = resultUrl(r.denoised_wav_filename);
      els.denoisedAudio.src = dw;
      els.downloadDenoised.href = dw;
      els.downloadDenoised.setAttribute("download", r.denoised_wav_filename);
      els.denoisedBlock.hidden = false;
    } else {
      els.denoisedBlock.hidden = true;
    }

    els.imgWaveform.src = resultUrl(r.waveform_filename) + `?t=${Date.now()}`;
    els.imgSpectrogram.src = resultUrl(r.spectrogram_filename) + `?t=${Date.now()}`;

    els.nyquistNote.textContent =
      `Sample rate ${r.sample_rate} Hz · Nyquist limit ≈ ${r.nyquist_hz} Hz. ` +
      `Frequencies above this cannot be represented by the video's frame rate.`;

    renderAnalysis(r.analysis || {}, r.analysis_text || "");
    renderTranscript(r.transcript || {});

    const notes = r.notes || [];
    if (notes.length) {
      els.notesList.innerHTML = "";
      notes.forEach((n) => {
        const li = document.createElement("li");
        li.textContent = n;
        els.notesList.appendChild(li);
      });
      els.notesBlock.hidden = false;
    } else {
      els.notesBlock.hidden = true;
    }

    show(els.stepResults);
    els.stepResults.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  let lastAnalysisText = "";

  function renderAnalysis(a, summary) {
    lastAnalysisText = buildAnalysisPlainText(a, summary);
    els.analysisSummary.textContent = summary || "No analysis text was produced.";

    // Key/value grid
    const rows = [
      ["Duration", `${Number(a.duration_seconds || 0).toFixed(2)} s`],
      ["Sample rate", `${a.sample_rate || "?"} Hz`],
      ["Nyquist limit", `${a.nyquist_hz || "?"} Hz`],
      ["Dominant frequency", `${Number(a.dominant_frequency_hz || 0).toFixed(2)} Hz`],
      ["Spectral centroid", `${Number(a.spectral_centroid_hz || 0).toFixed(2)} Hz`],
      ["RMS level", `${Number(a.rms || 0).toFixed(3)}`],
      ["Peak level", `${Number(a.peak || 0).toFixed(3)}`],
      ["Crest factor", `${Number(a.crest_factor_db || 0).toFixed(1)} dB`],
      ["Louder bursts", `${(a.bursts || []).length}`],
    ];
    els.analysisGrid.innerHTML = rows
      .map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`)
      .join("");

    // Band energy bars
    const be = a.band_energy_percent || {};
    const keys = Object.keys(be);
    els.bandEnergy.innerHTML = keys.length
      ? `<h4>Energy by frequency band</h4>` +
        keys
          .map((k) => {
            const pct = Math.max(0, Math.min(100, Number(be[k]) || 0));
            return `<div class="be-row"><span class="be-label">${k}</span>` +
              `<span class="be-track"><span class="be-fill" style="width:${pct}%"></span></span>` +
              `<span class="be-val">${pct.toFixed(0)}%</span></div>`;
          })
          .join("")
      : "";

    // Burst timeline
    const bursts = a.bursts || [];
    els.burstList.innerHTML = bursts.length
      ? `<h4>Louder bursts</h4><ul>` +
        bursts
          .map(
            (b) =>
              `<li><code>${Number(b.start_s).toFixed(2)}–${Number(b.end_s).toFixed(2)} s</code> ` +
              `(${Number(b.duration_s).toFixed(2)} s, level ${Number(b.relative_level).toFixed(2)})</li>`
          )
          .join("") +
        `</ul>`
      : "";
  }

  function buildAnalysisPlainText(a, summary) {
    const lines = [];
    lines.push("ACOUSTIC EYE — SIGNAL ANALYSIS");
    lines.push("");
    if (summary) { lines.push(summary); lines.push(""); }
    lines.push(`Duration:            ${Number(a.duration_seconds || 0).toFixed(2)} s`);
    lines.push(`Sample rate:         ${a.sample_rate || "?"} Hz`);
    lines.push(`Nyquist limit:       ${a.nyquist_hz || "?"} Hz`);
    lines.push(`Dominant frequency:  ${Number(a.dominant_frequency_hz || 0).toFixed(2)} Hz`);
    lines.push(`Spectral centroid:   ${Number(a.spectral_centroid_hz || 0).toFixed(2)} Hz`);
    lines.push(`RMS / peak:          ${Number(a.rms || 0).toFixed(3)} / ${Number(a.peak || 0).toFixed(3)}`);
    lines.push(`Crest factor:        ${Number(a.crest_factor_db || 0).toFixed(1)} dB`);
    const be = a.band_energy_percent || {};
    if (Object.keys(be).length) {
      lines.push("");
      lines.push("Energy by band:");
      Object.keys(be).forEach((k) => lines.push(`  ${k}: ${Number(be[k]).toFixed(0)}%`));
    }
    const bursts = a.bursts || [];
    if (bursts.length) {
      lines.push("");
      lines.push("Louder bursts:");
      bursts.forEach((b) =>
        lines.push(`  ${Number(b.start_s).toFixed(2)}-${Number(b.end_s).toFixed(2)} s (level ${Number(b.relative_level).toFixed(2)})`)
      );
    }
    return lines.join("\n");
  }

  function renderTranscript(t) {
    if (t && t.available && t.text) {
      els.transcriptText.textContent = t.text;
      els.transcriptText.classList.remove("muted");
      els.transcriptNote.textContent =
        (t.language ? `Detected language: ${t.language} ` +
          `(p=${t.language_probability}). ` : "") +
        `Model: ${t.model_size || "tiny"}.`;
    } else {
      els.transcriptText.textContent =
        (t && t.note) ||
        "Speech-to-text was not run. Enable it in Advanced parameters (requires " +
        "faster-whisper on the server).";
      els.transcriptText.classList.add("muted");
      els.transcriptNote.textContent =
        "At ordinary camera frame rates the recovered audio has no speech-band " +
        "content, so this is expected to be empty. It is meant for very " +
        "high-speed captures.";
    }
  }

  if (els.copyAnalysis) {
    els.copyAnalysis.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(lastAnalysisText);
        const prev = els.copyAnalysis.textContent;
        els.copyAnalysis.textContent = "✓ Copied";
        setTimeout(() => (els.copyAnalysis.textContent = prev), 1500);
      } catch (e) {
        // Fallback: select the summary text for manual copy.
        const range = document.createRange();
        range.selectNodeContents(els.analysisSummary);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      }
    });
  }

  els.restartBtn.addEventListener("click", () => {
    stopPolling();
    state.jobId = null;
    state.localMode = false;
    els.fileInput.value = "";
    els.startBtn.disabled = false;
    show(els.previewPlayer);
    hide(els.previewUnavailable);
    hide(els.stepPreview);
    hide(els.stepProcess);
    hide(els.stepResults);
    hide(els.processError);
    hide(els.localError);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
})();
