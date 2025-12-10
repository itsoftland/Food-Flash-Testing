
const statusClassMap = {
  preparing: 'preparing-color',
  ready: 'ready-color',
  allocated:'ready-color',
  delivered: 'delivered-color',
  checked_in: 'checked-in-color',
  boarding_shortly: 'boarding-shortly-color',
  boarding_announced: 'boarding-announced-color',
  gate_change: 'gate-change-color',
  rescheduled: 'rescheduled-color',
  cancelled: 'cancelled-color',
  booking_cancelled:'cancelled-color',
  operation_closed:'boarding-shortly-color',
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
  waiting:'Allocation Pending',
  allocated :'Table Allocated',
  booking_cancelled:'Booking Cancelled',
};

function buildStatusMessage(payload) {
  // console.log("payload status:",payload.status)
  const statusKey = payload?.status || 'unknown';
  const statusClass = statusClassMap[statusKey] || 'unknown-color';
  // console.log("status key:",statusKey)

  return `
    <div class="response-title">
      <img src="${localStorage.getItem("activeVendorLogo")}" class="server-logo" alt="Logo">
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
      <img src="${localStorage.getItem("activeVendorLogo")}" class="server-logo" alt="Logo">
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
      <img src="${localStorage.getItem("activeVendorLogo")}" class="server-logo" alt="Logo">
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
      <img src="${localStorage.getItem("activeVendorLogo")}" class="server-logo" alt="Logo">
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
      <img src="${localStorage.getItem("activeVendorLogo")}" class="server-logo" alt="Logo">
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

function buildBookingStatusMessage(payload) {
  const statusKey = payload?.status?.toLowerCase() || "unknown";
  const statusClass = statusClassMap[statusKey] || "unknown-color";
  const payloadStatus = dineInPayloadStatusMap[statusKey];

  return `
    <div class="response-title">
      <img src="${localStorage.getItem("activeVendorLogo")}" class="server-logo" alt="Logo">
      <span class="response-title-text">${payload.alias_name || "Dine Service"}</span>
    </div>

    <div class="status">
        Status:
        <span class="${statusClass}">
            ${payloadStatus || "Unknown"}
        </span>
    </div>

    <div class="dine-body">

      <div class="dine-card-header">
         <span class="customer-icon" aria-hidden="true">👤</span>
         <div class="customer-name">${payload.customer_name || "-"}</div>
      </div>

      <div class="dine-row">
          <div class="dine-label">
              <span class="dine-icon">🏷️</span>
              Booking No
          </div>
          <div class="dine-value">${payload.booking_no || "-"}</div>
      </div>

      <div class="dine-row">
          <div class="dine-label">
              <span class="dine-icon">👥</span>
              Guest
          </div>
          <div class="dine-value">${payload.no_of_packs || "-"}</div>
      </div>

      <div class="dine-row">
          <div class="dine-label">
              <span class="dine-icon">🪑</span>
              Area
          </div>
          <div class="dine-value dine-badge">${payload.utility_name || "-"}</div>
      </div>

    </div>
  `;
}

export const ChatTemplateService = {
  build(message) {
    // const payload = message.text || {};
    const payload = typeof message.text === "object" && Object.keys(message.text).length
    ? message.text
    : message;

    switch (message.type) {
      case "foodstatus":
        return buildStatusMessage(payload);
      case "offers":
        return buildOfferMessage(payload);
      case "manager":
        return buildManagerMessage(payload);
      case "airline_manager":
        return buildAirlineManagerMessage(payload);
      case "flightstatus":
        return buildFlightStatusMessage(payload);
      case "dinestatus":
        return buildBookingStatusMessage(payload);
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
