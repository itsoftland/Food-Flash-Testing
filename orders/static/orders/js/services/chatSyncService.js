// orders/static/orders/js/services/chatSyncService.js
//
// iOS Buffet PWA-only recovery when the service worker cannot postMessage to
// any window client (client_count=0). Android and other flavours are untouched:
// every entry point returns immediately when isEnabled() is false.

import { ChatHistoryService } from "./chatHistoryService.js";
import { appendMessage } from "./chatService.js";

const RECOVERABLE_TYPES = new Set([
    "item_preparing",
    "item_ready",
    "item_cancelled",
    "item_delivered",
    "item_operation_closed",
    "buffet_item_ready",
    "buffet_manager",
    "buffet_utilities_status",
    "order_delivered",
]);

const SYNC_INTERVAL_MS = 2 * 60 * 1000;

function isIosDevice() {
    return /iphone|ipad|ipod/i.test(window.navigator.userAgent || "");
}

function isStandalonePwa() {
    return Boolean(window.navigator.standalone);
}

function isDineFlashBuffetSurface() {
    const project = String(window.PROJECT_NAME || "").trim().toLowerCase();
    if (project === "dine_flash_buffet") return true;
    return String(window.location?.pathname || "").toLowerCase().includes("/dine_flash_buffet");
}

function isEnabled() {
    return isIosDevice() && isStandalonePwa() && isDineFlashBuffetSurface();
}

function hashString(str) {
    let hash = 5381;
    const input = String(str ?? "");
    for (let i = 0; i < input.length; i += 1) {
        hash = ((hash << 5) + hash) ^ input.charCodeAt(i);
    }
    return (hash >>> 0).toString(16);
}

function canonicalize(value) {
    if (value === null || typeof value !== "object") {
        return value;
    }
    if (Array.isArray(value)) {
        return value.map(canonicalize);
    }
    const sorted = {};
    Object.keys(value)
        .sort()
        .forEach((key) => {
            sorted[key] = canonicalize(value[key]);
        });
    return sorted;
}

function normalizeUtilitiesForFingerprint(rawUtilities) {
    return JSON.stringify(canonicalize(rawUtilities ?? {}));
}

function resolveMessageType(source) {
    if (!source || typeof source !== "object") return "";

    const outerType =
        source.type != null ? String(source.type).trim().toLowerCase() : "";

    const nested =
        typeof source.text === "object" && source.text !== null
            ? source.text
            : null;
    const innerType =
        nested?.type != null ? String(nested.type).trim().toLowerCase() : "";

    if (
        innerType.startsWith("item_") ||
        innerType.startsWith("buffet_item") ||
        innerType === "buffet_utilities_status" ||
        innerType === "buffet_utilities_ready" ||
        innerType === "buffet_manager" ||
        innerType === "order_delivered"
    ) {
        return innerType;
    }

    return outerType || innerType;
}

function resolvePayload(source) {
    if (!source || typeof source !== "object") return source;
    if (typeof source.text === "object" && source.text !== null && Object.keys(source.text).length) {
        return { ...source.text, ...source };
    }
    return source;
}

function resolveBody(source) {
    const payload = resolvePayload(source);
    return payload?.body ?? payload?.message ?? "";
}

function resolveBookingId(source) {
    const payload = resolvePayload(source);
    return String(payload?.booking_id ?? source?.booking_id ?? "").trim();
}

function resolveVendorId(source, fallbackVendorId) {
    const payload = resolvePayload(source);
    return String(
        payload?.vendor_id ?? source?.vendor_id ?? fallbackVendorId ?? ""
    ).trim();
}

function resolveItemId(source) {
    const payload = resolvePayload(source);
    return String(payload?.item_id ?? "").trim();
}

function resolveUtilities(source) {
    const payload = resolvePayload(source);
    return payload?.utilities ?? null;
}

function resolveMessageId(source) {
    const payload = resolvePayload(source);
    const messageId = payload?.message_id ?? source?.message_id;
    if (messageId == null || messageId === "") return "";
    return String(messageId).trim();
}

