// Dine Flash ONLY — Selected Booking restore for Multi-Booking Mode.

import { getSelectedBooking, setSelectedBooking, clearSelectedBooking } from "./selectedBookingService.js";
import { isMultiBookingMode } from "./multiBookingModeService.js";

const ACTIVE_DINE_BOOKING_KEY = "activeDineBookingId";

let dependenciesPromise = null;
let restoreSettledResolve = null;
let restoreSettledPromise = Promise.resolve();
/** @type {((orderLookupId: string) => Promise<Array|null>|Array|null)|null} */
let testFetchActiveBookingsImpl = null;

/**
 * Test-only hook: bypass network when exercising restore outcomes in Node harness.
 */
export function __setTestFetchActiveBookingsImpl(fn) {
    testFetchActiveBookingsImpl = fn;
}

export function resetRestoreSettledCycle() {
    restoreSettledPromise = new Promise((resolve) => {
        restoreSettledResolve = resolve;
    });
}

export function markRestoreSettled() {
    if (typeof restoreSettledResolve === "function") {
        restoreSettledResolve();
        restoreSettledResolve = null;
    }
    window.__dineFlashSelectedRestoreDone = true;
}

export function whenRestoreSettled() {
    return restoreSettledPromise;
}

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

function bookingsMatch(a, b) {
    return normalizeId(a) === normalizeId(b) && normalizeId(a) !== "";
}

async function fetchActiveBookings(orderLookupId) {
    const lookupId = normalizeId(orderLookupId);
    if (!lookupId) return null;

    if (testFetchActiveBookingsImpl) {
        return await testFetchActiveBookingsImpl(lookupId);
    }

    const { fetchWithAutoRefresh, API_ENDPOINTS } = await getDependencies();
    const url =
        `${API_ENDPOINTS.DINE_FLASH_ACTIVE_BOOKINGS}` +
        `?order_lookup_id=${encodeURIComponent(lookupId)}`;

    let response;
    try {
        response = await fetchWithAutoRefresh(url, { method: "GET" });
    } catch (e) {
        console.warn("[dine_flash] selected_booking validate fetch failed:", e);
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
    if (selected.booking_no && typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(String(selected.booking_no));
    }
    if (selected.booking_id && typeof AppUtils.storageSet === "function") {
        AppUtils.storageSet(ACTIVE_DINE_BOOKING_KEY, String(selected.booking_id));
    }
}

async function tryRestoreSelectedBooking() {
    if (!isMultiBookingMode()) {
        return { outcome: "disabled" };
    }

    const selected = getSelectedBooking();
    if (!selected) {
        return { outcome: "fallback", reason: "selected_missing" };
    }

    const bookings = await fetchActiveBookings(selected.order_lookup_id);
    if (bookings === null) {
        await applySelectedToHomeIdentity(selected);
        return { outcome: "restored", order: selected, validated: false };
    }

    const match = bookings.find(
        (entry) =>
            entry &&
            bookingsMatch(entry.booking_id, selected.booking_id) &&
            bookingsMatch(entry.vendor_id, selected.vendor_id)
    );

    if (!match) {
        clearSelectedBooking();
        return { outcome: "fallback", reason: "selected_not_active" };
    }

    const confirmed = setSelectedBooking({
        order_lookup_id: selected.order_lookup_id,
        vendor_id: normalizeId(match.vendor_id) || selected.vendor_id,
        booking_id: normalizeId(match.booking_id) || selected.booking_id,
        booking_no: normalizeId(match.booking_no) || selected.booking_no,
    });

    const order = confirmed || selected;
    await applySelectedToHomeIdentity(order);

    return { outcome: "restored", order, validated: true };
}

async function applyLatestBookingIdentity(resolved) {
    if (!resolved || typeof AppUtils === "undefined") return;

    const locationId = normalizeId(resolved.location_id);
    const vendorId = normalizeId(resolved.vendor_id);
    const bookingNo = normalizeId(resolved.booking_no);
    const bookingId = normalizeId(resolved.booking_id);

    if (locationId && typeof AppUtils.set === "function") {
        await AppUtils.set(locationId);
    }
    if (vendorId && typeof AppUtils.setCurrentVendors === "function") {
        await AppUtils.setCurrentVendors(vendorId);
    }
    if (bookingNo && typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(bookingNo);
    }
    if (bookingId && typeof AppUtils.storageSet === "function") {
        AppUtils.storageSet(ACTIVE_DINE_BOOKING_KEY, bookingId);
    }

    const orderLookupId =
        typeof AppUtils.getOrderLookupId === "function" ? AppUtils.getOrderLookupId() : null;
    if (orderLookupId && vendorId && bookingId && bookingNo) {
        setSelectedBooking({
            order_lookup_id: orderLookupId,
            vendor_id: vendorId,
            booking_id: bookingId,
            booking_no: bookingNo,
        });
    }
}

async function reactIfSelectedBookingInactive({ bookingHint } = {}) {
    const selected = getSelectedBooking();
    if (!selected) {
        return { outcome: "noop", reason: "no_selected" };
    }

    const hint = normalizeId(bookingHint);
    if (hint && !bookingsMatch(hint, selected.booking_id)) {
        return { outcome: "noop", reason: "different_booking" };
    }

    const bookings = await fetchActiveBookings(selected.order_lookup_id);
    if (bookings === null) {
        return { outcome: "noop", reason: "validate_unavailable" };
    }

    const stillActive = bookings.some(
        (entry) =>
            entry &&
            bookingsMatch(entry.booking_id, selected.booking_id) &&
            bookingsMatch(entry.vendor_id, selected.vendor_id)
    );
    if (stillActive) {
        return { outcome: "still_active" };
    }

    clearSelectedBooking();

    const orderLookupId =
        selected.order_lookup_id ||
        (typeof AppUtils !== "undefined" && typeof AppUtils.getOrderLookupId === "function"
            ? AppUtils.getOrderLookupId()
            : null);
    if (!orderLookupId) {
        return { outcome: "fallback_failed", reason: "no_order_lookup_id" };
    }

    try {
        const lookupMod = await import("./bookingLookupService.js");
        if (typeof lookupMod.resolveBookingLookupForRelaunch !== "function") {
            return { outcome: "fallback_failed", reason: "no_resolve" };
        }
        const lookupResult = await lookupMod.resolveBookingLookupForRelaunch({
            order_lookup_id: orderLookupId,
        });
        if (lookupResult.outcome !== "found" || !lookupResult.booking) {
            return {
                outcome: "fallback_failed",
                reason: lookupResult.reason || lookupResult.outcome || "not_found",
            };
        }

        await applyLatestBookingIdentity(lookupResult.booking);

        const hook = window.__dineFlashApplySelectedBookingHomeView;
        const latestId = normalizeId(lookupResult.booking.booking_id);
        const latestNo = normalizeId(lookupResult.booking.booking_no);
        if (latestId && typeof hook === "function") {
            try {
                await hook(latestId, latestNo);
            } catch (e) {
                console.warn("[dine_flash] Selected Booking lifecycle Home reload failed:", e);
            }
        }

        return { outcome: "fell_back_to_latest", booking_id: latestId };
    } catch (e) {
        console.warn("[dine_flash] Selected Booking lifecycle fallback failed:", e);
        return { outcome: "fallback_failed", reason: "exception" };
    }
}

export {
    tryRestoreSelectedBooking,
    applyLatestBookingIdentity,
    reactIfSelectedBookingInactive,
    applySelectedToHomeIdentity,
};
