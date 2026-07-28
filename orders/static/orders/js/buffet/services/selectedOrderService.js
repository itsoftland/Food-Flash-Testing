// orders/static/orders/js/buffet/services/selectedOrderService.js
//
// Dine Flash Buffet ONLY — Phase 5 Selected Order (client-side runtime view).
//
// Minimal identity for the order currently shown on Home. Never writes
// BuffetOrderLookup, Registry, chat, or push. Recovery continues to use
// BuffetOrderLookup (Latest) unchanged.
//
// Storage: prefixed localStorage via AppUtils (same convention as token /
// order_lookup_id). Survives refresh in this browser profile. Does not
// survive a cleared storage / new profile. On identity drift vs Home token
// (e.g. after recovery), callers reconcile by adopting Home identity.

const STORAGE_KEY = "selected_order";

function normalizeField(value) {
    if (value === null || value === undefined) return null;
    const text = String(value).trim();
    return text || null;
}

function readRaw() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageGet !== "function") {
        return null;
    }
    try {
        const raw = AppUtils.storageGet(STORAGE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object") return null;
        return parsed;
    } catch (e) {
        return null;
    }
}

/**
 * @returns {{ order_lookup_id: string, vendor_id: string, token_number: string } | null}
 */
function getSelectedOrder() {
    const parsed = readRaw();
    if (!parsed) return null;

    const orderLookupId = normalizeField(parsed.order_lookup_id);
    const vendorId = normalizeField(parsed.vendor_id);
    const tokenNumber = normalizeField(parsed.token_number);

    if (!orderLookupId || !vendorId || !tokenNumber) {
        return null;
    }

    return {
        order_lookup_id: orderLookupId,
        vendor_id: vendorId,
        token_number: tokenNumber,
    };
}

/**
 * Persist Selected Order identity only. No chat/push/recovery fields.
 *
 * @param {{ order_lookup_id?: *, vendor_id?: *, token_number?: * }} identity
 * @returns {{ order_lookup_id: string, vendor_id: string, token_number: string } | null}
 */
function setSelectedOrder(identity) {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageSet !== "function") {
        return null;
    }
    if (!identity || typeof identity !== "object") return null;

    const orderLookupId = normalizeField(identity.order_lookup_id);
    const vendorId = normalizeField(identity.vendor_id);
    const tokenNumber = normalizeField(identity.token_number);

    if (!orderLookupId || !vendorId || !tokenNumber) {
        return null;
    }

    const payload = {
        order_lookup_id: orderLookupId,
        vendor_id: vendorId,
        token_number: tokenNumber,
    };

    try {
        AppUtils.storageSet(STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {
        console.warn("[buffet] selected_order write failed:", e);
        return null;
    }

    return payload;
}

function clearSelectedOrder() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageRemove !== "function") {
        return;
    }
    try {
        AppUtils.storageRemove(STORAGE_KEY);
    } catch (e) {
        // ignore
    }
}

export { getSelectedOrder, setSelectedOrder, clearSelectedOrder };
