
const statusClassMap = {
  created: 'unknown-color',
  preparing: 'preparing-color',
  ready: 'ready-color',
  allocated: 'ready-color',
  occupied: 'checked-in-color',
  delivered: 'delivered-color',
  checked_in: 'checked-in-color',
  boarding_shortly: 'boarding-shortly-color',
  boarding_announced: 'boarding-announced-color',
  gate_change: 'gate-change-color',
  rescheduled: 'rescheduled-color',
  cancelled: 'cancelled-color',
  booking_cancelled: 'cancelled-color',
  operation_closed: 'boarding-shortly-color',
  utility_transfer: 'ready-color',
};


const payloadStatusMap = {
  checked_in: 'Checked-In',
  boarding_shortly: 'Boarding Shortly',
  boarding_announced: 'Boarding Announced',
  gate_change: 'Gate Change',
  rescheduled: 'Rescheduled',
  cancelled: 'Cancelled',
};
const dineInPayloadStatusMap = {
  waiting: 'Allocation Pending',
  allocated: 'Table Allocated',
  booking_cancelled: 'Booking Cancelled',
  occupied: 'Table Occupied',
  operation_closed: 'Operation Closed',
  utility_transfer: 'Table Transferred',
};

function getActiveVendorLogo() {
  try {
    const prefixedLogo = window.AppUtils?.storageGet?.("activeVendorLogo");
    if (prefixedLogo) return prefixedLogo;
  } catch (e) {
    // Ignore and fall back to legacy key.
  }
  return localStorage.getItem("activeVendorLogo") || "";
}

function getActiveLogoFromHeader() {
  try {
    const activeImg = document.querySelector(".vendor-logo-wrapper.active img");
    if (activeImg && activeImg.src) return activeImg.src;
    const firstImg = document.querySelector(".vendor-logo-wrapper img");
    if (firstImg && firstImg.src) return firstImg.src;
  } catch (e) {
    // Ignore DOM lookup failures.
  }
  return "";
}

function resolveLogo(payload) {
  const raw = (payload && payload.logo_url) || getActiveVendorLogo() || getActiveLogoFromHeader() || "";
  const safe = raw ? String(raw).replace(/ /g, "%20") : "";
  const project = (window.PROJECT_NAME || "dine_flash").trim();
  const fallback = safe.includes(`/${project}/media/`)
    ? safe.replace(`/${project}/media/`, "/media/")
    : safe.includes("/media/")
      ? safe.replace("/media/", `/${project}/media/`)
      : safe;
  return { primary: safe, fallback };
}

function buildLogoImg(payload) {
  const { primary, fallback } = resolveLogo(payload);
  return `<img src="${primary}" data-fallback-src="${fallback}" class="server-logo" alt="Logo" onerror="if(!this.dataset.fallbackApplied){this.dataset.fallbackApplied='1';this.src=this.dataset.fallbackSrc||'';}">`;
}

function buildThankYouMessage(payload) {
  const farewellMessage =
    payload.thank_you_note ||
    "Thank you for dining with us today. We appreciate your visit. Have a wonderful day!";

  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Thank You"}</span>
    </div>

    <div class="thankyou-card">
        <div class="thankyou-icon">✨</div>
        <div class="thankyou-message">
            ${farewellMessage}
        </div>
    </div>
  `;
}


function buildStatusMessage(payload) {
  // console.log("payload status:",payload.status)
  const statusKey = payload?.status || 'unknown';
  const statusClass = statusClassMap[statusKey] || 'unknown-color';
  // console.log("status key:",statusKey)

  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Outlet"}</span>
    </div>
    <div class="status">
        Status: 
        <span class="${statusClass}">
            ${payload.status || "Unknown"}
        </span>
    </div>
    <div class="info-badges">
        <div class="badge">Counter No: ${payload.counter_no || ""}</div>
        <div class="badge">Token No: ${payload.token_no || ""}</div>
    </div>
  `;
}

