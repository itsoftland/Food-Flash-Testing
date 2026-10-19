import { ImageLibraryService } from '../services/imageLibraryService.js';
import {
  setupSelectAllDays,
  setupTimeSlotHandlers,
  validateAllTimeSlots,
  buildProfilePayload,
  parseApiErrorMessage,
} from './profileFormCommon.js';

document.addEventListener('DOMContentLoaded', async () => {

  if (!window.BASE) throw new Error('window.BASE is not defined');

  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const WEB_ENDPOINTS = apiModule.WEB_ENDPOINTS;
  const ModalService = modalModule.ModalService;

  ImageLibraryService.init(fetchWithAutoRefresh, API_ENDPOINTS);
  setupSelectAllDays();
  setupFormSubmitHandler(fetchWithAutoRefresh, API_ENDPOINTS, WEB_ENDPOINTS, ModalService);
  setupTimeSlotHandlers(ModalService);
  $(function () {
    $('[data-toggle="tooltip"]').tooltip();
  });
});

function setupFormSubmitHandler(fetchWithAutoRefresh, API_ENDPOINTS, WEB_ENDPOINTS, ModalService) {
  document.getElementById('create-profile-form').addEventListener('submit', async function (e) {
    e.preventDefault();

    const payload = buildProfilePayload(ImageLibraryService.getSelectedImageIds());

    if (!validateAllTimeSlots(ModalService)) return;

    try {
      const res = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_AD_PROFILE, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': AppUtils.getCSRFToken(),
        },
        body: JSON.stringify(payload),
      });

      const result = await res.json();

      if (res.ok) {
        ModalService.showSuccess('Profile Created Successfully', () => {
          this.reset();
          ImageLibraryService.clearSelection();
          window.location.href = WEB_ENDPOINTS.PROFILE_LIST;
        });
      } else {
        ModalService.showError(parseApiErrorMessage(result));
      }
    } catch (err) {
      ModalService.showError('Unexpected error while creating profile.');
    }
  });
}

document.getElementById('open-image-library-btn')?.addEventListener('click', () => {
  ImageLibraryService.open();
});
