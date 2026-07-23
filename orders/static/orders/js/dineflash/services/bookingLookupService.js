// orders/static/orders/js/dineflash/services/bookingLookupService.js
//
// Dine Flash ONLY. Resolves order_lookup_id via the backend so the installed
// PWA can refresh booking/vendor/location before the existing relaunch flow
// continues. Does not touch browser_id, PushSubscription, or Chat.
// Never throws; always returns a typed outcome.
// Independent from Buffet orderLookupService.js.

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

function preserve(reason) {
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
        return { outcome: "not_found" };
    }

    if (status === "invalid_input") {
        return preserve("invalid_input");
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

    let response;
    try {
        console.log("[dine_flash] resolve_order_lookup url", url);
        console.log("[dine_flash] resolve_order_lookup request", {
            order_lookup_id_present: Boolean(body.order_lookup_id),
        });
        response = await fetchWithAutoRefresh(url, {
            method: "POST",
            body: JSON.stringify(body),
        });
    } catch (e) {
        return preserve("network_error");
    }

    let data;
    try {
        data = await response.json();
        console.log("[dine_flash] resolve_order_lookup response", data);
    } catch (e) {
        return preserve("json_parse_failure");
    }

    return mapResolvePayload(data);
}

export { resolveBookingLookupForRelaunch };
