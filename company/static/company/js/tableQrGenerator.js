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
  const saveQrBtn = document.getElementById("save-qr-btn");
  const printVendorName = document.getElementById("print-vendor-name");
  const printTableNo = document.getElementById("print-table-no");
  const printQrImage = document.getElementById("print-qr-image");
  const savedQrTbody = document.getElementById("saved-qr-tbody");
  const savedQrTable = document.getElementById("saved-qr-table");
  const savedQrEmpty = document.getElementById("saved-qr-empty");
  const savedQrError = document.getElementById("saved-qr-error");

  let currentQrUrl = "";
  let currentQrToken = "";
  let currentTableNo = "";
  let currentVendorId = "";
  let currentVendorName = "";
  let savedQrCache = [];

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

  function savedQrDeleteUrl(savedId) {
    const base =
      API_ENDPOINTS.BUFFET_SAVED_TABLE_QRS ||
      `${window.BASE}company/api/buffet_saved_table_qrs/`;
    return `${base}${savedId}/`;
  }

  function formatSavedAt(isoString) {
    if (!isoString) {
      return "—";
    }
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) {
      return isoString;
    }
    return date.toLocaleString();
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

  async function showQrPreview({ qrUrl, qrToken, tableNo, vendorId, vendorName }) {
    currentQrUrl = qrUrl || "";
    currentQrToken = qrToken || "";
    currentTableNo = tableNo || "";
    currentVendorId = vendorId || "";
    currentVendorName = vendorName || getSelectedVendorLabel();

    generatedUrlEl.textContent = currentQrUrl;
    previewTableNo.textContent = currentTableNo;
    printTableNo.textContent = currentTableNo;
    if (printVendorName) {
      printVendorName.textContent = currentVendorName;
    }

    await renderQr(currentQrUrl);
    previewWrap.classList.add("visible");
    previewWrap.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function setSavedQrError(message) {
    if (!savedQrError) {
      return;
    }
    if (!message) {
      savedQrError.style.display = "none";
      savedQrError.textContent = "";
      return;
    }
    savedQrError.textContent = message;
    savedQrError.style.display = "block";
  }

  function renderSavedQrList(rows) {
    if (!savedQrTbody || !savedQrTable || !savedQrEmpty) {
      return;
    }

    savedQrTbody.innerHTML = "";
    const items = Array.isArray(rows) ? rows : [];
    savedQrCache = items;

    if (items.length === 0) {
      savedQrTable.style.display = "none";
      savedQrEmpty.classList.add("visible");
      return;
    }

    savedQrEmpty.classList.remove("visible");
    savedQrTable.style.display = "table";

    for (const row of items) {
      const tr = document.createElement("tr");
      tr.dataset.savedId = String(row.id);

      const outletTd = document.createElement("td");
      outletTd.textContent = row.vendor_label || row.vendor_name || "—";

      const tableTd = document.createElement("td");
      tableTd.textContent = row.table_no || "—";

      const savedTd = document.createElement("td");
      savedTd.textContent = formatSavedAt(row.created_at);

      const actionsTd = document.createElement("td");
      actionsTd.className = "text-end";

      const viewBtn = document.createElement("button");
      viewBtn.type = "button";
      viewBtn.className = "btn btn-sm btn-outline-secondary me-2 saved-qr-view-btn";
      viewBtn.dataset.savedId = String(row.id);
      viewBtn.innerHTML = '<i class="fas fa-qrcode me-1"></i>View QR';

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "btn btn-sm btn-outline-danger saved-qr-delete-btn";
      deleteBtn.dataset.savedId = String(row.id);
      deleteBtn.innerHTML = '<i class="fas fa-trash me-1"></i>Delete';

      actionsTd.appendChild(viewBtn);
      actionsTd.appendChild(deleteBtn);

      tr.appendChild(outletTd);
      tr.appendChild(tableTd);
      tr.appendChild(savedTd);
      tr.appendChild(actionsTd);
      savedQrTbody.appendChild(tr);
    }
  }

  async function loadSavedQrList() {
    if (!API_ENDPOINTS.BUFFET_SAVED_TABLE_QRS) {
      return;
    }
    setSavedQrError("");
    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.BUFFET_SAVED_TABLE_QRS, {
        method: "GET",
      });
      const result = await response.json().catch(() => ([]));
      if (!response.ok) {
        throw new Error(result?.error || "Failed to load saved QR codes.");
      }
      renderSavedQrList(result);
    } catch (error) {
      console.error("Failed to load saved QR codes:", error);
      setSavedQrError(error.message || "Failed to load saved QR codes.");
      renderSavedQrList([]);
    }
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

      await showQrPreview({
        qrUrl: result.qr_url,
        qrToken: result.qr_token,
        tableNo: result.table_no || tableNo,
        vendorId,
        vendorName: result.vendor_name || getSelectedVendorLabel(),
      });
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

  saveQrBtn?.addEventListener("click", async () => {
    if (!currentQrToken || !currentQrUrl) {
      ModalService.showError("Generate a QR code before saving.");
      return;
    }
    if (!currentVendorId || !currentTableNo) {
      ModalService.showError("Outlet and table number are required to save.");
      return;
    }

    saveQrBtn.disabled = true;
    const originalLabel = saveQrBtn.innerHTML;
    saveQrBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Saving…';

    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.BUFFET_SAVED_TABLE_QRS, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vendor_id: currentVendorId,
          table_no: currentTableNo,
          qr_token: currentQrToken,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(result?.error || "Failed to save QR.");
      }
      ModalService.showSuccess("QR saved successfully.");
      await loadSavedQrList();
    } catch (error) {
      console.error("Save QR failed:", error);
      ModalService.showError(error.message || "Failed to save QR. Please try again.");
    } finally {
      saveQrBtn.disabled = false;
      saveQrBtn.innerHTML = originalLabel;
    }
  });

  savedQrTbody?.addEventListener("click", async (event) => {
    const viewBtn = event.target.closest(".saved-qr-view-btn");
    const deleteBtn = event.target.closest(".saved-qr-delete-btn");

    if (viewBtn) {
      const savedId = viewBtn.dataset.savedId;
      try {
        const saved = savedQrCache.find((item) => String(item.id) === String(savedId));
        if (!saved || !saved.qr_token || !saved.qr_url) {
          throw new Error("Saved QR not found.");
        }
        await showQrPreview({
          qrUrl: saved.qr_url,
          qrToken: saved.qr_token,
          tableNo: saved.table_no,
          vendorId: saved.vendor_id,
          vendorName: saved.vendor_name || saved.vendor_label,
        });
        if (vendorSelect && saved.vendor_id) {
          vendorSelect.value = String(saved.vendor_id);
        }
        if (tableInput && saved.table_no) {
          tableInput.value = saved.table_no;
        }
      } catch (error) {
        console.error("View saved QR failed:", error);
        ModalService.showError(error.message || "Failed to view saved QR.");
        await loadSavedQrList();
      }
      return;
    }

    if (deleteBtn) {
      const savedId = deleteBtn.dataset.savedId;
      if (!savedId) {
        return;
      }
      const confirmed = window.confirm(
        "Remove this QR from the saved list? Printed or copied QR codes will continue to work."
      );
      if (!confirmed) {
        return;
      }

      deleteBtn.disabled = true;
      try {
        const response = await fetchWithAutoRefresh(savedQrDeleteUrl(savedId), {
          method: "DELETE",
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(result?.error || "Failed to delete saved QR.");
        }
        ModalService.showSuccess("Saved QR deleted.");
        await loadSavedQrList();
      } catch (error) {
        console.error("Delete saved QR failed:", error);
        ModalService.showError(error.message || "Failed to delete saved QR.");
        deleteBtn.disabled = false;
      }
    }
  });

  await loadSavedQrList();
});
