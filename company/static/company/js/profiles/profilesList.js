import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ConfirmModalService } from '../services/confirmModalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  await fetchAdProfiles();
  $(function () {
  $('[data-toggle="tooltip"]').tooltip();
  });
});

// =================== FETCH PROFILES ===================

async function fetchAdProfiles() {
  try {
    const res = await fetchWithAutoRefresh('/company/api/get_ad_profiles/');
    const data = await res.json();
    const profiles = data.profiles || data.banners || data.ad_profiles || [];
    renderAdProfiles(profiles);
  } catch (err) {
    console.error('Error fetching advertisement profiles:', err);
  }
}
function renderAdProfiles(profiles) {
  const tbody = document.getElementById("ad-profile-table-body");
  tbody.innerHTML = "";

  profiles.forEach(profile => {
    const row = document.createElement("tr");

    // === Days Active (Compact with Tooltip) ===
    const fullDays = profile.days_active || [];
    const dayMap = {
      Monday: 'Mon', Tuesday: 'Tue', Wednesday: 'Wed', Thursday: 'Thu',
      Friday: 'Fri', Saturday: 'Sat', Sunday: 'Sun'
    };
    const short = fullDays.map(d => dayMap[d] || d);
    const titleText = fullDays.join(', ');
    const days = fullDays.length > 0
      ? `<span class="badge-days-active" data-toggle="tooltip" title="${titleText}">${short.join(', ')}</span>`
      : `<span class="text-muted">No Days Set</span>`;
    const priorityLabels = {
      1: "Top Priority",
      2: "High Priority",
      3: "Standard Priority",
      4: "Low Priority",
      5: "Backup Priority"
    };

    const dateStart = profile.date_start || "";
    const dateEnd = profile.date_end || "";
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
                : "No Date Set"
        }
      </td>
      <td data-label="Days Active">${days}</td>
      <td data-label="Priority" class="text-center">
        <span class="badge-priority">${priorityLabels[profile.priority] || "Unknown Priority"}</span>
      </td>
      <td data-label="Actions">
        <button class="icon-btn icon-view" title="View Images" data-images='${JSON.stringify(profile.images)}'>
          <i class="fa-regular fa-eye"></i>
        </button>

        <button class="icon-btn icon-edit" title="Edit Profile" data-id="${profile.id}">
          <i class="fas fa-edit"></i>
        </button>

        <button class="icon-btn icon-delete" title="Delete Profile" data-id="${profile.id}">
          <i class="fas fa-trash"></i>
        </button>
      </td>
    `;

    tbody.appendChild(row);
  });

  attachActionListeners();

}

// =================== ACTIONS ===================

function attachActionListeners() {
  document.querySelectorAll('.icon-view').forEach(btn => {
    btn.addEventListener('click', () => {
      const images = JSON.parse(btn.dataset.images || '[]');
      const container = document.getElementById('modal-image-container');
      console.log(container)
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

  document.querySelectorAll('.icon-edit').forEach(btn => {
    btn.addEventListener('click', () => {
      const profileId = btn.dataset.id;
      console.log('Edit profile:', profileId);
      // TODO: Open modal and load data for editing
    });
  });

  document.querySelectorAll('.icon-delete').forEach(btn => {
    btn.addEventListener('click', async () => {
      const profileId = btn.dataset.id;
      console.log('Delete profile:', profileId);
      const confirmed = await ConfirmModalService.show("Do you want to discard this Ad Profile?");
      if (!confirmed) return;
      try {
      const res = await fetchWithAutoRefresh(`/company/api/delete_ad_profile/?ad_profile_id=${profileId}`, {
        method: 'DELETE',
      });
      await fetchAdProfiles();
      } 
      catch (err) {
        console.error('Error submitting form:', err);
        alert('Unexpected error while creating profile.');
      }
    });
  });
}