function buildOfferMessage(payload) {
  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Outlet"}</span>
    </div>
    <div class="response-title">🔥 ${payload.title || ""}</div>
    <div style="color: #333; font-size: 15px;">
        ${payload.body || "Delicious deals await. Come grab your favorite combo now!"}
    </div>
  `;
}

function buildManagerMessage(payload) {
  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Outlet"}</span>
    </div>

    <div class="manager-message-body">
        <div class="manager-badge">Manager Notification</div>
        <div class="custom-manager-message">
            ${payload.status || "Hello! Here's an update regarding your order."}
        </div>
    </div>
  `;
}

function buildAirlineManagerMessage(payload) {
  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Airline Outlet"}</span>
    </div>

    <div class="manager-message-body">
      <div class="manager-badge">Notification</div>

      <div class="passenger-info">
        👤 <strong>${payload.passenger_name || "Unknown Passenger"}</strong>
      </div>

      <div class="custom-manager-message">
        ${payload.status || "Update received from airline staff."}
      </div>
    </div>
  `;
}

function buildFlightStatusMessage(payload) {
  const statusKey = payload?.status?.toLowerCase() || 'unknown';
  const statusClass = statusClassMap[statusKey] || 'unknown-color';
  const payloadStatus = payloadStatusMap[statusKey];
  const maskedCode = maskSequenceCode(payload.sequence_code);
  const encodedRealCode = btoa(payload.sequence_code); // base64 encode real value

  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Airline Service"}</span>
    </div>

    <div class="status">
        Status:
        <span class="${statusClass}">
            ${payloadStatus || "Unknown"}
        </span>
    </div>

    <div class="flight-card-body">
      <!-- Passenger Name -->
      <div class="flight-card-header">
        <span class="passenger-icon" aria-hidden="true">👤</span>
        <div class="passenger-name">${payload.passenger_name || "-"}</div>
      </div>

      <!-- Sequence Code -->
      <div class="sequence-code-row">
        <span class="sequence-code-label">Sequence Code:</span>
        <div class="sequence-code-display d-flex align-items-center">
          <span class="sequence-code-text" data-bs-toggle="tooltip" 
                data-bs-placement="top" title="Copy to recheck">
            ${maskedCode || "-"}
          </span>
          <button class="btn btn-outline-primary ms-2 secure-copy-btn" 
                  data-code="${encodedRealCode}">
            <i class="fas fa-copy"></i>
          </button>
        </div>
      </div>

      <!-- Flight + Seat Row -->
      <div class="flight-row">
        <div class="flight-item">
          <span class="flight-icon" aria-hidden="true">✈️</span>
          <span class="flight-label">Flight</span>
          <span class="flight-badge">${payload.flight_no || "-"}</span>
        </div>

        <div class="flight-item">
          <span class="seat-icon" aria-hidden="true">💺</span>
          <span class="flight-label">Seat</span>
          <span class="flight-badge seat-badge">${payload.seat_no || "-"}</span>
        </div>
      </div>

      <!-- PNR + Zone Row -->
      <div class="pnr-zone-row">
        <div class="pnr-item">
          <span class="pnr-icon" aria-hidden="true">🎫</span>
          <span class="flight-label">PNR</span>
          <span class="flight-badge pnr-badge">${payload.pnr_no || "-"}</span>
        </div>

        <div class="zone-item">
          <span class="zone-icon" aria-hidden="true">🛫</span>
          <span class="flight-label">Zone</span>
          <span class="flight-badge zone-badge">${payload.zone || "-"}</span>
        </div>
      </div>
    </div>
  `;
}

/** Dine Flash Buffet customer chat only — other flash variants must not use buffet-specific UI. */
function isDineFlashBuffetChatSurface() {
  const project = String(window.PROJECT_NAME || "").trim().toLowerCase();
  if (project === "dine_flash_buffet") return true;
  const path = String(window.location?.pathname || "").toLowerCase();
  return path.includes("/dine_flash_buffet") || path.includes("/dineflashbuffet");
}

