// ============================================================================
// 🌐 Universal Service Worker — Multi-Flavour Safe + Persistent BASE_URL + ACK
// ============================================================================

let BASE_URL = null;
let lastVisitedPage = null;

const CACHE_NAME = "push-store";
const BASE_URL_CACHE = "sw-base-url-store";
// Expected project/flavour for this PWA deployment.
// Used to ignore cross-flavour pushes (e.g., food_flash -> airline_flash).
//
// Derive from the SW scope (/food_flash/ or /airline_flash/) instead of relying
// only on server-side template context.
const EXPECTED_PROJECT = (() => {
  try {
    const scope = String(self.registration?.scope || "").toLowerCase();
    if (scope.includes("/airline_flash")) return "airline_flash";
    if (scope.includes("/dine_flash_buffet")) return "dine_flash_buffet";
    if (scope.includes("/dine_flash")) return "dine_flash";
    if (scope.includes("/food_flash")) return "food_flash";
    
    // Fallback to last segment if none matches
    const parts = scope.split("/").filter(Boolean);
    const last = parts[parts.length - 1];
    return (last || "food_flash").toLowerCase().trim();
  } catch (e) {
    return "food_flash";
  }
})();

// ⚠️ TEMP DIAGNOSTIC (iOS chat-card loss). Dine Flash AND Dine Flash Buffet
// deployments only (EXPECTED_PROJECT derived from SW scope). Logs how many window
// clients a push is delivered to, and which branch the notification click takes.
// Remove with the other `[diag]` logs once root cause is found.
function dineFlashSwDiag(label, data) {
  if (EXPECTED_PROJECT !== "dine_flash" && EXPECTED_PROJECT !== "dine_flash_buffet") return;
  console.info(`[diag][${EXPECTED_PROJECT}] ${label}`, {
    ts: new Date().toISOString(),
    ...(data || {}),
  });
}

// ⚠️ TEMP DIAGNOSTIC (iOS push-delivery chain). POSTs a single breadcrumb to the
// server (/api/dine_flash_client_diag/) so a push can be traced end-to-end
// without Safari Web Inspector. Dine Flash + Dine Flash Buffet only. Fire-and-
// forget, never throws, never blocks push delivery. Remove with the other
// `[diag]` logs once root cause is found.
function dineFlashClientDiag(step, fields) {
  if (EXPECTED_PROJECT !== "dine_flash" && EXPECTED_PROJECT !== "dine_flash_buffet") return;
  try {
    const root = BASE_URL || self.registration.scope; // both end with "/"
    const url = `${root}api/dine_flash_client_diag/`;
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      keepalive: true, // survive the SW going idle after the push handler
      body: JSON.stringify({
        step,
        source: "service_worker",
        timestamp: Date.now(),
        ...(fields || {}),
      }),
    }).catch(() => {});
  } catch (e) {
    // Diagnostics must never affect push delivery.
  }
}

function normalizeProjectName(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[_-]/g, "")
    .trim();
}

function projectsMatch(expected, incoming) {
  const e = normalizeProjectName(expected);
  const i = normalizeProjectName(incoming);
  if (!e || !i) return false;
  return e === i || e.startsWith(i) || i.startsWith(e);
}

function inferProjectFromUrl(url) {
  const raw = String(url || "").toLowerCase();
  if (raw.includes("/airline_flash") || raw.includes("/airlineflash")) return "airline_flash";
  if (raw.includes("/dine_flash_buffet") || raw.includes("/dineflashbuffet")) return "dine_flash_buffet";
  if (raw.includes("/dine_flash") || raw.includes("/dineflash")) return "dine_flash";
  if (raw.includes("/food_flash") || raw.includes("/foodflash")) return "food_flash";

  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    return (parts[0] || "").toLowerCase();
  } catch (e) {
    const parts = raw.split("/").filter(Boolean);
    return (parts[0] || "").toLowerCase();
  }
}

// ============================================================================
// 🧱 Install & Activate
// ============================================================================
self.addEventListener("install", (event) => {
  // console.log("[Service Worker] ✅ Installed");
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // console.log("[Service Worker] 🚀 Activated — Scope:", self.registration.scope);
  // One-time purge of cached pushes that may have been stored before
  // the `payload.project` filtering was introduced.
  event.waitUntil((async () => {
    try {
      await caches.delete(CACHE_NAME);
      // console.log("[Service Worker] 🧹 Purged old push cache:", CACHE_NAME);
    } catch (err) {
      console.warn("[Service Worker] ⚠️ Failed to purge push cache:", err);
    }
  })().finally(() => self.clients.claim()));
});

