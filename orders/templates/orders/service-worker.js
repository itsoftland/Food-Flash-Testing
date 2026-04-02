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
    const scope = String(self.registration?.scope || "");
    const parts = scope.split("/").filter(Boolean);
    const last = parts[parts.length - 1];
    return (last || "food_flash").toLowerCase().trim();
  } catch (e) {
    return "food_flash";
  }
})();

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

  // Filter out unrelated flavour pushes.
  const incomingProject =
    payload?.project != null ? String(payload.project).toLowerCase().trim() : null;
  if (EXPECTED_PROJECT && incomingProject !== EXPECTED_PROJECT) {
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

      let shouldShowSystemNotification = true;

      allClients.forEach((client) => {
        client.postMessage({
          type: "PUSH_STATUS_UPDATE",
          payload,
        });

        if (client.focused || client.visibilityState === "visible") {
          shouldShowSystemNotification = false;
        }
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
        if (EXPECTED_PROJECT && incomingProject !== EXPECTED_PROJECT) {
          return;
        }

        // Extra safety: Airline UI expects `sequence_code`.
        if (EXPECTED_PROJECT === "airline_flash") {
          const seq = pushData?.sequence_code != null ? String(pushData.sequence_code).trim() : "";
          if (!seq) return;
        }

      const allClients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });

      if (allClients.length > 0) {
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
