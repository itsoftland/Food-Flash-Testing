// Dine Flash ONLY — Selected Booking client state.

const STORAGE_KEY = "selected_dine_booking";
const ACTIVE_DINE_BOOKING_KEY = "activeDineBookingId";

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

function getSelectedBooking() {
    const parsed = readRaw();
    if (!parsed) return null;

    const orderLookupId = normalizeField(parsed.order_lookup_id);
    const vendorId = normalizeField(parsed.vendor_id);
    const bookingId = normalizeField(parsed.booking_id);
    const bookingNo = normalizeField(parsed.booking_no);

    if (!orderLookupId || !vendorId || !bookingId || !bookingNo) {
        return null;
    }

    return { order_lookup_id: orderLookupId, vendor_id: vendorId, booking_id: bookingId, booking_no: bookingNo };
}

function setSelectedBooking(identity) {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageSet !== "function") {
        return null;
    }
    if (!identity || typeof identity !== "object") return null;

    const orderLookupId = normalizeField(identity.order_lookup_id);
    const vendorId = normalizeField(identity.vendor_id);
    const bookingId = normalizeField(identity.booking_id);
    const bookingNo = normalizeField(identity.booking_no);

    if (!orderLookupId || !vendorId || !bookingId || !bookingNo) {
        return null;
    }

    const payload = {
        order_lookup_id: orderLookupId,
        vendor_id: vendorId,
        booking_id: bookingId,
        booking_no: bookingNo,
    };

    try {
        AppUtils.storageSet(STORAGE_KEY, JSON.stringify(payload));
        AppUtils.storageSet(ACTIVE_DINE_BOOKING_KEY, bookingId);
    } catch (e) {
        console.warn("[dine_flash] selected_dine_booking write failed:", e);
        return null;
    }

    return payload;
}

function clearSelectedBooking() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageRemove !== "function") {
        return;
    }
    try {
        AppUtils.storageRemove(STORAGE_KEY);
    } catch (e) {
        /* ignore */
    }
}

export { getSelectedBooking, setSelectedBooking, clearSelectedBooking };