// ============================================================================
// 💬 Message Listener (Base URL + ACK Support)
// ============================================================================
self.addEventListener("message", (event) => {
  const data = event.data || {};

  // 🔹 Persist BASE_URL
  if (data.type === "SET_BASE_URL") {
    BASE_URL = data.baseUrl;
    // console.log("[Service Worker] 🌐 Base URL set to:", BASE_URL);

    event.waitUntil((async () => {
      try {
        const cache = await caches.open(BASE_URL_CACHE);
        await cache.put("base_url", new Response(BASE_URL));
        // console.log("[Service Worker] 💾 Base URL saved persistently");
      } catch (err) {
        console.warn("[Service Worker] ⚠️ Failed to store BASE_URL:", err);
      }
    })());
  }

  // 🔹 Track last visited page
  if (data.type === "UPDATE_LAST_PAGE") {
    lastVisitedPage = data.url;
    // console.log("[Service Worker] 🔄 Last visited page updated:", lastVisitedPage);
  }

  // 🔹 Acknowledgment from client
  if (data.type === "PUSH_STATUS_ACK") {
    // console.log(`[Service Worker] ✅ ACK received from client: ${data.clientId}`);
  }
});

// ============================================================================
// 📦 Push Received
// ============================================================================
self.addEventListener("push", (event) => {
  if (!event.data) return;

  const payload = event.data.json();

  dineFlashClientDiag("SW_PUSH_RECEIVED", {
    message_id: payload?.message_id,
    booking_id: payload?.booking_id,
    token_no: payload?.token_no,
    type: payload?.type,
  });

  const isDineFlashPush =
    projectsMatch(EXPECTED_PROJECT, "dine_flash") &&
    payload?.type === "dinestatus";
  if (isDineFlashPush) {
    console.info("[dine_flash] SW push received", {
      booking_id: payload.booking_id,
      status: payload.status,
      token_no: payload.token_no,
    });
  }

  // Filter out unrelated flavour pushes.
  const incomingProject =
    payload?.project != null ? String(payload.project).toLowerCase().trim() : null;
  if (EXPECTED_PROJECT && !projectsMatch(EXPECTED_PROJECT, incomingProject)) {
    return; // Don't forward/cache/show notification for other project.
  }

  // Extra safety: Airline UI expects `sequence_code`.
  if (EXPECTED_PROJECT === "airline_flash") {
    const seq = payload?.sequence_code != null ? String(payload.sequence_code).trim() : "";
    if (!seq) return;
  }

  const key = `push_${payload.token_no}`;

  // 🔹 Notify active clients (live update)
  event.waitUntil((async () => {
    const allClients = await self.clients.matchAll({ includeUncontrolled: true });
    for (const client of allClients) {
      const clientProject = inferProjectFromUrl(client?.url);
      if (EXPECTED_PROJECT && !projectsMatch(EXPECTED_PROJECT, clientProject)) {
        continue;
      }
      client.postMessage({ type: "PUSH_RECEIVED", payload });
    }
  })());

  // 🔹 Cache and show system notification if needed
  event.waitUntil(
    (async () => {
      try {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(new Request(key), new Response(JSON.stringify(payload)));
        // console.log("[Service Worker] 💾 Push data cached:", key);
      } catch (err) {
        console.error("[Service Worker] ❌ Caching failed:", err);
      }

      const allClients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });

      console.info("[dine_flash][diag] window clients", {
        booking_id: payload?.booking_id,
        booking_no: payload?.booking_no,
        type: payload?.type,
        client_count: allClients.length,
        urls: allClients.map(client => client.url),
      });

      let shouldShowSystemNotification = true;

      dineFlashClientDiag("SW_POSTMESSAGE_SENT", {
        message_id: payload?.message_id,
        booking_id: payload?.booking_id,
        token_no: payload?.token_no,
        client_count: allClients.length,
        type: payload?.type,
      });

      allClients.forEach((client) => {
        const clientProject = inferProjectFromUrl(client?.url);
        if (EXPECTED_PROJECT && !projectsMatch(EXPECTED_PROJECT, clientProject)) {
          return;
        }

        client.postMessage({
          type: "PUSH_STATUS_UPDATE",
          payload,
        });

        if (client.focused || client.visibilityState === "visible") {
          shouldShowSystemNotification = false;
        }
      });

      dineFlashSwDiag("push -> PUSH_STATUS_UPDATE dispatched to window clients", {
        booking_id: payload?.booking_id,
        token_no: payload?.token_no,
        type: payload?.type,
        window_client_count: allClients.length,
        matching_client_count: allClients.filter(
          (c) => projectsMatch(EXPECTED_PROJECT, inferProjectFromUrl(c?.url))
        ).length,
        will_show_system_notification: shouldShowSystemNotification,
      });

      if (shouldShowSystemNotification) {
        const customTitle = payload.title || "🍽 New Update";
        const customBody = payload.body || "You have a new update.";
        const icon = payload.icon;

        // console.log("[Service Worker] 🔔 Showing system notification");

        await self.registration.showNotification(customTitle, {
          body: customBody,
          data: payload,
          icon: icon,
          badge: icon,
          tag: payload.token_no,
          requireInteraction: true,
          vibrate: [200, 100, 200],
          renotify: true,
        });
      } else {
        console.log("[Service Worker] 👁 Active tab present — skipped system notification");
      }
    })()
  );
});

