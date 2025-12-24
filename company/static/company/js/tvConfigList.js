import { ConfirmModalService } from './services/confirmModalService.js';

// Dynamic imports for ModalService and utilities
let ModalService;
let apiEndpoints;
let fetchWithAutoRefresh;

async function loadServices() {
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
  ModalService = modalModule.ModalService;
  
  const endpointsModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  // apiEndpoints file exports `API_ENDPOINTS` — map to local `apiEndpoints` and provide fallbacks
  apiEndpoints = endpointsModule.API_ENDPOINTS || endpointsModule.apiEndpoints || window.API_ENDPOINTS || {};

  const authModule = await import(
    `${window.BASE}static/utils/js/services/authFetchService.js`
  );

  // Assign to module-level variable, not local constant
  fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;

}

class TVConfigListManager {
    constructor() {
        this.configs = [];
        this.filteredConfigs = [];
        this.currentPage = 1;
        this.itemsPerPage = 4;
        this.actionMenuConfig = null;
        this.currentEditingConfigId = null;
        this.choicesInstance = null;
        this.initializeElements();
        this.attachEventListeners();
        this.loadConfigurations();
    }

    initializeElements() {
        this.elements = {
        configTable: document.getElementById('config-table'),
        configTbody: document.getElementById('config-tbody'),
        paginationContainer: document.getElementById('pagination-container'),
        emptyState: document.getElementById('empty-state'),
        orientationFilter: document.getElementById('orientation-filter'),
        qrStatusFilter: document.getElementById('qr-status-filter'),
        actionMenu: document.getElementById('action-menu'),
        actionMenuList: document.getElementById('action-menu-list'),
        viewModal: document.getElementById('view-modal'),
        editModal: document.getElementById('edit-modal'),
        viewDetailsContent: document.getElementById('view-details-content'),
        editAlertContainer: document.getElementById('edit-alert'),
        editForm: document.getElementById('edit-form'),
        };
    }

    attachEventListeners() {
        // Check if elements exist before attaching listeners
        if (this.elements.orientationFilter) {
        this.elements.orientationFilter.addEventListener('change', () => this.applyFilters());
        }

        if (this.elements.qrStatusFilter) {
        this.elements.qrStatusFilter.addEventListener('change', () => this.applyFilters());
        }

        // Action menu close on outside click
        document.addEventListener('click', (e) => {
        if (!e.target.closest('.action-menu') && !e.target.closest('.action-btn')) {
            this.hideActionMenu();
        }
        });

        // Modal close handlers
        if (this.elements.viewModal) {
        this.elements.viewModal.addEventListener('hidden.bs.modal', () => {
            this.hideActionMenu();
        });
        }
        if (this.elements.editModal) {
        this.elements.editModal.addEventListener('hidden.bs.modal', () => {
            this.hideActionMenu();
            if (this.choicesInstance) {
            this.choicesInstance.destroy();
            this.choicesInstance = null;
            }
        });
        }

        // Edit form submit
        if (this.elements.editForm) {
        this.elements.editForm.addEventListener('submit', (e) => this.handleEditSubmit(e));
        }
    }

    async loadConfigurations() {
        try {
        const response = await fetchWithAutoRefresh(apiEndpoints.GET_TV_CONFIG, {
            method: 'GET',
            headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': AppUtils.getCSRFToken(),
            },
        });

        if (!response.ok) {
            throw new Error('Failed to load configurations');
        }

        const data = await response.json();
        // Handle response structure: { configs: [...], count: ... }
        this.configs = data.configs || data.results || data;
        this.filteredConfigs = [...this.configs];
        this.currentPage = 1;
        this.renderTable();
        this.renderPagination();
        } catch (error) {
        console.error('Error loading configurations:', error);
        ModalService.showError('Failed to load configurations');
        }
    }

//   applyFilters() {
//     const orientation = this.elements.orientationFilter.value;
//     const qrStatus = this.elements.qrStatusFilter.value;
//     console.log(`🔎 Applying filters: Orientation: ${orientation}, QR Status: ${qrStatus}`);

//     this.filteredConfigs = this.configs.filter((config) => {
//       // Orientation filter
//       if (orientation && orientation !== 'all' && config.screen_orientation !== orientation) {
//         return false;
//       }

