import { ConfirmModalService } from './services/confirmModalService.js';

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
  const configForm = document.getElementById('configuration-form');
  const outletsSelect = document.getElementById('outlets');
  const phoneNumberEnabledEl = document.getElementById('phone_number_enabled');
  const utilitiesEnabledEl = document.getElementById('utilities_enabled');

  if (!configForm || !outletsSelect) return;

  /* ------------------------------------
     Initialize Choices (ONCE)
  ------------------------------------ */
  const outletsChoices = new Choices(outletsSelect, {
    searchEnabled: true,
    shouldSort: false,
    placeholderValue: 'Select Outlet',
    classNames: {
      containerInner: 'choices-inner-foodflash',
      item: 'choices-item-foodflash',
    }
  });

  /* ------------------------------------
     Fetch vendors & populate outlets
  ------------------------------------ */
  let result = null;
  try {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS, {
      method: 'GET'
    });

    result = await response.json();

    if (!response.ok) {
      throw new Error(result?.message || 'Failed to fetch vendors');
    }

    if (Array.isArray(result.vendors)) {
      const choicesData = result.vendors.map(vendor => ({
        value: vendor.id,
        label: `${vendor.name} (${vendor.location})`
      }));

      outletsChoices.setChoices(choicesData, 'value', 'label', true);
    }

  } catch (error) {
    console.error('Vendor fetch failed:', error);
    ModalService.showError(
      'Unable to load outlet list. Please refresh the page.'
    );
    return;
  }

  // Build a map of vendors returned by GET_VENDORS so we can populate the form
  // without making an extra network request for details.
  const vendorsMap = new Map();
  if (Array.isArray(result.vendors)) {
    result.vendors.forEach(v => {
      // normalize key as string for consistent lookup
      vendorsMap.set(String(v.id), v);
    });
  }

  const loadVendorConfigFromMap = (vendorId) => {
    if (!vendorId) {
      phoneNumberEnabledEl.checked = false;
      utilitiesEnabledEl.checked = false;
      return;
    }

    const vendor = vendorsMap.get(String(vendorId)) || null;
    const vendorConfig = vendor?.config || vendor?.vendor_config || null;

    if (vendorConfig && Object.prototype.hasOwnProperty.call(vendorConfig, 'phone_number_enabled')) {
      phoneNumberEnabledEl.checked = Boolean(vendorConfig.phone_number_enabled);
    } else {
      phoneNumberEnabledEl.checked = false;
    }

    if (vendorConfig && Object.prototype.hasOwnProperty.call(vendorConfig, 'use_utilities')) {
      utilitiesEnabledEl.checked = Boolean(vendorConfig.use_utilities);
    } else {
      utilitiesEnabledEl.checked = false;
    }
  };

  // Listen for selection changes on the underlying select element
  outletsSelect.addEventListener('change', () => {
    const sel = outletsChoices.getValue(true);
    const id = Array.isArray(sel) ? (sel[0] || null) : (sel || null);
    loadVendorConfigFromMap(id);
  });

  // If a default selection exists after populating choices, load its config
  const initialValue = outletsChoices.getValue(true);
  const initialId = Array.isArray(initialValue) ? (initialValue[0] || null) : (initialValue || null);
  if (initialId) {
    loadVendorConfigFromMap(initialId);
  }

  /* ------------------------------------
     Submit configuration
  ------------------------------------ */
  configForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    let selected = outletsChoices.getValue(true); // may be string or array
    const vendorId = Array.isArray(selected) ? (selected[0] || null) : (selected || null);

    if (!vendorId) {
      ModalService.showError('Please select an outlet.');
      return;
    }

    const confirmed = await ConfirmModalService.show(
      'Are you sure you want to update these configurations? This action will immediately affect system behavior.'
    );

    if (!confirmed) return;

    const payload = {
      vendor_id: vendorId,
      phone_number_enabled: Boolean(phoneNumberEnabledEl.checked),
      use_utilities: Boolean(utilitiesEnabledEl.checked)
    };

    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.CONFIG, {
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
          'Configurations updated successfully.',
          () => window.location.reload()
        );
        return;
      }

      let message = 'Something went wrong.';

      if (result?.details) {
        message = Object.entries(result.details)
          .map(([key, value]) =>
            `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
          )
          .join('\n');
      } else if (result?.message) {
        message = result.message;
      }

      ModalService.showError(message);

    } catch (error) {
      console.error('Configuration update failed:', error);
      ModalService.showError(
        'Unexpected error occurred. Please try again.'
      );
    }
  });
});
