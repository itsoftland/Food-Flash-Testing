document.addEventListener('DOMContentLoaded', async () => {
    const loginForm = document.getElementById('loginForm');

    let callProductAuthAPI, ModalService, apiEndpoints, webEndpoints;

    try {
        const base = window.BASE || '/caller_on/';

        // Dynamically import modules
        const productAuthModule = await import(`${base}static/utils/js/services/productAuthService.js`);
        const modalServiceModule = await import(`${base}static/utils/js/services/modalService.js`);
        const endpointsModule = await import(`${base}static/utils/js/apiEndpoints.js`);

        callProductAuthAPI = productAuthModule.callProductAuthAPI;
        ModalService = modalServiceModule.ModalService;

        // Retrieve both endpoints from the same module
        apiEndpoints = endpointsModule.API_ENDPOINTS;
        webEndpoints = endpointsModule.WEB_ENDPOINTS;
    } catch (importError) {
        console.error('❌ Failed to import required modules:', importError);
        alert('System error: unable to load essential modules.');
        return;
    }

    loginForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value.trim();

        const payload = { username, password };

        try {
            const response = await fetch(apiEndpoints.LOGIN, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();

            if (!response.ok) {
                alert(data.error || 'Login failed');
                return;
            }

            const role = data.user.role;

            // Store tokens
            localStorage.setItem('access_token', data.access);
            localStorage.setItem('refresh_token', data.refresh);
            AppUtils.setCustomerName(data.user.username);
            localStorage.setItem('role', role);

            if (role !== 'Super Admin') {
                AppUtils.setCustomerId(data.user.customer_id || '');
                // Validate license
                const { status } = await callProductAuthAPI();
                if (status === false) {
                    ModalService.showError(
                        "Your license has expired. Please click OK to return to login.",
                        () => { window.location.href = webEndpoints.LOGIN; } // Use webEndpoints for redirect
                    );
                    return;
                }
            }

            // Redirect based on role using webEndpoints
            if (role === 'Super Admin') {
                window.location.href = webEndpoints.ADMIN_DASHBOARD;
            } else if (role === 'Company') {
                window.location.href = webEndpoints.COMPANY_DASHBOARD;
            } else if (role === 'Outlet') {
                window.location.href = webEndpoints.DASHBOARD;
            } else {
                alert('Unknown user role');
            }

        } catch (err) {
            console.error('Login error:', err);
            alert('An unexpected error occurred.');
        }
    });
});
