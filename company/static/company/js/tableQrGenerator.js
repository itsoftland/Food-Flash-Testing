document.addEventListener("DOMContentLoaded", async () => {
  if (!window.BASE) {
    throw new Error("window.BASE is not defined");
  }

  const vendorSelect = document.getElementById("vendor-select");
  const tableInput = document.getElementById("table-no-input");
  const generateBtn = document.getElementById("generate-qr-btn");
  if (!vendorSelect || !tableInput || !generateBtn) {
    return;
  }

  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;

  const vendorError = document.getElementById("vendor-error");
  const tableError = document.getElementById("table-no-error");
  const previewWrap = document.getElementById("qr-preview-wrap");
  const previewTableNo = document.getElementById("preview-table-no");
  const qrCanvas = document.getElementById("qr-canvas");
  const generatedUrlEl = document.getElementById("generated-url");
  const copyUrlBtn = document.getElementById("copy-url-btn");
  const downloadQrBtn = document.getElementById("download-qr-btn");
  const printQrBtn = document.getElementById("print-qr-btn");
  const printVendorName = document.getElementById("print-vendor-name");
  const printTableNo = document.getElementById("print-table-no");
  const printQrImage = document.getElementById("print-qr-image");

  let currentQrUrl = "";
  let currentTableNo = "";
  let currentVendorName = "";

  function isPositiveInteger(value) {
    const text = String(value ?? "").trim();
    return /^[1-9]\d*$/.test(text);
  }

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
      showFieldError(vendorSelect, vendorError, "Please select an outlet.");
      return null;
    }
    clearFieldError(vendorSelect, vendorError);
    return value;
  }

  function validateTableInput() {
    const value = tableInput.value.trim();
    if (!value) {
      showFieldError(tableInput, tableError, "Table number is required.");
      return null;
    }
    if (!isPositiveInteger(value)) {
      showFieldError(tableInput, tableError, "Table number must be a positive integer (1 or greater).");
      return null;
    }
    clearFieldError(tableInput, tableError);
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
    const tableNo = validateTableInput();
    if (!vendorId || !tableNo) {
      return;
    }

    generateBtn.disabled = true;
    generateBtn.textContent = "Generating…";

    try {
      const payload = { table_no: tableNo };
      if (vendorId) {
        payload.vendor_id = vendorId;
      }

      const response = await fetchWithAutoRefresh(API_ENDPOINTS.GENERATE_BUFFET_TABLE_QR, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.error || "Failed to generate QR.");
      }

      currentQrUrl = result.qr_url;
      currentTableNo = result.table_no || tableNo;
      currentVendorName = result.vendor_name || getSelectedVendorLabel();

      generatedUrlEl.textContent = currentQrUrl;
      previewTableNo.textContent = currentTableNo;
      printTableNo.textContent = currentTableNo;
      if (printVendorName) {
        printVendorName.textContent = currentVendorName;
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

  tableInput.addEventListener("input", () => {
    if (tableInput.classList.contains("is-invalid")) {
      validateTableInput();
    }
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
    link.download = `table-${currentTableNo || "qr"}-qr.png`;
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
