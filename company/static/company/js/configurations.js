import { ConfirmModalService } from './services/confirmModalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
 
  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;
  const configForm = document.getElementById('congiguration-form');
  try {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.CONFIG, {
      method: 'GET',
    });

    const result = await response.json();

    if (response.ok && result.auto_delete_hours !== undefined) {
      const dropdown = document.getElementById('autoDeleteTime');
      dropdown.value = result.auto_delete_hours?.toString() || '';
    }

  } catch (err) {
    console.error("Failed to fetch current config:", err);
  }

  configForm.addEventListener('submit', async function (e) {
    e.preventDefault();

    const confirmed = await ConfirmModalService.show(
        "Are you sure you want to update these configurations? This action will immediately affect system behavior.");
    if (!confirmed) return;

    const rawValue = document.getElementById('autoDeleteTime').value;
    const autoDeleteHours = rawValue === '' ? null : parseInt(rawValue, 10);
    
    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.CONFIG, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': AppUtils.getCSRFToken()
        },
        body: JSON.stringify({
          auto_delete_hours: autoDeleteHours
        })
      });

      const result = await response.json();

      if (response.ok) {
        ModalService.showSuccess('Configurations updated successfully.', () => {
          window.location.reload();
        });
      } else {
        let msg = 'Something went wrong.';

        if (result?.details) {
          const errorDetails = result.details;
          if (Array.isArray(errorDetails.non_field_errors)) {
            msg = errorDetails.non_field_errors.join('\n');
          } else {
            msg = Object.entries(errorDetails)
              .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
              .join('\n');
          }
        } else if (result?.error) {
          msg = result.error;
        } else if (result?.message) {
          msg = result.message;
        }

        ModalService.showError(msg);
      }
    } catch (err) {
      console.error(err);
      ModalService.showError('Unexpected error occurred. Please try again.');
    }
  });
});
