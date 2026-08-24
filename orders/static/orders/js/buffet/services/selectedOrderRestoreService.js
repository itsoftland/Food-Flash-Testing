// orders/static/orders/js/buffet/services/selectedOrderRestoreService.js
//
// Dine Flash Buffet ONLY — Phase 6 Selected Order restore for Multi-Order Mode.
//
// When Multi-Order Mode is enabled, attempts to restore Selected Order by
// validating it against GET active_orders (Registry read). Never writes
// BuffetOrderLookup, never uses Selected Order as the recovery key.
//
// When Multi-Order Mode is disabled → outcome "disabled" (caller keeps
// existing Latest resolve path unchanged).

import { getSelectedOrder, setSelectedOrder, clearSelectedOrder } from "./selectedOrderService.js";
import { isMultiOrderMode } from "./multiOrderModeService.js";

let dependenciesPromise = null;

async function loadDependencies() {
    const base = window.BASE || "/caller_on/";
    const [authModule, apiModule] = await Promise.all([
        import(`${base}static/utils/js/services/authFetchService.js`),
        import(`${base}static/utils/js/apiEndpoints.js`),
    ]);
    return {
        fetchWithAutoRefresh: authModule.fetchWithAutoRefresh,
        API_ENDPOINTS: apiModule.API_ENDPOINTS,
    };
}

function getDependencies() {
    if (!dependenciesPromise) {
        dependenciesPromise = loadDependencies();
    }
    return dependenciesPromise;
}

function normalizeId(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
}

function tokensMatch(a, b) {
    const left = normalizeId(a);
    const right = normalizeId(b);
    if (!left || !right) return false;
    return left === right;
}

function vendorsMatch(a, b) {
    return tokensMatch(a, b);
}

/**
 * GET active_orders for validation only. Returns array or null. Never throws.
 */
async function fetchActiveOrders(orderLookupId) {
    const lookupId = normalizeId(orderLookupId);
    if (!lookupId) return null;

    const { fetchWithAutoRefresh, API_ENDPOINTS } = await getDependencies();
    const url =
        `${API_ENDPOINTS.BUFFET_ACTIVE_ORDERS}` +
        `?order_lookup_id=${encodeURIComponent(lookupId)}`;

    let response;
    try {
        response = await fetchWithAutoRefresh(url, { method: "GET" });
    } catch (e) {
        console.warn("[buffet] selected_order validate fetch failed:", e);
        return null;
    }

    if (!response || !response.ok) return null;

    let data;
    try {
        data = await response.json();
    } catch (e) {
        return null;
    }

    return Array.isArray(data) ? data : null;
}

async function applySelectedToHomeIdentity(selected) {
    if (!selected || typeof AppUtils === "undefined") return;

    if (selected.vendor_id && typeof AppUtils.setCurrentVendors === "function") {
        await AppUtils.setCurrentVendors(String(selected.vendor_id));
    }
    if (selected.token_number && typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(String(selected.token_number));
    }
}

/**
 * Try restore Selected Order when Multi-Order Mode is on.
 *
 * @returns {Promise<
 *   | { outcome: "disabled" }
 *   | { outcome: "restored", order: { order_lookup_id, vendor_id, token_number } }
 *   | { outcome: "fallback", reason: string }
 * >}
 */
async function tryRestoreSelectedOrder() {
    if (!isMultiOrderMode()) {
        return { outcome: "disabled" };
    }

    const selected = getSelectedOrder();
    if (!selected) {
        return { outcome: "fallback", reason: "selected_missing" };
    }

    const orders = await fetchActiveOrders(selected.order_lookup_id);
    if (!orders) {
        return { outcome: "fallback", reason: "validate_unavailable" };
    }

    const match = orders.find(
        (entry) =>
            entry &&
            tokensMatch(entry.token_number, selected.token_number) &&
            vendorsMatch(entry.vendor_id, selected.vendor_id)
    );

    if (!match) {
        clearSelectedOrder();
        return { outcome: "fallback", reason: "selected_not_active" };
    }

    // Keep Selected Order in sync with the validated registry row.
    const confirmed = setSelectedOrder({
        order_lookup_id: selected.order_lookup_id,
        vendor_id: normalizeId(match.vendor_id) || selected.vendor_id,
        token_number: normalizeId(match.token_number) || selected.token_number,
    });

    const order = confirmed || selected;
    await applySelectedToHomeIdentity(order);

    return { outcome: "restored", order };
}

