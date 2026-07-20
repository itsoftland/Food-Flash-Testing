document.addEventListener("DOMContentLoaded", async () => {
  if (!window.BASE) {
    throw new Error("window.BASE is not defined");
  }

  const vendorSelect = document.getElementById("vendor-select");
  const generateBtn = document.getElementById("generate-qr-btn");
  if (!vendorSelect || !generateBtn) {
    return;
  }

  // Cache-bust dynamic imports so newly added endpoints are picked up after deploy.
  const assetVersion = encodeURIComponent(window.APP_VERSION || "1.0.0");
  const authModule = await import(
    `${window.BASE}static/utils/js/services/authFetchService.js?v=${assetVersion}`
  );
  const apiModule = await import(
    `${window.BASE}static/utils/js/apiEndpoints.js?v=${assetVersion}`
  );
  const modalModule = await import(
    `${window.BASE}static/utils/js/services/modalService.js?v=${assetVersion}`
  );

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;
  const generateHospitalBranchQrUrl =
    API_ENDPOINTS.GENERATE_HOSPITAL_BRANCH_QR ||
    `${window.BASE}company/api/generate_hospital_branch_qr/`;

  const vendorError = document.getElementById("vendor-error");
  const previewWrap = document.getElementById("qr-preview-wrap");
  const previewVendorName = document.getElementById("preview-vendor-name");
  const qrCanvas = document.getElementById("qr-canvas");
  const generatedUrlEl = document.getElementById("generated-url");
  const copyUrlBtn = document.getElementById("copy-url-btn");
  const downloadQrBtn = document.getElementById("download-qr-btn");
  const printQrBtn = document.getElementById("print-qr-btn");
  const printVendorName = document.getElementById("print-vendor-name");
  const printVendorLocation = document.getElementById("print-vendor-location");
  const printQrImage = document.getElementById("print-qr-image");

  let currentQrUrl = "";
  let currentVendorName = "";
  let currentVendorId = "";

  function showFieldError(inputEl, errorEl, message) {
    inputEl.classList.add("is-invalid");
    errorEl.textContent = message;
    errorEl.style.display = "block";
  }

  function clearFieldError(inputEl, errorEl) {
    inputEl.classList.remove("is-invalid");
    errorEl.style.display = "none";
    errorEl.textContent = "";
  }

  function validateVendorSelection() {
    const value = vendorSelect.value.trim();
    if (!value) {
      showFieldError(vendorSelect, vendorError, "Please select a branch.");
      return null;
    }
    clearFieldError(vendorSelect, vendorError);
    return value;
  }

  function getSelectedVendorLabel() {
    const option = vendorSelect.options[vendorSelect.selectedIndex];
    return option ? option.textContent.trim() : "";
  }

  async function renderQr(url) {
    if (typeof QRCode === "undefined" || typeof QRCode.toCanvas !== "function") {
      throw new Error("QR rendering library failed to load. Please refresh the page.");
    }
    await QRCode.toCanvas(qrCanvas, url, {
      width: 280,
      margin: 2,
      errorCorrectionLevel: "M",
    });
    printQrImage.src = qrCanvas.toDataURL("image/png");
  }

  generateBtn.addEventListener("click", async () => {
    const vendorId = validateVendorSelection();
    if (!vendorId) {
      return;
    }

    generateBtn.disabled = true;
    generateBtn.textContent = "Generating…";

    try {
      const response = await fetchWithAutoRefresh(generateHospitalBranchQrUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vendor_id: vendorId }),
      });

      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        throw new Error(
          response.ok
            ? "Unexpected response while generating QR."
            : `Failed to generate QR (HTTP ${response.status}).`
        );
      }

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.error || "Failed to generate QR.");
      }

      currentQrUrl = result.qr_url;
      currentVendorId = result.vendor_id || vendorId;
      currentVendorName = result.vendor_name || getSelectedVendorLabel();

      generatedUrlEl.textContent = currentQrUrl;
      if (previewVendorName) {
        previewVendorName.textContent = currentVendorName;
      }
      if (printVendorName) {
        printVendorName.textContent = currentVendorName;
      }
      if (printVendorLocation) {
        printVendorLocation.textContent = result.vendor_location || "";
      }

      await renderQr(currentQrUrl);
      previewWrap.classList.add("visible");
    } catch (error) {
      console.error("QR generation failed:", error);
      ModalService.showError(error.message || "Failed to generate QR. Please try again.");
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate QR";
    }
  });

  vendorSelect.addEventListener("change", () => {
    if (vendorSelect.classList.contains("is-invalid")) {
      validateVendorSelection();
    }
    previewWrap.classList.remove("visible");
  });

  copyUrlBtn?.addEventListener("click", async () => {
    if (!currentQrUrl) {
      return;
    }
    try {
      await navigator.clipboard.writeText(currentQrUrl);
      ModalService.showSuccess("URL copied to clipboard.");
    } catch (error) {
      console.error("Copy failed:", error);
      ModalService.showError("Unable to copy URL. Please copy it manually.");
    }
  });

  downloadQrBtn?.addEventListener("click", () => {
    if (!currentQrUrl || !qrCanvas) {
      return;
    }
    const link = document.createElement("a");
    const safeName = String(currentVendorId || "branch").replace(/[^\w.-]+/g, "-");
    link.download = `branch-${safeName}-qr.png`;
    link.href = qrCanvas.toDataURL("image/png");
    link.click();
  });

  printQrBtn?.addEventListener("click", () => {
    if (!currentQrUrl) {
      return;
    }
    window.print();
  });
});
