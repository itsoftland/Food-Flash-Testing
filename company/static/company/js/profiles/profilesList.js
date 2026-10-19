import { ConfirmModalService } from '../services/confirmModalService.js';
import { ImageLibraryService } from '../services/imageLibraryService.js';
import {
  setupSelectAllDays,
  setupTimeSlotHandlers,
  rebindTimeSlotValidation,
  validateAllTimeSlots,
  buildProfilePayload,
  populateProfileForm,
  parseApiErrorMessage,
} from './profileFormCommon.js';

let fetchWithAutoRefreshRef = null;
let API_ENDPOINTS_REF = null;
let ModalServiceRef = null;
let editingProfileId = null;
let editDetailRequestSeq = 0;
let editFormInitialized = false;

function isAdProfileEditEnabled() {
  return window.AD_PROFILE_EDIT_ENABLED === true;
}

function getEditProfileModalInstance() {
  const el = document.getElementById('editProfileModal');
  return el && typeof bootstrap !== 'undefined' && bootstrap.Modal
    ? bootstrap.Modal.getOrCreateInstance(el)
    : null;
}

document.addEventListener('DOMContentLoaded', async () => {

  if (!window.BASE) throw new Error('window.BASE is not defined');

  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);

  fetchWithAutoRefreshRef = authModule.fetchWithAutoRefresh;
  API_ENDPOINTS_REF = apiModule.API_ENDPOINTS;
  ModalServiceRef = modalModule.ModalService;

  if (isAdProfileEditEnabled()) {
    ImageLibraryService.init(fetchWithAutoRefreshRef, API_ENDPOINTS_REF);
    initEditProfileWorkflow();
  }

  await fetchAdProfiles(fetchWithAutoRefreshRef, API_ENDPOINTS_REF);
  $(function () {
    $('[data-toggle="tooltip"]').tooltip();
  });
});

function initEditProfileWorkflow() {
  setupSelectAllDays();
  setupTimeSlotHandlers(ModalServiceRef);

  document.getElementById('open-image-library-btn')?.addEventListener('click', () => {
    ImageLibraryService.open();
  });

  const editForm = document.getElementById('edit-profile-form');
  if (editForm && !editFormInitialized) {
    editFormInitialized = true;
    editForm.addEventListener('submit', handleEditFormSubmit);
  }

  const editModal = document.getElementById('editProfileModal');
  if (editModal && !editModal.dataset.lifecycleBound) {
    editModal.dataset.lifecycleBound = '1';
    editModal.addEventListener('hidden.bs.modal', () => {
      editDetailRequestSeq += 1;
      editingProfileId = null;
    });
  }
}

async function handleEditFormSubmit(e) {
  e.preventDefault();
  if (!editingProfileId) return;

  if (!validateAllTimeSlots(ModalServiceRef)) return;

  const payload = buildProfilePayload(ImageLibraryService.getSelectedImageIds());
  const url = API_ENDPOINTS_REF.UPDATE_AD_PROFILE.replace('{id}', editingProfileId);

  try {
    const res = await fetchWithAutoRefreshRef(url, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': AppUtils.getCSRFToken(),
      },
      body: JSON.stringify(payload),
    });
    const result = await res.json();

    if (res.ok) {
      ModalServiceRef.showSuccess('Profile Updated Successfully', () => {
        getEditProfileModalInstance()?.hide();
        fetchAdProfiles(fetchWithAutoRefreshRef, API_ENDPOINTS_REF);
      });
    } else {
      ModalServiceRef.showError(parseApiErrorMessage(result));
    }
  } catch (err) {
    console.error('Error updating profile:', err);
    ModalServiceRef.showError('Unexpected error while updating profile.');
  }
}

async function openEditProfileModal(profileId) {
  if (!isAdProfileEditEnabled()) return;

  const requestSeq = ++editDetailRequestSeq;
  editingProfileId = null;

  const url = API_ENDPOINTS_REF.GET_AD_PROFILE_DETAIL.replace('{id}', profileId);

  try {
    const res = await fetchWithAutoRefreshRef(url);
    const data = await res.json();

    if (requestSeq !== editDetailRequestSeq) {
      return;
    }

    if (!res.ok) {
      ModalServiceRef.showError(parseApiErrorMessage(data));
      return;
    }

    const profile = data.profile;
    if (!profile || profile.id == null) {
      ModalServiceRef.showError('Failed to load profile for editing.');
      return;
    }

    populateProfileForm(profile);

    const imageIds = (profile.images || []).map(img => img.id);
    ImageLibraryService.setSelectedImageIds(imageIds);
    const preview = document.getElementById('selected-images-preview');
    if (preview) {
      preview.innerHTML = '';
      (profile.images || []).forEach(img => {
        const thumb = document.createElement('img');
        thumb.src = img.image_url;
        thumb.className = 'preview-thumb';
        preview.appendChild(thumb);
      });
    }

    rebindTimeSlotValidation(ModalServiceRef);

    if (requestSeq !== editDetailRequestSeq) {
      return;
    }

    editingProfileId = String(profile.id);

    getEditProfileModalInstance()?.show();
    $('[data-toggle="tooltip"]').tooltip();
  } catch (err) {
    if (requestSeq !== editDetailRequestSeq) {
      return;
    }
    editingProfileId = null;
    console.error('Error loading profile for edit:', err);
    ModalServiceRef.showError('Failed to load profile for editing.');
  }
}

