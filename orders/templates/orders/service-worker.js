let BASE_URL = null;
let lastVisitedPage = null;

self.addEventListener("install", (event) => {
  console.log("[Service Worker] ✅ Installed");
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  console.log("[Service Worker] 🚀 Activated");
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  const data = event.data || {};

  if (data.type === "SET_BASE_URL") {
    BASE_URL = data.baseUrl;
    console.log("[Service Worker] 🌐 Base URL set to:", BASE_URL);
  }

  if (data.type === "UPDATE_LAST_PAGE") {
    lastVisitedPage = data.url;
    console.log("[Service Worker] 🔄 Last visited page updated:", lastVisitedPage);
  }
});
self.addEventListener("push", (event) => {
  if (!event.data) return;

  const payload = event.data.json();
  const key = `push_${payload.token_no}`;
  // Store last push time for monitoring
  event.waitUntil((async () => {
    const allClients = await self.clients.matchAll({ includeUncontrolled: true });
    for (const client of allClients) {
      client.postMessage({
        type: "PUSH_RECEIVED",
        payload
      });
    }
  })());

  event.waitUntil(
    (async () => {
      try {
        const cache = await caches.open("push-store");
        await cache.put(new Request(key), new Response(JSON.stringify(payload)));
        console.log("[Service Worker] 💾 Push data cached:", key);
      } catch (err) {
        console.error("[Service Worker] ❌ Caching failed:", err);
      }

      const allClients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      let shouldShowSystemNotification = true;

      allClients.forEach((client) => {
        client.postMessage({
          type: "PUSH_STATUS_UPDATE",
          payload,
        });

        // Check if at least one tab is focused
        if (client.focused || client.visibilityState === "visible") {
          shouldShowSystemNotification = false;
        }
      });

      if (shouldShowSystemNotification) {
        // ✅ Show custom notification using your payload data
        const customTitle = payload.title || "🍽 Food Flash Update";
        const customBody = payload.body || "You have a new update.";
        const icon = payload.icon || "/static/orders/images/food-flash-logo.png";

        console.log("[Service Worker] 🔔 Showing system notification");

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

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const token = data.token_no;
  const key = `push_${token}`;

  event.waitUntil(
    (async () => {
      let pushData = data;

      try {
        const cache = await caches.open("push-store");
        const response = await cache.match(new Request(key));
        if (response) {
          pushData = await response.json();
          await cache.delete(new Request(key));
          console.log("[Service Worker] ✅ Retrieved cached push:", key);
        }
      } catch (err) {
        console.warn("[Service Worker] ⚠️ Failed to retrieve cached push:", err);
      }

      const allClients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });

      if (allClients.length > 0) {
        const client = allClients[0];
        client.focus();
        client.postMessage({
          type: "OPEN_CHAT",
          payload: pushData,
        });
        console.log("[Service Worker] 📨 Sent OPEN_CHAT to client");
      } else {
        const targetUrl = `${BASE_URL || "/"}?from_push=true`;
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
