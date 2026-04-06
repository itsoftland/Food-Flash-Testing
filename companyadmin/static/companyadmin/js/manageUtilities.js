document.addEventListener('DOMContentLoaded', async () => {
    if (!window.BASE) {
        throw new Error('window.BASE is not defined');
    }

    /* ------------------------------------
       Dynamic imports
    ------------------------------------ */
    const authModule = await import(
        `${window.BASE}static/utils/js/services/authFetchService.js`
    );
    const apiModule = await import(
        `${window.BASE}static/utils/js/apiEndpoints.js`
    );
    const modalModule = await import(
        `${window.BASE}static/utils/js/services/modalService.js`
    );

    const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
    const API_ENDPOINTS = apiModule.API_ENDPOINTS;
    const ModalService = modalModule.ModalService;

    /* ------------------------------------
       Super Admin Specific Endpoints
    ------------------------------------ */
    const SA_API = {
        GET_UTILITIES: `${window.BASE}companyadmin/api/get_all_utilities/`,
        UPDATE_UTILITY_STATUS: `${window.BASE}companyadmin/api/update_utility_status_sa/`,
        UPDATE_UTILITY: `${window.BASE}companyadmin/api/update_utility_sa/`,
        CREATE_OPTION: (utilId) => `${window.BASE}companyadmin/api/create_utility_option_sa/${utilId}/`,
        UPDATE_OPTION: (optId) => `${window.BASE}companyadmin/api/update_utility_option_sa/${optId}/`,
        DELETE_OPTION: (optId) => `${window.BASE}companyadmin/api/delete_utility_option_sa/${optId}/`
    };

    /* ------------------------------------
       DOM references
    ------------------------------------ */
    const searchInput = document.getElementById('search-input');
    const vendorFilter = document.getElementById('vendor-filter');
    const statusFilter = document.getElementById('status-filter');
    const utilitiesTbody = document.getElementById('utilities-tbody');
    const emptyState = document.getElementById('empty-state-no-utilities');
    const tableContainer = document.getElementById('table-container');

    let allUtilitiesData = [];
    const projectName = (window.PROJECT_NAME || '').toLowerCase().trim();
    const isBuffetProject = typeof window.IS_BUFFET_PROJECT === 'boolean'
        ? window.IS_BUFFET_PROJECT
        : projectName === 'dine_flash_buffet';

    if (!utilitiesTbody) return;

    /* ------------------------------------
       Helpers
    ------------------------------------ */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /* ------------------------------------
       Fetch outlets for filter
    ------------------------------------ */
    async function loadOutlets() {
        try {
            const response = await fetchWithAutoRefresh(API_ENDPOINTS.COMPANY_OUTLETS, {
                method: 'GET'
            });
            const result = await response.json();
            if (response.ok && Array.isArray(result)) {
                vendorFilter.innerHTML = '<option value="">All Outlets</option>';
                result.forEach(vendor => {
                    const option = document.createElement('option');
                    option.value = vendor.vendor_id;
                    option.textContent = `${vendor.name} (${vendor.location}) - ${vendor.company_name}`;
                    vendorFilter.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Failed to load outlets:', error);
        }
    }

    /* ------------------------------------
       Fetch and render utilities
    ------------------------------------ */
    async function loadUtilities() {
        const search = searchInput.value.trim();
        const vendorId = vendorFilter.value;
        const status = statusFilter.value;

        const url = `${SA_API.GET_UTILITIES}?search=${encodeURIComponent(search)}&vendor_id=${vendorId}&status=${status}`;

        try {
            const response = await fetchWithAutoRefresh(url, {
                method: 'GET'
            });
            const result = await response.json();

            if (response.ok && result.success) {
                allUtilitiesData = result.utilities;
                renderUtilities(allUtilitiesData);
            } else {
                ModalService.showError(result.error || 'Failed to load utilities');
            }
        } catch (error) {
            console.error('Failed to load utilities:', error);
            ModalService.showError('Unexpected error occurred');
        }
    }

    function renderUtilities(utilities) {
        utilitiesTbody.innerHTML = '';
        if (utilities.length === 0) {
            tableContainer.style.display = 'none';
            emptyState.style.display = 'block';
            return;
        }

        tableContainer.style.display = 'block';
        emptyState.style.display = 'none';

        utilities.forEach(u => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${escapeHtml(u.utility_name)}</td>
                <td>${escapeHtml(u.display_name)}</td>
                ${!isBuffetProject ? `
                <td>${escapeHtml(u.display_code)}</td>
                <td>${escapeHtml(u.prefix)}</td>
                <td>${escapeHtml(u.token_mode)}</td>
                ` : ''}
                <td>${escapeHtml(u.company_name)}</td>
                <td>${escapeHtml(u.vendor_name)} (${escapeHtml(u.vendor_location)})</td>
                <td>
                    <span class="badge ${u.is_active ? 'bg-success' : 'bg-danger'}">
                        ${u.is_active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td>
                    <div class="dropdown">
                        <button class="action-btn dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                            <i class="fas fa-ellipsis-v"></i>
                        </button>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item edit-utility" href="#" data-id="${u.id}">Edit</a></li>
                            ${isBuffetProject ? `<li><a class="dropdown-item manage-options" href="#" data-id="${u.id}">Manage Options</a></li>` : ''}
                            <li><a class="dropdown-item toggle-status" href="#" data-id="${u.id}" data-active="${u.is_active}">
                                ${u.is_active ? 'Deactivate' : 'Activate'}
                            </a></li>
                        </ul>
                    </div>
                </td>
            `;
            utilitiesTbody.appendChild(tr);
        });

        attachActionListeners();
    }

    function attachActionListeners() {
        document.querySelectorAll('.toggle-status').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const id = e.target.dataset.id;
                const currentActive = e.target.dataset.active === 'true';
                await toggleUtilityStatus(id, !currentActive);
            });
        });

        document.querySelectorAll('.edit-utility').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const id = e.target.dataset.id;
                const utility = allUtilitiesData.find(u => u.id == id);
                if (utility) showEditModal(utility);
            });
        });

        document.querySelectorAll('.manage-options').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const id = e.target.dataset.id;
                // Since options are not in the main list, we'll need to fetch them or assume they are empty for now
                // Actually, I'll add options to the get_all_utilities API later if needed.
                // For now, let's just show an empty placeholder or fetch specifically.
                showManageOptionsModal(id);
            });
        });
    }

    /* ------------------------------------
       Actions
    ------------------------------------ */
    async function toggleUtilityStatus(id, newStatus) {
        try {
            const response = await fetchWithAutoRefresh(SA_API.UPDATE_UTILITY_STATUS, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': AppUtils.getCSRFToken()
                },
                body: JSON.stringify({
                    utility_id: id,
                    is_active: newStatus
                })
            });
            if (response.ok) {
                loadUtilities();
            } else {
                const result = await response.json();
                ModalService.showError(result.error || 'Failed to update status');
            }
        } catch (error) {
            console.error('Failed to update status:', error);
        }
    }

    function showEditModal(utility) {
        const isBuffet = isBuffetProject;
        const body = `
            <div id="edit-error-message" style="display: none; margin-bottom: 12px;"></div>
            <form id="edit-utility-form">
                <div class="mb-3">
                    <label class="form-label">Utility Name</label>
                    <input type="text" id="edit-utility-name" class="form-control" value="${escapeHtml(utility.utility_name)}">
                </div>
                <div class="mb-3">
                    <label class="form-label">Display Name</label>
                    <input type="text" id="edit-display-name" class="form-control" value="${escapeHtml(utility.display_name)}">
                </div>
                ${!isBuffet ? `
                <div class="mb-3">
                    <label class="form-label">Display Code</label>
                    <input type="text" id="edit-display-code" class="form-control" value="${escapeHtml(utility.display_code)}">
                </div>
                <div class="mb-3">
                    <label class="form-label">Prefix</label>
                    <input type="text" id="edit-prefix" class="form-control" value="${escapeHtml(utility.prefix)}">
                </div>
                <div class="mb-3">
                    <label class="form-label">Token Mode</label>
                    <select id="edit-token-mode" class="form-select">
                        <option value="continuous" ${utility.token_mode === 'continuous' ? 'selected' : ''}>Continuous</option>
                        <option value="utility_specific" ${utility.token_mode === 'utility_specific' ? 'selected' : ''}>Utility Specific</option>
                    </select>
                </div>
                ` : ''}
                <div class="mt-4 pt-4 border-top text-end">
                    <button type="button" class="btn btn-secondary rounded-pill px-4 me-2" ${isBuffet ? 'style="color:#495057 !important;border:1px solid #ced4da !important;background:#fff !important;"' : ''} data-bs-dismiss="modal">Cancel</button>
                    <button type="submit" class="btn ${isBuffet ? 'btn-golden' : 'btn-primary'} rounded-pill px-4" ${isBuffet ? 'style="background-color:#f0a934 !important;border:1px solid #f0a934 !important;color:#fff !important;"' : ''}>Save Changes</button>
                </div>
            </form>
        `;

        ModalService.showCustom({
            title: 'Edit Food Counter',
            body: body,
            onShown: () => {
                document.getElementById('edit-utility-form').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const payload = {
                        utility_id: utility.id,
                        utility_name: document.getElementById('edit-utility-name').value,
                        display_name: document.getElementById('edit-display-name').value,
                    };
                    if (!isBuffet) {
                        payload.display_code = document.getElementById('edit-display-code').value;
                        payload.prefix = document.getElementById('edit-prefix').value;
                        payload.token_mode = document.getElementById('edit-token-mode').value;
                    }

                    const response = await fetchWithAutoRefresh(SA_API.UPDATE_UTILITY, {
                        method: 'PATCH',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': AppUtils.getCSRFToken()
                        },
                        body: JSON.stringify(payload)
                    });

                    if (response.ok) {
                        bootstrap.Modal.getInstance(document.getElementById('customModal')).hide();
                        loadUtilities();
                    } else {
                        const result = await response.json();
                        document.getElementById('edit-error-message').textContent = result.error || 'Failed to update utility';
                        document.getElementById('edit-error-message').style.display = 'block';
                    }
                });
            }
        });
    }

    async function showManageOptionsModal(utilityId) {
        const utility = allUtilitiesData.find(u => u.id == utilityId);
        if (!utility) return;

        function renderOptionsList(options) {
            if (options.length === 0) {
                return '<p class="text-muted">No options added yet.</p>';
            }
            return `
                <ul class="list-group mb-3">
                    ${options.map(opt => `
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <div>
                                <span class="${opt.is_active ? '' : 'text-decoration-line-through text-muted'}">${escapeHtml(opt.name)}</span>
                                ${!opt.is_active ? '<span class="badge bg-secondary ms-2 text-white">Inactive</span>' : ''}
                            </div>
                            <div class="btn-group btn-group-sm">
                                <button class="btn btn-outline-primary edit-option" data-id="${opt.id}" data-name="${escapeHtml(opt.name)}" data-active="${opt.is_active}" title="Edit">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn btn-outline-danger delete-option" data-id="${opt.id}" title="Delete">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </li>
                    `).join('')}
                </ul>
            `;
        }

        const body = `
            <div id="options-error-message" class="alert alert-danger" style="display: none;"></div>
            <div class="mb-4">
                <h6 id="option-form-title">Add New Option</h6>
                <form id="add-option-form" class="d-flex gap-2">
                    <input type="hidden" id="editing-option-id" value="">
                    <input type="hidden" id="editing-option-active" value="true">
                    <input type="text" id="new-option-name" class="form-control" placeholder="e.g. Extra Cheese" required>
                    <button type="submit" id="save-option-btn" class="btn btn-success">Save</button>
                    <button type="button" id="cancel-option-edit-btn" class="btn btn-secondary" style="display:none;">Cancel</button>
                </form>
            </div>
            <hr>
            <h6>Current Options</h6>
            <div id="options-list-container">
                ${renderOptionsList(utility.options)}
            </div>
        `;

        ModalService.showCustom({
            title: `Manage Options: ${escapeHtml(utility.utility_name)}`,
            body: body,
            onShown: () => {
                const addForm = document.getElementById('add-option-form');
                const listContainer = document.getElementById('options-list-container');
                const errorMsg = document.getElementById('options-error-message');
                const optionNameInput = document.getElementById('new-option-name');
                const editingOptionIdInput = document.getElementById('editing-option-id');
                const editingOptionActiveInput = document.getElementById('editing-option-active');
                const saveOptionBtn = document.getElementById('save-option-btn');
                const cancelEditBtn = document.getElementById('cancel-option-edit-btn');
                const optionFormTitle = document.getElementById('option-form-title');

                const resetOptionForm = () => {
                    addForm.reset();
                    editingOptionIdInput.value = '';
                    editingOptionActiveInput.value = 'true';
                    saveOptionBtn.textContent = 'Save';
                    optionFormTitle.textContent = 'Add New Option';
                    cancelEditBtn.style.display = 'none';
                };

                const setOptionEditMode = (optId, optionName, isActive) => {
                    editingOptionIdInput.value = optId;
                    editingOptionActiveInput.value = String(isActive);
                    optionNameInput.value = optionName;
                    saveOptionBtn.textContent = 'Update';
                    optionFormTitle.textContent = 'Edit Option';
                    cancelEditBtn.style.display = 'inline-block';
                    optionNameInput.focus();
                };

                const refreshOptions = async () => {
                    // Update the main data and re-render local list
                    const response = await fetchWithAutoRefresh(SA_API.GET_UTILITIES, { method: 'GET' });
                    const result = await response.json();
                    if (response.ok && result.success) {
                        allUtilitiesData = result.utilities;
                        const updatedUtil = allUtilitiesData.find(u => u.id == utilityId);
                        listContainer.innerHTML = renderOptionsList(updatedUtil.options);
                        attachOptionListeners();
                        renderUtilities(allUtilitiesData); // Also refresh the main table status if needed
                        resetOptionForm();
                    }
                };

                const attachOptionListeners = () => {
                    document.querySelectorAll('.delete-option').forEach(btn => {
                        btn.addEventListener('click', async (e) => {
                            const optId = e.currentTarget.dataset.id;
                            if (confirm('Are you sure you want to delete this option?')) {
                                const response = await fetchWithAutoRefresh(SA_API.DELETE_OPTION(optId), {
                                    method: 'DELETE',
                                    headers: { 'X-CSRFToken': AppUtils.getCSRFToken() }
                                });
                                if (response.ok) refreshOptions();
                                else {
                                    const res = await response.json();
                                    errorMsg.textContent = res.error || 'Failed to delete option';
                                    errorMsg.style.display = 'block';
                                }
                            }
                        });
                    });

                    document.querySelectorAll('.edit-option').forEach(btn => {
                        btn.addEventListener('click', (e) => {
                            const optId = e.currentTarget.dataset.id;
                            const currentName = e.currentTarget.dataset.name;
                            const currentActive = e.currentTarget.dataset.active === 'true';
                            setOptionEditMode(optId, currentName, currentActive);
                        });
                    });
                };

                addForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    errorMsg.style.display = 'none';
                    const name = optionNameInput.value.trim();
                    const editingOptionId = editingOptionIdInput.value;
                    if (!name) {
                        errorMsg.textContent = 'Option name is required';
                        errorMsg.style.display = 'block';
                        return;
                    }

                    const isEdit = Boolean(editingOptionId);
                    const endpoint = isEdit ? SA_API.UPDATE_OPTION(editingOptionId) : SA_API.CREATE_OPTION(utilityId);
                    const method = isEdit ? 'PUT' : 'POST';
                    const isActive = isEdit ? editingOptionActiveInput.value === 'true' : true;

                    const response = await fetchWithAutoRefresh(endpoint, {
                        method,
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': AppUtils.getCSRFToken()
                        },
                        body: JSON.stringify({ name, is_active: isActive })
                    });
                    if (response.ok) {
                        refreshOptions();
                    } else {
                        const res = await response.json();
                        errorMsg.textContent = res.error || `Failed to ${isEdit ? 'update' : 'add'} option`;
                        errorMsg.style.display = 'block';
                    }
                });

                cancelEditBtn.addEventListener('click', () => {
                    resetOptionForm();
                });

                attachOptionListeners();
            }
        });
    }

    /* ------------------------------------
       Event listeners
    ------------------------------------ */
    searchInput.addEventListener('input', loadUtilities);
    vendorFilter.addEventListener('change', loadUtilities);
    statusFilter.addEventListener('change', loadUtilities);

    /* ------------------------------------
       Initialization
    ------------------------------------ */
    await loadOutlets();
    await loadUtilities();
});
