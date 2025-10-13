const statusClassMap = {
  preparing: 'preparing-color',
  ready: 'ready-color',
  delivered: 'delivered-color',
  cancelled: 'cancelled-color'
};

function buildStatusMessage(payload) {
  const statusKey = payload?.status || 'unknown';
  const statusClass = statusClassMap[statusKey] || 'unknown-color';

  return `
    <div class="response-title">${payload.alias_name || "Unknown"}</div>
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
    <div class="response-title">${payload.alias_name || "Outlet"}</div>
    <div class="response-title">🔥 ${payload.title || ""}</div>
    <div style="color: #333; font-size: 15px;">
        ${payload.body || "Delicious deals await. Come grab your favorite combo now!"}
    </div>
  `;
}

function buildManagerMessage(payload) {
  return `
    <div class="response-title">📩 ${payload.alias_name || "Outlet"}</div>
    <div class="manager-message-body">
        <div class="manager-badge">Manager Notification</div>
        <div class="custom-manager-message">
            ${payload.status || "Hello! Here's an update regarding your order."}
        </div>
    </div>
  `;
}

export const ChatTemplateService = {
  build(message) {
    const payload = message.text || {};

    switch (message.type) {
      case "foodstatus":
        return buildStatusMessage(payload);
      case "offers":
        return buildOfferMessage(payload);
      case "manager":
        return buildManagerMessage(payload);
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