/**
 * Apply Latest Order resolve payload into Home identity (fallback path helper).
 * Does not touch BuffetOrderLookup — only client storage mirrors.
 */
async function applyLatestOrderIdentity(resolved) {
    if (!resolved || typeof AppUtils === "undefined") return;

    const locationId = normalizeId(resolved.location_id);
    const vendorId = normalizeId(resolved.vendor_id);
    const token = normalizeId(resolved.token_no);

    if (locationId && typeof AppUtils.set === "function") {
        await AppUtils.set(locationId);
    }
    if (vendorId && typeof AppUtils.setCurrentVendors === "function") {
        await AppUtils.setCurrentVendors(vendorId);
    }
    if (token && typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(token);
    }

    // Align Selected Order with Latest after fallback so Current badge matches Home.
    const orderLookupId =
        typeof AppUtils.getOrderLookupId === "function"
            ? AppUtils.getOrderLookupId()
            : null;
    if (orderLookupId && vendorId && token) {
        setSelectedOrder({
            order_lookup_id: orderLookupId,
            vendor_id: vendorId,
            token_number: token,
        });
    }
}

/**
 * In-session lifecycle: if Selected Order matches the updated token and is no
 * longer in the selectable Registry list, fall back to Latest Order and reload
 * Home status. No-op when Selected is missing or refers to a different token.
 *
 * @param {{ tokenHint?: * }} [options]
 * @returns {Promise<{ outcome: string, reason?: string }>}
 */
async function reactIfSelectedOrderInactive({ tokenHint } = {}) {
    const selected = getSelectedOrder();
    if (!selected) {
        return { outcome: "noop", reason: "no_selected" };
    }

    const hint = normalizeId(tokenHint);
    if (hint && !tokensMatch(hint, selected.token_number)) {
        return { outcome: "noop", reason: "different_token" };
    }

    const orders = await fetchActiveOrders(selected.order_lookup_id);
    if (!orders) {
        return { outcome: "noop", reason: "validate_unavailable" };
    }

    const stillActive = orders.some(
        (entry) =>
            entry &&
            tokensMatch(entry.token_number, selected.token_number) &&
            vendorsMatch(entry.vendor_id, selected.vendor_id)
    );
    if (stillActive) {
        return { outcome: "still_active" };
    }

    clearSelectedOrder();

    const orderLookupId =
        selected.order_lookup_id ||
        (typeof AppUtils !== "undefined" && typeof AppUtils.getOrderLookupId === "function"
            ? AppUtils.getOrderLookupId()
            : null);
    if (!orderLookupId) {
        return { outcome: "fallback_failed", reason: "no_order_lookup_id" };
    }

    try {
        const lookupMod = await import("./orderLookupService.js?v=20260824_2");
        if (typeof lookupMod.resolveOrderLookupForRelaunch !== "function") {
            return { outcome: "fallback_failed", reason: "no_resolve" };
        }
        const lookupResult = await lookupMod.resolveOrderLookupForRelaunch({
            order_lookup_id: orderLookupId,
        });
        if (lookupResult.outcome !== "found" || !lookupResult.order) {
            return {
                outcome: "fallback_failed",
                reason: lookupResult.reason || lookupResult.outcome || "not_found",
            };
        }

        await applyLatestOrderIdentity(lookupResult.order);

        const latestToken = normalizeId(lookupResult.order.token_no);
        const hook = window.__buffetApplySelectedOrderHomeView;
        if (latestToken && typeof hook === "function") {
            try {
                await hook(latestToken);
            } catch (e) {
                console.warn("[buffet] Selected Order lifecycle Home reload failed:", e);
            }
        }

        return { outcome: "fell_back_to_latest", token: latestToken };
    } catch (e) {
        console.warn("[buffet] Selected Order lifecycle fallback failed:", e);
        return { outcome: "fallback_failed", reason: "exception" };
    }
}

export {
    tryRestoreSelectedOrder,
    applyLatestOrderIdentity,
    fetchActiveOrders,
    reactIfSelectedOrderInactive,
};