// ============================================================================
// 🔔 Notification Click Handler (ACK-enabled)
// ============================================================================
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const token = data.token_no;
  const key = `push_${token}`;

  event.waitUntil(
    (async () => {
      let pushData = data;

      try {
        const cache = await caches.open(CACHE_NAME);
        const response = await cache.match(new Request(key));
        if (response) {
          pushData = await response.json();
          await cache.delete(new Request(key));
          // console.log("[Service Worker] ✅ Retrieved cached push:", key);
        }
      } catch (err) {
        console.warn("[Service Worker] ⚠️ Failed to retrieve cached push:", err);
      }

        // Final guard for already-cached pushes (created before this filter shipped).
        const incomingProject =
          pushData?.project != null ? String(pushData.project).toLowerCase().trim() : null;
        if (EXPECTED_PROJECT && !projectsMatch(EXPECTED_PROJECT, incomingProject)) {
          return;
        }

        // Extra safety: Airline UI expects `sequence_code`.
        if (EXPECTED_PROJECT === "airline_flash") {
          const seq = pushData?.sequence_code != null ? String(pushData.sequence_code).trim() : "";
          if (!seq) return;
        }

      const allClients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });

      dineFlashSwDiag("notificationclick", {
        booking_id: pushData?.booking_id,
        token_no: pushData?.token_no,
        window_client_count: allClients.length,
        branch: allClients.length > 0 ? "focus + OPEN_CHAT" : "openWindow ?from_push=true",
      });

      if (allClients.length > 0) {
        dineFlashClientDiag("NOTIFICATIONCLICK_BRANCH", {
          branch: "focus_existing_client",
          message_id: pushData?.message_id,
          booking_id: pushData?.booking_id,
          token_no: pushData?.token_no,
          browser_id: pushData?.browser_id,
          project: EXPECTED_PROJECT,
          client_count: allClients.length,
        });
        const client = allClients[0];
        client.focus();
        client.postMessage({ type: "OPEN_CHAT", payload: pushData });
        // console.log("[Service Worker] 📨 Sent OPEN_CHAT to client");

        try {
          const ack = await waitForAck(client.id, 2000);
          // console.log(`[Service Worker] ✅ ACK received from client: ${ack}`);
        } catch {
          console.warn(`[Service Worker] ⚠️ No ACK received from client: ${client.id}`);
        }
      } else {
        // 🧩 Restore BASE_URL if missing
        if (!BASE_URL) {
          try {
            const cache = await caches.open(BASE_URL_CACHE);
            const response = await cache.match("base_url");
            if (response) {
              BASE_URL = await response.text();
              // console.log("[Service Worker] 🔁 Restored BASE_URL from cache:", BASE_URL);
            }
          } catch (err) {
            console.warn("[Service Worker] ⚠️ Could not restore BASE_URL:", err);
          }
        }

        const targetUrl = `${BASE_URL || self.registration.scope}?from_push=true`;
        // console.log("[Service Worker] 🌐 Opening page from push:", targetUrl);

        dineFlashClientDiag("NOTIFICATIONCLICK_BRANCH", {
          branch: "open_new_window",
          message_id: pushData?.message_id,
          booking_id: pushData?.booking_id,
          token_no: pushData?.token_no,
          browser_id: pushData?.browser_id,
          project: EXPECTED_PROJECT,
          client_count: allClients.length,
        });

        const openedClient = await self.clients.openWindow(targetUrl);
        if (openedClient) {
          console.log("[Service Worker] 🌐 Opened new tab at:", targetUrl);
        } else {
          console.error("[Service Worker] ❌ Failed to open new tab");
        }
      }
    })()
  );
});

// ============================================================================
// 🧩 Helper: Wait for ACK message
// ============================================================================
function waitForAck(clientId, timeout = 2000) {
  return new Promise((resolve, reject) => {
    const channel = new BroadcastChannel("push_ack_channel");
    const timer = setTimeout(() => {
      channel.close();
      reject();
    }, timeout);

    channel.onmessage = (e) => {
      if (
        e.data?.type === "PUSH_STATUS_ACK" &&
        e.data?.clientId === clientId
      ) {
        clearTimeout(timer);
        channel.close();
        resolve(clientId);
      }
    };
  });
}
