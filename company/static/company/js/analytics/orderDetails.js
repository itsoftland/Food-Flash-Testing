// company/js/analytics/orderDetails.js
import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { API_ENDPOINTS } from '/static/utils/js/apiEndpoints.js';

let currentPage = 1;

document.addEventListener('DOMContentLoaded', () => {
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
    console.log("Query Params:", query); // Debugging line
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
      const resVendors = await fetchWithAutoRefresh('/company/api/get_vendors/');
      const { vendors } = await resVendors.json();

      outletSelect.innerHTML = '<option value="">All Outlets</option>';
      vendors.forEach(vendor => {
        outletSelect.innerHTML += `<option value="${vendor.id}">${vendor.name}</option>`;
      });

      // Fetch Devices
      const resDevices = await fetchWithAutoRefresh('/company/api/get_devices/');
      const { devices } = await resDevices.json();

      deviceSelect.innerHTML = '<option value="">All Devices</option>';
      devices.forEach(device => {
        deviceSelect.innerHTML += `<option value="${device.id}">Device ${device.serial_no}</option>`;
      });
    } catch (error) {
      console.error("Error populating filters:", error);
    }
  }

  function renderTable(orders) {
    tableBody.innerHTML = "";
    if (orders.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="8" class="text-center">No orders found.</td></tr>`;
      return;
    }

    orders.forEach((order, index) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${index + 1}</td>
        <td>${order.token_no}</td>
        <td>${order.status}</td>
        <td>${order.counter_no}</td>
        <td>${order.vendor_name || "Not Assigned"}</td>
        <td>${order.device_name || "Not Assigned"}</td>
        <td>${new Date(order.created_at).toLocaleString()}</td>
        <td>--</td>
      `;
      tableBody.appendChild(row);
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