function normalizeBuffetUtilitiesBlocks(payload) {
  const u = payload.utilities;
  if (Array.isArray(u) && u.length) {
    return u;
  }
  const legacy = payload.ready_utilities;
  if (Array.isArray(legacy) && legacy.length) {
    return legacy.map((x) => ({
      id: x.id,
      name: x.name,
      lines: [{ status: "ready", quantity: 1, item_id: null }],
    }));
  }
  return [];
}

function formatBuffetLineDetailsInline(remarks, customizations) {
  const parts = [];
  const cust = Array.isArray(customizations) ? customizations : [];
  const custStr = cust.map((c) => String(c).trim()).filter(Boolean).join(", ");
  if (custStr) parts.push(custStr);
  const rem = (remarks || "").trim();
  if (rem) parts.push(`Note: ${rem}`);
  return parts.length ? ` <span class="buffet-line-details text-muted">(${parts.join(" · ")})</span>` : "";
}

function formatBuffetLineDetailsBlock(remarks, customizations) {
  const bits = [];
  const cust = Array.isArray(customizations) ? customizations : [];
  const custStr = cust.map((c) => String(c).trim()).filter(Boolean).join(", ");
  if (custStr) bits.push(`<div class="buffet-line-customizations">${custStr}</div>`);
  const rem = (remarks || "").trim();
  if (rem) bits.push(`<div class="buffet-line-remarks"><strong>Note:</strong> ${rem}</div>`);
  return bits.join("");
}

function formatBuffetUtilityLinesHtml(lines) {
  const arr = Array.isArray(lines) ? lines : [];
  if (!arr.length) {
    return '<span class="text-muted">No lines</span>';
  }
  return arr
    .map((ln) => {
      const st = String(ln.status || "unknown").toLowerCase();
      const cls = statusClassMap[st] || "unknown-color";
      const qty = ln.quantity != null ? Number(ln.quantity) : 1;
      const q = Number.isFinite(qty) && qty !== 1 ? ` ×${qty}` : "";
      const detailsBlock = formatBuffetLineDetailsBlock(ln.remarks, ln.customizations);
      return `
        <div class="buffet-utility-line mb-2">
          <span class="buffet-status-badge ${cls} me-1 mb-1 d-inline-block">${st.toUpperCase()}${q}</span>
          ${detailsBlock}
        </div>`;
    })
    .join("");
}

function buildBuffetUtilitiesStationCard(payload) {
  const blocks = normalizeBuffetUtilitiesBlocks(payload);
  const rows = blocks
    .map((b) => {
      const name = (b && b.name) ? String(b.name) : "Station";
      const linesHtml = formatBuffetUtilityLinesHtml(b.lines);
      return `
        <div class="buffet-station-row mb-2 pb-2 border-bottom border-light">
          <div class="fw-bold text-dark mb-1">${name}</div>
          <div>${linesHtml}</div>
        </div>`;
    })
    .join("");

  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Buffet Service"}</span>
    </div>
    <div class="buffet-status-card buffet-utilities-ready-card">
        <div class="buffet-item-header">
            <span class="buffet-item-name">Station update</span>
        </div>
        <div class="buffet-status-body">
            ${rows || '<span class="text-muted">No stations</span>'}
        </div>
        <div class="buffet-status-body small text-muted mt-2">
            Order <strong>#${payload.token_no ?? ""}</strong>
        </div>
    </div>
  `;
}

function buildBuffetUtilitiesStatusSummary(payload) {
  const blocks = normalizeBuffetUtilitiesBlocks(payload);
  const summary = blocks
    .map((b) => {
      const name = (b && b.name) ? String(b.name) : "Station";
      const lines = Array.isArray(b.lines) ? b.lines : [];
      let total = 0;
      for (const ln of lines) {
        const qty = ln.quantity != null ? Number(ln.quantity) : 1;
        total += Number.isFinite(qty) ? qty : 1;
      }
      const display = lines.length ? String(total) : "—";
      return `<strong>${name}</strong>: ${display}`;
    })
    .join("<br>");

  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Buffet Service"}</span>
    </div>
    <div class="buffet-status-card buffet-ready-summary-card">
        <div class="buffet-item-header">
            <span class="buffet-item-name">Stations (current status)</span>
        </div>
        ${
          String(payload.status || "").toLowerCase() === "created"
            ? `<div class="buffet-status-body small fw-semibold mb-2 pb-2 border-bottom border-light">order created</div>`
            : ""
        }
        <div class="buffet-status-body small">
            ${summary || "—"}
        </div>
    </div>
  `;
}

