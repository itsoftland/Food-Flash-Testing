import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ConfirmModalService } from '../services/confirmModalService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  await loadAssignedProfiles();
});

// =================== INIT HELPERS ===================

async function loadAssignedProfiles() {
    const accordion = document.getElementById('outletAccordion');
    accordion.innerHTML = `<p class="text-muted text-center">Loading...</p>`;

    try {

        const response = await fetchWithAutoRefresh('/company/api/assigned_profiles/');
        const data = await response.json();

        if (!response.ok) throw new Error();
        const outlets = data.profiles;

        if (!outlets.length) {
        console.log("success");
        accordion.innerHTML = `<p class="text-muted text-center">No profiles assigned yet.</p>`;
        return;
        }

        accordion.innerHTML = '';
        outlets.forEach(outlet => {
            const assignedChips = outlet.assigned_profiles.map(profile => `
            <span class="profile-chip" onclick="window.location.href='/company/profile_list/'">
                ${profile.name}
                <i class="fas fa-times remove-icon" data-vendor="${outlet.outlet_id}" data-profile="${profile.id}"></i>
            </span>
            `).join('');
            accordion.innerHTML += `
            <div class="card mb-2 border-0 shadow-sm">
                <div class="card-header bg-light-gray d-flex justify-content-between align-items-center"
                    data-bs-toggle="collapse"
                    data-bs-target="#collapse${outlet.outlet_id}"
                    style="cursor: pointer;">
                
                    <!-- Outlet Name (left-aligned) -->
                    <div class="d-flex align-items-center gap-2">
                        <i class="fas fa-store text-muted"></i>
                        <span class="fw-semibold text-dark">${outlet.outlet_name}</span>
                    </div>

                    <!-- Profile Count + Dropdown (right-aligned) -->
                    <div class="d-flex align-items-center gap-2 ms-auto" style="margin-left: auto;">
                        <span class="badge bg-secondary bg-opacity-25 text-dark">
                            ${outlet.assigned_count} ${outlet.assigned_count === 1 ? 'Profile' : 'Profiles'}
                        </span>
                        <i class="fas fa-chevron-down text-muted dropdown-chevron chevron-${outlet.outlet_id}"></i>
                    </div>
                </div>

                <div id="collapse${outlet.outlet_id}" class="collapse" data-bs-parent="#outletAccordion">
                    <div class="card-body">
                        <label class="form-label fw-bold text-secondary">Assigned Profiles:</label>
                        <div class="profile-chip-container mb-3">
                            ${assignedChips || '<span class="text-muted">No Profiles Assigned</span>'}
                        </div>

                        <button class="btn btn-sm btn-outline-primary assign-profile" data-vendor="${outlet.outlet_id}",)">
                            + Add Profile
                        </button>
                    </div>
                </div>
            </div>
            `;
        },
        setTimeout(() => {
        document.querySelectorAll('[id^="collapse"]').forEach(collapseEl => {
            const outletId = collapseEl.id.replace('collapse', '');
            const chevron = document.querySelector(`.chevron-${outletId}`);

            collapseEl.addEventListener('show.bs.collapse', () => {
            chevron?.classList.add('rotate');
            });

            collapseEl.addEventListener('hide.bs.collapse', () => {
            chevron?.classList.remove('rotate');
            });
        });
        }, 50))
        } catch (err) {
        accordion.innerHTML = `<p class="text-danger text-center">Error loading data.</p>`;
        }
        await attachActionListeners();
    }
async function attachActionListeners() {
    document.querySelectorAll('.remove-icon').forEach(icon => {
        icon.addEventListener('click', async (e) => {
        e.stopPropagation();
        const confirmed = await ConfirmModalService.show("Do you want to Unmap Profile from Outlet?");
        if (!confirmed) return;
        const vendorId = icon.dataset.vendor;
        const profileId = icon.dataset.profile;
        await unmapProfile(vendorId, profileId);
        });
    });
    document.querySelectorAll('.assign-profile').forEach(button => {
        button.addEventListener('click', async (e) => {
            e.stopPropagation();
            const vendorId = button.dataset.vendor;
            console.log(vendorId);
            await openAssignModal(vendorId);
        });
    });
    }

