// companyadmin/static/companyadmin/js/company_registration.js

document.addEventListener("DOMContentLoaded", async function () {
    // Validate BASE exists
    if (!window.BASE) throw new Error('window.BASE is not defined');

    // Import modules once
    const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
    const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);

    const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
    const API_ENDPOINTS = apiModule.API_ENDPOINTS;
    const WEB_ENDPOINTS = apiModule.WEB_ENDPOINTS;

    const form = document.getElementById("companyForm");
    if (!form) {
        console.warn("Company form not found!");
        return;
    }

    form.addEventListener("submit", async function (e) {
        e.preventDefault();

        const payload = {
            CustomerName: form.companyname.value,
            PhoneNumber: form.phonenumber.value,
            CustomerEmail: form.companyemail.value,
            GSTNumber: form.gst.value,
            CustomerContactPerson: form.contactperson.value,
            CustomerContact: form.contactphonenumber.value,
            CustomerAddress: form.comaddress1.value,
            CustomerAddress2: form.comaddress2.value,
            CustomerState: form.state.value,
            CustomerCity: form.city.value,
            CustomerUsername: form.CustomerUsername.value,
            CustomerPassword: form.CustomerPassword.value,
            DeviceModel: "Windows",
            DeviceIdentifier1: form.companyname.value,
            DeviceType: 1,
            Version: "FoodFlash 1.00",
            ProjectName: "FoodFlash 1.00"
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
                window.location.href = WEB_ENDPOINTS.COMPANY_LIST;
            } else {
                console.warn("Error: " + (result.message || "Unknown error occurred"));
            }
        } catch (err) {
            console.error("Request failed:", err);
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
