import {
    hospitalOnly,
    cleanAndFormatName,
    resolveVendorId,
    loadVendorBranding,
    saveDraft,
    departmentSelectionUrl,
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

    if (!vendorId) {
        ModalService?.showError?.("Missing branch information. Please scan the branch QR code again.");
        return;
    }

    void loadVendorBranding(vendorId, apiEndpoints);

    const nameInput = document.getElementById("patient_name");
    const nameError = document.getElementById("patient_name_error");
    const continueBtn = document.getElementById("continue-btn");
    if (!continueBtn || !nameInput) return;

    function validatePatientName() {
        const value = nameInput.value.trim();
        if (!value) {
            nameInput.classList.add("is-invalid");
            if (nameError) {
                nameError.textContent = "Patient name is required.";
                nameError.style.display = "block";
            }
            return false;
        }
        if (!/^[A-Za-z\s]+$/.test(value)) {
            nameInput.classList.add("is-invalid");
            if (nameError) {
                nameError.textContent = "Names should only contain letters.";
                nameError.style.display = "block";
            }
            return false;
        }
        if (value.length > 30) {
            nameInput.classList.add("is-invalid");
            if (nameError) {
                nameError.textContent = "Name too long (max 30 letters).";
                nameError.style.display = "block";
            }
            return false;
        }
        nameInput.classList.remove("is-invalid");
        if (nameError) nameError.style.display = "none";
        return true;
    }

    nameInput.addEventListener("input", validatePatientName);

    continueBtn.addEventListener("click", () => {
        if (!validatePatientName()) return;

        const patientName = cleanAndFormatName(nameInput.value);
        const phoneEl = document.getElementById("phone_number");
        const mrEl = document.getElementById("mr_number");
        const billEl = document.getElementById("bill_number");
        const remarksEl = document.getElementById("remarks");

        const phoneEnabled =
            window.PHONE_NUMBER_ENABLED === true || window.PHONE_NUMBER_ENABLED === "true";
        let phoneNumber = phoneEl ? phoneEl.value.trim() : "";
        if (phoneEnabled && phoneNumber && phoneNumber.length > 20) {
            ModalService.showError("Phone number is too long.");
            return;
        }
        if (!phoneEnabled) phoneNumber = "";

        const mrEnabled =
            window.MR_NUMBER_ENABLED === true || window.MR_NUMBER_ENABLED === "true";
        const billEnabled =
            window.BILL_NUMBER_ENABLED === true || window.BILL_NUMBER_ENABLED === "true";
        const mrNumber = mrEnabled && mrEl ? mrEl.value.trim() : "";
        const billNumber = billEnabled && billEl ? billEl.value.trim() : "";

        const remarks = remarksEl ? remarksEl.value.trim() : "";
        if (remarks.length > 200) {
            ModalService.showError("Remarks cannot exceed 200 characters.");
            return;
        }

        const utilitiesEnabled =
            window.UTILITIES_ENABLED === true || window.UTILITIES_ENABLED === "true";
        if (!utilitiesEnabled) {
            ModalService.showError("Departments are not enabled for this branch.");
            return;
        }

        saveDraft({
            vendor_id: vendorId,
            patient_name: patientName,
            phone_number: phoneNumber || null,
            mr_number: mrNumber || null,
            bill_number: billNumber || null,
            remarks: remarks || null,
        });

        window.location.href = departmentSelectionUrl(vendorId);
    });
});
