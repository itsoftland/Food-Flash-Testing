// orders/static/orders/js/services/PushSubscriptionService.js
import { appendMessage } from "./chatService.js";

const base = AppUtils.getStartUrl();
const apiModulePath = `${base}static/utils/js/apiEndpoints.js`;
let apiEndpoints;

try {
    const endpointsModule = await import(apiModulePath);
    apiEndpoints = endpointsModule.API_ENDPOINTS;
} catch (error) {
    console.error("Failed to import apiEndpoints:", error);
}


export const PushSubscriptionService = (() => {
    const VAPID_PUBLIC_KEY = "BAv_HFvgMBKxx3Jnse3fLMjzUEn3n3zS76GwEGQ_oOPR_40U1e7O4AiezuOReRTK4ULx2EaGC9kGAz-lzV791Tw".trim();

    const subscribe = async (token, vendor_id) => {
        try {
            if (!token) {
                console.error("Token not provided. Cannot subscribe.");
                return;
            }

            if (Notification.permission !== "granted") {
                console.error("Notification permission is not granted.");
                return;
            }

            // Ensure SW is fully controlling page before continuing
            const registration = await ensureServiceWorkerReady();
            if (!registration) {
                console.warn("Proceeding without push subscription.");
                return null;
            }

            // Check for an existing subscription
            let subscription = await registration.pushManager.getSubscription();

            if (!subscription) {
                // Create a new one only if none exists
                const convertedKey = AppUtils.urlBase64ToUint8Array(VAPID_PUBLIC_KEY);
                try {
                    subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: convertedKey
                    });
                } catch (err) {
                    console.warn("First subscribe attempt failed, retrying in 2s...", err);
                    await new Promise(res => setTimeout(res, 2000));
                    try {
                        subscription = await registration.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: convertedKey
                        });
                    } catch (retryErr) {
                        console.error("Retry also failed. Skipping push subscription.", retryErr);
                        return; // stop here instead of saving null
                    }
                }
            } else {
                console.log("Reusing existing push subscription:", subscription);
            }

            // Always send the current subscription to the server
            const newSubscriptionJSON = JSON.stringify(subscription);
            const storedSubscription = localStorage.getItem("pushSubscription");

            if (storedSubscription !== newSubscriptionJSON) {
                localStorage.setItem("pushSubscription", newSubscriptionJSON);
            }
         
            const browserId = AppUtils.getBrowserId();
            const sub = subscription.toJSON();

            const payload = {
                endpoint: sub.endpoint,
                keys: sub.keys,
                browser_id: browserId,
                token_number: token,
                vendor_id: vendor_id
            };

            const response = await fetch(apiEndpoints.SAVE_SUBSCRIPTION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': AppUtils.getCSRFToken()
                },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                console.log("Push subscription saved/updated successfully.");
            } else {
                console.error("Failed to save subscription to server.");
            }

        } catch (err) {
            console.error("Error in subscribe:", err);
        }
    };

    return {
        subscribe
    };
})();

async function ensureServiceWorkerReady(timeout = 5000) {
    if (!('serviceWorker' in navigator)) {
        console.warn("⚠️ Service workers not supported. Skipping push features.");
        appendMessage(`Real-time notifications are currently unavailable.
             Please refresh the page and try entering your token number once more. 
             If it still doesn’t work, enter your token number periodically to 
             check the current status.`,
            "server",'chat'
        )
        return null;
    }

    try {
        const controllerReady = new Promise(resolve => {
            if (navigator.serviceWorker.controller) {
                return resolve();
            }
            navigator.serviceWorker.addEventListener("controllerchange", () => resolve(), { once: true });
        });

        const registrationReady = navigator.serviceWorker.ready;

        // Race timeout vs SW ready
        const registration = await Promise.race([
            Promise.all([registrationReady, controllerReady]).then(([reg]) => reg),
            new Promise((_, reject) => setTimeout(() => reject(new Error("SW ready timeout")), timeout))
        ]);

        console.log("✅ Service worker ready and controlling page");
        return registration;

    } catch (err) {
        console.error("❌ Service worker not ready:", err);
        appendMessage(`Real-time notifications are currently unavailable.
             Please refresh the page and try entering your token number once more. 
             If it still doesn’t work, enter your token number periodically to 
             check the current status.`,
            "server",'chat'
        )
        return null; // fallback
    }
}
