// Dine Flash ONLY — per-booking conversation isolation in Multi-Booking Mode.

import { ChatHistoryService } from "../../services/chatHistoryService.js";
import { ChatSyncService } from "../../services/chatSyncService.js?v=20261027_1";
import { appendMessage } from "../../services/chatService.js";
import { WelcomeMessageService } from "../../services/welcomeMessageService.js";
import { getSelectedBooking } from "./selectedBookingService.js?v=20261027_1";
import { isMultiBookingMode } from "./multiBookingModeService.js?v=20261027_1";
import { isPushForSelectedBooking } from "./multiBookingPushCompatibilityService.js?v=20261027_1";

let inFlightLoad = null;

function isDineFlashSurface() {
    return String(window.PROJECT_NAME || "").trim().toLowerCase() === "dine_flash";
}

function normalizeId(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
}

function messageMatchesSelectedBooking(msg, bookingId) {
    const selected = normalizeId(bookingId);
    if (!selected) return true;

    const msgId =
        normalizeId(msg && (msg.booking_id ?? msg.payload?.booking_id ?? msg.data?.booking_id));
    if (!msgId) return true;

    return msgId === selected;
}

function shouldIsolateConversation() {
    return isDineFlashSurface() && isMultiBookingMode();
}

function shouldPaintPushMessage(pushData) {
    if (!shouldIsolateConversation()) return true;
    return isPushForSelectedBooking(pushData);
}

function shouldPaintHistoryMessage(msg) {
    if (!shouldIsolateConversation()) return true;
    const selected = getSelectedBooking();
    if (!selected || !selected.booking_id) return true;
    return messageMatchesSelectedBooking(msg, selected.booking_id);
}

async function loadChatHistoryFresh(vendorId, browserId) {
    const key = `${vendorId}:${browserId}`;
    if (inFlightLoad && inFlightLoad.key === key) {
        return inFlightLoad.promise;
    }

    const promise = ChatHistoryService.load(vendorId, browserId)
        .then((messages) => (Array.isArray(messages) ? messages : []))
        .finally(() => {
            if (inFlightLoad && inFlightLoad.key === key) {
                inFlightLoad = null;
            }
        });

    inFlightLoad = { key, promise };
    return promise;
}

async function rebuildVisibleConversation(bookingId) {
    if (!shouldIsolateConversation()) return;

    const selectedId = normalizeId(bookingId) || normalizeId(getSelectedBooking()?.booking_id);
    if (!selectedId) return;

    const container = document.getElementById("chat-container");
    if (!container) return;

    container.innerHTML = "";

    const vendorId =
        typeof AppUtils !== "undefined" && typeof AppUtils.getActiveVendor === "function"
            ? await AppUtils.getActiveVendor()
            : AppUtils?.storageGet?.("activeVendor");
    const browserId =
        typeof AppUtils !== "undefined" && typeof AppUtils.getBrowserId === "function"
            ? AppUtils.getBrowserId()
            : null;

    if (!vendorId || !browserId) return;

    const messages = await loadChatHistoryFresh(vendorId, browserId);
    const filtered = messages.filter((msg) => messageMatchesSelectedBooking(msg, selectedId));

    if (WelcomeMessageService && typeof WelcomeMessageService.ensureWelcome === "function") {
        await WelcomeMessageService.ensureWelcome(vendorId);
    }

    filtered.forEach((msg) => {
        const messageType = msg.type || msg.message_type || "dinestatus";
        appendMessage(
            msg.rendered || msg.message || "",
            msg.sender || "server",
            msg.timestamp,
            messageType,
            msg.booking_id || selectedId,
            msg.message_id
        );
    });

    if (typeof ChatSyncService.seedFromMessages === "function") {
        ChatSyncService.seedFromMessages(filtered, vendorId);
    }
}

export {
    shouldPaintPushMessage,
    shouldPaintHistoryMessage,
    rebuildVisibleConversation,
    messageMatchesSelectedBooking,
};
