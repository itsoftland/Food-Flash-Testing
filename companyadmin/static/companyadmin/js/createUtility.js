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
  const createUtilityForm = document.getElementById('create-utilities-form');
  const vendorSelect = document.getElementById('vendor-select');
  const utilityNameInput = document.querySelector('input[name="utility_name"]');
  const displayNameInput = document.querySelector('input[name="display_name"]');
  const displayCodeInput = document.querySelector('input[name="display_code"]');
  const tokenModeSelect = document.querySelector('select[name="token_mode"]');
  const prefixInput = document.querySelector('input[name="prefix"]');
  const isActiveCheckbox = document.querySelector('input[name="is_active"]');

  if (!createUtilityForm || !vendorSelect) return;

  /* ------------------------------------
     Fetch all vendors (outlets) for Super Admin
  ------------------------------------ */
  let vendorsData = [];
  try {
    // Super Admin uses COMPANY_OUTLETS to see all vendors across all companies
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.COMPANY_OUTLETS, {
      method: 'GET'
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result?.message || 'Failed to fetch vendors');
    }

    // result is an array for COMPANY_OUTLETS according to companyadmin/views.py all_outlets
    if (Array.isArray(result)) {
      vendorsData = result;
      
      vendorSelect.innerHTML = '<option value="">Select outlet</option>';
      result.forEach(vendor => {
        const option = document.createElement('option');
        option.value = vendor.vendor_id;
        // Include company name for Super Admin clarity
        option.textContent = `${vendor.name} (${vendor.location}) - ${vendor.company_name}`;
        vendorSelect.appendChild(option);
      });
    }

  } catch (error) {
    console.error('Vendor fetch failed:', error);
    ModalService.showError(
      'Unable to load outlet list. Please refresh the page.'
    );
    return;
  }

  /* ------------------------------------
     Form submission handler
  ------------------------------------ */
  createUtilityForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const vendorId = vendorSelect.value;
    if (!vendorId) {
      ModalService.showError('Please select an outlet.');
      return;
    }

    const utilityName = utilityNameInput.value.trim();
    const displayName = displayNameInput.value.trim();
    const isBuffet = window.PROJECT_NAME === 'dine_flash_buffet';
    const displayCode = isBuffet ? "" : (displayCodeInput ? displayCodeInput.value.trim() : '');
    const tokenMode = isBuffet ? 'continuous' : (tokenModeSelect ? tokenModeSelect.value.trim() : '');
    const prefix = isBuffet ? null : (prefixInput ? prefixInput.value.trim() : '');
    const isActive = isActiveCheckbox.checked;

    if (!utilityName) {
      ModalService.showError('Utility Name is required.');
      return;
    }
    if (!displayName) {
      ModalService.showError('Display Name is required.');
      return;
    }
    if (!isBuffet && !displayCode) {
      ModalService.showError('Display Code is required.');
      return;
    }
    if (!isBuffet && !tokenMode) {
      ModalService.showError('Token Mode is required.');
      return;
    }

    const payload = {
      vendor_id: vendorId,
      utility_name: utilityName,
      display_name: displayName,
      display_code: displayCode,
      token_mode: tokenMode,
      prefix: prefix,
      is_active: isActive
    };

    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_UTILITY, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': AppUtils.getCSRFToken()
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json();

      if (response.ok) {
        ModalService.showSuccess(
          'Utility created successfully!',
          () => {
            createUtilityForm.reset();
            // Optionally redirect or stay on page
          }
        );
        return;
      }

      ModalService.showError(result?.error || result?.message || 'Failed to create utility.');

    } catch (error) {
      console.error('Create utility failed:', error);
      ModalService.showError('Unexpected error occurred. Please try again.');
    }
  });
});
