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
     DOM references
  ------------------------------------ */
  const vendorFilter = document.getElementById('vendor-filter');
  const searchInput = document.getElementById('search-input');
  const statusFilter = document.getElementById('status-filter');
  const tableContainer = document.getElementById('table-container');
  const utilitiesTbody = document.getElementById('utilities-tbody');
  const emptyStateNoUtilities = document.getElementById('empty-state-no-utilities');
  const actionMenu = document.getElementById('action-menu');
  const paginationContainer = document.getElementById('pagination-container');

  let vendorsData = [];
  let utilitiesData = [];
  let selectedVendorId = null;
  let currentPage = 1;
  const itemsPerPage = 4;

  /* ------------------------------------
     Load vendors on page load
  ------------------------------------ */
  async function loadVendors() {
    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS, {
        method: 'GET'
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result?.message || 'Failed to fetch vendors');
      }

      if (Array.isArray(result.vendors)) {
        vendorsData = result.vendors;

        // Populate vendor filter dropdown
        vendorFilter.innerHTML = '<option value="">All Outlets</option>';
        result.vendors.forEach(vendor => {
          const option = document.createElement('option');
          option.value = vendor.vendor_id;
          option.textContent = `${vendor.name} (${vendor.location})`;
          vendorFilter.appendChild(option);
        });
      }
    } catch (error) {
      console.error('Error loading vendors:', error);
      ModalService.showError('Failed to load outlets. Please refresh the page.');
    }
  }

  /* ------------------------------------
     Load utilities for selected vendor or all utilities
  ------------------------------------ */
  async function loadUtilities(vendorId = null) {
    selectedVendorId = vendorId;
    currentPage = 1;

    try {
      const url = vendorId 
        ? `${API_ENDPOINTS.GET_UTILITIES}?vendor_id=${vendorId}`
        : API_ENDPOINTS.GET_UTILITIES;

      const response = await fetchWithAutoRefresh(url, { method: 'GET' });
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result?.error || 'Failed to fetch utilities');
      }

      // Get utilities from API response
      if (result.success && Array.isArray(result.utilities)) {
        utilitiesData = result.utilities;
      } else {
        utilitiesData = [];
      }

      // If no utilities exist, show empty state
      if (utilitiesData.length === 0) {
        tableContainer.style.display = 'block';
        emptyStateNoUtilities.style.display = 'block';
        utilitiesTbody.innerHTML = '';
        paginationContainer.innerHTML = '';
        return;
      }

      // Render table and pagination
      renderUtilitiesTable();
      renderPagination();
      tableContainer.style.display = 'block';
      emptyStateNoUtilities.style.display = 'none';

    } catch (error) {
      console.error('Error loading utilities:', error);
      ModalService.showError('Failed to load utilities. Please try again.');
    }
  }

  /* ------------------------------------
     Render utilities table with pagination
  ------------------------------------ */
  function renderUtilitiesTable() {
    const filteredUtilities = filterUtilities();

    if (filteredUtilities.length === 0) {
      emptyStateNoUtilities.style.display = 'block';
      utilitiesTbody.innerHTML = '';
      paginationContainer.innerHTML = '';
      return;
    }

    emptyStateNoUtilities.style.display = 'none';
    utilitiesTbody.innerHTML = '';

    // Calculate pagination
    const totalPages = Math.ceil(filteredUtilities.length / itemsPerPage);
    if (currentPage > totalPages) currentPage = totalPages;
    
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const paginatedUtilities = filteredUtilities.slice(startIndex, endIndex);

    paginatedUtilities.forEach(utility => {
      const row = document.createElement('tr');
      const vendorName = utility.vendor_name || 'N/A';
      const tokenModeLabel = utility.token_mode === 'continuous' ? 'Continuous' : 'Utility Specific';
      const statusClass = utility.is_active ? 'active' : 'inactive';
      const statusLabel = utility.is_active ? 'Active' : 'Inactive';

      row.innerHTML = `
        <td class="utility-id-cell">${escapeHtml(String(utility.id))}</td>
        <td>${escapeHtml(utility.utility_name)}</td>
        <td>${escapeHtml(utility.display_name)}</td>
        ${window.PROJECT_NAME !== 'dine_flash_buffet' ? `
        <td><strong>${escapeHtml(utility.display_code)}</strong></td>
        <td>${utility.prefix ? escapeHtml(utility.prefix) : '—'}</td>
        <td><span class="token-mode-badge ${utility.token_mode === 'utility_specific' ? 'utility-specific' : ''}">${tokenModeLabel}</span></td>
        ` : ''}
        <td>${escapeHtml(vendorName)}</td>
        <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
        <td>
          <button class="action-btn" data-utility-id="${utility.id}" data-utility='${JSON.stringify(utility)}' title="More actions">
            <i class="fas fa-ellipsis-v"></i>
          </button>
        </td>
      `;

      utilitiesTbody.appendChild(row);
    });

    // Attach action button listeners
    document.querySelectorAll('.action-btn').forEach(btn => {
      btn.addEventListener('click', (e) => handleActionMenu(e, btn));
    });

    // Render pagination if needed
    if (filteredUtilities.length > itemsPerPage) {
      renderPagination();
    } else {
      paginationContainer.innerHTML = '';
    }
  }

  /* ------------------------------------
     Render pagination controls
  ------------------------------------ */
  function renderPagination() {
    const filteredUtilities = filterUtilities();
    const totalPages = Math.ceil(filteredUtilities.length / itemsPerPage);

    if (totalPages <= 1) {
      paginationContainer.innerHTML = '';
      return;
    }

    let paginationHTML = '<div class="pagination-wrapper"><ul class="pagination">';

    // Previous button
    if (currentPage > 1) {
      paginationHTML += `<li><button class="page-btn" data-page="${currentPage - 1}" title="Previous page"><i class="fas fa-chevron-left"></i></button></li>`;
    } else {
      paginationHTML += `<li><button class="page-btn" disabled title="Previous page"><i class="fas fa-chevron-left"></i></button></li>`;
    }

    // Page numbers
    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
        const activeClass = i === currentPage ? 'active' : '';
        paginationHTML += `<li><button class="page-btn ${activeClass}" data-page="${i}">${i}</button></li>`;
      } else if (i === 2 && currentPage > 3) {
        paginationHTML += `<li><span class="page-ellipsis">…</span></li>`;
      } else if (i === totalPages - 1 && currentPage < totalPages - 2) {
        paginationHTML += `<li><span class="page-ellipsis">…</span></li>`;
      }
    }

    // Next button
    if (currentPage < totalPages) {
      paginationHTML += `<li><button class="page-btn" data-page="${currentPage + 1}" title="Next page"><i class="fas fa-chevron-right"></i></button></li>`;
    } else {
      paginationHTML += `<li><button class="page-btn" disabled title="Next page"><i class="fas fa-chevron-right"></i></button></li>`;
    }

    paginationHTML += '</ul></div>';
    paginationContainer.innerHTML = paginationHTML;

    // Attach pagination listeners
    document.querySelectorAll('.page-btn:not(:disabled)').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        currentPage = parseInt(btn.dataset.page);
        renderUtilitiesTable();
        // Scroll to table top
        tableContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  /* ------------------------------------
     Filter utilities based on search and status
  ------------------------------------ */
  function filterUtilities() {
    const searchTerm = searchInput.value.toLowerCase().trim();
    const statusValue = statusFilter.value;

    return utilitiesData.filter(utility => {
      // Status filter
      const statusMatch =
        !statusValue ||
        (statusValue === 'active' && utility.is_active) ||
        (statusValue === 'inactive' && !utility.is_active);

      // Search filter (id, utility name, display name, display code)
      const searchMatch =
        !searchTerm ||
        String(utility.id).includes(searchTerm) ||
        utility.utility_name.toLowerCase().includes(searchTerm) ||
        utility.display_name.toLowerCase().includes(searchTerm) ||
        (utility.display_code && utility.display_code.toLowerCase().includes(searchTerm));

      return statusMatch && searchMatch;
    });
  }

  let currentUtility = null; // Store current utility for menu actions

  /* ------------------------------------
     Handle action menu
  ------------------------------------ */
  function handleActionMenu(e, btn) {
    e.stopPropagation();
    const utility = JSON.parse(btn.dataset.utility);

    // Get viewport height and button position
    const rect = btn.getBoundingClientRect();
    const menuHeight = 120; // Approximate menu height
    const viewportHeight = window.innerHeight;
    const spaceBelow = viewportHeight - rect.bottom;

    let top, left;

    // If there's enough space below, show below; otherwise show above
    if (spaceBelow > menuHeight + 20) {
      // Show below the button
      top = rect.bottom + window.scrollY + 4;
    } else {
      // Show above the button
      top = rect.top + window.scrollY - menuHeight - 4;
    }

    // Position horizontally - align right with button or adjust if needed
    left = rect.right - 160 + window.scrollX;

    // Ensure menu doesn't go off-screen on right side
    if (left + 160 > window.innerWidth) {
      left = window.innerWidth - 170;
    }

    actionMenu.style.top = top + 'px';
    actionMenu.style.left = left + 'px';
    actionMenu.style.display = 'block';

    // Store current utility for menu actions
    currentUtility = utility;

    // Update toggle button text
    const toggleText = document.getElementById('toggle-text');
    toggleText.textContent = utility.is_active ? 'Deactivate' : 'Activate';
  }

  /* ------------------------------------
     Handle menu actions
  ------------------------------------ */
  async function handleMenuAction(action, utility) {
    switch (action) {
      case 'view':
        showUtilityDetails(utility);
        break;
      case 'edit':
        editUtility(utility);
        break;
      case 'options':
        manageOptions(utility);
        break;
      case 'toggle':
        toggleUtilityStatus(utility);
        break;
    }
  }

  /* ------------------------------------
     Show utility details
  ------------------------------------ */
  function showUtilityDetails(utility) {
    const vendor = vendorsData.find(v => v.id === utility.vendor);
    const vendorName = vendor ? `${vendor.name} (${vendor.location})` : 'N/A';
    const tokenMode = utility.token_mode === 'continuous' ? 'Continuous' : 'Utility Specific';
    const isBuffet = window.PROJECT_NAME === 'dine_flash_buffet';

    const details = `
      <div style="text-align: left;">
        <p><strong>Utility ID:</strong> ${escapeHtml(String(utility.id))}</p>
        <p><strong>Utility Name:</strong> ${escapeHtml(utility.utility_name)}</p>
        <p><strong>Display Name:</strong> ${escapeHtml(utility.display_name)}</p>
        ${!isBuffet ? `
        <p><strong>Display Code:</strong> ${escapeHtml(utility.display_code)}</p>
        <p><strong>Prefix:</strong> ${utility.prefix ? escapeHtml(utility.prefix) : 'N/A'}</p>
        <p><strong>Token Mode:</strong> ${tokenMode}</p>
        ` : ''}
        <p><strong>Outlet:</strong> ${escapeHtml(vendorName)}</p>
        <p><strong>Status:</strong> ${utility.is_active ? 'Active' : 'Inactive'}</p>
      </div>
    `;

    ModalService.showCustom('Utility Details', details, 'OK');
  }

  /* ------------------------------------
     Edit utility (modal with inline validation)
  ------------------------------------ */
  function editUtility(utility) {
    // Build edit form HTML with error display and compact 2-column layout
    const body = `
      <div id="edit-error-message" style="display: none; margin-bottom: 12px;"></div>
      <form id="edit-utility-form" class="px-0 py-0" style="max-width: 100%;">
        <!-- Row 1: Utility Name & Display Name -->
        <div class="row g-2">
          <div class="form-group col-md-6 mb-2">
            <label class="form-label" style="font-size: 0.9rem; margin-bottom: 4px;">Utility Name</label>
            <input type="text" id="edit-utility-name" class="form-control form-control-sm" value="${escapeHtml(utility.utility_name)}" maxlength="30" />
            <small class="form-text text-muted" style="font-size: 0.75rem;">Max 30 characters</small>
          </div>
          <div class="form-group col-md-6 mb-2">
            <label class="form-label" style="font-size: 0.9rem; margin-bottom: 4px;">Display Name</label>
            <input type="text" id="edit-display-name" class="form-control form-control-sm" value="${escapeHtml(utility.display_name)}" maxlength="20" />
            <small class="form-text text-muted" style="font-size: 0.75rem;">Max 20 characters</small>
          </div>
        </div>

        ${window.PROJECT_NAME === 'dine_flash_buffet' ? `
        <div class="row g-2">
          <div class="form-group col-12 mb-2">
            <label class="form-label" style="font-size: 0.9rem; margin-bottom: 4px;">Utility image <span class="text-muted fw-normal">(optional)</span></label>
            ${utility.image_url ? `<div class="mb-2"><img src="${escapeHtml(utility.image_url)}" alt="" style="max-height:72px;border-radius:4px;border:1px solid #dee2e6;" /></div>` : ''}
            <input type="file" id="edit-buffet-image" name="buffet_utility_image" class="form-control form-control-sm" accept="image/jpeg,image/png,image/gif,image/webp" />
            <div class="form-check mt-2">
              <input type="checkbox" class="form-check-input" id="clear-buffet-image" />
              <label class="form-check-label" for="clear-buffet-image" style="font-size: 0.85rem;">Remove image</label>
            </div>
            <small class="form-text text-muted" style="font-size: 0.75rem;">JPEG, PNG, GIF or WebP, max 2 MB. APIs continue to expose this as image_url.</small>
          </div>
        </div>
        ` : ''}

        ${window.PROJECT_NAME !== 'dine_flash_buffet' ? `
        <!-- Row 2: Display Code & Token Mode -->
        <div class="row g-2">
          <div class="form-group col-md-6 mb-2">
            <label class="form-label" style="font-size: 0.9rem; margin-bottom: 4px;">Display Code</label>
            <input type="text" id="edit-display-code" class="form-control form-control-sm" value="${escapeHtml(utility.display_code)}" maxlength="10" />
            <small class="form-text text-muted" style="font-size: 0.75rem;">Max 10 characters</small>
          </div>
          <div class="form-group col-md-6 mb-2">
            <label class="form-label" style="font-size: 0.9rem; margin-bottom: 4px;">Token Mode</label>
            <select id="edit-token-mode" class="form-select form-select-sm">
              <option value="continuous" ${utility.token_mode === 'continuous' ? 'selected' : ''}>Continuous</option>
              <option value="utility_specific" ${utility.token_mode === 'utility_specific' ? 'selected' : ''}>Utility Specific</option>
            </select>
          </div>
        </div>

        <!-- Row 3: Prefix -->
        <div class="row g-2">
          <div class="form-group col-md-6 mb-2">
            <label class="form-label" style="font-size: 0.9rem; margin-bottom: 4px;">Prefix</label>
            <input type="text" id="edit-prefix" class="form-control form-control-sm" value="${utility.prefix ? escapeHtml(utility.prefix) : ''}" maxlength="4" />
            <small class="form-text text-muted" style="font-size: 0.75rem;">Max 4 characters</small>
          </div>
        </div>
        ` : ''}

        <!-- Submit Buttons -->
        <div class="d-flex justify-content-end gap-2 mt-3">
          <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
          <button type="button" id="save-utility-btn" class="btn btn-golden btn-sm">Save</button>
        </div>
      </form>
    `;

    ModalService.showCustom({ title: 'Edit Utility', body, onShown: () => {
      // attach handler to save button (replace to avoid dup listeners)
      const saveBtn = document.getElementById('save-utility-btn');
      const newSave = saveBtn.cloneNode(true);
      saveBtn.parentNode.replaceChild(newSave, saveBtn);

      // Error display helper (show inline errors in modal, not in popup modal)
      const showInlineError = (message) => {
        const errorDiv = document.getElementById('edit-error-message');
        errorDiv.innerHTML = `<div class="alert alert-danger alert-dismissible fade show" role="alert">
          ${escapeHtml(message)}
          <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>`;
        errorDiv.style.display = 'block';
        // Auto-scroll to top of modal
        const modal = document.querySelector('#customModal .modal-body');
        if (modal) modal.scrollTop = 0;
      };

      newSave.addEventListener('click', async (e) => {
        e.preventDefault();

        const isBuffet = window.PROJECT_NAME === 'dine_flash_buffet';
        const name = document.getElementById('edit-utility-name').value.trim();
        const dname = document.getElementById('edit-display-name').value.trim();
        const dcode = isBuffet ? "" : document.getElementById('edit-display-code').value.trim();
        const tmode = isBuffet ? 'continuous' : document.getElementById('edit-token-mode').value;
        const pref = isBuffet ? '' : document.getElementById('edit-prefix').value.trim();

        // Client-side validations (same limits as server) - show inline
        if (!name) return showInlineError('Utility name is required');
        if (!dname) return showInlineError('Display name is required');
        if (!isBuffet && !dcode) return showInlineError('Display code is required');
        if (!isBuffet && !tmode) return showInlineError('Token mode is required');
        if (!isBuffet && (pref === '' || pref === null)) return showInlineError('Prefix is required');

        if (name.length > 30) return showInlineError('Utility name must be at most 30 characters');
        if (dname.length > 20) return showInlineError('Display name must be at most 20 characters');
        if (!isBuffet && dcode.length > 10) return showInlineError('Display code must be at most 10 characters');
        if (!isBuffet && pref.length > 4) return showInlineError('Prefix must be at most 4 characters');

        if (!isBuffet && !['continuous','utility_specific'].includes(tmode)) return showInlineError('Invalid token mode');

        if (isBuffet) {
          const clearEl = document.getElementById('clear-buffet-image');
          const fileEl = document.getElementById('edit-buffet-image');
          if (clearEl && clearEl.checked && fileEl && fileEl.files && fileEl.files[0]) {
            return showInlineError('Uncheck "Remove image" or clear the chosen file.');
          }
        }

        try {
          let response;
          if (isBuffet) {
            const fd = new FormData();
            fd.append('utility_id', String(utility.id));
            fd.append('utility_name', name);
            fd.append('display_name', dname);
            fd.append('display_code', dcode);
            fd.append('token_mode', tmode);
            fd.append('prefix', pref);
            const clearEl = document.getElementById('clear-buffet-image');
            const fileEl = document.getElementById('edit-buffet-image');
            if (clearEl && clearEl.checked) {
              fd.append('clear_buffet_image', 'true');
            }
            if (fileEl && fileEl.files && fileEl.files[0]) {
              fd.append('buffet_utility_image', fileEl.files[0]);
            }
            response = await fetchWithAutoRefresh(API_ENDPOINTS.UPDATE_UTILITY, {
              method: 'PATCH',
              headers: {
                'X-CSRFToken': window.AppUtils.getCSRFToken()
              },
              body: fd
            });
          } else {
            response = await fetchWithAutoRefresh(API_ENDPOINTS.UPDATE_UTILITY, {
              method: 'PATCH',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': window.AppUtils.getCSRFToken()
              },
              body: JSON.stringify({
                utility_id: utility.id,
                utility_name: name,
                display_name: dname,
                display_code: dcode,
                token_mode: tmode,
                prefix: pref
              })
            });
          }

          const result = await response.json();

          if (response.ok) {
            // hide custom modal
            const customEl = document.getElementById('customModal');
            const bs = bootstrap.Modal.getInstance(customEl) || bootstrap.Modal.getOrCreateInstance(customEl);
            bs.hide();

            // show success and reload utilities on OK
            ModalService.showSuccess(result.message || 'Utility updated', async () => {
              await loadUtilities(selectedVendorId);
            });
          } else {
            // Server-side validation error - show inline in modal
            showInlineError(result?.error || 'Failed to update utility');
          }
        } catch (err) {
          console.error('Error updating utility:', err);
          showInlineError('An error occurred while updating utility');
        }
      });
    }});
  }

  /* ------------------------------------
     Manage Options (modal for specific utility)
  ------------------------------------ */
  function manageOptions(utility) {
    let optionsHtml = '';
    const options = utility.options || [];
    
    if (options.length === 0) {
      optionsHtml = '<p class="text-muted small">No options configured.</p>';
    } else {
      optionsHtml = '<ul class="list-group mb-3">';
      options.forEach(opt => {
        const activeBadge = opt.is_active ? '<span class="badge bg-success" style="font-size:0.7em;">Active</span>' : '<span class="badge bg-warning text-dark" style="font-size:0.7em;">Inactive</span>';
        optionsHtml += `
          <li class="list-group-item d-flex justify-content-between align-items-center py-1 px-2">
            <div>
              <strong>${escapeHtml(opt.name)}</strong> ${activeBadge}
            </div>
            <div>
              <button class="btn btn-sm btn-outline-secondary edit-opt-btn" data-id="${opt.id}" data-name="${escapeHtml(opt.name)}" data-active="${opt.is_active}"><i class="fas fa-edit"></i></button>
              <button class="btn btn-sm btn-outline-danger del-opt-btn" data-id="${opt.id}"><i class="fas fa-trash"></i></button>
            </div>
          </li>
        `;
      });
      optionsHtml += '</ul>';
    }

    const body = `
      <div id="options-error-message" style="display: none; margin-bottom: 12px;"></div>
      <div id="options-list-container" style="max-height: 200px; overflow-y:auto; margin-bottom: 15px;">
        ${optionsHtml}
      </div>
      <hr>
      <h6 class="mb-2" id="option-form-title" style="font-size: 0.95rem;">Add New Option</h6>
      <form id="manage-option-form" class="px-0 py-0" style="max-width: 100%;">
        <input type="hidden" id="edit-option-id" value="">
        <div class="row g-2 align-items-end">
          <div class="col-md-7 mb-2">
            <label class="form-label" style="font-size: 0.85rem; margin-bottom: 4px;">Option Name</label>
            <input type="text" id="new-option-name" class="form-control form-control-sm" placeholder="e.g. No onion" maxlength="100" />
          </div>
          <div class="col-md-3 mb-2">
            <label class="form-label" style="font-size: 0.85rem; margin-bottom: 4px;">Status</label>
            <select id="new-option-status" class="form-select form-select-sm">
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </div>
          <div class="col-md-2 mb-2">
            <button type="button" id="save-option-btn" class="btn btn-golden btn-sm w-100">Save</button>
          </div>
        </div>
        <div class="row g-2 mt-1" id="cancel-edit-row" style="display:none;">
          <div class="col-12 text-end">
             <button type="button" class="btn btn-sm btn-secondary" id="cancel-edit-opt-btn">Cancel Edit</button>
          </div>
        </div>
      </form>
    `;

    ModalService.showCustom({ title: `Manage Options: ${escapeHtml(utility.display_name)}`, body, onShown: () => {
      const errorDiv = document.getElementById('options-error-message');
      const showInlineError = (msg) => {
        errorDiv.innerHTML = `<div class="alert alert-danger alert-dismissible fade show" role="alert" style="padding: 0.5rem 1rem; font-size: 0.85rem;">
          ${escapeHtml(msg)}
          <button type="button" class="btn-close" style="padding: 0.6rem;" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>`;
        errorDiv.style.display = 'block';
      };

      const saveBtn = document.getElementById('save-option-btn');
      const cancelBtn = document.getElementById('cancel-edit-opt-btn');
      const nameInput = document.getElementById('new-option-name');
      const statusInput = document.getElementById('new-option-status');
      const idInput = document.getElementById('edit-option-id');
      const formTitle = document.getElementById('option-form-title');
      const cancelRow = document.getElementById('cancel-edit-row');

      // Edit handlers
      document.querySelectorAll('.edit-opt-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.preventDefault();
          nameInput.value = btn.dataset.name;
          statusInput.value = btn.dataset.active;
          idInput.value = btn.dataset.id;
          formTitle.textContent = 'Edit Option';
          saveBtn.textContent = 'Update';
          cancelRow.style.display = 'block';
        });
      });

      cancelBtn.addEventListener('click', () => {
        nameInput.value = '';
        statusInput.value = 'true';
        idInput.value = '';
        formTitle.textContent = 'Add New Option';
        saveBtn.textContent = 'Save';
        cancelRow.style.display = 'none';
      });

      // Delete handlers
      document.querySelectorAll('.del-opt-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.preventDefault();
          if(!confirm('Are you sure you want to delete this option?')) return;
          try {
            const resp = await fetchWithAutoRefresh(`${window.BASE}company/api/delete_utility_option/${btn.dataset.id}/`, {
              method: 'DELETE',
              headers: { 'X-CSRFToken': window.AppUtils.getCSRFToken() }
            });
            if (resp.ok) {
              await loadUtilities(selectedVendorId);
              const updatedUtil = utilitiesData.find(u => u.id === utility.id);
              if(updatedUtil) {
                const customEl = document.getElementById('customModal');
                const bs = bootstrap.Modal.getInstance(customEl);
                if(bs) bs.hide();
                setTimeout(() => manageOptions(updatedUtil), 300);
              }
            } else {
              const res = await resp.json();
              showInlineError(res.error || 'Failed to delete');
            }
          } catch(err) {
            showInlineError('Error deleting option');
          }
        });
      });

      saveBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        const nameVal = nameInput.value.trim();
        const activeVal = statusInput.value;
        const optId = idInput.value;

        if (!nameVal) return showInlineError('Option name is required');

        const isEdit = !!optId;
        const url = isEdit 
          ? `${window.BASE}company/api/update_utility_option/${optId}/`
          : `${window.BASE}company/api/create_utility_option/${utility.id}/`;
        const method = isEdit ? 'PUT' : 'POST';

        try {
          const resp = await fetchWithAutoRefresh(url, {
            method,
            headers: {
               'Content-Type': 'application/json',
               'X-CSRFToken': window.AppUtils.getCSRFToken()
            },
            body: JSON.stringify({ name: nameVal, is_active: activeVal })
          });
          const res = await resp.json();
          if (resp.ok) {
            await loadUtilities(selectedVendorId);
            const updatedUtil = utilitiesData.find(u => u.id === utility.id);
            if(updatedUtil) {
              const customEl = document.getElementById('customModal');
              const bs = bootstrap.Modal.getInstance(customEl);
              if(bs) bs.hide();
              setTimeout(() => manageOptions(updatedUtil), 300);
            }
          } else {
            showInlineError(res.error || 'Failed to save option');
          }
        } catch(err) {
          showInlineError('Error saving option');
        }
      });
    }});
  }

  /* ------------------------------------
     Toggle utility status
  ------------------------------------ */
  async function toggleUtilityStatus(utility) {
    const newStatus = !utility.is_active;
    const actionLabel = newStatus ? 'activate' : 'deactivate';

    try {
      const response = await fetchWithAutoRefresh(
        API_ENDPOINTS.UPDATE_UTILITY_STATUS,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': AppUtils.getCSRFToken()
          },
          body: JSON.stringify({
            utility_id: utility.id,
            is_active: newStatus
          })
        }
      );

      const result = await response.json();

      if (response.ok) {
        ModalService.showSuccess(`Utility ${actionLabel}d successfully!`, () => {
          // Reload utilities from API to get fresh data
          loadUtilities(selectedVendorId);
        });
      } else {
        ModalService.showError(result?.error || `Failed to ${actionLabel} utility`);
      }
    } catch (error) {
      console.error('Error toggling utility status:', error);
      ModalService.showError('An error occurred. Please try again.');
    }
  }

  /* ------------------------------------
     Event listeners
  ------------------------------------ */
  vendorFilter.addEventListener('change', (e) => {
    loadUtilities(e.target.value || null);
  });

  searchInput.addEventListener('input', () => {
    currentPage = 1;
    renderUtilitiesTable();
  });

  statusFilter.addEventListener('change', () => {
    currentPage = 1;
    renderUtilitiesTable();
  });

  // Delegated menu item click handler (single listener, not recreated each time)
  actionMenu.addEventListener('click', (e) => {
    const menuItem = e.target.closest('.menu-item');
    if (menuItem && currentUtility) {
      e.stopPropagation();
      const action = menuItem.dataset.action;
      handleMenuAction(action, currentUtility);
      actionMenu.style.display = 'none';
    }
  });

  // Close action menu when clicking outside
  document.addEventListener('click', () => {
    actionMenu.style.display = 'none';
  });

  /* ------------------------------------
     Utility functions
  ------------------------------------ */
  function escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
  }

  /* ------------------------------------
     Initialize
  ------------------------------------ */
  await loadVendors();
  // Load all utilities on page load
  await loadUtilities();
});
