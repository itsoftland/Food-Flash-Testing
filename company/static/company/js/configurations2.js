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
    removeItemButton: true,
    searchEnabled: true,
    shouldSort: false,
    placeholderValue: 'Select Outlets',
    classNames: {
      containerInner: 'choices-inner-foodflash',
      item: 'choices-item-foodflash',
    }
  });

  /* ------------------------------------
     Fetch vendors & populate outlets
  ------------------------------------ */
  try {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS, {
      method: 'GET'
    });

    const result = await response.json();

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

  /* ------------------------------------
     Submit configuration
  ------------------------------------ */
  configForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const selectedOutlets = outletsChoices.getValue(true); // returns array of values

    if (!selectedOutlets.length) {
      ModalService.showError('Please select at least one outlet.');
      return;
    }

    const confirmed = await ConfirmModalService.show(
      'Are you sure you want to update these configurations? This action will immediately affect system behavior.'
    );

    if (!confirmed) return;

    const payload = {
      vendor_ids: selectedOutlets,
      phone_number_enabled:
        phoneNumberEnabledEl.value === ''
          ? null
          : phoneNumberEnabledEl.value === 'true',
      utilities_enabled:
        utilitiesEnabledEl.value === ''
          ? null
          : utilitiesEnabledEl.value === 'true'
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
