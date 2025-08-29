import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';
import { API_ENDPOINTS } from '/static/utils/js/apiEndpoints.js';

document.addEventListener('DOMContentLoaded', async () => {
    const outletSelect = document.getElementById('outlet');
    const roleSelect = document.getElementById('role');
    const createUserForm = document.getElementById('create-user-form');

    try {
        const response = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS, { method: 'GET' });

        if (!response.ok) {
            throw new Error('Failed to fetch outlets');
        }

        const data = await response.json();

        if (data.vendors && Array.isArray(data.vendors)) {
            outletSelect.innerHTML = '<option value="">Select Outlet</option>';

            data.vendors.forEach(vendor => {
                const option = document.createElement('option');
                option.value = vendor.id; // or vendor.vendor_id as per backend expectation
                option.textContent = `${vendor.name} - ${vendor.location}`;
                outletSelect.appendChild(option);
            });
        }

        toggleOutletBasedOnRole();
    } catch (error) {
        console.error('Error loading outlets:', error);
        ModalService.showError('Failed to load outlets. Please try again later.');
    }

    roleSelect.addEventListener('change', toggleOutletBasedOnRole);

    function toggleOutletBasedOnRole() {
        if (roleSelect.value === 'admin_manager') {
            outletSelect.disabled = true;
            outletSelect.value = '';
        } else {
            outletSelect.disabled = false;
        }
    }

    // === CREATE USER API INTEGRATION ===
    createUserForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const name = document.getElementById('name').value.trim();
        const username = document.getElementById('username').value.trim();
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirm_password').value;
        const role = roleSelect.value;
        const vendorId = outletSelect.value || null;
        const customerId = localStorage.getItem('customer_id');

        if (!name || !username || !password || !confirmPassword || !role) {
            ModalService.showError('Please fill all required fields.');
            return;
        }

        if (password !== confirmPassword) {
            ModalService.showError('Passwords do not match.');
            return;
        }

        try {
            const payload = {
                name,
                username,
                password,
                confirm_password: confirmPassword,
                role,
                customer_id: parseInt(customerId),
                vendor_id: vendorId ? parseInt(vendorId) : null
            };

            const res = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_USER, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const resData = await res.json();

            if (res.ok) {
                ModalService.showSuccess('User created successfully!');
                createUserForm.reset();
                toggleOutletBasedOnRole(); // reset outlet state if needed
            } else {
                ModalService.showError(resData.message || 'Failed to create user.');
            }
        } catch (err) {
            console.error('Error creating user:', err);
            ModalService.showError('An error occurred. Please try again.');
        }
    });
});