async function unmapProfile(vendorId, profileId) {
    try {
        const res = await fetchWithAutoRefresh(
        `/company/api/unmap_profile/${vendorId}/${profileId}/`,
        { method: 'DELETE' }
        );

        if (res.ok) {
        ModalService.showSuccess("Profile unmapped successfully", async () => {
            await loadAssignedProfiles();
        });
        } else {
        const data = await res.json();
        ModalService.showError(data.error || 'Failed to unmap profile');
        }
    } catch (err) {
        ModalService.showError('Server error while unmapping profile');
    }
}

async function openAssignModal(vendorId) {
  const modalBodyHTML = `
    <form id="assign-profile-form" class="px-4 py-3 mx-auto" style="max-width: 900px;">
      <h4 class="text-center mb-4">Map Profiles to Outlets</h4>

      <div class="form-group col-md-12 col-12">
        <label for="ad-profile-select">Advertisement Profiles</label>
        <div class="choices-scroll-wrapper">
          <select id="ad-profile-select" name="profiles[]" multiple class="form-select">
            <option disabled>Loading...</option>
          </select>
        </div>
      </div>

      <div class="text-center mt-4">
        <button type="submit" class="btn btn-golden px-4 py-2 shadow-sm">
          <i class="fas fa-link mr-2"></i> Assign Profiles
        </button>
      </div>
    </form>
  `;

  ModalService.showCustom({
    title: 'Assign Profiles',
    body: modalBodyHTML,
    onShown: async () => {
      const profileSelect = document.getElementById('ad-profile-select');
      try {
        const response = await fetchWithAutoRefresh(`/company/api/available_profiles/${vendorId}/`);
        const data = await response.json();
        const profiles = data.profiles || [];

        if (!profiles.length) {
          profileSelect.innerHTML = '<option disabled>No profiles available</option>';
        } else {
          profileSelect.innerHTML = profiles.map(p => `<option value="${p.id}">${p.name}</option>`).join('');
        }
      } catch (error) {
        profileSelect.innerHTML = '<option disabled>Error loading profiles</option>';
      }
    // Initialize Choices
    const profileChoices = new Choices(profileSelect, {
    removeItemButton: true,
    placeholderValue: 'Select profiles',
    classNames: {
        containerInner: 'choices-inner-foodflash',
        item: 'choices-item-foodflash',
    },

    });

      // Form submission
      document.getElementById('assign-profile-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const profileIds = profileChoices.getValue(true);

      if (!profileIds.length || !vendorId.length) {
        ModalService.showError("Please select at least one profile and one outlet.");
        return;
      }

      try {
        const requestBody = JSON.stringify({ 
          profile_ids: profileIds, 
          vendor_ids: [vendorId]
        });

        console.log("Request Body:", requestBody);

        const res = await fetchWithAutoRefresh('/company/api/assign_ad_profile/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: requestBody
        });

        const result = await res.json();
        console.log(result);

        // Get current modal instance (Assign Modal)
        const modalElement = document.querySelector('.modal.show');
        const modalInstance = bootstrap.Modal.getInstance(modalElement);

        if (res.ok) {
          const msg = `${result.summary}\n${result.duplicates_skipped} duplicate mappings were skipped.`;
          
          // Close Assign modal first
          modalInstance.hide();

          // Show success modal after a short delay
          setTimeout(() => {
            ModalService.showSuccess(msg, () => {
              profileChoices.clearStore();
              window.location.href = "/company/mapped_list/";
            });
          }, 300);

        } else {
          // Handle API errors
          let msg = "Something went wrong.";

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

          // Close Assign modal before showing error
          modalInstance.hide();

          // Show error modal, then reopen Assign modal
          setTimeout(() => {
            ModalService.showError(msg, () => {
              openAssignModal(vendorId);
            });
          }, 300);
        }

      } catch (err) {
        const modalElement = document.querySelector('.modal.show');
        const modalInstance = bootstrap.Modal.getInstance(modalElement);
        if (modalInstance) modalInstance.hide();

        setTimeout(() => {
          ModalService.showError("Unexpected error occurred during assignment.", () => {
            openAssignModal(vendorId);
          });
        }, 300);
      }
    });

    }
  });
}

