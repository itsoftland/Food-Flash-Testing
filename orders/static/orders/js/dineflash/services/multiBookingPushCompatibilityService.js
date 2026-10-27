// Dine Flash ONLY — Multi-Booking push compatibility.

import { getSelectedBooking } from "./selectedBookingService.js?v=20261027_1";
import { isMultiBookingMode } from "./multiBookingModeService.js?v=20261027_1";

const TERMINAL_DINE_STATUSES = new Set(["booking_cancelled", "operation_closed"]);

function normalizeId(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
}

function isTerminalDinePush(pushData, messageType) {
    const type = String(messageType || pushData?.type || "").toLowerCase();
    if (type === "thankyou") return true;
    if (type === "dinestatus") {
        const status = String(pushData?.status || "").trim().toLowerCase();
        return TERMINAL_DINE_STATUSES.has(status);
    }
    return false;
}

function isPushForSelectedBooking(pushData) {
    if (!isMultiBookingMode()) return true;

    const selected = getSelectedBooking();
    if (!selected || !selected.booking_id) return true;

    const pushBookingId = normalizeId(pushData && pushData.booking_id);
    if (!pushBookingId) return true;

    return pushBookingId === normalizeId(selected.booking_id);
}

function shouldApplyPushHomeContext(pushData) {
    return isPushForSelectedBooking(pushData);
}

async function handleDineFlashActiveBookingLifecyclePush(pushData, messageType) {
    if (!isTerminalDinePush(pushData, messageType)) {
        return { outcome: "noop", reason: "not_terminal" };
    }

    const bookingHint = normalizeId(pushData && pushData.booking_id);

    try {
        const restoreMod = await import("./selectedBookingRestoreService.js?v=20261027_1");
        if (typeof restoreMod.reactIfSelectedBookingInactive === "function") {
            await restoreMod.reactIfSelectedBookingInactive({ bookingHint });
        }
        const selectorMod = await import("./activeBookingSelectorService.js?v=20261027_1");
        if (typeof selectorMod.refreshActiveBookingSelector === "function") {
            await selectorMod.refreshActiveBookingSelector();
        }
    } catch (e) {
        console.warn("[dine_flash] lifecycle push handling failed:", e);
    }

    return { outcome: "handled" };
}

export {
    isPushForSelectedBooking,
    shouldApplyPushHomeContext,
    handleDineFlashActiveBookingLifecyclePush,
};
