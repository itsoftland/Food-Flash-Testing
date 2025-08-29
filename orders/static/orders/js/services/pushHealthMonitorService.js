// pushHealthMonitorService.js
import { PushSubscriptionService } from "./pushSubscriptionService.js";

export const PushHealthMonitorService = (() => {
    const CHECK_INTERVAL_MS = 2 * 60 * 1000; // check every 2 min
    const STALE_THRESHOLD_MS = 5 * 60 * 1000; // 5 min without push = stale

    let tokenNo = null;
    let vendorId = null;
    let intervalId = null;

    // Called from service worker push event in your PWA
    function recordPushReceived() {
        localStorage.setItem("lastPushReceivedAt", Date.now().toString());
        console.log("[PushHealth] Push received at", new Date().toLocaleTimeString());
    }

    // Called when app starts (after token/vendor is known)
    function startMonitor(token, vendor) {
        tokenNo = token;
        vendorId = vendor;

        if (intervalId) {
            clearInterval(intervalId);
        }

        intervalId = setInterval(checkHealth, CHECK_INTERVAL_MS);
        console.log("[PushHealth] Monitoring started...");
    }

    async function checkHealth() {
        const lastPush = parseInt(localStorage.getItem("lastPushReceivedAt") || "0", 10);
        const now = Date.now();
        const diff = now - lastPush;

        if (!lastPush) {
            console.warn("[PushHealth] No push received yet.");
            // await refreshSubscription();
            return;
        }

        if (diff > STALE_THRESHOLD_MS) {
            console.warn(`[PushHealth] Push stale for ${Math.round(diff / 1000)}s — refreshing subscription...`);
            await refreshSubscription();
        } else {
            console.log(`[PushHealth] Push channel healthy. Last push ${Math.round(diff / 1000)}s ago.`);
        }
    }

    async function refreshSubscription() {
        if (!tokenNo || !vendorId) {
            console.error("[PushHealth] Cannot refresh subscription — token/vendor missing.");
            return;
        }
        await PushSubscriptionService.subscribe(tokenNo, vendorId);
        console.log("[PushHealth] Subscription refreshed successfully.");
    }

    return {
        recordPushReceived,
        startMonitor
    };
})();
