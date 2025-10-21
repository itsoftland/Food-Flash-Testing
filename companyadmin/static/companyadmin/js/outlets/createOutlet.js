import getFriendlyFieldLabels from '/food_flash/static/utils/js/formFieldLabelService.js';
import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';
import { ModalService } from '/food_flash/static/utils/js/services/modalService.js';
import { API_ENDPOINTS,WEB_ENDPOINTS } from '/food_flash/static/utils/js/apiEndpoints.js';

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('create-outlet-form');
  
    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const locationSelect = document.getElementById('location');
        const timezoneSelect = document.getElementById('timezone');
        const companySelect = document.getElementById('company');
       
        const selectedOption = locationSelect.options[locationSelect.selectedIndex];
        const selectedTimezone = timezoneSelect.value;
        
        const locationValue = selectedOption.value;  
        const locationKey = selectedOption.dataset.locationName;
        
        const formData = new FormData();
        formData.append('name', document.getElementById('name').value);
        formData.append('alias_name', document.getElementById('alias_name').value);
        formData.append('location', locationKey);     
        formData.append('location_id', locationValue);
        formData.append('place_id', document.getElementById('place_id').value || '');
        formData.append('tv_communication_mode', document.getElementById('tv_communication_mode').value || '');
        formData.append('business_day_start_hour', document.getElementById('business_day_start_hour').value || '');
        formData.append('timezone', selectedTimezone || '');

        const customer_id = companySelect.value; 
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

        try {
            const response = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_VENDOR, {
            method: 'POST',
            headers: {
                'X-CSRFToken': AppUtils.getCSRFToken() 
            },
            body: formData,
            });
  
        const result = await response.json();
  
        if (result.success) {
          ModalService.showSuccess("Outlet Created Successfully", () => {
          form.reset();
          window.location.href = WEB_ENDPOINTS.COMPANY_OUTLETS;
        });
        } else {
          const userFriendlyMessage = getFriendlyFieldLabels(result);
          ModalService.showError(userFriendlyMessage);
        }
        } catch (err) {
        ModalService.showError(err);
        console.error('Error creating outlet:', err);
        }
    });
});