//       // QR Status filter
//       if (qrStatus !== 'all') {
//         const isQrEnabled = config.show_qr;
//         if (qrStatus === 'enabled' && !isQrEnabled) return false;
//         if (qrStatus === 'disabled' && isQrEnabled) return false;
//       }

//       return true;
//     });

//     this.currentPage = 1;
//     this.renderTable();
//     this.renderPagination();
//   }
    applyFilters() {
        const orientationFilter = this.elements.orientationFilter;
        const qrStatusFilter = this.elements.qrStatusFilter;

        if (orientationFilter && qrStatusFilter) {
            const orientation = orientationFilter.value;
            const qrStatus = qrStatusFilter.value;
            console.log(`🔎 Applying filters: Orientation: ${orientation}, QR Status: ${qrStatus}`);

            this.filteredConfigs = this.configs.filter((config) => {
            // Orientation filter
            if (orientation && orientation !== 'all' && config.screen_orientation !== orientation) {
                return false;
            }

            // QR Status filter
            if (qrStatus !== 'all') {
                const isQrEnabled = config.show_qr;
                if (qrStatus === 'enabled' && !isQrEnabled) return false;
                if (qrStatus === 'disabled' && isQrEnabled) return false;
            }

            return true;
            });

            this.currentPage = 1;
            this.renderTable();
            this.renderPagination();
        }
    }

    renderTable() {
        if (this.filteredConfigs.length === 0) {
            if (this.elements.configTable) {
            this.elements.configTable.style.display = 'none';
            }
            this.elements.paginationContainer.innerHTML = '';
            this.elements.emptyState.style.display = 'block';
            return;
        }

        if (this.elements.configTable) {
            this.elements.configTable.style.display = 'table';
        }
        this.elements.emptyState.style.display = 'none';

        const start = (this.currentPage - 1) * this.itemsPerPage;
        const end = start + this.itemsPerPage;
        const pageConfigs = this.filteredConfigs.slice(start, end);

        this.elements.configTbody.innerHTML = pageConfigs
        .map((config) => this.createTableRow(config))
        .join('');

        // Attach action button listeners
        this.elements.configTbody.querySelectorAll('.action-btn').forEach((btn) => {
        btn.addEventListener('click', (e) => this.showActionMenu(e, btn));
        });
    }

    createTableRow(config) {
        console.log(config);
        const qrBadgeClass = config.show_qr ? 'enabled' : 'disabled';
        const qrBadgeText = config.show_qr ? 'Enabled' : 'Disabled';
        const utilitiesCount = config.utilities.length;
        const createdDate = new Date(config.created_at).toLocaleDateString('en-US');

        return `
            <tr>
            <td class="config-code">${this.escapeHtml(config.utility_name_mode )|| ''}</td>
            <td><span class="config-items">${config.items_to_show}</span></td>
            <td><span class="qr-badge ${qrBadgeClass}">${qrBadgeText}</span></td>
            <td><span class="orientation-badge">${config.screen_orientation.charAt(0).toUpperCase() + config.screen_orientation.slice(1)}</span></td>
            <td><span class="utilities-count">${utilitiesCount}</span></td>
            <td class="date-created">${createdDate}</td>
            <td>
                <button class="action-btn" data-config-id="${config.id}" title="Actions">
                <i class="fas fa-ellipsis-v"></i>
                </button>
            </td>
            </tr>
        `;
        }

    renderPagination() {
        const totalPages = Math.ceil(this.filteredConfigs.length / this.itemsPerPage);

        if (totalPages <= 1) {
        this.elements.paginationContainer.innerHTML = '';
        return;
        }

        let html = '';

        // Previous button
        if (this.currentPage > 1) {
        html += `<button class="page-btn" onclick="tvConfigManager.goToPage(${this.currentPage - 1})">← Previous</button>`;
        } else {
        html += `<button class="page-btn disabled" disabled>← Previous</button>`;
        }

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
        if (i === this.currentPage) {
            html += `<button class="page-btn active">${i}</button>`;
        } else {
            html += `<button class="page-btn" onclick="tvConfigManager.goToPage(${i})">${i}</button>`;
        }
        }

        // Next button
        if (this.currentPage < totalPages) {
        html += `<button class="page-btn" onclick="tvConfigManager.goToPage(${this.currentPage + 1})">Next →</button>`;
        } else {
        html += `<button class="page-btn disabled" disabled>Next →</button>`;
        }

        this.elements.paginationContainer.innerHTML = html;
    }

    goToPage(page) {
        this.currentPage = page;
        this.renderTable();
        this.renderPagination();
    }

    showActionMenu(event, btn) {
        event.preventDefault();
        event.stopPropagation();

        const configId = btn.dataset.configId;
        this.actionMenuConfig = this.configs.find((c) => c.id === parseInt(configId));

        const rect = btn.getBoundingClientRect();
        this.elements.actionMenu.style.display = 'block';
        this.elements.actionMenu.style.position = 'fixed';
        this.elements.actionMenu.style.top = rect.bottom + 5 + 'px';
        this.elements.actionMenu.style.left = rect.left + 'px';
        this.elements.actionMenu.style.zIndex = '1000';

        // Clear previous event listeners
        const newList = this.elements.actionMenuList.cloneNode(true);
        this.elements.actionMenu.replaceChild(newList, this.elements.actionMenuList);
        this.elements.actionMenuList = newList;

        // Attach new event listeners
        this.elements.actionMenuList.querySelectorAll('.action-menu-item').forEach((item) => {
        item.addEventListener('click', (e) => this.handleActionMenuClick(e));
        });
    }

    hideActionMenu() {
        this.elements.actionMenu.style.display = 'none';
        this.actionMenuConfig = null;
    }

    handleActionMenuClick(event) {
        const action = event.currentTarget.dataset.action;
        const configId = this.actionMenuConfig.id;

        if (action === 'view') {
        this.openViewModal(this.actionMenuConfig);
        } else if (action === 'edit') {
        this.openEditModal(this.actionMenuConfig);
        } else if (action === 'delete') {
        this.openDeleteModal(configId);
        }

        this.hideActionMenu();
    }

    openViewModal(config) {
        const utilitiesHtml = config.utilities
        .map((utility) => `<span class="badge bg-light text-dark">${this.escapeHtml(utility.name)}</span>`)
        .join(' ');

        const bookingFieldsHtml = config.booking_fields
        .map((field) => `<span class="badge bg-info">${field.charAt(0).toUpperCase() + field.slice(1)}</span>`)
        .join(' ');

        const detailsHtml = `
        <div class="details-grid">
            <div class="detail-item">
            <span class="detail-label">Display Code</span>
            <span class="detail-value">${this.escapeHtml(config.display_code)}</span>
            </div>
            <div class="detail-item">
            <span class="detail-label">Items to Show</span>
            <span class="detail-value">${config.items_to_show}</span>
            </div>
            <div class="detail-item">
            <span class="detail-label">Screen Orientation</span>
            <span class="detail-value">${config.screen_orientation.charAt(0).toUpperCase() + config.screen_orientation.slice(1)}</span>
            </div>
            <div class="detail-item">
            <span class="detail-label">QR Code Status</span>
            <span class="detail-value badge ${config.show_qr ? 'qr-enabled' : 'qr-disabled'}">${config.show_qr ? 'Enabled' : 'Disabled'}</span>
            </div>
            ${config.show_qr ? `
            <div class="detail-item">
                <span class="detail-label">QR Alignment</span>
                <span class="detail-value">${config.qr_alignment.charAt(0).toUpperCase() + config.qr_alignment.slice(1)}</span>
            </div>
            ` : ''}
            <div class="detail-item">
            <span class="detail-label">Utility Display Mode</span>
            <span class="detail-value">${config.utility_name_mode === 'display_code' ? 'Code' : 'Name'}</span>
            </div>
            <div class="detail-item" style="grid-column: 1 / -1;">
            <span class="detail-label">Associated Utilities</span>
            <span class="detail-value" style="margin-top: 0.5rem;">${utilitiesHtml}</span>
            </div>
            <div class="detail-item" style="grid-column: 1 / -1;">
            <span class="detail-label">Booking Fields</span>
            <span class="detail-value" style="margin-top: 0.5rem;">${bookingFieldsHtml}</span>
            </div>
            <div class="detail-item">
            <span class="detail-label">Created</span>
            <span class="detail-value">${new Date(config.created_at).toLocaleString('en-US')}</span>
            </div>
        </div>
        `;

        this.elements.viewDetailsContent.innerHTML = detailsHtml;
        const modal = new bootstrap.Modal(this.elements.viewModal);
        modal.show();
    }

    async openEditModal(config) {
        this.currentEditingConfigId = config.id;

        // Populate form fields
        document.getElementById('edit-show-qr').checked = config.show_qr;
        document.getElementById('edit-qr-alignment').value = config.qr_alignment;
        document.getElementById('edit-qr-alignment').disabled = !config.show_qr;
        document.getElementById('edit-items-to-show').value = config.items_to_show;
        document.getElementById('edit-utility-name-mode').value = config.utility_name_mode;
        document.getElementById('edit-screen-orientation').value = config.screen_orientation;

        // Populate booking fields checkboxes
        ['name', 'guest_count', 'token'].forEach((field) => {
        const fieldMapId = {
            'name': 'edit-field-name',
            'guest_count': 'edit-field-guest-count',
            'token': 'edit-field-token'
        };
        const checkbox = document.getElementById(fieldMapId[field]);
        if (checkbox) {
            checkbox.checked = config.booking_fields.includes(field);
        }
        });

        // Clear previous alert
        this.elements.editAlertContainer.innerHTML = '';

        // Initialize or update Choices.js for utilities
        this.initializeUtilitiesSelect(config.utilities.map((u) => u.id));

        const modal = new bootstrap.Modal(this.elements.editModal);
        modal.show();

        // QR checkbox handler
        const showQrCheckbox = document.getElementById('edit-show-qr');
        const qrAlignmentSelect = document.getElementById('edit-qr-alignment');
        showQrCheckbox.addEventListener('change', () => {
        qrAlignmentSelect.disabled = !showQrCheckbox.checked;
        if (!showQrCheckbox.checked) {
            qrAlignmentSelect.value = '';
        }
        });
    }

    initializeUtilitiesSelect(selectedUtilityIds) {
        const selectElement = document.getElementById('edit-utilities-list');

        // Destroy previous instance
        if (this.choicesInstance) {
        this.choicesInstance.destroy();
        }

        // Reset the select element
        selectElement.innerHTML = '';

        // Fetch utilities for options
        fetchWithAutoRefresh(apiEndpoints.GET_UTILITIES || '/company/api/utilities/', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': AppUtils.getCSRFToken(),
        },
        })
        .then((response) => response.json())
        .then((data) => {
            const utilities = data.results || data;

            // Add options
            utilities.forEach((utility) => {
            const option = document.createElement('option');
            option.value = utility.id;
            option.textContent = utility.name;
            option.selected = selectedUtilityIds.includes(utility.id);
            selectElement.appendChild(option);
            });

            // Initialize Choices.js
            this.choicesInstance = new Choices(selectElement, {
            removeItemButton: true,
            placeholder: true,
            placeholderValue: 'Select utilities',
            maxItemCount: -1,
            searchFloor: 0,
            allowHTML: true,
            classNames: {
                containerOuter: 'choices choices-edit',
                containerInner: 'choices__inner',
                input: 'choices__input',
                inputCloned: 'choices__input--cloned',
                list: 'choices__list',
                listItems: 'choices__list--multiple',
                listSingle: 'choices__list--single',
                listDropdown: 'choices__list--dropdown',
                item: 'choices__item',
                itemSelectable: 'choices__item--selectable',
                itemDeletable: 'choices__item--deletable',
                itemChoice: 'choices__item--choice',
                placeholder: 'choices__placeholder',
                group: 'choices__group',
                groupHeading: 'choices__heading',
                button: 'choices__button',
                activeState: 'is-active',
                focusState: 'is-focused',
                openState: 'is-open',
                disabledState: 'is-disabled',
                selectedState: 'is-selected',
                loadingState: 'is-loading',
                noResults: 'has-no-results',
                noChoices: 'has-no-choices',
            },
            });
        })
        .catch((error) => {
            console.error('Error loading utilities:', error);
            ModalService.showError('Failed to load utilities');
        });
    }

    handleEditSubmit(event) {
        event.preventDefault();

        // Clear previous alerts
        this.elements.editAlertContainer.innerHTML = '';

        // Get form values
        const showQr = document.getElementById('edit-show-qr').checked;
        const qrAlignment = document.getElementById('edit-qr-alignment').value;
        const itemsToShow = parseInt(document.getElementById('edit-items-to-show').value);
        const utilityNameMode = document.getElementById('edit-utility-name-mode').value;
        const screenOrientation = document.getElementById('edit-screen-orientation').value;

        const bookingFields = [];
        const fieldMapId = {
        'name': 'edit-field-name',
        'guest_count': 'edit-field-guest-count',
        'token': 'edit-field-token'
        };
        
        ['name', 'guest_count', 'token'].forEach((field) => {
        const checkbox = document.getElementById(fieldMapId[field]);
        if (checkbox && checkbox.checked) {
            bookingFields.push(field);
        }
        });

        const utilityIds = this.choicesInstance.getValue(true);

        // Validation
        const errors = [];

        if (!screenOrientation) {
        errors.push('Screen Orientation is required');
        }

        if (itemsToShow < 1 || itemsToShow > 5) {
        errors.push('Items to Show must be between 1 and 5');
        }

        if (showQr && !qrAlignment) {
        errors.push('QR Alignment is required when QR is enabled');
        }

        if (utilityIds.length === 0) {
        errors.push('At least one utility must be selected');
        }

        if (bookingFields.length === 0) {
        errors.push('At least one booking field must be selected');
        }

        if (errors.length > 0) {
        const errorHtml = `<div class="alert alert-danger"><strong>Errors:</strong><ul style="margin: 0.5rem 0 0 1rem;"><li>${errors.join('</li><li>')}</li></ul></div>`;
        this.elements.editAlertContainer.innerHTML = errorHtml;
        return;
        }

        // Submit update
        this.submitUpdate({
        show_qr: showQr,
        qr_alignment: qrAlignment,
        items_to_show: itemsToShow,
        utility_name_mode: utilityNameMode,
        screen_orientation: screenOrientation,
        booking_fields: bookingFields,
        utilities: utilityIds,
        });
    }

    async submitUpdate(data) {
        try {
        const response = await fetchWithAutoRefresh(
            apiEndpoints.UPDATE_TV_CONFIG.replace('{id}', this.currentEditingConfigId),
            {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken(),
            },
            body: JSON.stringify(data),
            }
        );

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Failed to update configuration');
        }

        ModalService.showSuccess('Configuration updated successfully!');
        bootstrap.Modal.getInstance(this.elements.editModal).hide();
        await this.loadConfigurations();
        this.applyFilters();
        } catch (error) {
        console.error('Error updating configuration:', error);
        const errorHtml = `<div class="alert alert-danger">${this.escapeHtml(error.message)}</div>`;
        this.elements.editAlertContainer.innerHTML = errorHtml;
        }
    }

    openDeleteModal(configId) {
        const config = this.configs.find((c) => c.id === configId);
        if (!config) return;

        const title = 'Delete Configuration';
        const message = `Are you sure you want to delete the configuration "${this.escapeHtml(config.display_code)}"? This action cannot be undone.`;
        const confirmButtonText = 'Delete';
        const cancelButtonText = 'Cancel';

        ConfirmModalService.show({
        title,
        message,
        confirmButtonText,
        cancelButtonText,
        isDangerous: true,
        onConfirm: () => this.handleDelete(configId),
        onCancel: () => {
            // Handle cancel if needed
        },
        });
    }

    async handleDelete(configId) {
        try {
        const response = await fetchWithAutoRefresh(
            apiEndpoints.DELETE_TV_CONFIG.replace('{id}', configId),
            {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken(),
            },
            }
        );

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Failed to delete configuration');
        }

        ModalService.showSuccess('Configuration deleted successfully!');
        await this.loadConfigurations();
        this.applyFilters();
        } catch (error) {
        console.error('Error deleting configuration:', error);
        ModalService.showError(error.message);
        }
    }

    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;',
        };
        return text && text.replace(/[&<>"']/g, (m) => map[m]);
        }
    }

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
  await loadServices();
  window.tvConfigManager = new TVConfigListManager();
});
