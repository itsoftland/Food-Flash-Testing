// orders/static/orders/js/services/PushSubscriptionService.js
import { appendMessage } from "./chatService.js?v=20260819_1";

const base = AppUtils.getStartUrl();
const apiModulePath = `${base}static/utils/js/apiEndpoints.js`;
let apiEndpoints;

try {
    const endpointsModule = await import(apiModulePath);
    apiEndpoints = endpointsModule.API_ENDPOINTS;
} catch (error) {
    console.error("Failed to import apiEndpoints:", error);
}

function isDineFlashSurface() {
    return (
        typeof window !== "undefined" &&
        window.BASE?.includes("/dine_flash/") &&
        !window.BASE?.includes("/dine_flash_buffet/")
    );
}

function dineFlashProjectLabel() {
    if (typeof window === "undefined") return null;
    if (window.PROJECT_NAME) return window.PROJECT_NAME;
    if (window.BASE?.includes("/dine_flash/")) return "dine_flash";
    return null;
}

function dineFlashLog(message, data) {
    if (!isDineFlashSurface()) return;
    if (data !== undefined) {
        console.info(`[dine_flash] ${message}`, data);
    } else {
        console.info(`[dine_flash] ${message}`);
    }
}


export const PushSubscriptionService = (() => {
    const VAPID_PUBLIC_KEY = "BAv_HFvgMBKxx3Jnse3fLMjzUEn3n3zS76GwEGQ_oOPR_40U1e7O4AiezuOReRTK4ULx2EaGC9kGAz-lzV791Tw".trim();

    const subscribe = async (token, vendor_id) => {
        const isDineFlash = isDineFlashSurface();

        try {
            if (isDineFlash) {
                dineFlashLog("Push subscribe entry", {
                    token,
                    vendor_id,
                    url: window.location?.href,
                    notification_permission: Notification.permission,
                    project: dineFlashProjectLabel(),
                });
            }

            if (!token) {
                dineFlashLog("Push subscribe early return", { reason: "missing token" });
                console.error("Token not provided. Cannot subscribe.");
                return;
            }

            if (Notification.permission !== "granted") {
                dineFlashLog("Push subscribe early return", {
                    reason: "notification permission not granted",
                    notification_permission: Notification.permission,
                });
                console.error("Notification permission is not granted.");
                return;
            }

            dineFlashLog("Before ensureServiceWorkerReady / navigator.serviceWorker.ready");

            // Ensure SW is fully controlling page before continuing
            const registration = await ensureServiceWorkerReady(5000, isDineFlash);
            if (!registration) {
                dineFlashLog("Push subscribe early return", {
                    reason: "service worker unavailable or not ready",
                });
                console.warn("Proceeding without push subscription.");
                return null;
            }

            dineFlashLog("ensureServiceWorkerReady succeeded");

            dineFlashLog("Before pushManager.getSubscription");

            // Check for an existing subscription
            let subscription = await registration.pushManager.getSubscription();

            dineFlashLog("After pushManager.getSubscription", {
                existing_subscription_found: Boolean(subscription),
            });

            if (!subscription) {
                // Create a new one only if none exists
                const convertedKey = AppUtils.urlBase64ToUint8Array(VAPID_PUBLIC_KEY);
                dineFlashLog("Before pushManager.subscribe");
                try {
                    subscription = await registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: convertedKey
                    });
                    const subAfterSubscribe = subscription?.toJSON?.() || {};
                    dineFlashLog("pushManager.subscribe succeeded", {
                        endpoint_present: Boolean(subAfterSubscribe.endpoint),
                        browser_id: AppUtils.storageGet("browser_id") || null,
                        subscription_obtained: true,
                    });
                } catch (err) {
                    dineFlashLog("pushManager.subscribe failed (first attempt)", {
                        error: err,
                        stack: err?.stack,
                    });
                    console.warn("First subscribe attempt failed, retrying in 2s...", err);
                    await new Promise(res => setTimeout(res, 2000));
                    try {
                        subscription = await registration.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: convertedKey
                        });
                        const subAfterRetry = subscription?.toJSON?.() || {};
                        dineFlashLog("pushManager.subscribe succeeded (retry)", {
                            endpoint_present: Boolean(subAfterRetry.endpoint),
                            browser_id: AppUtils.storageGet("browser_id") || null,
                            subscription_obtained: true,
                        });
                    } catch (retryErr) {
                        dineFlashLog("pushManager.subscribe failed (retry)", {
                            error: retryErr,
                            stack: retryErr?.stack,
                        });
                        dineFlashLog("Push subscribe early return", {
                            reason: "pushManager.subscribe failed after retry",
                        });
                        console.error("Retry also failed. Skipping push subscription.", retryErr);
                        return; // stop here instead of saving null
                    }
                }
            } else {
                console.log("Reusing existing push subscription:", subscription);
                const subReuse = subscription?.toJSON?.() || {};
                dineFlashLog("Reusing existing push subscription", {
                    endpoint_present: Boolean(subReuse.endpoint),
                    browser_id: AppUtils.storageGet("browser_id") || null,
                });
            }

            // Always send the current subscription to the server
            const newSubscriptionJSON = JSON.stringify(subscription);
            const storedSubscription = AppUtils.storageGet("pushSubscription");

            if (storedSubscription !== newSubscriptionJSON) {
                AppUtils.storageSet("pushSubscription", newSubscriptionJSON);
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

            dineFlashLog("Before fetch save-subscription", {
                token_number: token,
                vendor_id,
                browser_id: browserId,
                endpoint_present: Boolean(sub.endpoint),
                payload_summary: {
                    has_endpoint: Boolean(sub.endpoint),
                    has_keys: Boolean(sub.keys),
                    key_names: sub.keys ? Object.keys(sub.keys) : [],
                },
            });

            const response = await fetch(apiEndpoints.SAVE_SUBSCRIPTION, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': AppUtils.getCSRFToken()
                },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            });

            dineFlashLog("After fetch save-subscription", {
                status: response.status,
                ok: response.ok,
            });

            if (response.ok) {
                console.log("Push subscription saved/updated successfully.");
                dineFlashLog("Push subscribe saved", {
                    booking_id: token,
                    vendor_id,
                    browser_id: browserId,
                });
            } else {
                dineFlashLog("save-subscription non-200 response", {
                    status: response.status,
                    ok: response.ok,
                });
                console.error("Failed to save subscription to server.");
            }

        } catch (err) {
            dineFlashLog("Push subscribe error", {
                error: err,
                stack: err?.stack,
            });
            console.error("Error in subscribe:", err);
        }
    };

    return {
        subscribe
    };
})();


async function ensureServiceWorkerReady(timeout = 5000, isDineFlash = false) {
    if (!('serviceWorker' in navigator)) {
        if (isDineFlash) {
            dineFlashLog("ensureServiceWorkerReady early return", {
                reason: "service workers not supported",
            });
        }
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

        if (isDineFlash) {
            dineFlashLog("Before navigator.serviceWorker.ready");
        }

        // Race timeout vs SW ready
        const registration = await Promise.race([
            Promise.all([registrationReady, controllerReady]).then(([reg]) => reg),
            new Promise((_, reject) => setTimeout(() => reject(new Error("SW ready timeout")), timeout))
        ]);

        if (isDineFlash) {
            dineFlashLog("navigator.serviceWorker.ready succeeded", {
                has_registration: Boolean(registration),
                has_controller: Boolean(navigator.serviceWorker.controller),
            });
        }

        console.log("✅ Service worker ready and controlling page");
        return registration;

    } catch (err) {
        if (isDineFlash) {
            dineFlashLog("ensureServiceWorkerReady failed", {
                reason: "SW ready timeout or error",
                error: err,
                stack: err?.stack,
            });
        }
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
