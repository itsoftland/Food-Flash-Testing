// orders/static/orders/js/buffet/services/multiOrderPushCompatibilityService.js
//
// Dine Flash Buffet ONLY — Phase 8 Multi-Order push compatibility.
//
// Adapts client-side push handling so Selected Order remains the user's
// Home context. Does not redesign push delivery, SW, subscription binding,
// BuffetOrderLookup, Registry semantics, or chat architecture.
//
// Reuses Phase 5–7 services:
//   - selectedOrderService (read Selected)
//   - multiOrderModeService (gate)
//   - selectedOrderRestoreService.reactIfSelectedOrderInactive (Phase 7)
//   - activeOrderSelectorService.refreshActiveOrderSelector (Phase 7)

import { getSelectedOrder } from "./selectedOrderService.js";
import { isMultiOrderMode } from "./multiOrderModeService.js";

const TERMINAL_PUSH_TYPES = new Set([
    "item_cancelled",
    "item_delivered",
    "item_operation_closed",
    "buffet_item_cancelled",
    "buffet_item_delivered",
    "buffet_item_operation_closed",
    "order_delivered",
]);

function normalizeToken(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
}

function isTerminalPushType(messageType) {
    return TERMINAL_PUSH_TYPES.has(String(messageType || ""));
}

/**
 * True when the push belongs to the currently Selected Order.
 * When Multi-Order Mode is off, or Selected is missing, treat as Selected
 * so single-order / pre-seed behaviour stays unchanged.
 */
function isPushForSelectedOrder(pushData) {
    if (!isMultiOrderMode()) return true;

    const selected = getSelectedOrder();
    if (!selected || !selected.token_number) return true;

    const pushToken = normalizeToken(pushData && pushData.token_no);
    if (!pushToken) return true;

    return pushToken === normalizeToken(selected.token_number);
}

/**
 * Whether push handling may update Home-facing vendor/outlet context
 * (e.g. updateChatOnPush → activeVendor). Never true for a different
 * active order while Multi-Order Mode is on — that would steal focus
 * from Selected Order without changing AppUtils token.
 */
function shouldApplyPushHomeContext(pushData) {
    return isPushForSelectedOrder(pushData);
}

/**
 * Terminal buffet push lifecycle for Multi-Order Mode.
 *
 * - Push for Selected Order that left the Registry → Phase 7 fallback
 *   (restore Latest, update Selected, soft Home refresh).
 * - Push for a different order → Phase 7 no-ops Selected; still refresh
 *   the selector so a completed order disappears.
 * - Non-terminal → no-op.
 *
 * Never sets Selected Order or AppUtils token from the push payload itself.
 */
async function handleMultiOrderTerminalPush(pushData, messageType) {
    if (!isTerminalPushType(messageType)) {
        return { outcome: "noop", reason: "not_terminal" };
    }

    const tokenHint = normalizeToken(pushData && pushData.token_no);

    let restoreOutcome = { outcome: "skipped" };
    try {
        const restoreMod = await import("./selectedOrderRestoreService.js?v=20260824_2");
        if (typeof restoreMod.reactIfSelectedOrderInactive === "function") {
            restoreOutcome = await restoreMod.reactIfSelectedOrderInactive({
                tokenHint: tokenHint || undefined,
            });
        }
    } catch (e) {
        console.warn("[buffet] multi-order push Selected lifecycle failed:", e);
        restoreOutcome = { outcome: "error", reason: "restore_exception" };
    }

    try {
        const selectorMod = await import("./activeOrderSelectorService.js?v=20260824_1");
        if (typeof selectorMod.refreshActiveOrderSelector === "function") {
            await selectorMod.refreshActiveOrderSelector();
        }
    } catch (e) {
        console.warn("[buffet] multi-order push selector refresh failed:", e);
    }

    return {
        outcome: "handled",
        for_selected: isPushForSelectedOrder(pushData),
        restore: restoreOutcome,
    };
}

export {
    TERMINAL_PUSH_TYPES,
    isTerminalPushType,
    isPushForSelectedOrder,
    shouldApplyPushHomeContext,
    handleMultiOrderTerminalPush,
};
