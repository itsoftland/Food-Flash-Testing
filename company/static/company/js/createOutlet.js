import getFriendlyFieldLabels from '/static/utils/js/formFieldLabelService.js';
import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';

document.addEventListener('DOMContentLoaded', function () {
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

      // You can replace this with dynamic customer_id if needed
      const customer_id =AppUtils.getCustomerId('customer_id');
      // const customer_id = localStorage.getItem('customerId');
      console.log("customerId",customer_id)
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

      console.log(formData)
  
      try {
        const response = await fetchWithAutoRefresh('/company/api/create_vendor/', {
          method: 'POST',
          headers: {
            'X-CSRFToken': AppUtils.getCSRFToken()  // ✅ CSRF token only,
          },
          body: formData,
        });
  
        const result = await response.json();
  
        if (result.success) {
          ModalService.showSuccess("Outlet Created Successfully", () => {
          // Callback on OK button click
          form.reset();
          window.location.href = "/company/outlets/";
        });
        } else {
          const userFriendlyMessage = getFriendlyFieldLabels(result);
          ModalService.showError(userFriendlyMessage);
        }
      } catch (err) {
        ModalService.showError(err);
      }
    });
  });
  