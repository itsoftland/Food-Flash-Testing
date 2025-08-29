import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';
import { ConfirmModalService } from '../services/confirmModalService.js';
import { API_ENDPOINTS } from '/static/utils/js/apiEndpoints.js';

document.addEventListener('DOMContentLoaded', () => {
    // Initialize tooltips
    $(function () {
        $('[data-toggle="tooltip"]').tooltip();
    });

    const userTableBody = document.getElementById('users-table-body');
    const filterDropdown = document.getElementById('userFilter'); // optional if you want filter

    loadUsers('all');

    if (filterDropdown) {
        filterDropdown.addEventListener('change', (e) => {
        loadUsers(e.target.value);
        });
    }

    async function loadUsers(filter = 'all') {
        try {
        let url = API_ENDPOINTS.GET_USERS;
        if (filter !== 'all') {
            url += `?filter=${filter}`;
        }

        const response = await fetchWithAutoRefresh(url, { method: 'GET' });
        if (!response.ok) throw new Error('Failed to fetch users');

        const data = await response.json();
        const users = data.users || [];
        userTableBody.innerHTML = '';

        if (!users.length) {
            userTableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted">No users found.</td>
            </tr>`;
            return;
        }

        users.forEach((user, index) => {
            const createdTime = formatDate(user.created_at);
            const mappedVendor = user.vendor_name ? user.vendor_name : 'Unassigned';
            const isMapped = !!user.vendor_name;

            const iconClass = isMapped ? 'fa-link-slash' : 'fa-link';
            const iconTitle = isMapped ? 'Unassign User from Outlet' : 'Assign User to Outlet';
            const outletClass = isMapped ? 'name' : 'text-muted';

            const row = `
            <tr>
                <td class="text-center">${index + 1}</td>
                <td>${user.name || '-'}</td>
                <td>${formatRoles(user.roles)}</td>
                <td class="${outletClass}">${mappedVendor}</td>
                <td class="text-muted">${createdTime}</td>
                <td class="text-center">
                <button class="icon-btn icon-link-toggle ${isMapped ? 'linked' : 'unlinked'}"
                        data-toggle="tooltip"
                        title="${iconTitle}"
                        data-id="${user.id}"
                        data-username="${user.username}"
                        data-outlet_name="${mappedVendor}"
                        data-mapped="${isMapped}">
                    <i class="fa-solid ${iconClass}"></i>
                </button>
                </td>
            </tr>`;
            userTableBody.insertAdjacentHTML('beforeend', row);
        });

        $('[data-toggle="tooltip"]').tooltip('dispose').tooltip();
        attachActionListeners();
        } catch (error) {
        console.error('Error loading users:', error);
        ModalService.showError('Failed to load users. Please try again later.');
        }
    }

    function attachActionListeners() {
        document.querySelectorAll('.icon-link-toggle').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const userId = btn.dataset.id;
            const username = btn.dataset.username;
            const outletName = btn.dataset.outlet_name;
            const isMapped = btn.dataset.mapped === 'true';

            if (isMapped) {
            const confirmed = await ConfirmModalService.show(
                `Are you sure you want to unassign user <b>${username}</b> from <b>${outletName}</b>?`
            );
            if (!confirmed) return;

            try {
                const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.UNASSIGN_USER}${userId}/`, {
                method: 'POST'
                });
                if (!res.ok) {
                const err = await res.json();
                ModalService.showError(err.error || 'Unable to unassign user.');
                return;
                }
                ModalService.showSuccess(`User ${username} unassigned successfully.`, () => {
                loadUsers(filterDropdown?.value || 'all');
                });
            } catch (err) {
                console.error('Error unassigning user:', err);
                ModalService.showError('Unexpected error occurred while unassigning user.');
            }
            } else {
            openAssignUserModal(userId, username);
            }
        });
        });
    }

    async function openAssignUserModal(userId, username) {
        const modalBodyHTML = `
        <form id="assign-user-form" class="px-4 py-3 mx-auto" style="max-width: 600px;">
            <div class="form-group">
            <label for="vendor-select">Select Outlet</label>
            <select id="vendor-select" name="vendor_id" class="form-control">
                <option disabled selected>Loading outlets...</option>
            </select>
            </div>
            <div class="text-center mt-4">
            <button type="submit" class="btn btn-golden px-4 py-2 shadow-sm">
                <i class="fas fa-link mr-2"></i> Assign
            </button>
            </div>
        </form>`;

        ModalService.showCustom({
        title: `Assign ${username} to Outlet`,
        body: modalBodyHTML,
        onShown: async () => {
            const vendorSelect = document.getElementById('vendor-select');
            try {
            const res = await fetchWithAutoRefresh('/company/api/get_vendors/');
            const data = await res.json();
            const vendors = data.vendors || [];
            if (!vendors.length) {
                vendorSelect.innerHTML = `<option disabled>No outlets available</option>`;
            } else {
                vendorSelect.innerHTML = vendors.map(v => `<option value="${v.id}">${v.name} (${v.location})</option>`).join('');
            }
            } catch (err) {
            vendorSelect.innerHTML = `<option disabled>Error loading outlets</option>`;
            }

            document.getElementById('assign-user-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const vendorId = vendorSelect.value;
            if (!vendorId) {
                ModalService.showError('Please select an outlet.');
                return;
            }

            try {
                const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.ASSIGN_USER}${userId}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ vendor_id: vendorId })
                });

                const result = await res.json();

                const modalElement = document.querySelector('.modal.show');
                const modalInstance = bootstrap.Modal.getInstance(modalElement);
                if (modalInstance) modalInstance.hide();

                if (res.ok) {
                ModalService.showSuccess(`User ${username} assigned successfully.`, () => loadUsers(filterDropdown?.value || 'all'));
                } else {
                ModalService.showError(result?.error || 'Unable to assign user.', () => openAssignUserModal(userId, username));
                }
            } catch (err) {
                ModalService.showError('Unexpected error during assignment.', () => openAssignUserModal(userId, username));
            }
            });
        }
        });
    }

    function formatRoles(roles) {
        if (!roles || !roles.length) return '-';
        const map = {
            admin_manager: 'Admin Manager',
            outlet_manager: 'Outlet Manager',
            order_manager: 'Order Manager',
            web_user: 'Web User'
        };
        return roles
            .map(r => `<span class="badge mr-1" style="background-color: var(--chip-hover-bg); color: var(--text-dark); font-size: 0.95rem; padding: 0.35em 0.6em;">${map[r] || r}</span>`)
            .join('');
    }



    function formatDate(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleString(undefined, {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
        });
    }
});
