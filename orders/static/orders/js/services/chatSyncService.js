// orders/static/orders/js/services/chatSyncService.js
//
// iOS standalone PWA recovery when the service worker cannot postMessage to
// any window client (client_count=0). Covers Dine Flash Buffet and Dine Flash
// table booking. Android, desktop, and Safari browser tabs are untouched:
// every entry point returns immediately when isEnabled() is false.

import { ChatHistoryService } from "./chatHistoryService.js?v=20260819_1";
import { appendMessage } from "./chatService.js?v=20260819_1";
import { HOSPITAL_MANAGER_PUSH_TYPE } from "../hospital/hospitalCommon.js";

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

const DINE_FLASH_RECOVERABLE_DINESTATUS_STATUSES = new Set([
    "allocated",
    "occupied",
    "booking_cancelled",
]);

const DINE_FLASH_EXCLUDED_DINESTATUS_STATUSES = new Set([
    "waiting",
    "created",
]);

const SYNC_INTERVAL_MS = 60 * 1000;

function isIosDevice() {
    return /iphone|ipad|ipod/i.test(window.navigator.userAgent || "");
}

function isStandalonePwa() {
    return Boolean(window.navigator.standalone);
}

function normalizeProjectName(value) {
    return String(value || "").toLowerCase().replace(/[_-]/g, "").trim();
}

function projectsMatch(expected, incoming) {
    const e = normalizeProjectName(expected);
    const i = normalizeProjectName(incoming);
    if (!e || !i) return false;
    return e === i || e.startsWith(i) || i.startsWith(e);
}

function currentProject() {
    const project = String(window.PROJECT_NAME || "").trim().toLowerCase();
    if (project) return project;
    const path = String(window.location?.pathname || "").toLowerCase();
    if (path.includes("/dine_flash_buffet") || path.includes("/dineflashbuffet")) {
        return "dine_flash_buffet";
    }
    if (path.includes("/dine_flash") || path.includes("/dineflash")) {
        return "dine_flash";
    }
    return project;
}

function isDineFlashBuffetSurface() {
    const project = String(window.PROJECT_NAME || "").trim().toLowerCase();
    if (project === "dine_flash_buffet") return true;
    return String(window.location?.pathname || "").toLowerCase().includes("/dine_flash_buffet");
}

function isDineFlashTableBookingSurface() {
    const project = String(window.PROJECT_NAME || "").trim().toLowerCase();
    if (project === "dine_flash_buffet") return false;
    if (project === "dine_flash") return true;
    const path = String(window.location?.pathname || "").toLowerCase();
    if (path.includes("/dine_flash_buffet") || path.includes("/dineflashbuffet")) {
        return false;
    }
    return path.includes("/dine_flash") || path.includes("/dineflash");
}

function isDineFlashDiagSurface() {
    return projectsMatch(currentProject(), "dine_flash");
}

// ⚠️ TEMP DIAGNOSTIC (iOS sync recovery). POSTs breadcrumbs to
// /api/dine_flash_client_diag/ — server logs only, no console output.
function syncDiagFields(extra) {
    return {
        browser_id: AppUtils.getBrowserId?.() || AppUtils.getCurrentBrowserId?.() || null,
        project: currentProject(),
        ...(extra || {}),
    };
}

function dineFlashClientDiag(step, fields) {
    if (!isDineFlashDiagSurface()) return;
    try {
        const url = `${AppUtils.getStartUrl()}api/dine_flash_client_diag/`;
        fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": AppUtils.getCSRFToken?.() || "",
            },
            credentials: "same-origin",
            keepalive: true,
            body: JSON.stringify({
                step,
                source: "page",
                browser_id: AppUtils.getBrowserId?.() || AppUtils.getCurrentBrowserId?.() || null,
                timestamp: Date.now(),
                ...(fields || {}),
            }),
        }).catch(() => {});
    } catch (e) {
        // Diagnostics must never break sync.
    }
}

