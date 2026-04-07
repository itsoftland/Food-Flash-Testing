document.addEventListener('DOMContentLoaded', async function () {
    if (!window.BASE) throw new Error('window.BASE is not defined');

    // Import modules once
    const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
    const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
    const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
    const labelModule = await import(`${window.BASE}static/utils/js/formFieldLabelService.js`);
  
    const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
    const API_ENDPOINTS = apiModule.API_ENDPOINTS;
    const WEB_ENDPOINTS = apiModule.WEB_ENDPOINTS
    const ModalService = modalModule.ModalService;
    const getFriendlyFieldLabels = labelModule.default;

    const form = document.getElementById('create-outlet-form');
  
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      const locationSelect = document.getElementById('location');
      const selectedOption = locationSelect.options[locationSelect.selectedIndex];
      
      const locationValue = selectedOption.value;  // This is loc.value
      const locationKey = selectedOption.dataset.locationName;  // This is loc.key
      
      const formData = new FormData();
      formData.append('name', document.getElementById('name').value);
      formData.append('alias_name', document.getElementById('alias_name').value);
      formData.append('location', locationKey);     // Sending readable name
      formData.append('location_id', locationValue); // Sending internal value
      formData.append('place_id', document.getElementById('place_id').value || '');
      formData.append('tv_communication_mode', document.getElementById('tv_communication_mode').value || '');
      formData.append('business_day_start_hour', document.getElementById('business_day_start_hour').value || '');
      const timezoneEl = document.getElementById('timezone');
      formData.append('timezone', timezoneEl ? timezoneEl.value : 'Asia/Kolkata');

      const customer_id =AppUtils.getCustomerId('customer_id');
      formData.append('customer_id', customer_id);
  
      // File fields
      const logoInput = document.getElementById('logo');
      if (logoInput.files.length > 0) {
        formData.append('logo', logoInput.files[0]);
      }
  
      const menuFilesInput = document.getElementById('menu_files');
      for (let i = 0; i < menuFilesInput.files.length; i++) {
        formData.append('menu_files', menuFilesInput.files[i]);
      }
  
      // ✅ Handle device mapping
      const deviceSelect = document.getElementById('device-select');
      [...deviceSelect.selectedOptions].forEach(option => {
        formData.append('device_mapping[]', option.value);
      });

      // ✅ Handle tv mapping
      const tvSelect = document.getElementById('tv-select');
      [...tvSelect.selectedOptions].forEach(option => {
        formData.append('tv_mapping[]', option.value);
      });

      // console.log(formData)
  
      try {
        const response = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_VENDOR, {
          method: 'POST',
          headers: {
            'X-CSRFToken': AppUtils.getCSRFToken()  // ✅ CSRF token only,
          },
          body: formData,
        });

        let result = {};
        try {
          result = await response.json();
        } catch (_) {
          result = {};
        }

        if (response.ok && result.success) {
          ModalService.showSuccess("Outlet Created Successfully", () => {
          // Callback on OK button click
          form.reset();
          window.location.href = WEB_ENDPOINTS.OUTLETS;
        });
        } else {
          const userFriendlyMessage = getFriendlyFieldLabels(result);
          const fallbackMessage =
            userFriendlyMessage ||
            result?.error ||
            result?.message ||
            `Failed to create outlet (HTTP ${response.status})`;
          ModalService.showError(fallbackMessage);
          console.error('Create outlet failed:', { status: response.status, result });
        }
      } catch (err) {
        const errMessage = err?.message || 'Unexpected error while creating outlet.';
        ModalService.showError(errMessage);
      }
    });
  });
