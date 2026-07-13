import {
    hospitalOnly,
    escapeHtml,
    getCSRFToken,
    resolveVendorId,
    loadVendorBranding,
    loadDraft,
    saveResult,
    patientRegistrationUrl,
    confirmationUrl,
} from "./hospitalCommon.js";

document.addEventListener("DOMContentLoaded", async () => {
    if (!hospitalOnly()) return;

    const base = window.BASE || "/hospital_flash/";
    let apiEndpoints, ModalService, vendorId;

    try {
        const [endpointsModule, modalServiceModule, vendorStore] = await Promise.all([
            import(`${base}static/utils/js/apiEndpoints.js`),
            import(`${base}static/utils/js/services/modalService.js`),
            import(`${base}static/orders/js/config/vendorStore.js`),
        ]);
        apiEndpoints = endpointsModule.API_ENDPOINTS;
        ModalService = modalServiceModule.ModalService;
        vendorId = await resolveVendorId(vendorStore);
    } catch (err) {
        console.error("Failed to load modules:", err);
        return;
    }

    const draft = loadDraft();
    if (!draft || !draft.patient_name) {
        window.location.href = patientRegistrationUrl(vendorId || "");
        return;
    }

    if (vendorId && draft.vendor_id && Number(draft.vendor_id) !== Number(vendorId)) {
        vendorId = Number(draft.vendor_id);
    }

    const summaryEl = document.getElementById("patient-summary");
    if (summaryEl) {
        summaryEl.textContent = `Patient: ${draft.patient_name}`;
    }

    void loadVendorBranding(vendorId, apiEndpoints);

    async function loadDepartments() {
        const grid = document.getElementById("utility-grid");
        if (!apiEndpoints?.UTILITY_LIST || !vendorId) {
            ModalService?.showError?.("Unable to load departments.");
            return;
        }

        try {
            const url = `${apiEndpoints.UTILITY_LIST}?vendor_id=${encodeURIComponent(vendorId)}`;
            const response = await fetch(url, { headers: { Accept: "application/json" } });
            const data = await response.json();
            if (!response.ok) {
                ModalService.showError(data.error || "Unable to load departments.");
                return;
            }
            renderDepartments(data.utilities || []);
            if (grid) grid.dataset.loaded = "1";
        } catch (err) {
            console.error("Error loading departments:", err);
            ModalService.showError("Network error while loading departments.");
        }
    }

    function isGroupDepartment(util) {
        return util.department_type === "GROUP" || util.is_group_department === true;
    }

    function sortGroupDepartments(members) {
        return [...members].sort((a, b) => {
            const orderA = Number(a.display_order) || 0;
            const orderB = Number(b.display_order) || 0;
            if (orderA !== orderB) return orderA - orderB;
            return (Number(a.id) || 0) - (Number(b.id) || 0);
        });
    }

    function getGroupMemberNames(util) {
        if (Array.isArray(util.group_departments) && util.group_departments.length) {
            return sortGroupDepartments(util.group_departments)
                .map((member) => member.display_name || member.utility_name)
                .filter(Boolean);
        }
        if (Array.isArray(util.group_department_names) && util.group_department_names.length) {
            return util.group_department_names.filter(Boolean);
        }
        return [];
    }

    function renderDepartments(utilities) {
        const container = document.getElementById("utility-grid");
        if (!container) return;
        container.innerHTML = "";

        if (!utilities.length) {
            container.innerHTML =
                '<div class="col-12 text-muted small text-center py-2">No active departments found.</div>';
            return;
        }

        utilities.forEach((util) => {
            const item = document.createElement("div");
            const isGroup = isGroupDepartment(util);
            item.className = `utility-item premium-utility-card multi-select${
                isGroup ? " group-department-card" : ""
            }`;
            item.dataset.id = util.id;

            const name = escapeHtml(util.display_name || util.utility_name);
            if (isGroup) {
                const memberNames = getGroupMemberNames(util);
                const includesText = memberNames.length
                    ? memberNames.map(escapeHtml).join(", ")
                    : "No departments configured";
                item.innerHTML = `
                    <div class="utility-display group-department-display">
                        <span class="group-department-name">${name}</span>
                        <span class="group-department-badge">Package</span>
                    </div>
                    <div class="group-department-includes">Includes: ${includesText}</div>
                `;
            } else {
                item.innerHTML = `<div class="utility-display">${name}</div>`;
            }

            item.addEventListener("click", () => {
                item.classList.toggle("selected");
            });
            container.appendChild(item);
        });
    }

    function getSelectedUtilityIds() {
        return Array.from(document.querySelectorAll(".utility-item.selected")).map((el) =>
            parseInt(el.dataset.id, 10)
        );
    }

    function extractReadableError(err) {
        if (!err) return null;
        if (typeof err === "string") return err;
        if (Array.isArray(err)) return err.map(extractReadableError).filter(Boolean).join(", ");
        if (typeof err === "object") {
            const [, value] = Object.entries(err)[0] || [];
            const message = extractReadableError(value);
            return message || JSON.stringify(err);
        }
        return String(err);
    }

    async function submitRegistration() {
        const submitBtn = document.getElementById("submit-btn");
        if (!submitBtn) return;

        const selectedIds = getSelectedUtilityIds().filter((id) => !isNaN(id));
        if (!selectedIds.length) {
            ModalService.showError("Please select at least one department.");
            return;
        }

        submitBtn.disabled = true;
        const originalHtml = submitBtn.innerHTML;
        submitBtn.innerHTML =
            '<span class="spinner-border spinner-border-sm me-2"></span>Registering...';

        try {
            const payload = {
                vendor_id: vendorId,
                customer_name: draft.patient_name,
                phone_number: draft.phone_number,
                mr_number: draft.mr_number,
                bill_number: draft.bill_number,
                remarks: draft.remarks,
                utility_ids: selectedIds,
            };

            const resp = await fetch(apiEndpoints.HOSPITAL_PATIENT_SUBMIT, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCSRFToken(),
                },
                credentials: "same-origin",
                body: JSON.stringify(payload),
            });

            const data = await resp.json();
            if (resp.status !== 201) {
                const msg =
                    extractReadableError(data?.error) ||
                    extractReadableError(data?.detail) ||
                    "Registration failed. Please try again.";
                ModalService.showError(msg);
                return;
            }

            saveResult({
                vendor_id: vendorId,
                patient_name: data.patient_name || draft.patient_name,
                registration_batch_id: data.registration_batch_id,
                location_id: data.location_id,
                tracking_url: data.tracking_url,
                departments: data.departments || [],
            });

            window.location.href = confirmationUrl(vendorId);
        } catch (err) {
            console.error("Registration error:", err);
            ModalService.showError("Network error. Please try again.");
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalHtml;
        }
    }

    document.getElementById("back-btn")?.addEventListener("click", () => {
        window.location.href = patientRegistrationUrl(vendorId);
    });

    document.getElementById("submit-btn")?.addEventListener("click", submitRegistration);

    void loadDepartments();
});