function isEnabled() {
    return isIosDevice()
        && isStandalonePwa()
        && (isDineFlashBuffetSurface() || isDineFlashTableBookingSurface());
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
        innerType === "order_delivered" ||
        innerType === "dinestatus" ||
        innerType === "dine_manager" ||
        innerType === HOSPITAL_MANAGER_PUSH_TYPE ||
        innerType === "thankyou"
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

function resolveRegistrationBatchId(source) {
    const payload = resolvePayload(source);
    const batchId = payload?.registration_batch_id ?? source?.registration_batch_id;
    return batchId != null && String(batchId).trim() !== "" ? String(batchId).trim() : "";
}

function resolveDepartments(source) {
    const payload = resolvePayload(source);
    return Array.isArray(payload?.departments) ? payload.departments : null;
}

function fingerprintDepartments(departments) {
    if (!Array.isArray(departments) || !departments.length) return "";
    return departments
        .map((dept) => `${dept?.booking_id ?? ""}:${dept?.status ?? ""}`)
        .join("|");
}

function resolveVendorId(source, fallbackVendorId) {
    const payload = resolvePayload(source);
    return String(
        payload?.vendor_id ?? source?.vendor_id ?? fallbackVendorId ?? ""
    ).trim();
}

function resolveStatus(source) {
    const payload = resolvePayload(source);
    return String(payload?.status ?? "").trim().toLowerCase();
}

function resolveSeat(source) {
    const payload = resolvePayload(source);
    return String(payload?.seat_no ?? payload?.table_number ?? "").trim();
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

function isDineFlashRecoverableMessage(source) {
    if (!source || typeof source !== "object") return false;

    const sender = String(source.sender ?? "").toLowerCase();
    if (sender && sender !== "server") return false;

    const type = resolveMessageType(source);
    if (!type) return false;

    if (type === "dinestatus") {
        const status = resolveStatus(source);
        if (!status || DINE_FLASH_EXCLUDED_DINESTATUS_STATUSES.has(status)) {
            return false;
        }
        return DINE_FLASH_RECOVERABLE_DINESTATUS_STATUSES.has(status);
    }

    if (type === "thankyou") {
        const status = resolveStatus(source);
        return !status || status === "operation_closed";
    }

    if (type === "dine_manager") {
        return true;
    }

    return false;
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

    if (type === "dinestatus") {
        return `${vendorId}|${bookingId}|dinestatus|${resolveStatus(source)}|${resolveSeat(source)}`;
    }

    if (type === "hospitalstatus") {
        const batchId = resolveRegistrationBatchId(source);
        const departments = resolveDepartments(source);
        if (batchId && departments?.length) {
            return `${vendorId}|${batchId}|hospitalstatus|${hashString(fingerprintDepartments(departments))}`;
        }
        return `${vendorId}|${bookingId}|hospitalstatus|${resolveStatus(source)}`;
    }

    if (type === "hospital_pre_announcement") {
        // Include distance so an updated ETA after the queue advances is a
        // distinct message; same-distance retries still dedupe.
        const distance =
            source?.distance_from_called ??
            resolvePayload(source)?.distance_from_called ??
            "";
        return `${vendorId}|${bookingId}|hospital_pre_announcement|${distance}`;
    }

    if (type === HOSPITAL_MANAGER_PUSH_TYPE) {
        const messageId = resolveMessageId(source);
        if (messageId) {
            return `${vendorId}|${bookingId}|${HOSPITAL_MANAGER_PUSH_TYPE}|${messageId}`;
        }
        return `${vendorId}|${bookingId}|${HOSPITAL_MANAGER_PUSH_TYPE}|${hashString(resolveBody(source))}`;
    }

    if (type === "dine_manager") {
        const messageId = resolveMessageId(source);
        if (messageId) {
            return `${vendorId}|${bookingId}|dine_manager|${messageId}`;
        }
        return `${vendorId}|${bookingId}|dine_manager|${hashString(resolveBody(source))}`;
    }

    if (type === "thankyou") {
        return `${vendorId}|${bookingId}|thankyou|operation_closed`;
    }

    return `${vendorId}|${bookingId}|${type}`;
}

function isRecoverableMessage(source) {
    if (!source || typeof source !== "object") return false;

    if (isDineFlashTableBookingSurface()) {
        return isDineFlashRecoverableMessage(source);
    }

    const sender = String(source.sender ?? "").toLowerCase();
    if (sender && sender !== "server") return false;

    const type = resolveMessageType(source);
    if (!type || type === "buffet_order_details") return false;

    return RECOVERABLE_TYPES.has(type);
}

function resolveAppendKey(msg) {
    const type = resolveMessageType(msg);
    if (
        isDineFlashTableBookingSurface()
        && (type === "dinestatus" || type === "dine_manager" || type === "thankyou")
    ) {
        return msg.booking_id ?? resolveBookingId(msg);
    }
    return msg.token_no;
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

function passesDineFlashBookingGuard(msg) {
    if (!isDineFlashTableBookingSurface()) return true;

    const active = String(AppUtils.storageGet?.("activeDineBookingId") || "").trim();
    if (!active) return true;

    const incoming = resolveBookingId(msg);
    if (!incoming) return true;

    return incoming === active;
}

function passesRecoveryGuard(msg) {
    if (!passesBuffetQrTokenGuard(msg)) return false;
    if (!passesDineFlashBookingGuard(msg)) return false;
    return true;
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

    async function syncMissing() {
        dineFlashClientDiag("SYNC_ENTER", syncDiagFields());

        if (!isEnabled()) {
            dineFlashClientDiag("SYNC_SKIP_NOT_ENABLED", syncDiagFields());
            return;
        }
        if (window.isRestoringHistory === true) {
            dineFlashClientDiag("SYNC_SKIP_RESTORE_ACTIVE", syncDiagFields());
            return;
        }
        if (syncInProgress) {
            dineFlashClientDiag("SYNC_SKIP_ALREADY_RUNNING", syncDiagFields());
            return;
        }

        syncInProgress = true;
        try {
            const vendorId =
                activeVendorId != null
                    ? parseInt(activeVendorId, 10)
                    : await AppUtils.getActiveVendor();
            if (!vendorId) {
                dineFlashClientDiag("SYNC_SKIP_NO_VENDOR", syncDiagFields());
                return;
            }

            const browserId = AppUtils.getBrowserId();
            if (!browserId) {
                dineFlashClientDiag("SYNC_SKIP_NO_BROWSER_ID", syncDiagFields());
                return;
            }

            const messages = (await ChatHistoryService.load(vendorId, browserId)) || [];

            dineFlashClientDiag("SYNC_LOADED", {
                vendor_id: vendorId,
                browser_id: browserId,
                message_count: messages.length,
                project: currentProject(),
            });

            for (const msg of messages) {
                dineFlashClientDiag("SYNC_ROW", {
                    booking_id: resolveBookingId(msg),
                    token_no: msg.token_no,
                    type: resolveMessageType(msg),
                    browser_id: browserId,
                    project: currentProject(),
                });

                const recoverable = isRecoverableMessage(msg);

                let recoveryGuard = false;
                let alreadyHandled = false;

                if (recoverable) {
                    recoveryGuard = passesRecoveryGuard(msg);

                    if (recoveryGuard) {
                        alreadyHandled = isAlreadyHandled(msg, vendorId);
                    }
                }

                dineFlashClientDiag("SYNC_CHECK", {
                    booking_id: resolveBookingId(msg),
                    token_no: msg.token_no,
                    type: resolveMessageType(msg),
                    recoverable,
                    qr_guard: recoveryGuard,
                    already_handled: alreadyHandled,
                    project: currentProject(),
                });

                if (!recoverable) continue;
                if (!recoveryGuard) continue;
                if (alreadyHandled) continue;

                // Phase 9: Buffet Multi-Order — do not paint non-Selected
                // tokens into the visible conversation. Still mark handled
                // so sync state stays correct; rebuild loads them later.
                let paintMessage = true;
                if (isDineFlashBuffetSurface()) {
                    try {
                        const convMod = await import(
                            "../buffet/services/selectedOrderConversationService.js"
                        );
                        if (typeof convMod.shouldPaintHistoryMessage === "function") {
                            paintMessage = Boolean(convMod.shouldPaintHistoryMessage(msg));
                        }
                    } catch (e) {
                        paintMessage = true;
                    }
                }

                const messageType = resolveMessageType(msg);
                const appendKey = resolveAppendKey(msg);

                dineFlashClientDiag("SYNC_APPENDING", {
                    booking_id: resolveBookingId(msg),
                    token_no: msg.token_no,
                    type: messageType,
                    project: currentProject(),
                    paint: paintMessage,
                });

                if (paintMessage) {
                    appendMessage(
                        msg.rendered,
                        msg.sender,
                        msg.timestamp,
                        messageType,
                        appendKey
                    );

                    dineFlashClientDiag("SYNC_APPENDED", {
                        booking_id: resolveBookingId(msg),
                        token_no: msg.token_no,
                        type: messageType,
                        project: currentProject(),
                    });
                }

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
            dineFlashClientDiag("SYNC_TIMER_TICK", syncDiagFields());
            syncMissing();
        }, SYNC_INTERVAL_MS);
        dineFlashClientDiag("SYNC_TIMER_STARTED", syncDiagFields({
            interval_ms: SYNC_INTERVAL_MS,
        }));
    }

    function init() {
        dineFlashClientDiag("SYNC_INIT", syncDiagFields({
            vendor_id: activeVendorId != null ? activeVendorId : null,
        }));

        if (!isEnabled()) return;
        startPeriodicSync();

        if (listenersBound) return;
        listenersBound = true;

        document.addEventListener("visibilitychange", () => {
            dineFlashClientDiag("VISIBILITY_CHANGE", syncDiagFields());
            if (document.visibilityState === "visible") {
                syncMissing();
            }
        });

        window.addEventListener("pageshow", (event) => {
            dineFlashClientDiag("PAGE_SHOW", syncDiagFields());
            if (event.persisted || document.visibilityState === "visible") {
                syncMissing();
            }
        });

        window.addEventListener("pagehide", () => {
            dineFlashClientDiag("PAGE_HIDE", syncDiagFields());
        });

        window.addEventListener("focus", () => {
            dineFlashClientDiag("WINDOW_FOCUS", syncDiagFields());
        });

        window.addEventListener("blur", () => {
            dineFlashClientDiag("WINDOW_BLUR", syncDiagFields());
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
