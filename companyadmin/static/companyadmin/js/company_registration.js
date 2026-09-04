// companyadmin/static/companyadmin/js/company_registration.js

const STRICT_STATE_CITY_PROJECTS = new Set([
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
]);

function currentProjectName() {
    return String(window.PROJECT_NAME || "").trim().toLowerCase();
}

function requiresStrictStateCityValidation() {
    return STRICT_STATE_CITY_PROJECTS.has(currentProjectName());
}

/** Trim, collapse spaces; return { ok, value, message }. */
function normalizeAndValidateStateOrCity(raw, fieldLabel) {
    const text = String(raw ?? "")
        .trim()
        .replace(/\s+/g, " ");
    if (!text || !/^[A-Za-z]+(?: [A-Za-z]+)*$/.test(text)) {
        return {
            ok: false,
            value: text,
            message: `${fieldLabel} must contain alphabetic characters and spaces only.`,
        };
    }
    if (text.length > 100) {
        return {
            ok: false,
            value: text,
            message: `${fieldLabel} cannot exceed 100 characters.`,
        };
    }
    return { ok: true, value: text, message: "" };
}

function setFieldError(inputEl, message) {
    if (!inputEl) return;
    const group = inputEl.closest(".form-group");
    const errorEl = group ? group.querySelector(".error-message") : null;
    if (errorEl) errorEl.textContent = message || "";
    if (message) {
        inputEl.classList.add("is-invalid");
    } else {
        inputEl.classList.remove("is-invalid");
    }
}

function validateStateCityInputs(stateInput, cityInput, { showErrors } = { showErrors: true }) {
    if (!requiresStrictStateCityValidation()) {
        return { ok: true, state: stateInput?.value ?? "", city: cityInput?.value ?? "" };
    }

    const stateResult = normalizeAndValidateStateOrCity(stateInput?.value, "State");
    const cityResult = normalizeAndValidateStateOrCity(cityInput?.value, "City");

    if (showErrors) {
        setFieldError(stateInput, stateResult.ok ? "" : stateResult.message);
        setFieldError(cityInput, cityResult.ok ? "" : cityResult.message);
    }

    return {
        ok: stateResult.ok && cityResult.ok,
        state: stateResult.value,
        city: cityResult.value,
        message: !stateResult.ok
            ? stateResult.message
            : !cityResult.ok
              ? cityResult.message
              : "",
    };
}

document.addEventListener("DOMContentLoaded", async function () {
    // Validate BASE exists
    if (!window.BASE) throw new Error('window.BASE is not defined');

    // Import modules once
    const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
    const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
    const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
    const labelModule = await import(`${window.BASE}static/utils/js/formFieldLabelService.js`);

    const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
    const API_ENDPOINTS = apiModule.API_ENDPOINTS;
    const WEB_ENDPOINTS = apiModule.WEB_ENDPOINTS;
    const ModalService = modalModule.ModalService;
    const getFriendlyFieldLabels = labelModule.default;

    const form = document.getElementById("companyForm");
    if (!form) {
        console.warn("Company form not found!");
        return;
    }

    const stateInput = form.state || document.getElementById("state");
    const cityInput = form.city || document.getElementById("city");

    if (requiresStrictStateCityValidation()) {
        const onStateCityInput = () => {
            validateStateCityInputs(stateInput, cityInput, { showErrors: true });
        };
        stateInput?.addEventListener("input", onStateCityInput);
        stateInput?.addEventListener("blur", onStateCityInput);
        cityInput?.addEventListener("input", onStateCityInput);
        cityInput?.addEventListener("blur", onStateCityInput);
    }

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const stateCity = validateStateCityInputs(stateInput, cityInput, { showErrors: true });
        if (!stateCity.ok) {
            ModalService.showError(stateCity.message || "Please correct State and City.");
            return;
        }

        const payload = {
            CustomerName: form.companyname.value,
            PhoneNumber: form.phonenumber.value,
            CustomerEmail: form.companyemail.value,
            GSTNumber: form.gst.value,
            CustomerContactPerson: form.contactperson.value,
            CustomerContact: form.contactphonenumber.value,
            CustomerAddress: form.comaddress1.value,
            CustomerAddress2: form.comaddress2.value,
            CustomerState: requiresStrictStateCityValidation() ? stateCity.state : form.state.value,
            CustomerCity: requiresStrictStateCityValidation() ? stateCity.city : form.city.value,
            CustomerUsername: form.CustomerUsername.value,
            CustomerPassword: form.CustomerPassword.value,
            DeviceModel: "Windows",
            DeviceIdentifier1: form.companyname.value,
            DeviceType: 1,
            Version: `${window.APP_VERSION}`,
            ProjectName: window.PROJECT_NAME
        };

        try {
            const response = await fetchWithAutoRefresh(API_ENDPOINTS.REGISTER_COMPANY, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': AppUtils.getCSRFToken()
                },
                body: JSON.stringify(payload),
                credentials: 'include'
            });

            const result = await response.json();

            if (result.status === "success") {
                const successMessage = window.PROJECT_NAME === "hospital_flash"
                    ? "Hospital registered successfully"
                    : "Restaurant registered successfully";
                ModalService.showSuccess(successMessage, () => {
                    window.location.href = WEB_ENDPOINTS.COMPANY_LIST;
                });
            } else {
                const errorMessage = getFriendlyFieldLabels(result);
                ModalService.showError(errorMessage || result.error || "Unknown error occurred");
            }
        } catch (err) {
            console.error("Request failed:", err);
            ModalService.showError("An error occurred during registration. Please check the network or try again.");
        }
    });
});

// Toggle password visibility
const toggleBtn = document.getElementById('togglePassword');
if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
        const passwordInput = document.getElementById('CustomerPassword');
        const toggleIcon = document.getElementById('toggleIcon');

        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            toggleIcon.classList.remove('fa-eye-slash');
            toggleIcon.classList.add('fa-eye');
        } else {
            passwordInput.type = 'password';
            toggleIcon.classList.remove('fa-eye');
            toggleIcon.classList.add('fa-eye-slash');
        }
    });
}
