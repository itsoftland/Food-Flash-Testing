import { callProductAuthAPI } from '/static/utils/js/services/productAuthService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';

document.addEventListener('DOMContentLoaded', async () => {
    const loginForm = document.getElementById('loginForm');

    loginForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value.trim();

        const payload = { username, password };

        try {
            const response = await fetch('/api/login/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            console.log('Login response:', data);

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

            // Only set customer_id if not Super Admin
            if (role !== 'Super Admin') {
                AppUtils.setCustomerId(data.user.customer_id || '');
                console.log('✅ customer_id after setting:', localStorage.getItem('customer_id'));

                // Validate license only for non-Super Admin users
                const isAuthValid = await callProductAuthAPI();

                if (!isAuthValid) {
                    ModalService.showError("Your license has expired. Please click OK to return to login.", () => {
                        window.location.href = '/login/';
                    });
                    return;
                }
            }

            // Redirect based on role
            if (role === 'Super Admin') {
                window.location.href = '/companyadmin/dashboard/';
            } else if (role === 'Company') {
                window.location.href = '/company/dashboard/';
            } else if (role === 'Outlet') {
                window.location.href = '/vendor/dashboard/';
            } else {
                alert('Unknown user role');
            }
        } catch (err) {
            console.error('Login error:', err);
            alert('An unexpected error occurred.');
        }
    });
});
