// Dine Flash ONLY — Multi-Booking Mode (Buffet multiOrderModeService pattern).

const STORAGE_KEY = "multi_booking_mode";
const INTENT_SESSION_KEY = "dine_flash_additional_booking_intent";

function isDineFlashProject() {
    return String(window.PROJECT_NAME || "").trim().toLowerCase() === "dine_flash";
}

function isMultiBookingMode() {
    if (!isDineFlashProject()) return false;
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageGet !== "function") {
        return false;
    }
    try {
        const value = AppUtils.storageGet(STORAGE_KEY);
        return value === "1" || value === "true";
    } catch (e) {
        return false;
    }
}

function enableMultiBookingMode() {
    if (!isDineFlashProject()) return false;
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageSet !== "function") {
        return false;
    }
    try {
        AppUtils.storageSet(STORAGE_KEY, "1");
        return true;
    } catch (e) {
        console.warn("[dine_flash] multi_booking_mode write failed:", e);
        return false;
    }
}

function markAdditionalBookingIntent() {
    try {
        sessionStorage.setItem(INTENT_SESSION_KEY, "1");
    } catch (e) {
        /* ignore */
    }
}

function clearAdditionalBookingIntent() {
    try {
        sessionStorage.removeItem(INTENT_SESSION_KEY);
    } catch (e) {
        /* ignore */
    }
}

function hasAdditionalBookingIntent() {
    try {
        return sessionStorage.getItem(INTENT_SESSION_KEY) === "1";
    } catch (e) {
        return false;
    }
}

function shouldSubmitAsAdditionalBooking() {
    if (!isDineFlashProject()) return false;
    return hasAdditionalBookingIntent() || isMultiBookingMode();
}

export {
    isMultiBookingMode,
    enableMultiBookingMode,
    markAdditionalBookingIntent,
    clearAdditionalBookingIntent,
    hasAdditionalBookingIntent,
    shouldSubmitAsAdditionalBooking,
};
