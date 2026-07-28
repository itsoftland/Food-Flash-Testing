// orders/static/orders/js/buffet/services/multiOrderModeService.js
//
// Dine Flash Buffet ONLY — Phase 6 Multi-Order Mode flag.
//
// Enabled only after a successful "+" / additional-order submit.
// Never inferred from Registry count alone. When disabled, resume must
// follow BuffetOrderLookup (Latest) exactly as today.
//
// Storage: prefixed localStorage via AppUtils (same convention as
// order_lookup_id / selected_order). Not a recovery key.

const STORAGE_KEY = "multi_order_mode";
const INTENT_SESSION_KEY = "buffet_additional_order_intent";

function isMultiOrderMode() {
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

/**
 * Latch Multi-Order Mode on. Idempotent. Never clears automatically.
 */
function enableMultiOrderMode() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageSet !== "function") {
        return false;
    }
    try {
        AppUtils.storageSet(STORAGE_KEY, "1");
        return true;
    } catch (e) {
        console.warn("[buffet] multi_order_mode write failed:", e);
        return false;
    }
}

/**
 * Session-only intent: user entered the "+" ordering flow.
 * Survives utility → combined navigation; cleared after submit attempt.
 */
function markAdditionalOrderIntent() {
    try {
        sessionStorage.setItem(INTENT_SESSION_KEY, "1");
    } catch (e) {
        // ignore
    }
}

function clearAdditionalOrderIntent() {
    try {
        sessionStorage.removeItem(INTENT_SESSION_KEY);
    } catch (e) {
        // ignore
    }
}

function hasAdditionalOrderIntent() {
    try {
        return sessionStorage.getItem(INTENT_SESSION_KEY) === "1";
    } catch (e) {
        return false;
    }
}

/**
 * True when this submit should be treated as "+" (additional order).
 * Either explicit intent from Place Another Order, or already in Multi-Order Mode.
 */
function shouldSubmitAsAdditionalOrder() {
    return hasAdditionalOrderIntent() || isMultiOrderMode();
}

export {
    isMultiOrderMode,
    enableMultiOrderMode,
    markAdditionalOrderIntent,
    clearAdditionalOrderIntent,
    hasAdditionalOrderIntent,
    shouldSubmitAsAdditionalOrder,
};