function fingerprint(source, fallbackVendorId) {
    const type = resolveMessageType(source);
    const vendorId = resolveVendorId(source, fallbackVendorId);
    const bookingId = resolveBookingId(source);

    if (type.startsWith("item_")) {
        return `${vendorId}|${bookingId}|${resolveItemId(source)}|${type}`;
    }

    if (type === "buffet_item_ready") {
        return `${vendorId}|${bookingId}|buffet_item_ready|${resolveBody(source)}`;
    }

    if (type === "buffet_manager") {
        const messageId = resolveMessageId(source);
        if (messageId) {
            return `${vendorId}|${bookingId}|buffet_manager|${messageId}`;
        }
        return `${vendorId}|${bookingId}|buffet_manager|${hashString(resolveBody(source))}`;
    }

    if (type === "order_delivered") {
        return `${vendorId}|${bookingId}|order_delivered`;
    }

    if (type === "buffet_utilities_status") {
        const normalizedUtilities = normalizeUtilitiesForFingerprint(
            resolveUtilities(source)
        );
        return `${vendorId}|${bookingId}|buffet_utilities_status|${hashString(normalizedUtilities)}`;
    }

    return `${vendorId}|${bookingId}|${type}`;
}

function isRecoverableMessage(source) {
    if (!source || typeof source !== "object") return false;

    const sender = String(source.sender ?? "").toLowerCase();
    if (sender && sender !== "server") return false;

    const type = resolveMessageType(source);
    if (!type || type === "buffet_order_details") return false;

    return RECOVERABLE_TYPES.has(type);
}

export const ChatSyncService = (() => {
    let handledFingerprints = new Set();
    let activeVendorId = null;
    let periodicTimerId = null;
    let listenersBound = false;
    let syncInProgress = false;

    function isAlreadyHandled(source, fallbackVendorId) {
        if (!isEnabled()) return false;
        if (!isRecoverableMessage(source)) return false;
        return handledFingerprints.has(fingerprint(source, fallbackVendorId));
    }

    function registerPushDelivered(source, fallbackVendorId) {
        if (!isEnabled()) return;
        if (!isRecoverableMessage(source)) return;
        handledFingerprints.add(fingerprint(source, fallbackVendorId));
    }

    function seedFromMessages(messages, vendorId) {
        if (!isEnabled()) return;
        if (!Array.isArray(messages) || messages.length === 0) return;

        messages.forEach((msg) => {
            if (!isRecoverableMessage(msg)) return;
            handledFingerprints.add(fingerprint(msg, vendorId));
        });
    }

    function resetForVendor(vendorId) {
        if (!isEnabled()) return;
        activeVendorId = vendorId != null ? String(vendorId) : null;
        handledFingerprints = new Set();
    }

    function passesBuffetQrTokenGuard(msg) {
        if (!window.buffetQrTokenFromRedirect || msg?.token_no == null) {
            return true;
        }
        const expected = String(window.buffetQrTokenFromRedirect).trim();
        const incoming = String(msg.token_no).trim();
        if (expected && incoming && expected !== incoming) {
            return false;
        }
        return true;
    }

    async function syncMissing() {
        if (!isEnabled()) return;
        if (window.isRestoringHistory === true) return;
        if (syncInProgress) return;

        syncInProgress = true;
        try {
            const vendorId =
                activeVendorId != null
                    ? parseInt(activeVendorId, 10)
                    : await AppUtils.getActiveVendor();
            if (!vendorId) return;

            const browserId = AppUtils.getBrowserId();
            if (!browserId) return;

            const messages = (await ChatHistoryService.load(vendorId, browserId)) || [];

            for (const msg of messages) {
                if (!isRecoverableMessage(msg)) continue;
                if (!passesBuffetQrTokenGuard(msg)) continue;
                if (isAlreadyHandled(msg, vendorId)) continue;

                appendMessage(
                    msg.rendered,
                    msg.sender,
                    msg.timestamp,
                    msg.type,
                    msg.token_no
                );
                registerPushDelivered(msg, vendorId);
            }
        } catch (err) {
            console.error("ChatSyncService.syncMissing failed:", err);
        } finally {
            syncInProgress = false;
        }
    }

    function startPeriodicSync() {
        if (!isEnabled()) return;
        if (periodicTimerId != null) {
            clearInterval(periodicTimerId);
        }
        periodicTimerId = setInterval(() => {
            syncMissing();
        }, SYNC_INTERVAL_MS);
    }

    function init() {
        if (!isEnabled()) return;
        startPeriodicSync();

        if (listenersBound) return;
        listenersBound = true;

        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible") {
                syncMissing();
            }
        });

        window.addEventListener("pageshow", (event) => {
            if (event.persisted || document.visibilityState === "visible") {
                syncMissing();
            }
        });
    }

    return {
        isEnabled,
        isAlreadyHandled,
        registerPushDelivered,
        seedFromMessages,
        resetForVendor,
        syncMissing,
        startPeriodicSync,
        init,
    };
})();
