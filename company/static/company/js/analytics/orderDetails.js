// company/js/analytics/orderDetails.js

let currentPage = 1;

document.addEventListener('DOMContentLoaded', async () => {

  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiVersion = window.APP_VERSION ? `?v=${encodeURIComponent(window.APP_VERSION)}` : "";
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js${apiVersion}`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  
  const tableBody = document.getElementById("orders-table-body");

  // Filter elements
  const outletSelect = document.getElementById("outlet-filter");
  const deviceSelect = document.getElementById("device-filter");
  const statusSelect = document.getElementById("status-filter");
  const shownSelect = document.getElementById("shown-filter");
  const notifiedSelect = document.getElementById("notified-filter");
  const rangeSelect = document.getElementById("range-filter");
  const fromDate = document.getElementById("from-date");
  const toDate = document.getElementById("to-date");
  const applyBtn = document.getElementById("apply-filters");
  const resetBtn = document.getElementById("reset-filters");
  const customRangeDiv = document.getElementById("custom-date-range");

  const prevBtn = document.getElementById("prev-page");
  const nextBtn = document.getElementById("next-page");
  const pageInfo = document.getElementById("current-page-info");

  rangeSelect.addEventListener("change", () => {
    customRangeDiv.style.display = rangeSelect.value === "custom" ? "block" : "none";
  });

  applyBtn.addEventListener("click", () => {
    currentPage = 1;
    loadFilteredOrders();
  });

  resetBtn.addEventListener("click", () => {
    document.getElementById("order-filter-form").reset();
    customRangeDiv.style.display = "none";
    currentPage = 1;
    loadFilteredOrders();
  });

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        loadFilteredOrders();
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      currentPage++;
      loadFilteredOrders();
    });
  }

  function buildQueryParams() {
    const params = new URLSearchParams();

    if (outletSelect.value) params.append("outlet_id", outletSelect.value);
    if (deviceSelect.value) params.append("device_id", deviceSelect.value);
    if (statusSelect.value) params.append("status", statusSelect.value);
    if (shownSelect.value) params.append("shown_on_tv", shownSelect.value);
    if (notifiedSelect.value) params.append("notified", notifiedSelect.value);

    const range = rangeSelect.value;
    params.append("range", range);

    if (range === "custom") {
      if (fromDate.value) params.append("from", fromDate.value);
      if (toDate.value) params.append("to", toDate.value);
    }

    params.append("page", currentPage); // ✅ Add page param
    return params.toString();
  }

  async function loadFilteredOrders() {
    const query = buildQueryParams();
    // console.log("Query Params:", query); // Debugging line
    const url = `${API_ENDPOINTS.FILTERED_ORDERS}?${query}`;

    try {
      const res = await fetchWithAutoRefresh(url);
      const data = await res.json();
      renderTable(data.orders || data.data || []);
      updatePagination(data.meta || {});
    } catch (error) {
      console.error("Failed to load orders:", error);
    }
  }

  async function populateFilters() {
    try {
      // Fetch Vendors (Outlets)
      const resVendors = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS);
      const { vendors } = await resVendors.json();

      outletSelect.innerHTML = '<option value="">All Outlets</option>';
      vendors.forEach(vendor => {
        outletSelect.innerHTML += `<option value="${vendor.id}">${vendor.name}</option>`;
      });

      // Fetch Devices
      const resDevices = await fetchWithAutoRefresh(API_ENDPOINTS.GET_KEYPAD_DEVICES);
      const { devices } = await resDevices.json();

      deviceSelect.innerHTML = '<option value="">All Devices</option>';
      devices.forEach(device => {
        deviceSelect.innerHTML += `<option value="${device.id}">Device ${device.serial_no}</option>`;
      });
    } catch (error) {
      console.error("Error populating filters:", error);
    }
  }

  function adjustModalWidth() {
    const modal = document.getElementById('timelineModal');
    const items = modal.querySelectorAll('.timeline-item').length;
    const baseWidth = 180; 
    const gap = 70;        

    let newWidth = items * baseWidth + (items  * gap);
    console.log ("Calculated modal width:", newWidth);
    newWidth = Math.min(newWidth, window.innerWidth * 0.95); // max 95vw
    newWidth = Math.max(newWidth, 300); // min 300px

    modal.querySelector('.modal-dialog').style.width = newWidth + 'px';
  }

  function formatDateTime(isoString) {
    if (!isoString) return "N/A";
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return "N/A";
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
  }

  function formatCustomizations(customizations) {
    if (!Array.isArray(customizations) || customizations.length === 0) return "";
    const text = customizations.map((c) => String(c).trim()).filter(Boolean).join(", ");
    return text ? `<div class="buffet-utility-meta"><strong>Customizations:</strong> ${text}</div>` : "";
  }

  function formatRemarks(remarks) {
    const text = (remarks || "").trim();
    return text ? `<div class="buffet-utility-meta"><strong>Remarks:</strong> ${text}</div>` : "";
  }

  function restoreTimelineModalLayout() {
    const modal = document.getElementById('timelineModal');
    if (!modal) return;
    modal.querySelector('.modal-dialog').classList.add('custom-timeline-modal');
    modal.querySelector('.modal-dialog').style.width = '';
    const titleEl = modal.querySelector('.modal-title');
    if (titleEl) titleEl.textContent = 'Order Timeline';
    const bodyEl = modal.querySelector('.modal-body');
    if (bodyEl) {
      bodyEl.innerHTML = `
        <div class="timeline-container">
          <div class="timeline-track"></div>
        </div>
      `;
    }
  }

  function buffetOrderUtilitiesUrl(orderId) {
    const base =
      API_ENDPOINTS.BUFFET_ORDER_UTILITIES ||
      `${window.BASE}company/api/buffet_order_utilities/`;
    return `${base}${orderId}/`;
  }

  async function showBuffetOrderUtilities(orderId) {
    const url = buffetOrderUtilitiesUrl(orderId);

    try {
      const res = await fetchWithAutoRefresh(url);
      const contentType = res.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        console.error("Expected JSON from buffet order utilities API, got:", contentType, url);
        alert("Failed to load order utilities. The utilities API may be unavailable.");
        return;
      }

      const payload = await res.json();

      if (!res.ok) {
        alert(payload.detail || "No utilities found for this order.");
        return;
      }

      const utilities = Array.isArray(payload.utilities) ? payload.utilities : [];
      if (!utilities.length) {
        alert("No utilities found for this order.");
        return;
      }

      const modal = document.getElementById('timelineModal');
      modal.querySelector('.modal-dialog').classList.remove('custom-timeline-modal');
      modal.querySelector('.modal-dialog').style.width = '';

      const titleParts = [`Order #${payload.token_no ?? ""}`];
      if (payload.table_booking_no) {
        titleParts.push(`Table ${payload.table_booking_no}`);
      }
      modal.querySelector('.modal-title').textContent = `Order Utilities — ${titleParts.join(" · ")}`;

      const cardsHtml = utilities.map((utility) => {
        const status = (utility.status || "unknown").toUpperCase();
        const qtyBadge = utility.is_grouped && utility.quantity > 1
          ? `<span class="buffet-utility-qty">Qty: ${utility.quantity}</span>`
          : (utility.quantity > 1 ? `<span class="buffet-utility-qty">Qty: ${utility.quantity}</span>` : "");

        return `
          <div class="buffet-utility-detail-card">
            <div class="buffet-utility-detail-header">
              <h6 class="buffet-utility-name">${utility.utility_name || "Unknown"}</h6>
              ${qtyBadge}
            </div>
            <div class="buffet-utility-detail-row">
              <span class="buffet-utility-label">Current Status</span>
              <span class="buffet-utility-status">${status}</span>
            </div>
            <div class="buffet-utility-detail-row">
              <span class="buffet-utility-label">Latest Status Change</span>
              <span class="buffet-utility-time">${formatDateTime(utility.latest_status_change_at)}</span>
            </div>
            ${formatCustomizations(utility.customizations)}
            ${formatRemarks(utility.remarks)}
          </div>
        `;
      }).join("");

      modal.querySelector('.modal-body').innerHTML = `
        <div class="buffet-order-utilities-list">${cardsHtml}</div>
      `;

      const utilitiesModal = bootstrap.Modal.getOrCreateInstance(modal, {
        backdrop: 'static',
        keyboard: false
      });
      modal.addEventListener('hidden.bs.modal', restoreTimelineModalLayout, { once: true });
      utilitiesModal.show();

    } catch (error) {
      console.error("Failed to load order utilities:", error);
      alert("Failed to load order utilities. See console for details.");
    }
  }

  async function showOrderTimeline(orderId) {
    const url = `${API_ENDPOINTS.ORDER_TIMELINE}${orderId}/`;

    try {
      const res = await fetchWithAutoRefresh(url);
      const timeline = await res.json();

      if (!timeline.length) {
        alert("No status history found for this order.");
        return;
      }

      restoreTimelineModalLayout();

      const timelineHtml = timeline.map((item, index) => {
        const changedBy = item.changed_by || "System";
        const readableTime = timeAgo(new Date(item.changed_at));
        
        return `
          <div class="timeline-item">
            <div class="timeline-dot"></div>
            <div class="timeline-content">
              <div class="timeline-status">${item.new_status}</div>
              <span class="timeline-subtext">by ${changedBy} • ${readableTime}</span>
            </div>
          </div>
        `;
      }).join("");

      document.querySelector("#timelineModal .timeline-track").innerHTML = timelineHtml;
      adjustModalWidth();

      const timelineModal = bootstrap.Modal.getOrCreateInstance(document.getElementById('timelineModal'), {
        backdrop: 'static',
        keyboard: false
      });
      timelineModal.show();

    } catch (error) {
      console.error("Failed to load timeline:", error);
      alert("Failed to load timeline. See console for details.");
    }
  }

  // Convert date to human-readable time (e.g., "2 hours ago")
  function timeAgo(date) {
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    const intervals = [
      { label: 'year', seconds: 31536000 },
      { label: 'month', seconds: 2592000 },
      { label: 'day', seconds: 86400 },
      { label: 'hour', seconds: 3600 },
      { label: 'minute', seconds: 60 },
      { label: 'second', seconds: 1 },
    ];

    for (let interval of intervals) {
      const count = Math.floor(seconds / interval.seconds);
      if (count > 0) {
        return count === 1 ? `1 ${interval.label} ago` : `${count} ${interval.label}s ago`;
      }
    }
    return "just now";
  }


  // Dine Flash: "Booking No". Dine Flash Buffet: "Table No" (table_booking_no).
  // Other flash variants (airline, food, service, calleron) are unaffected.
  const isDineFlash = window.PROJECT_NAME === "dine_flash";
  const isDineFlashBuffet = window.PROJECT_NAME === "dine_flash_buffet";
  const showTableBookingCol = isDineFlash || isDineFlashBuffet;

  function getTableColCount() {
    if (isDineFlashBuffet) return 6;
    if (showTableBookingCol) return 10;
    return 9;
  }

  function renderTable(orders) {
    tableBody.innerHTML = "";

    const colCount = getTableColCount();

    if (orders.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="${colCount}" class="text-center">No orders found.</td></tr>`;
      return;
    }

    orders.forEach((order, index) => {
      const createdDate = new Date(order.created_at);
      const readyDate = order.ready_status ? new Date(order.ready_status) : null;

      const bookingCell = showTableBookingCol
        ? `<td>${order.table_booking_no || "N/A"}</td>`
        : "";

      const statusCells = isDineFlashBuffet
        ? ""
        : `
        <td>${order.status}</td>
        <td>${order.counter_no}</td>
      `;

      const deviceCell = isDineFlashBuffet
        ? ""
        : `<td>${order.device_name || "Not Assigned"}</td>`;

      const readyCell = isDineFlashBuffet
        ? ""
        : `<td>${readyDate ? `${readyDate.toLocaleDateString()}<br>${readyDate.toLocaleTimeString()}` : "N/A"}</td>`;

      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${index + 1}</td>
        <td>${order.token_no}</td>
        ${bookingCell}
        ${statusCells}
        <td>${order.vendor_name || "Not Assigned"}</td>
        ${deviceCell}
        <td>${createdDate.toLocaleDateString()}<br>${createdDate.toLocaleTimeString()}</td>
        ${readyCell}
        <td>
          <button class="icon-btn view-timeline-btn" title="View Order Details" data-order-id="${order.id}">
            <i class="fa-regular fa-eye"></i>
          </button>
        </td>
      `;
      tableBody.appendChild(row);
    });


    // Attach click listeners to timeline buttons after all rows are rendered
    document.querySelectorAll(".view-timeline-btn").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const orderId = e.currentTarget.dataset.orderId;
        if (isDineFlashBuffet) {
          await showBuffetOrderUtilities(orderId);
        } else {
          await showOrderTimeline(orderId);
        }
      });
    });
  }


  function updatePagination(meta) {
    if (!pageInfo || !prevBtn || !nextBtn) return;

    if (meta.page) {
      pageInfo.textContent = `Page ${meta.page}`;
    } else {
      pageInfo.textContent = `Page ${currentPage}`;
    }

    prevBtn.disabled = !meta.has_previous;
    nextBtn.disabled = !meta.has_next;
  }

  // Initial load
  loadFilteredOrders();
  populateFilters();
});
