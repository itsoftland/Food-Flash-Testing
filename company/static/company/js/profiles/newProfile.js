import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ImageLibraryService } from '../services/imageLibraryService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  ImageLibraryService.init();
  setupFormSubmitHandler();
  $(function () {
  $('[data-toggle="tooltip"]').tooltip();
  });
});

// =================== CREATE PROFILE ===================

document.getElementById('select-all-days').addEventListener('change', function () {
  const isChecked = this.checked;
  document.querySelectorAll('.day-checkbox').forEach(cb => {
    cb.checked = isChecked;
  });
});

function setupFormSubmitHandler() {
  document.getElementById('create-profile-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    const fieldLabelMap = {
      name: "Profile Name",
      date_start: "Start Date",
      date_end: "End Date",
      days_active: "Days Active",
      priority: "Priority",
      image_ids: "Token Number",
    };
    const payload = {
      name: document.getElementById('profile-name').value,
      date_start: document.getElementById('date-start').value || null,
      date_end: document.getElementById('date-end').value || null,
      days_active: Array.from(document.querySelectorAll('.day-checkbox:checked')).map(cb => cb.value),
      priority: parseInt(document.getElementById('priority').value),
      image_ids: ImageLibraryService.getSelectedImageIds() // Use the modal selection
    };

    try {
    const res = await fetchWithAutoRefresh('/company/api/create_ad_profile/', {
      method: 'POST',
      headers: {
            'X-CSRFToken': AppUtils.getCSRFToken()  // ✅ CSRF token only,
      },
      body: JSON.stringify(payload)
    });

    const result = await res.json();

    if (res.ok) {
      ModalService.showSuccess("Profile Created Successfully", () => {
        this.reset();
        document.getElementById('selected-images-preview').innerHTML = '';
        window.location.href = "/company/profile_list/";
        });
    } else {
      // Extract and show error message
      let msg = "Something went wrong.";

      if (result?.details) {
        const errorDetails = result.details;

        if (Array.isArray(errorDetails.non_field_errors)) {
          msg = errorDetails.non_field_errors.join('\n');
        } else {
          msg = Object.entries(errorDetails).map(
            ([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
          ).join('\n');
        }

      } else if (result?.error) {
        msg = result.error;
      } else if (result?.message) {
        msg = result.message;
      }
      ModalService.showError(msg);
    }
  } catch (err) {
    ModalService.showError("Unexpected error while creating profile.");
  }
  });
}
document.getElementById('open-image-library-btn')?.addEventListener('click', () => {
  ImageLibraryService.open();
});