import {
    hospitalOnly,
    escapeHtml,
    resolveVendorId,
    loadVendorBranding,
    loadResult,
    clearHospitalSession,
    patientRegistrationUrl,
    trackingUrlFromResult,
} from "./hospitalCommon.js";

document.addEventListener("DOMContentLoaded", async () => {
    if (!hospitalOnly()) return;

    const base = window.BASE || "/hospital_flash/";
    let apiEndpoints, vendorId;

    try {
        const [endpointsModule, vendorStore] = await Promise.all([
            import(`${base}static/utils/js/apiEndpoints.js`),
            import(`${base}static/orders/js/config/vendorStore.js`),
        ]);
        apiEndpoints = endpointsModule.API_ENDPOINTS;
        vendorId = await resolveVendorId(vendorStore);
    } catch (err) {
        console.error("Failed to load modules:", err);
        return;
    }

    const result = loadResult();
    if (!result || !result.departments?.length) {
        window.location.href = patientRegistrationUrl(vendorId || "");
        return;
    }

    if (vendorId && result.vendor_id && Number(result.vendor_id) !== Number(vendorId)) {
        vendorId = Number(result.vendor_id);
    }

    void loadVendorBranding(vendorId, apiEndpoints);

    const patientEl = document.getElementById("confirm-patient-name");
    if (patientEl) {
        patientEl.textContent = result.patient_name || "—";
    }

    const tokenList = document.getElementById("token-list");
    if (tokenList) {
        tokenList.innerHTML = (result.departments || [])
            .map(
                (row) => `
            <div class="token-row">
                <span class="dept-name">${escapeHtml(row.department_name || "Department")}</span>
                <span class="dept-token">${escapeHtml(row.token || "—")}</span>
            </div>`
            )
            .join("");
    }

    document.getElementById("track-status-btn")?.addEventListener("click", () => {
        const trackingUrl = trackingUrlFromResult(result, vendorId);
        if (!trackingUrl) {
            window.location.href = patientRegistrationUrl(vendorId);
            return;
        }
        window.location.href = trackingUrl;
    });

    document.getElementById("new-registration-btn")?.addEventListener("click", () => {
        clearHospitalSession();
        window.location.href = patientRegistrationUrl(vendorId);
    });
});
