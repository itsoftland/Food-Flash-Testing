export const HOSPITAL_DRAFT_KEY = "hospital_registration_draft";
export const HOSPITAL_RESULT_KEY = "hospital_registration_result";
export const HOSPITAL_TRACKING_BATCH_KEY = "hospital_registration_batch_id";

export function hospitalOnly() {
    const project = String(window.PROJECT_NAME || "").toLowerCase();
    const path = String(window.location?.pathname || "").toLowerCase();
    return project === "hospital_flash" || path.includes("/hospital_flash/");
}

export function getParam(key) {
    return new URLSearchParams(window.location.search).get(key);
}

export function escapeHtml(str) {
    if (!str && str !== 0) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function cleanAndFormatName(name) {
    if (!name) return "";
    name = name.trim().replace(/\s+/g, " ");
    return name
        .split(" ")
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(" ");
}

export function getCSRFToken() {
    const cookie = document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

export async function resolveVendorId(vendorStore) {
    const urlVendorId = getParam("vendor_id");
    const resolvedVendorId =
        typeof window.RESOLVED_VENDOR_ID === "string" ? window.RESOLVED_VENDOR_ID.trim() : "";
    const effectiveVendorId = urlVendorId || resolvedVendorId;

    if (effectiveVendorId) {
        const parsed = parseInt(effectiveVendorId, 10);
        if (!isNaN(parsed)) {
            await vendorStore.setVendorId(parsed);
            return parsed;
        }
    }
    return vendorStore.getVendorId();
}

export async function loadVendorBranding(vendorId, apiEndpoints) {
    if (!vendorId || !apiEndpoints?.VENDOR_LOGOS) return;

    const nameEl = document.getElementById("vendor-name");
    const logoEl = document.getElementById("vendor-logo");
    if (!nameEl && !logoEl) return;

    try {
        const response = await fetch(apiEndpoints.VENDOR_LOGOS, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vendor_ids: [vendorId] }),
        });
        const data = await response.json();
        if (!data?.length) return;

        const vendor = data[0];
        if (nameEl) nameEl.textContent = vendor.alias_name || vendor.name || "Branch";
        if (logoEl && vendor.logo_url) {
            logoEl.src = String(vendor.logo_url).replace(/ /g, "%20");
        }
    } catch (err) {
        console.error("Error loading vendor branding:", err);
    }
}

export function saveDraft(draft) {
    sessionStorage.setItem(HOSPITAL_DRAFT_KEY, JSON.stringify(draft));
}

export function loadDraft() {
    try {
        const raw = sessionStorage.getItem(HOSPITAL_DRAFT_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

export function saveResult(result) {
    sessionStorage.setItem(HOSPITAL_RESULT_KEY, JSON.stringify(result));
}

export function loadResult() {
    try {
        const raw = sessionStorage.getItem(HOSPITAL_RESULT_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch {
        return null;
    }
}

export function clearHospitalSession() {
    sessionStorage.removeItem(HOSPITAL_DRAFT_KEY);
    sessionStorage.removeItem(HOSPITAL_RESULT_KEY);
    sessionStorage.removeItem(HOSPITAL_TRACKING_BATCH_KEY);
}

export function getStoredBatchId() {
    try {
        const value = sessionStorage.getItem(HOSPITAL_TRACKING_BATCH_KEY);
        return value && String(value).trim() ? String(value).trim() : null;
    } catch {
        return null;
    }
}

export function saveBatchId(batchId) {
    if (!batchId) return;
    try {
        sessionStorage.setItem(HOSPITAL_TRACKING_BATCH_KEY, String(batchId));
    } catch (err) {
        console.warn("Hospital batch id storage failed:", err);
    }
}

export function isHospitalBatchPayload(payload) {
    return Boolean(
        payload?.registration_batch_id &&
        Array.isArray(payload?.departments) &&
        payload.departments.length > 0
    );
}

export function isHospitalStatusUpdatePayload(payload) {
    return Boolean(
        payload?.booking_id != null &&
        payload?.status &&
        !isHospitalBatchPayload(payload)
    );
}

export function buildTrackingUrl({
    vendorId,
    locationId,
    registrationBatchId,
    bookingId,
    bookingNo,
}) {
    const base = window.BASE || "/hospital_flash/";
    const params = new URLSearchParams();
    if (locationId) params.set("location_id", String(locationId));
    if (vendorId != null && vendorId !== "") params.set("vendor_id", String(vendorId));
    if (bookingNo) params.set("booking_no", String(bookingNo));
    if (bookingId != null && bookingId !== "") params.set("booking_id", String(bookingId));
    if (registrationBatchId) params.set("registration_batch_id", String(registrationBatchId));
    return `${base}home/?${params.toString()}`;
}

export function trackingUrlFromResult(result, vendorId) {
    if (!result) return null;
    if (result.tracking_url) return result.tracking_url;

    const departments = Array.isArray(result.departments) ? result.departments : [];
    const primary = departments[0];
    if (!primary) return null;

    return buildTrackingUrl({
        vendorId: result.vendor_id ?? vendorId,
        locationId: result.location_id,
        registrationBatchId: result.registration_batch_id,
        bookingId: primary.order_id,
        bookingNo: primary.token,
    });
}

export function departmentSelectionUrl(vendorId) {
    const base = window.BASE || "/hospital_flash/";
    return `${base}hospital/department_selection/?vendor_id=${encodeURIComponent(vendorId)}`;
}

export function patientRegistrationUrl(vendorId) {
    const base = window.BASE || "/hospital_flash/";
    return `${base}hospital/patient_registration/?vendor_id=${encodeURIComponent(vendorId)}`;
}

export function confirmationUrl(vendorId) {
    const base = window.BASE || "/hospital_flash/";
    return `${base}hospital/registration_confirmation/?vendor_id=${encodeURIComponent(vendorId)}`;
}