function buildBuffetItemStatusMessage(payload) {
  const statusKey = String(payload.status || 'unknown').toLowerCase();
  const statusClass = statusClassMap[statusKey] || 'unknown-color';
  const itemName = payload.item_name || payload.name || 'Item';
  const isBuffet = isDineFlashBuffetChatSurface();
  const detailsHtml = isBuffet
    ? formatBuffetLineDetailsBlock(payload.remarks, payload.customizations)
    : "";
  const hasStructuredDetails = Boolean(detailsHtml);
  const bodyText =
    isBuffet && hasStructuredDetails
      ? `Your ${itemName} is now ${statusKey}.`
      : payload.message || `Your ${itemName} is now ${statusKey}.`;

  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Buffet Service"}</span>
    </div>
    <div class="buffet-status-card">
        <div class="buffet-item-header">
            <span class="buffet-item-name">${itemName}</span>
            <span class="buffet-status-badge ${statusClass}">${statusKey.toUpperCase()}</span>
        </div>
        <div class="buffet-status-body">
            ${bodyText}
            ${hasStructuredDetails ? `<div class="buffet-line-details mt-2">${detailsHtml}</div>` : ""}
        </div>
    </div>
  `;
}

function buildBuffetDeliveredMessage(payload) {
  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Buffet Service"}</span>
    </div>
    <div class="buffet-delivered-card">
        <div class="delivered-icon">✅</div>
        <div class="delivered-text">
            ${payload.message || "Your order has been delivered. Enjoy your meal!"}
        </div>
    </div>
  `;
}

