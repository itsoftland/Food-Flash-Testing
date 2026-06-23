// orders/static/orders/js/dineflash/services/pwaRelaunchService.js
//
// Dine Flash ONLY. Resolves a table booking via the backend after PWA relaunch.
// Never clears local booking tokens except when the backend returns
// status === "not_found_or_stale".

const TOKEN_KEY = "token";
const ACTIVE_DINE_BOOKING_KEY = "activeDineBookingId";

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

/** Sole cleanup entry point — only called for not_found_or_stale. */
function clearStaleDineFlashBookingTokens() {
    AppUtils.storageRemove(TOKEN_KEY);
    AppUtils.storageRemove(ACTIVE_DINE_BOOKING_KEY);
}

function buildRequestBody({ vendor_id, booking_no, location_id } = {}) {
    const body = {};

    if (vendor_id !== null && vendor_id !== undefined && String(vendor_id).trim() !== "") {
        body.vendor_id = vendor_id;
    }
    if (booking_no !== null && booking_no !== undefined && String(booking_no).trim() !== "") {
        body.booking_no = booking_no;
    }
    if (location_id !== null && location_id !== undefined && String(location_id).trim() !== "") {
        body.location_id = location_id;
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
        console.log("[dine_flash] resolve_booking found booking", {
            booking_id: data.booking_id,
            booking_no: data.booking_no,
            vendor_id: data.vendor_id,
            location_id: data.location_id,
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

    if (status === "not_found_or_stale") {
        console.warn("[dine_flash] resolve_booking stale booking detected");
        clearStaleDineFlashBookingTokens();
        return { outcome: "stale" };
    }

    if (status === "vendor_not_found") {
        return preserve("vendor_not_found");
    }

    if (status === "ambiguous") {
        return preserve("ambiguous");
    }

    if (status === "invalid_input") {
        return preserve("invalid_input");
    }

    return preserve("unknown_status");
}

/**
 * Resolve a Dine Flash booking via backend after PWA relaunch.
 * Never throws; always returns a typed outcome.
 *
 * @param {{
 *   vendor_id?: string|number|null,
 *   booking_no?: string|null,
 *   location_id?: string|number|null,
 * }} params
 * @returns {Promise<
 *   | { outcome: "found", booking: { booking_id, booking_no, vendor_id, location_id } }
 *   | { outcome: "stale" }
 *   | { outcome: "preserve", reason: string }
 * >}
 */
async function resolveBookingForRelaunch({
    vendor_id,
    booking_no,
    location_id,
} = {}) {
    const { fetchWithAutoRefresh, API_ENDPOINTS } = await getDependencies();
    const base = window.BASE || "/caller_on/";
    const url = `${base}${API_ENDPOINTS.DINE_FLASH_RESOLVE_BOOKING}`;
    const body = buildRequestBody({ vendor_id, booking_no, location_id });

    let response;
    try {
        console.log("[dine_flash] resolve_booking url", url);
        console.log("[dine_flash] resolve_booking request", body);
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
        console.log("[dine_flash] resolve_booking response", data);
    } catch (e) {
        return preserve("json_parse_failure");
    }

    return mapResolvePayload(data);
}

export { resolveBookingForRelaunch };
