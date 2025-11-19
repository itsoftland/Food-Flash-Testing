/**
 * ==========================================================
 * 📘 Full Scanner (stable reads + TRY_HARDER + candidate voting)
 * File: /orders/static/orders/js/scanner.js
 *
 * Features:
 *  - Dynamically loads ZXing UMD
 *  - Picks rear camera when available
 *  - Probes and toggles torch when supported
 *  - Waits for video stabilization before decoding
 *  - Uses TRY_HARDER hints and restricts formats
 *  - Candidate voting (require N identical reads)
 *  - Fallback timeout chooses best candidate
 *  - Detailed debug raw output (JSON.stringify) for exact BCBP strings
 *  - BCBP-aware parsePayload() with PNR fix (7→6 for leading 'E')
 * ==========================================================
 */

document.addEventListener("DOMContentLoaded", async () => {
  const base = window.BASE || "/caller_on/";
  let apiEndpoints = null;
  let ModalService = null;

  try {
    const endpointsModule = await import(`${base}static/utils/js/apiEndpoints.js`);
    apiEndpoints = endpointsModule.API_ENDPOINTS;
  } catch (e) {
    console.warn("apiEndpoints not available:", e);
  }

  try {
    const modalModule = await import(`${base}static/utils/js/services/modalService.js`);
    ModalService = modalModule.ModalService;
  } catch (e) {
    console.warn("ModalService not available:", e);
  }

  // DOM elements (must exist in your modal/page)
  const scannerModalEl = document.getElementById("scannerModal");
  if (!scannerModalEl) {
    console.warn("#scannerModal not found — scanner disabled.");
    return;
  }
  const scannerModal = bootstrap.Modal.getOrCreateInstance(scannerModalEl);
  const video = document.getElementById("scanner-video");
  const statusEl = document.getElementById("scanner-status");
  const closeBtn = document.getElementById("scanner-close-btn");
  const retryBtn = document.getElementById("scanner-retry-btn");
  const manualBtn = document.getElementById("scanner-manual-btn");
  const torchBtn = document.getElementById("scanner-toggle-torch");
  const scanBtnOnPage = document.getElementById("scan-btn");

  // Form fields to autofill
  const fieldFlight = document.getElementById("flight_no");
  const fieldSeat = document.getElementById("seat_no");
  const fieldPnr = document.getElementById("pnr_no");
  const fieldName = document.getElementById("passenger_name");
  const fieldZone = document.getElementById("zone");

  // state
  let ZXing = null;
  let codeReader = null;
  let scanning = false;
  let candidateCounts = {}; // rawString -> count
  let candidateFirstSeen = {}; // rawString -> timestamp
  let acceptedRaw = null;
  let activeDeviceId = null;
  let torchAvailable = false;
  let torchOn = false;
  let decodeTimeoutId = null;
  let stabilizationTimeoutId = null;
  let decodeStartTs = null;

  // config (tweak as needed)
  const REQUIRED_MATCHES = 3;    // accept once a candidate seen this many times
  const MAX_WAIT_MS = 7000;     // max wait for stable acceptance (fallback to best candidate)
  const STABILIZE_MS = 700;     // wait for camera to stabilize (video frames)
  const CHECK_STABLE_FRAMES = 3; // require same video dims for N checks

  function setStatus(msg) { if (statusEl) statusEl.textContent = msg || ""; }
  function safeLog(...args) { console.log("[scanner]", ...args); }

  // ---- load ZXing UMD bundle ----
  async function loadZXingUmd() {
    if (window.ZXing && window.ZXing.BrowserMultiFormatReader) return window.ZXing;
    return new Promise((resolve, reject) => {
      const src = "https://unpkg.com/@zxing/library@0.18.6/umd/index.min.js";
      const s = document.createElement("script");
      s.src = src; s.async = true;
      s.onload = () => {
        if (window.ZXing && window.ZXing.BrowserMultiFormatReader) resolve(window.ZXing);
        else reject(new Error("ZXing loaded but API missing"));
      };
      s.onerror = (e) => reject(new Error("Failed to load ZXing UMD: " + e));
      document.body.appendChild(s);
    });
  }

  // ---- pick rear camera deviceId if available ----
  async function pickRearCameraDeviceId() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoInputs = devices.filter(d => d.kind === "videoinput");
      if (!videoInputs.length) return null;
      for (const dev of videoInputs) {
        const label = (dev.label || "").toLowerCase();
        if (label.includes("back") || label.includes("rear") || label.includes("environment")) return dev.deviceId;
      }
      // fallback: choose last device (often rear on phones)
      return videoInputs[videoInputs.length - 1].deviceId;
    } catch (err) {
      console.warn("enumerateDevices failed:", err);
      return null;
    }
  }

  // ---- probe torch support quickly ----
  async function probeTorch(deviceId) {
    try {
      const constraints = {
        video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: "environment" } },
        audio: false
      };
      const s = await navigator.mediaDevices.getUserMedia(constraints);
      const track = s.getVideoTracks()[0];
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      const ok = Boolean(caps && caps.torch);
      try { s.getTracks().forEach(t => t.stop()); } catch (e) {}
      return ok;
    } catch (err) {
      console.warn("probeTorch failed:", err);
      return false;
    }
  }

  // ---- wait for video to have stable frames (dimensions) ----
  async function waitForVideoReady(maxWait = STABILIZE_MS) {
    if (!video) return;
    try { await video.play().catch(()=>{}); } catch(e) {}
    let stableCount = 0;
    const start = performance.now();
    let lastW = video.videoWidth;
    let lastH = video.videoHeight;

    while (performance.now() - start < maxWait) {
      await new Promise(r => setTimeout(r, 80));
      const w = video.videoWidth, h = video.videoHeight;
      if (w === lastW && h === lastH && w > 0 && h > 0) {
        stableCount++;
      } else {
        stableCount = 0;
        lastW = w; lastH = h;
      }
      if (stableCount >= CHECK_STABLE_FRAMES && video.readyState >= 3) return true;
    }
    return video.readyState >= 2 && video.videoWidth > 0;
  }

  // ---- candidate aggregator helpers ----
  function resetCandidates() {
    candidateCounts = {};
    candidateFirstSeen = {};
    acceptedRaw = null;
    if (decodeTimeoutId) {
      clearTimeout(decodeTimeoutId);
      decodeTimeoutId = null;
    }
  }

  function acceptBestCandidateOrShowRaw() {
    let best = null, bestCount = 0;
    for (const key of Object.keys(candidateCounts)) {
      const c = candidateCounts[key] || 0;
      if (c > bestCount) { best = key; bestCount = c; }
    }
    if (best) {
      safeLog("Fallback accept best candidate:", best, bestCount);
      processAcceptedRaw(best);
    } else {
      safeLog("No candidates found within timeout");
      const message = "Scan timed out. Please try again or enter details manually.";
      setStatus(message);
      ModalService && ModalService.showError && ModalService.showError(message);
    }
    resetCandidates();
  }

  // ---- process accepted raw (fill fields + UI) ----
  function processAcceptedRaw(raw) {
    acceptedRaw = raw;
    const parsed = parsePayload(raw || "");
    safeLog("Accepted raw -> parsed:", parsed);
    if (parsed.flight_no && fieldFlight) fieldFlight.value = parsed.flight_no;
    if (parsed.seat_no && fieldSeat) fieldSeat.value = parsed.seat_no;
    if (parsed.pnr_no && fieldPnr) fieldPnr.value = parsed.pnr_no;
    if (parsed.passenger_name && fieldName) fieldName.value = parsed.passenger_name;
    if (parsed.zone && fieldZone) fieldZone.value = parsed.zone;
    if (ModalService && ModalService.showToast) ModalService.showToast("Scan successful — form auto-filled.");
    else setStatus("Scan successful — form auto-filled.");
    // close modal shortly so user sees result
    setTimeout(()=> { try{ scannerModal.hide(); } catch(e){}; setStatus(""); }, 700);
  }

  // ---- parsePayload: BCBP-aware + heuristics + PNR fix ----
  function parsePayload(text) {
        if (!text) return {};
        const raw = String(text).replace(/\r?\n/g, " ").trim();
        const res = { raw, pnr_no: null, seat_no: null, flight_no: null, passenger_name: null, zone: null };

        // ---- helper: clean seat ----
        function cleanSeat(v) {
            if (!v) return null;
            return v.replace(/[^0-9A-Z]/gi, ""); // remove > or other symbols
        }

        // ---- fix wrong 7-char PNRs ----
        function fixPnr(pnr) {
            if (!pnr) return pnr;
            if (pnr.length === 6) return pnr;          // correct
            if (pnr.length === 7 && pnr[0] === "E") {
                return pnr.substring(1);               // drop leading junk
            }
            return pnr;
        }

        // ---- extract name (always works for both samples) ----
        const nameMatch = raw.match(/^M\d?([A-Z\/\-\s]+?)\s{2,}/);
        if (nameMatch) {
            const nameRaw = nameMatch[1].trim();
            if (nameRaw.includes("/")) {
                const [last, first] = nameRaw.split("/");
                res.passenger_name = `${first.trim()} ${last.trim()}`;
            } else {
                res.passenger_name = nameRaw;
            }
        }

        // ---- extract PNR (first 5–7 alphanumeric group after name) ----
        const afterName = raw.replace(/^M\d?[A-Z\/\-\s]+\s{2,}/, "");
        const pnrMatch = afterName.match(/\b([A-Z0-9]{5,7})\b/);
        if (pnrMatch) res.pnr_no = fixPnr(pnrMatch[1]);

        // ---- extract seat (handles 35D, 35D>, 12A#, etc.) ----
        const seatMatch = raw.match(/\b([0-9]{1,2}[A-Z])[>\s]?\b/i);
        if (seatMatch) res.seat_no = cleanSeat(seatMatch[1].toUpperCase());

        // ---- extract flight number (supports: AI0658, AI 0658, AI658) ----
        const flightMatch = raw.match(/\b([A-Z]{2})\s?0?(\d{3,4})\b/);
        if (flightMatch) {
            res.flight_no = `${flightMatch[1].toUpperCase()}${flightMatch[2]}`;
        }

        // ---- zone if present ----
        const zoneMatch = raw.match(/\bZONE[:\s]*([A-Z0-9])\b/i);
        if (zoneMatch) res.zone = zoneMatch[1].toUpperCase();

        return res;
    }


  // ---- toggle torch ----
  async function toggleTorch() {
    try {
      const s = video && video.srcObject;
      if (!s) return false;
      const track = s.getVideoTracks()[0];
      if (!track) return false;
      const caps = track.getCapabilities ? track.getCapabilities() : {};
      if (!caps || !caps.torch) return false;
      torchOn = !torchOn;
      await track.applyConstraints({ advanced: [{ torch: torchOn }] });
      if (torchBtn) torchBtn.classList.toggle("active", torchOn);
      return true;
    } catch (err) {
      console.warn("toggleTorch failed:", err);
      return false;
    }
  }

  // ---- stop scanner cleanly ----
  function stopScanner() {
    setStatus("");
    scanning = false;
    try { if (codeReader && codeReader.reset) codeReader.reset(); } catch(e){}
    try {
      const s = video && video.srcObject;
      if (s && s.getTracks) s.getTracks().forEach(t=>{ try{ t.stop(); } catch(e){} });
      if (video) video.srcObject = null;
    } catch(e){}
    resetCandidates();
    if (decodeTimeoutId) { clearTimeout(decodeTimeoutId); decodeTimeoutId = null; }
    if (stabilizationTimeoutId) { clearTimeout(stabilizationTimeoutId); stabilizationTimeoutId = null; }
    torchOn = false; if (torchBtn) torchBtn.classList.remove("active");
  }

  // ---- start scanner (main flow) ----
  async function startScanner() {
    setStatus("Initializing scanner...");
    safeLog("startScanner");

    // load ZXing
    try { ZXing = await loadZXingUmd(); } catch (e) {
      console.error("ZXing load error:", e);
      setStatus("Scanner unavailable.");
      ModalService && ModalService.showError && ModalService.showError("Scanner unavailable.");
      return;
    }

    // Build hint map (TRY_HARDER + restrict formats)
    let hints = null;
    try {
      hints = new Map();
      hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
      // prefer PDF_417, QR_CODE, AZTEC, DATA_MATRIX
      const formats = [
        ZXing.BarcodeFormat.PDF_417,
        ZXing.BarcodeFormat.QR_CODE,
        ZXing.BarcodeFormat.AZTEC,
        ZXing.BarcodeFormat.DATA_MATRIX
      ];
      hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, formats);
    } catch (e) {
      console.warn("Could not set ZXing hints:", e);
      hints = null;
    }

    try {
      if (codeReader && codeReader.reset) codeReader.reset();
    } catch (e) { /* ignore */ }

    try {
      if (hints && typeof ZXing.BrowserMultiFormatReader === "function") {
        try { codeReader = new ZXing.BrowserMultiFormatReader(hints); }
        catch (e) { codeReader = new ZXing.BrowserMultiFormatReader(); }
      } else codeReader = new ZXing.BrowserMultiFormatReader();
    } catch (err) {
      console.error("create reader failed:", err);
      setStatus("Scanner init failed.");
      return;
    }

    // pick camera
    activeDeviceId = await pickRearCameraDeviceId();

    // torch probe
    torchAvailable = await probeTorch(activeDeviceId);
    if (torchBtn) torchBtn.style.display = torchAvailable ? "inline-block" : "none";

    // getUserMedia and attach
    setStatus("Requesting camera permission...");
    try {
      const constraints = activeDeviceId ? { video: { deviceId: { exact: activeDeviceId } }, audio: false }
                                         : { video: { facingMode: { ideal: "environment" } }, audio: false };

      const s = await navigator.mediaDevices.getUserMedia(constraints);
      video.srcObject = s;
      try { await video.play(); } catch(e) { console.warn("video.play() error:", e); }

      // wait for stabilization
      const ready = await waitForVideoReady(STABILIZE_MS + 300);
      safeLog("video readyState", video.readyState, "w/h", video.videoWidth, video.videoHeight, "stable?", ready);
      // small extra delay to let autofocus/AE settle
      await new Promise(r => setTimeout(r, 180));
    } catch (err) {
      console.error("getUserMedia / play failed:", err);
      setStatus("Camera unavailable.");
      ModalService && ModalService.showError && ModalService.showError("Camera unavailable or permission denied.");
      return;
    }

    // reset candidates and start decode
    resetCandidates();
    setStatus("Scanning...");
    scanning = true;
    decodeStartTs = Date.now();

    // start continuous decode (UMD-friendly)
    try {
      codeReader.decodeFromVideoDevice(activeDeviceId, video, (result, err) => {
        if (!scanning) return;
        if (result) {
          const raw = (result.getText && result.getText()) || result.text || String(result);

          // ----- DEBUG RAW OUTPUT (exact string with spaces) -----
          console.log("\n<start>\n" + JSON.stringify(raw) + "\n</end>\n");

          // voting aggregator
          if (!candidateCounts[raw]) { candidateCounts[raw] = 0; candidateFirstSeen[raw] = Date.now(); }
          candidateCounts[raw] += 1;
          safeLog("candidate seen:", raw, "count:", candidateCounts[raw]);

          // accept if hit required matches
          if (candidateCounts[raw] >= REQUIRED_MATCHES) {
            try { codeReader.reset(); } catch (e) {}
            processAcceptedRaw(raw);
            resetCandidates();
            return;
          }
        }
        // timeout fallback
        if (Date.now() - decodeStartTs > MAX_WAIT_MS) {
          try { codeReader.reset(); } catch(e){}
          acceptBestCandidateOrShowRaw();
        }
      });
    } catch (err) {
      console.error("decodeFromVideoDevice error:", err);
      setStatus("Scanner error.");
      ModalService && ModalService.showError && ModalService.showError("Scanner error. Try again.");
      scanning = false;
    }
  }

  // ---- UI bindings ----
  if (closeBtn) closeBtn.addEventListener("click", () => scannerModal.hide());

  if (retryBtn) retryBtn.addEventListener("click", async () => {
    setStatus("Restarting scanner...");
    stopScanner();
    setTimeout(() => startScanner(), 300);
  });

  if (manualBtn) manualBtn.addEventListener("click", () => {
    try { scannerModal.hide(); } catch(e) {}
    if (fieldFlight) fieldFlight.focus();
  });

  if (torchBtn) torchBtn.addEventListener("click", async () => {
    const ok = await toggleTorch();
    if (!ok) {
      ModalService && ModalService.showToast && ModalService.showToast("Torch not supported on this device.");
    }
  });

  if (scanBtnOnPage) scanBtnOnPage.addEventListener("click", () => {
    if (scanBtnOnPage.classList.contains("disabled-feature")) return;
    try { scannerModal.show(); } catch(e) {}
  });

  scannerModalEl.addEventListener("shown.bs.modal", () => {
    setTimeout(() => { if (!scanning) startScanner(); }, 150);
  });

  scannerModalEl.addEventListener("hidden.bs.modal", () => { stopScanner(); });

  window.addEventListener("pagehide", () => stopScanner());
  window.addEventListener("beforeunload", () => stopScanner());

  safeLog("Stable scanner module loaded.");
});
