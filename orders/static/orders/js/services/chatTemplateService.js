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
    <div class="response-title">${payload.name || "Unknown"}</div>
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
    <div class="response-title">${payload.name || "Outlet"}</div>
    <div class="response-title">🔥 ${payload.title || ""}</div>
    <div style="color: #333; font-size: 15px;">
        ${payload.body || "Delicious deals await. Come grab your favorite combo now!"}
    </div>
  `;
}

function buildManagerMessage(payload) {
  return `
    <div class="response-title">📩 ${payload.name || "Outlet"}</div>
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



// // services/chatTemplateService.js

// const statusClassMap = {
//   preparing: 'preparing-color',
//   ready: 'ready-color',
//   delivered: 'delivered-color',
//   cancelled: 'cancelled-color'
// };

// function buildStatusMessage(pushData) {
//   const statusKey = pushData?.status || 'unknown';
//   const statusClass = statusClassMap[statusKey] || 'unknown-color';

//   return `
//     <div class="response-title">${pushData.name || "Unknown"}</div>
//     <div class="status">
//         Status: 
//         <span class="${statusClass}">
//             ${pushData.status || "Unknown"}
//         </span>
//     </div>
//     <div class="info-badges">
//         <div class="badge">Counter No: ${pushData.counter_no || ""}</div>
//         <div class="badge">Token No: ${pushData.token_no || ""}</div>
//     </div>
//   `;
// }

// function buildOfferMessage(pushData) {
//   return `
//     <div class="response-title">${pushData.name || "Outlet"}</div>
//     <div class="response-title">🔥 ${pushData.title || ""}</div>
//     <div style="color: #333; font-size: 15px;">
//         ${pushData.body || "Delicious deals await. Come grab your favorite combo now!"}
//     </div>
//   `;
// }

// function buildManagerMessage(pushData) {
//   return `
//     <div class="response-title">📩 ${pushData.name || "Outlet"}</div>
//     <div class="manager-message-body">
//         <div class="manager-badge">Manager Notification</div>
//         <div class="custom-manager-message">
//             ${pushData.text || "Hello! Here's an update regarding your order."}
//         </div>
//     </div>
//   `;
// }

// export const ChatTemplateService = {
//   build(message) {
//     // message is raw data from DB
//     switch (message.type) {
//       case "foodstatus":
//         return buildStatusMessage(message);
//       case "offers":
//         return buildOfferMessage(message);
//       case "manager":
//         return buildManagerMessage(message);
//       case "chat":
//         // user-typed messages, return plain text
//         return message.text || "";
//       default:
//         // fallback: normal chat
//         return message.text || "";
//     }
//   }
// };
