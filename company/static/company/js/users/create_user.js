document.addEventListener('DOMContentLoaded', async () => {

    if (!window.BASE) throw new Error('window.BASE is not defined');

    // Import modules once
    const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
    const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
    const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
    const labelModule = await import(`${window.BASE}static/utils/js/formFieldLabelService.js`);

    const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
    const API_ENDPOINTS = apiModule.API_ENDPOINTS;
    const ModalService = modalModule.ModalService;
    const getFriendlyFieldLabels = labelModule.default;

    /** DRF 400 bodies are nested objects; buffet shows these instead of a blank legacy parser result */
    function flattenDrfErrorPayload(payload) {
        if (!payload || typeof payload !== 'object') return '';
        if (typeof payload.detail === 'string') return payload.detail;
        const parts = [];
        const walk = (node) => {
            if (!node) return;
            if (typeof node === 'string') {
                parts.push(node);
                return;
            }
            if (Array.isArray(node)) {
                node.forEach(walk);
                return;
            }
            if (typeof node === 'object') {
                Object.values(node).forEach(walk);
            }
        };
        walk(payload);
        return parts.filter(Boolean).join(' ');
    }

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
        
        // Get customerId from localStorage or hidden field fallback
        let customerId = localStorage.getItem('customer_id');
        if (!customerId) {
            const hiddenCustomerId = document.querySelector('input[name="customer_id"]');
            if (hiddenCustomerId) {
                customerId = hiddenCustomerId.value;
            }
        }

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
                vendor_id: vendorId ? parseInt(vendorId, 10) : null
            };
            if (window.PROJECT_NAME === 'dine_flash_buffet') {
                const hiddenCust = document.querySelector('input[name="customer_id"]');
                const rawCust =
                    localStorage.getItem('customer_id') || (hiddenCust && hiddenCust.value);
                const n =
                    rawCust != null && String(rawCust).trim() !== ''
                        ? parseInt(String(rawCust).trim(), 10)
                        : NaN;
                payload.customer_id = Number.isFinite(n) ? n : null;
            } else {
                payload.customer_id = parseInt(customerId, 10);
            }

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
                console.log('Error response data:', resData);
                let userFriendlyMessage = '';
                if (window.PROJECT_NAME === 'dine_flash_buffet') {
                    userFriendlyMessage =
                        flattenDrfErrorPayload(resData) || getFriendlyFieldLabels(resData);
                } else {
                    userFriendlyMessage = getFriendlyFieldLabels(resData);
                }
                console.log ('User friendly message:', userFriendlyMessage);
                ModalService.showError(userFriendlyMessage || 'Failed to create user.');
            }
        } catch (err) {
            console.error('Error creating user:', err);
            ModalService.showError('An error occurred. Please try again.');
        }
    });
});
