import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  await initAssignProfileForm();
  $(function () {
  $('[data-toggle="tooltip"]').tooltip();
  });
});

// =================== ASSIGN PROFILE ===================

async function initAssignProfileForm() {
  try {
    // Fetch Ad Profiles
    const profilesRes = await fetchWithAutoRefresh('/company/api/get_ad_profiles/');
    const profilesData = await profilesRes.json();
    const profiles = profilesData.profiles || [];
    

    const profileSelect = document.getElementById('ad-profile-select');
    profileSelect.innerHTML = profiles.map(p => `<option value="${p.id}">${p.name}</option>`).join('');

    // Fetch Outlets
    const outletsRes = await fetchWithAutoRefresh('/company/api/get_vendors/');
    const outletsData = await outletsRes.json();
    const outlets = outletsData.vendors || [];
    console.log("outlet data",outlets)

    const outletSelect = document.getElementById('outlet-select');
    outletSelect.innerHTML = outlets.map(o => `<option value="${o.id}">${o.name}</option>`).join('');

    // Initialize Choices
    const profileChoices = new Choices(profileSelect, {
      removeItemButton: true,
      placeholderValue: 'Select profiles',
      classNames: {
        containerInner: 'choices-inner-foodflash',
        item: 'choices-item-foodflash',
      },

    });

    const outletChoices = new Choices(outletSelect, {
      removeItemButton: true,
      placeholderValue: 'Select outlets',
      classNames: {
        containerInner: 'choices-inner-foodflash',
        item: 'choices-item-foodflash',
      },
      searchEnabled: true,
    });

    // Submit Handler
    document.getElementById('assign-profile-form')?.addEventListener('submit', async function (e) {
      e.preventDefault();

      const profileIds = profileChoices.getValue(true); // Array
      const outletIds = outletChoices.getValue(true);   // Array

      if (!profileIds.length || !outletIds.length) {
        showErrorModal("Please select at least one profile and one outlet.");
        return;
      }

      try {
        console.log("request body",JSON.stringify({ 
          profile_ids: profileIds, 
          vendor_ids: outletIds
        }));
        const res = await fetchWithAutoRefresh('/company/api/assign_ad_profile/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            profile_ids: profileIds, 
            vendor_ids: outletIds 
          })
        });

        const result = await res.json();
        console.log(result)
        if (res.ok) {
          const msg = `${result.summary}\n${result.duplicates_skipped} duplicate mappings were skipped.`;
          ModalService.showSuccess(msg, () => {
            profileChoices.clearStore();
            outletChoices.clearStore();
            // Callback on OK button click
            window.location.href = "/company/mapped_list/";
          });
        } else {
            ModalService.showError(result.message || "Assignment failed.");
        }
      } catch (err) {
        ModalService.showError("Unexpected error occurred during assignment.");
      }
    });

  } catch (err) {
    ModalService.showError("Failed to load data for assigning profiles.");
  }
}