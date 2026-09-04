// companyadmin/static/companyadmin/js/company_registration.js

const STRICT_STATE_CITY_PROJECTS = new Set([
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
]);

const STRICT_GST_PROJECTS = new Set([
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
]);

const STRICT_COMPANY_NAME_PROJECTS = new Set([
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
]);

const GST_FORMAT_ERROR =
    "GST Number must be exactly 15 characters, contain only letters and digits " +
    "(A-Z, a-z, 0-9), include at least one letter and one digit, and must not " +
    "contain spaces or special characters.";

const COMPANY_NAME_FORMAT_ERROR =
    "Company Name cannot be empty and must contain at least one alphabetic character.";

const COMPANY_NAME_MAX_LENGTH = 255;

function currentProjectName() {
    return String(window.PROJECT_NAME || "").trim().toLowerCase();
}

function requiresStrictStateCityValidation() {
    return STRICT_STATE_CITY_PROJECTS.has(currentProjectName());
}

function requiresStrictGstValidation() {
    return STRICT_GST_PROJECTS.has(currentProjectName());
}

function requiresStrictCompanyNameValidation() {
    return STRICT_COMPANY_NAME_PROJECTS.has(currentProjectName());
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

/** Simplified GST rules; does not strip spaces or special characters. */
function validateGstNumberInput(raw) {
    if (!requiresStrictGstValidation()) {
        return { ok: true, value: raw ?? "", message: "" };
    }
    const value = String(raw ?? "");
    // Preserve HTML required for empty; whitespace/format still validated here.
    if (!value) {
        return { ok: true, value, message: "" };
    }
    const formatOk =
        /^[A-Za-z0-9]{15}$/.test(value) &&
        /[A-Za-z]/.test(value) &&
        /[0-9]/.test(value);
    if (!formatOk) {
        return { ok: false, value, message: GST_FORMAT_ERROR };
    }
    return { ok: true, value, message: "" };
}

/**
 * Strict Company Name: non-empty after trim, at least one Unicode letter.
 * Numbers/special characters remain allowed when letters are also present.
 */
function normalizeAndValidateCompanyName(raw) {
    if (!requiresStrictCompanyNameValidation()) {
        return { ok: true, value: raw ?? "", message: "" };
    }
    const text = String(raw ?? "").trim();
    if (!text || !/[\p{L}]/u.test(text)) {
        return { ok: false, value: text, message: COMPANY_NAME_FORMAT_ERROR };
    }
    if (text.length > COMPANY_NAME_MAX_LENGTH) {
        return {
            ok: false,
            value: text,
            message: `Company Name cannot exceed ${COMPANY_NAME_MAX_LENGTH} characters.`,
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

function flattenSerializerErrors(result) {
    if (!result || typeof result !== "object") return "";
    const messages = [];

    function walk(node) {
        if (node == null) return;
        if (typeof node === "string") {
            messages.push(node);
            return;
        }
        if (Array.isArray(node)) {
            node.forEach(walk);
            return;
        }
        if (typeof node === "object") {
            Object.values(node).forEach(walk);
        }
    }

    walk(result);
    return messages.join(" ");
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

    function registrationErrorMessage(result) {
        const fromLabels = getFriendlyFieldLabels(result);
        if (fromLabels) return fromLabels;
        if (result?.error) return result.error;
        const fromSerializer = flattenSerializerErrors(result);
        if (fromSerializer) return fromSerializer;
        return "Unknown error occurred";
    }

    const form = document.getElementById("companyForm");
    if (!form) {
        console.warn("Company form not found!");
        return;
    }

    const stateInput = form.state || document.getElementById("state");
    const cityInput = form.city || document.getElementById("city");
    const gstInput = form.gst || document.getElementById("gst");
    const companyNameInput =
        form.companyname || document.getElementById("companyname");

    if (requiresStrictCompanyNameValidation()) {
        const onCompanyNameInput = () => {
            const nameResult = normalizeAndValidateCompanyName(companyNameInput?.value);
            setFieldError(companyNameInput, nameResult.ok ? "" : nameResult.message);
        };
        companyNameInput?.addEventListener("input", onCompanyNameInput);
        companyNameInput?.addEventListener("blur", onCompanyNameInput);
    }

    if (requiresStrictStateCityValidation()) {
        const onStateCityInput = () => {
            validateStateCityInputs(stateInput, cityInput, { showErrors: true });
        };
        stateInput?.addEventListener("input", onStateCityInput);
        stateInput?.addEventListener("blur", onStateCityInput);
        cityInput?.addEventListener("input", onStateCityInput);
        cityInput?.addEventListener("blur", onStateCityInput);
    }

    if (requiresStrictGstValidation()) {
        const onGstInput = () => {
            const gstResult = validateGstNumberInput(gstInput?.value);
            setFieldError(gstInput, gstResult.ok ? "" : gstResult.message);
        };
        gstInput?.addEventListener("input", onGstInput);
        gstInput?.addEventListener("blur", onGstInput);
    }

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const companyNameResult = normalizeAndValidateCompanyName(companyNameInput?.value);
        if (requiresStrictCompanyNameValidation()) {
            setFieldError(
                companyNameInput,
                companyNameResult.ok ? "" : companyNameResult.message
            );
            if (!companyNameResult.ok) {
                ModalService.showError(
                    companyNameResult.message || COMPANY_NAME_FORMAT_ERROR
                );
                return;
            }
        }

        const stateCity = validateStateCityInputs(stateInput, cityInput, { showErrors: true });
        if (!stateCity.ok) {
            ModalService.showError(stateCity.message || "Please correct State and City.");
            return;
        }

        const gstResult = validateGstNumberInput(gstInput?.value);
        if (requiresStrictGstValidation()) {
            setFieldError(gstInput, gstResult.ok ? "" : gstResult.message);
            if (!gstResult.ok) {
                ModalService.showError(gstResult.message || GST_FORMAT_ERROR);
                return;
            }
        }

        const customerName = requiresStrictCompanyNameValidation()
            ? companyNameResult.value
            : form.companyname.value;

        const payload = {
            CustomerName: customerName,
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
            DeviceIdentifier1: customerName,
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
                const errorMessage = registrationErrorMessage(result);
                ModalService.showError(errorMessage);
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
