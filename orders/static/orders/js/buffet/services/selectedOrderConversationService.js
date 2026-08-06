// orders/static/orders/js/buffet/services/selectedOrderConversationService.js
//
// Dine Flash Buffet ONLY — Phase 9 Per-Order Conversation Isolation.
//
// Makes the visible #chat-container a projection of Selected Order while
// Multi-Order Mode is on. Does not change WebChatMessage persistence,
// ChatHistoryService APIs, push delivery, ACK, Selected Order storage,
// Registry, or BuffetOrderLookup.
//
// Reuses Phase 5–8:
//   - selectedOrderService / multiOrderModeService (gates)
//   - multiOrderPushCompatibilityService.isPushForSelectedOrder (push paint)
//   - ChatHistoryService.load + appendMessage + WelcomeMessageService (render)

import { ChatHistoryService } from "../../services/chatHistoryService.js";
import { ChatSyncService } from "../../services/chatSyncService.js";
import { appendMessage } from "../../services/chatService.js?v=20260806_1";
import { WelcomeMessageService } from "../../services/welcomeMessageService.js";
import { getSelectedOrder } from "./selectedOrderService.js";
import { isMultiOrderMode } from "./multiOrderModeService.js";
import { isPushForSelectedOrder } from "./multiOrderPushCompatibilityService.js";

/** @type {{ key: string, promise: Promise<Array> } | null} */
let inFlightLoad = null;

function isDineFlashBuffetSurface() {
    if (
        typeof window.PROJECT_NAME === "string" &&
        window.PROJECT_NAME.trim().toLowerCase() === "dine_flash_buffet"
    ) {
        return true;
    }
    const base = window.BASE || "";
    if (base.includes("/dine_flash_buffet/")) return true;
    const path = (window.location?.pathname || "").toLowerCase();
    return path.includes("/dine_flash_buffet") || path.includes("/dineflashbuffet");
}

function normalizeToken(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
}

function tokensMatch(a, b) {
    const left = normalizeToken(a);
    const right = normalizeToken(b);
    if (!left || !right) return false;
    return left === right;
}

/**
 * Whether a history/push message belongs to the Selected conversation.
 * Tokenless (vendor-level) messages remain visible.
 */
function messageMatchesSelectedToken(msg, selectedToken) {
    const selected = normalizeToken(selectedToken);
    if (!selected) return true;

    const msgToken = normalizeToken(msg && msg.token_no);
    if (!msgToken) return true;

    return msgToken === selected;
}

function shouldIsolateConversation() {
    return isDineFlashBuffetSurface() && isMultiOrderMode();
}

/**
 * Live push paint gate. Outside Multi-Order Mode always paints (unchanged).
 */
function shouldPaintPushMessage(pushData) {
    if (!shouldIsolateConversation()) return true;
    return isPushForSelectedOrder(pushData);
}

/**
 * History / sync paint gate using current Selected Order.
 */
function shouldPaintHistoryMessage(msg) {
    if (!shouldIsolateConversation()) return true;
    const selected = getSelectedOrder();
    if (!selected || !selected.token_number) return true;
    return messageMatchesSelectedToken(msg, selected.token_number);
}

/**
 * Fresh ChatHistoryService.load with same-tick in-flight coalesce only.
 * Never keeps a long-lived transcript cache.
 */
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

/**
 * Render filtered buffet history into a cleared #chat-container.
 * Reuses ChatRestoreService snapshot-dedup rules for the Selected token only.
 */
function renderBuffetMessagesForToken(messages, selectedToken) {
    const token = normalizeToken(selectedToken);
    window.buffetOrderSnapshotTokens = new Set();

    const latestSnapshotIndexByToken = new Map();
    messages.forEach((msg, idx) => {
        if (msg.type === "buffet_order_details" && msg.token_no != null) {
            const tokenKey = String(msg.token_no);
            if (token && !tokensMatch(tokenKey, token)) return;
            latestSnapshotIndexByToken.set(tokenKey, idx);
        }
    });

    messages.forEach((msg, idx) => {
        if (!messageMatchesSelectedToken(msg, token)) return;

        if (msg.type === "buffet_order_details" && msg.token_no != null) {
            const tokenKey = String(msg.token_no);
            if (latestSnapshotIndexByToken.get(tokenKey) !== idx) {
                return;
            }
            appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.token_no);
            window.buffetOrderSnapshotTokens.add(tokenKey);
            return;
        }

        appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.token_no);
    });
}

/**
 * Clear visible chat and rebuild from a fresh history load for Selected token.
 * No-op outside Buffet Multi-Order Mode.
 *
 * @param {string|number} tokenNumber
 * @returns {Promise<boolean>} true when rebuild ran
 */
async function rebuildVisibleConversation(tokenNumber) {
    if (!shouldIsolateConversation()) return false;

    const token = normalizeToken(tokenNumber);
    if (!token) return false;

    const chatContainer = document.getElementById("chat-container");
    if (!chatContainer) {
        console.warn("[buffet] conversation rebuild: chat container missing");
        return false;
    }

    let vendorId = null;
    try {
        if (typeof AppUtils !== "undefined" && typeof AppUtils.getActiveVendor === "function") {
            vendorId = await AppUtils.getActiveVendor();
        }
    } catch (e) {
        vendorId = null;
    }
    if (!vendorId) {
        const selected = getSelectedOrder();
        vendorId = selected && selected.vendor_id ? selected.vendor_id : null;
    }
    if (!vendorId) {
        console.warn("[buffet] conversation rebuild: no vendor");
        return false;
    }

    const browserId =
        typeof AppUtils !== "undefined" && typeof AppUtils.getBrowserId === "function"
            ? AppUtils.getBrowserId()
            : null;
    if (!browserId) {
        console.warn("[buffet] conversation rebuild: no browser id");
        return false;
    }

    const wasRestoring = window.isRestoringHistory === true;
    window.isRestoringHistory = true;
    try {
        const messages = await loadChatHistoryFresh(vendorId, browserId);
        ChatSyncService.seedFromMessages(messages, vendorId);

        chatContainer.innerHTML = "";
        renderBuffetMessagesForToken(messages, token);

        // Exactly once after clear — WelcomeMessageService.show also no-ops
        // duplicates if a wrapper somehow remains.
        WelcomeMessageService.show(
            (typeof AppUtils !== "undefined" &&
            typeof AppUtils.getSelectedOutletName === "function"
                ? AppUtils.getSelectedOutletName()
                : null) || "our outlet"
        );

        return true;
    } catch (e) {
        console.warn("[buffet] conversation rebuild failed:", e);
        return false;
    } finally {
        window.isRestoringHistory = wasRestoring;
    }
}

export {
    messageMatchesSelectedToken,
    shouldPaintPushMessage,
    shouldPaintHistoryMessage,
    shouldIsolateConversation,
    loadChatHistoryFresh,
    rebuildVisibleConversation,
};