function maskSequenceCode(sequenceCode) {
  const parts = (sequenceCode || "").split("-");
  if (parts.length === 6) {
    parts[0] = "****";
    parts[1] = "***";
    parts[2] = "***";
    parts[3] = "*";
  }
  return parts.join("-");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function buildBookingStatusMessage(payload) {
  const path = String(window.location?.pathname || "").toLowerCase();
  const project = String(window.PROJECT_NAME || "").toLowerCase();
  const isDineFlashCustomerSurface =
    project === "dine_flash" &&
    path.includes("/dine_flash/") &&
    !path.includes("/manager/");
  const statusKey = payload?.status?.toLowerCase() || "unknown";
  const statusClass = statusClassMap[statusKey] || "unknown-color";
  const payloadStatus = dineInPayloadStatusMap[statusKey];
  const allocatedPlaceValue = payload?.utility_name || "-";
  const tableNumberRaw =
    payload?.table_number ??
    payload?.table_no ??
    payload?.table_num ??
    payload?.table_id ??
    "";
  const tableNumber = String(tableNumberRaw).trim();
  const sanitizedAllocatedPlace =
    isDineFlashCustomerSurface && tableNumber && allocatedPlaceValue
      ? String(allocatedPlaceValue)
          .replace(new RegExp(`\\(\\s*${escapeRegExp(tableNumber)}\\s*\\)`, "gi"), "")
          .replace(/\s{2,}/g, " ")
          .trim()
      : allocatedPlaceValue;
  const tableNumberRow =
    isDineFlashCustomerSurface && tableNumber !== ""
      ? `
      <div class="dine-row">
        <span class="dine-label"><span class="dine-icon">🔢</span>Table Number</span>
        <span class="dine-value dine-badge">${tableNumber}</span>
      </div>`
      : "";

  return `
    <div class="response-title">
      ${buildLogoImg(payload)}
      <span class="response-title-text">${payload.alias_name || "Dine Service"}</span>
    </div>

    <div class="dine-status-row">
      <span class="dine-status-label">Status:</span>
      <span class="dine-status-value ${statusClass}">
        ${payloadStatus || "Unknown"}
      </span>
    </div>

    <div class="dine-body">
      <div class="dine-card-header">
        <span class="customer-icon" aria-hidden="true">👤</span>
        <div class="customer-name">${payload.customer_name || "-"}</div>
      </div>

      <div class="dine-row">
        <span class="dine-label"><span class="dine-icon">🧾</span>Booking No</span>
        <span class="dine-value">${payload.booking_no || "-"}</span>
      </div>

      <div class="dine-row">
        <span class="dine-label"><span class="dine-icon">👥</span>Guest</span>
        <span class="dine-value">${payload.no_of_packs || "-"}</span>
      </div>

      <div class="dine-row">
        <span class="dine-label"><span class="dine-icon">🪑</span>Allocated Place</span>
        <span class="dine-value dine-badge">${sanitizedAllocatedPlace || "-"}</span>
      </div>
      ${tableNumberRow}
    </div>
  `;
}


function resolveMessageKind(message) {
  const outer = (message.type || "").toLowerCase();
  const inner =
    typeof message.text === "object" && message.text !== null && typeof message.text.type === "string"
      ? String(message.text.type).toLowerCase()
      : "";
  // Prefer nested payload type for item/buffet events (WebChat may truncate outer `type` in DB).
  if (
    inner.startsWith("item_") ||
    inner.startsWith("buffet_item") ||
    inner === "buffet_utilities_ready" ||
    inner === "buffet_utilities_status"
  ) {
    return inner;
  }
  return outer || inner;
}

export const ChatTemplateService = {
  build(message) {
    // const payload = message.text || {};
    const payload = typeof message.text === "object" && message.text !== null && Object.keys(message.text).length
      ? message.text
      : message;

    const type = resolveMessageKind(message);
    switch (type) {
      case "buffet_utilities_status":
      case "buffet_utilities_ready":
        return buildBuffetUtilitiesStationCard(payload);
      case "buffet_utilities_status_summary":
      case "buffet_ready_utilities_summary":
        return buildBuffetUtilitiesStatusSummary(payload);
      case "buffet_item_update":
      case "buffet_item_preparing":
      case "buffet_item_ready":
      case "buffet_item_cancelled":
      case "item_preparing":
      case "item_ready":
      case "item_delivered":
      case "buffet_item_delivered":
      case "item_cancelled":
      case "item_operation_closed":
        return buildBuffetItemStatusMessage(payload);
      case "order_delivered":
        return buildBuffetDeliveredMessage(payload);
      case "foodstatus":
        return buildStatusMessage(payload);
      case "offers":
        return buildOfferMessage(payload);
      case "manager":
        return buildManagerMessage(payload);
      case "airline_manager":
        return buildAirlineManagerMessage(payload);
      case "dine_manager":
      case "buffet_manager":
        return buildManagerMessage(payload);
      case "flightstatus":
        return buildFlightStatusMessage(payload);
      case "dinestatus":
        return buildBookingStatusMessage(payload);
      case "buffetstatus":
        // Fallback for buffet order status itself (though usually items are handled individually)
        return buildStatusMessage(payload);
      case "thankyou":
        return buildThankYouMessage(payload);

      case "chat":
        // user-typed messages → extract content
        return typeof payload === "object" && payload.content
          ? payload.content
          : typeof payload === "string"
            ? payload
            : "";
      default:
        return typeof payload === "string" ? payload : JSON.stringify(payload);
    }
  }
};
