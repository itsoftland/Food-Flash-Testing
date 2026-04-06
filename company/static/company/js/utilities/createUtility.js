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
     Token Mode Choices (from Utility model)
  ------------------------------------ */
  const TOKEN_MODE_CHOICES = [
    { value: 'continuous', label: 'Continuous' },
    { value: 'utility_specific', label: 'Utility Specific' }
  ];

  // Populate token mode dropdown
  if (tokenModeSelect) {
    TOKEN_MODE_CHOICES.forEach(choice => {
      const option = document.createElement('option');
      option.value = choice.value;
      option.textContent = choice.label;
      tokenModeSelect.appendChild(option);
    });
  }

  /* ------------------------------------
     Fetch vendors & populate outlets
  ------------------------------------ */
  let vendorsData = [];
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
      
      // Populate vendor select with plain HTML options
      vendorSelect.innerHTML = '<option value="">Select outlet</option>';
      result.vendors.forEach(vendor => {
        const option = document.createElement('option');
        option.value = vendor.vendor_id;
        option.textContent = `${vendor.name} (${vendor.location})`;
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

  // Build a map of vendors for quick lookup
  const vendorsMap = new Map();
  vendorsData.forEach(vendor => {
    vendorsMap.set(String(vendor.vendor_id), vendor);
  });

  /* ------------------------------------
     Form submission handler
  ------------------------------------ */
  createUtilityForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Get vendor selection
    const vendorId = vendorSelect.value;
    if (!vendorId) {
      ModalService.showError('Please select an outlet.');
      return;
    }

    // Get form values
    const utilityName = utilityNameInput.value.trim();
    const displayName = displayNameInput.value.trim();
    const isBuffet = window.PROJECT_NAME === 'dine_flash_buffet';
    const displayCode = isBuffet ? "" : (displayCodeInput ? displayCodeInput.value.trim() : '');
    const tokenMode = isBuffet ? 'continuous' : (tokenModeSelect ? tokenModeSelect.value.trim() : '');
    const prefix = isBuffet ? null : (prefixInput ? prefixInput.value.trim() : '');
    const isActive = isActiveCheckbox.checked;

    // Basic validation
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

    // Prepare payload
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
            // Reset vendor select to default
            vendorSelect.innerHTML = '<option value="">Select outlet</option>';
            vendorsData.forEach(vendor => {
              const option = document.createElement('option');
              option.value = vendor.vendor_id;
              option.textContent = `${vendor.name} (${vendor.location})`;
              vendorSelect.appendChild(option);
            });
          }
        );
        return;
      }

      let message = 'Failed to create utility.';

      if (result?.error) {
        message = result.error;
      } else if (result?.message) {
        message = result.message;
      }

      ModalService.showError(message);

    } catch (error) {
      console.error('Create utility failed:', error);
      ModalService.showError(
        'Unexpected error occurred. Please try again.'
      );
    }
  });
});