async function fetchAdProfiles(fetchWithAutoRefresh, API_ENDPOINTS) {
  try {
    const res = await fetchWithAutoRefresh(API_ENDPOINTS.GET_AD_PROFILES);
    const data = await res.json();
    const profiles = data.profiles || data.banners || data.ad_profiles || [];
    renderAdProfiles(profiles, fetchWithAutoRefresh, API_ENDPOINTS);
  } catch (err) {
    console.error('Error fetching advertisement profiles:', err);
  }
}

function renderAdProfiles(profiles, fetchWithAutoRefresh, API_ENDPOINTS) {
  const tbody = document.getElementById('ad-profile-table-body');
  tbody.innerHTML = '';

  profiles.forEach(profile => {
    const row = document.createElement('tr');

    const fullDays = profile.days_active || [];
    const dayMap = {
      Monday: 'Mon', Tuesday: 'Tue', Wednesday: 'Wed', Thursday: 'Thu',
      Friday: 'Fri', Saturday: 'Sat', Sunday: 'Sun',
    };
    const short = fullDays.map(d => dayMap[d] || d);
    const titleText = fullDays.join(', ');
    const days = fullDays.length > 0
      ? `<span class="badge-days-active" data-toggle="tooltip" title="${titleText}">${short.join(', ')}</span>`
      : `<span class="text-muted">No Days Set</span>`;
    const priorityLabels = {
      1: 'Top Priority',
      2: 'High Priority',
      3: 'Standard Priority',
      4: 'Low Priority',
      5: 'Backup Priority',
    };

    const dateStart = profile.date_start || '';
    const dateEnd = profile.date_end || '';
    row.innerHTML = `
      <td data-label="Name" class="profile-name">${profile.name}</td>
      <td data-label="Date Range" class="text-muted">
        ${
          dateStart && dateEnd
            ? `${dateStart} → ${dateEnd}`
            : dateStart
              ? `From ${dateStart}`
              : dateEnd
                ? `Until ${dateEnd}`
                : 'No Date Set'
        }
      </td>
      <td data-label="Days Active">${days}</td>
      <td data-label="Priority" class="text-center">
        <span class="badge-priority">${priorityLabels[profile.priority] || 'Unknown Priority'}</span>
      </td>
      <td data-label="Actions">
        <button class="icon-btn icon-view" title="View Images" data-images='${JSON.stringify(profile.images)}'>
          <i class="fa-regular fa-eye"></i>
        </button>
        ${
          isAdProfileEditEnabled()
            ? `<button class="icon-btn icon-edit" title="Edit Profile" data-id="${profile.id}">
          <i class="fas fa-edit"></i>
        </button>`
            : ''
        }

        <button class="icon-btn icon-delete" title="Delete Profile" data-id="${profile.id}">
          <i class="fas fa-trash"></i>
        </button>
      </td>
    `;

    tbody.appendChild(row);
  });

  attachActionListeners(fetchWithAutoRefresh, API_ENDPOINTS);
}

function attachActionListeners(fetchWithAutoRefresh, API_ENDPOINTS) {
  document.querySelectorAll('.icon-view').forEach(btn => {
    btn.addEventListener('click', () => {
      const images = JSON.parse(btn.dataset.images || '[]');
      const container = document.getElementById('modal-image-container');
      container.innerHTML = '';

      images.forEach(img => {
        const imgBox = document.createElement('div');
        imgBox.className = 'm-2';
        imgBox.innerHTML = `<img src="${img.image_url}" class="preview-image">`;
        container.appendChild(imgBox);
      });

      $('#imageModal').modal('show');
    });
  });

  if (isAdProfileEditEnabled()) {
    document.querySelectorAll('.icon-edit').forEach(btn => {
      btn.addEventListener('click', () => {
        const profileId = btn.dataset.id;
        openEditProfileModal(profileId);
      });
    });
  }

  document.querySelectorAll('.icon-delete').forEach(btn => {
    btn.addEventListener('click', async () => {
      const profileId = btn.dataset.id;
      const confirmed = await ConfirmModalService.show('Do you want to discard this Ad Profile?');
      if (!confirmed) return;
      try {
        await fetchWithAutoRefresh(`${API_ENDPOINTS.DELETE_AD_PROFILE}?ad_profile_id=${profileId}`, {
          method: 'DELETE',
        });
        await fetchAdProfiles(fetchWithAutoRefresh, API_ENDPOINTS);
      } catch (err) {
        console.error('Error deleting profile:', err);
        alert('Unexpected error while deleting profile.');
      }
    });
  });
}
