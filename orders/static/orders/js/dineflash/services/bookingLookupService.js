// orders/static/orders/js/dineflash/services/bookingLookupService.js
//
// Dine Flash ONLY. Resolves order_lookup_id via the backend so the installed
// PWA can refresh booking/vendor/location before the existing relaunch flow
// continues. Does not touch browser_id, PushSubscription, or Chat.
// Never throws; always returns a typed outcome.
// Independent from Buffet orderLookupService.js.

let dependenciesPromise = null;

function bookingLookupDiag(step, fields) {
    if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
        AppUtils.handoffDiag(step, fields || {});
    }
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

function preserve(reason) {
    bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_PRESERVE", {
        page: "booking_lookup_service",
        outcome: "preserve",
        reason: reason || "",
    });
    return { outcome: "preserve", reason };
}

function buildRequestBody({ order_lookup_id } = {}) {
    const body = {};
    if (
        order_lookup_id !== null &&
        order_lookup_id !== undefined &&
        String(order_lookup_id).trim() !== ""
    ) {
        body.order_lookup_id = String(order_lookup_id).trim();
    }
    return body;
}

function mapResolvePayload(data) {
    if (!data || typeof data !== "object") {
        return preserve("invalid_payload");
    }

    if (typeof data.error === "string" && data.error.trim()) {
        return preserve("server_error");
    }

    const status = data.status;

    if (status === "found") {
        bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_FOUND", {
            page: "booking_lookup_service",
            outcome: "found",
            lookup_status: "found",
            booking_id: data.booking_id != null ? String(data.booking_id) : "",
            booking_no: data.booking_no != null ? String(data.booking_no) : "",
            vendor_id: data.vendor_id != null ? String(data.vendor_id) : "",
            location_id: data.location_id != null ? String(data.location_id) : "",
        });
        return {
            outcome: "found",
            booking: {
                booking_id: data.booking_id,
                booking_no: data.booking_no,
                vendor_id: data.vendor_id,
                location_id: data.location_id,
            },
        };
    }

    if (status === "not_found") {
        bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_NOT_FOUND", {
            page: "booking_lookup_service",
            outcome: "not_found",
            lookup_status: "not_found",
        });
        return { outcome: "not_found" };
    }

    if (status === "invalid_input") {
        bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_INVALID", {
            page: "booking_lookup_service",
            outcome: "preserve",
            lookup_status: "invalid_input",
            reason: "invalid_input",
        });
        return { outcome: "preserve", reason: "invalid_input" };
    }

    return preserve("unknown_status");
}

/**
 * Resolve a Dine Flash booking via order_lookup_id after PWA startup.
 * Never throws; always returns a typed outcome.
 *
 * @param {{ order_lookup_id?: string|null }} params
 * @returns {Promise<
 *   | { outcome: "found", booking: { booking_id, booking_no, vendor_id, location_id } }
 *   | { outcome: "not_found" }
 *   | { outcome: "preserve", reason: string }
 * >}
 */
async function resolveBookingLookupForRelaunch({ order_lookup_id } = {}) {
    const { fetchWithAutoRefresh, API_ENDPOINTS } = await getDependencies();
    const url = API_ENDPOINTS.DINE_FLASH_RESOLVE_ORDER_LOOKUP;
    const body = buildRequestBody({ order_lookup_id });

    bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_REQUEST", {
        page: "booking_lookup_service",
        order_lookup_id: body.order_lookup_id || "",
        has_order_lookup_id: Boolean(body.order_lookup_id),
        standalone: Boolean(window.navigator.standalone),
    });
    bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_PAYLOAD", {
        page: "booking_lookup_service",
        order_lookup_id: body.order_lookup_id || "",
        has_order_lookup_id: Boolean(body.order_lookup_id),
    });

    let response;
    try {
        response = await fetchWithAutoRefresh(url, {
            method: "POST",
            body: JSON.stringify(body),
        });
    } catch (e) {
        bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_EXCEPTION", {
            page: "booking_lookup_service",
            outcome: "preserve",
            reason: "network_error",
            error: e && e.message ? String(e.message) : String(e),
        });
        return preserve("network_error");
    }

    let data;
    try {
        data = await response.json();
        bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_RESPONSE", {
            page: "booking_lookup_service",
            http_status: String(response.status || ""),
            lookup_status: data && data.status != null ? String(data.status) : "",
            booking_id: data && data.booking_id != null ? String(data.booking_id) : "",
            booking_no: data && data.booking_no != null ? String(data.booking_no) : "",
            vendor_id: data && data.vendor_id != null ? String(data.vendor_id) : "",
            location_id: data && data.location_id != null ? String(data.location_id) : "",
            reason: data && data.error != null ? String(data.error) : "",
        });
    } catch (e) {
        bookingLookupDiag("DINE_FLASH_BOOKING_LOOKUP_EXCEPTION", {
            page: "booking_lookup_service",
            outcome: "preserve",
            reason: "json_parse_failure",
            http_status: String(response && response.status ? response.status : ""),
            error: e && e.message ? String(e.message) : String(e),
        });
        return preserve("json_parse_failure");
    }

    return mapResolvePayload(data);
}

export { resolveBookingLookupForRelaunch };
