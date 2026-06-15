import { ConfirmModalService } from './services/confirmModalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  if (!window.BASE) throw new Error('window.BASE is not defined');

  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;

  $(function () {
    $('[data-toggle="tooltip"]').tooltip();
  });

  const tableBody = document.getElementById('utility-user-devices-table-body');
  const filterDropdown = document.getElementById('deviceFilter');
  const showReleaseDevice = (window.PROJECT_NAME || '').trim().toLowerCase() === 'dine_flash_buffet';

  const RELEASE_DEVICE_CONFIRM = {
    title: 'Release Device',
    message: 'This will remove device ownership from the current outlet/customer.<br><br>The device will need to be registered again before use.<br><br>Continue?',
    confirmButtonText: 'Release Device',
    cancelButtonText: 'Cancel',
  };

  loadDevices('all');

  filterDropdown.addEventListener('change', (e) => {
    loadDevices(e.target.value);
  });

  async function loadDevices(filter = 'all') {
    try {
      let url = API_ENDPOINTS.GET_UTILITY_USER_DEVICES;
      if (filter !== 'all') {
        url += `?filter=${filter}`;
      }

      const res = await fetchWithAutoRefresh(url);
      const data = await res.json();
      const utilityDevices = data.devices;

      tableBody.innerHTML = '';

      if (!utilityDevices || utilityDevices.length === 0) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="6" class="text-center text-muted">No devices found.</td>
          </tr>
        `;
        return;
      }

      utilityDevices.forEach((device, index) => {
        const id = index + 1;
        const isMapped = !!device.user_profile;
        const utilityUserName = isMapped ? device.user_profile.name : 'Unmapped';
        const createdTime = new Date(device.created_at).toLocaleString();

        const iconClass = isMapped ? 'fa-link-slash' : 'fa-link';
        const iconTitle = isMapped ? 'Unlink Device' : 'Link Device';
        const userClass = isMapped ? 'name' : 'text-muted';
        const releaseButton = showReleaseDevice ? `
                <button class="icon-btn icon-release-device"
                        data-toggle="tooltip"
                        title="Release Device"
                        data-id="${device.id}"
                        data-mac_address="${device.mac_address}">
                  <i class="fa-solid fa-mobile-screen-button"></i>
                </button>` : '';

        const row = `
          <tr>
              <td class="text-muted text-center" data-label="ID">${id}</td>
              <td class="name" data-label="MAC Address">${device.mac_address}</td>
              <td class="${userClass}" data-label="Utility User">${utilityUserName}</td>
              <td class="text-muted" data-label="Created Time">${createdTime}</td>
              <td class="text-center" data-label="Actions">
                <button class="icon-btn icon-link-toggle ${isMapped ? 'linked' : 'unlinked'}"
                        data-toggle="tooltip"
                        title="${iconTitle}"
                        data-id="${device.id}"
                        data-mac_address="${device.mac_address}"
                        data-utility_user_name="${utilityUserName}"
                        data-mapped="${isMapped}">
                  <i class="fa-solid ${iconClass}"></i>
                </button>
                ${releaseButton}
              </td>
          </tr>
        `;

        tableBody.insertAdjacentHTML('beforeend', row);
      });

      $('[data-toggle="tooltip"]').tooltip('dispose').tooltip();
      attachActionListeners();
      if (showReleaseDevice) {
        attachReleaseListeners();
      }
    } catch (error) {
      console.error('Error loading utility user devices:', error);
    }
  }

  function attachActionListeners() {
    document.querySelectorAll('.icon-link-toggle').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const deviceId = btn.dataset.id;
        const macAddress = btn.dataset.mac_address;
        const utilityUserName = btn.dataset.utility_user_name;
        const isMapped = btn.dataset.mapped === 'true';

        if (isMapped) {
          const confirmed = await ConfirmModalService.show(
            `Are you sure you want to unlink device ${macAddress} from ${utilityUserName}?`
          );
          if (!confirmed) return;

          try {
            const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.UNMAP_UTILITY_USER_DEVICES}${deviceId}/`, {
              method: 'POST',
            });

            if (!res.ok) {
              const err = await res.json();
              ModalService.showError(`Error: ${err.error || 'Unable to unlink device.'}`);
              return;
            }

            ModalService.showSuccess(`Device #${macAddress} unlinked successfully.`, () => {
              loadDevices(filterDropdown.value);
            });
          } catch (err) {
            console.error('Error unlinking utility user device:', err);
            ModalService.showError('Unexpected error occurred while unlinking device.');
          }
        } else {
          openMapDeviceModal(deviceId, macAddress);
        }
      });
    });
  }

  function attachReleaseListeners() {
    document.querySelectorAll('.icon-release-device').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const deviceId = btn.dataset.id;
        const macAddress = btn.dataset.mac_address;

        const confirmed = await ConfirmModalService.show(RELEASE_DEVICE_CONFIRM);
        if (!confirmed) return;

        try {
          const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.RELEASE_ANDROID_APK}${deviceId}/`, {
            method: 'POST',
          });

          if (!res.ok) {
            const err = await res.json();
            ModalService.showError(`Error: ${err.error || 'Unable to release device.'}`);
            return;
          }

          ModalService.showSuccess(`Device #${macAddress} released successfully.`, () => {
            loadDevices(filterDropdown.value);
          });
        } catch (err) {
          console.error('Error releasing utility user device:', err);
          ModalService.showError('Unexpected error occurred while releasing device.');
        }
      });
    });
  }

  async function openMapDeviceModal(deviceId, macAddress) {
    const modalBodyHTML = `
      <form id="map-device-form" class="px-4 py-3 mx-auto" style="max-width: 600px;">
        <div class="form-group col-md-12 col-12">
          <label for="utility-user-select">Choose Utility User</label>
          <select id="utility-user-select" name="utility_user_id" class="form-control">
            <option disabled selected>Loading utility users...</option>
          </select>
        </div>

        <div class="text-center mt-4">
          <button type="submit" class="btn btn-golden px-4 py-2 shadow-sm">
            <i class="fas fa-link mr-2"></i> Link Device
          </button>
        </div>
      </form>
    `;

    ModalService.showCustom({
      title: 'Link Device to Utility User',
      body: modalBodyHTML,
      onShown: async () => {
        const utilityUserSelect = document.getElementById('utility-user-select');
        try {
          const res = await fetchWithAutoRefresh(API_ENDPOINTS.GET_USERS);
          const data = await res.json();
          const users = data.users || [];
          const utilityUsers = users.filter((user) => Array.isArray(user.roles) && user.roles.includes('utility_user'));

          if (!utilityUsers.length) {
            utilityUserSelect.innerHTML = '<option disabled>No utility users available</option>';
          } else {
            utilityUserSelect.innerHTML = utilityUsers
              .map((user) => `<option value="${user.id}">${user.name}</option>`)
              .join('');
          }
        } catch (err) {
          utilityUserSelect.innerHTML = '<option disabled>Error loading utility users</option>';
        }

        document.getElementById('map-device-form').addEventListener('submit', async (e) => {
          e.preventDefault();

          const utilityUserId = utilityUserSelect.value;
          if (!utilityUserId) {
            ModalService.showError('Please select a utility user.');
            return;
          }

          try {
            const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.MAP_UTILITY_USER_DEVICES}${deviceId}/`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ utility_user_id: utilityUserId }),
            });

            const result = await res.json();

            const modalElement = document.querySelector('.modal.show');
            const modalInstance = bootstrap.Modal.getInstance(modalElement);
            if (modalInstance) modalInstance.hide();

            if (res.ok) {
              setTimeout(() => {
                ModalService.showSuccess(`Device #${macAddress} linked to selected utility user.`, () => {
                  location.reload();
                });
              }, 300);
            } else {
              const msg = result?.error || result?.message || 'Unable to map device.';
              setTimeout(() => {
                ModalService.showError(msg, () => openMapDeviceModal(deviceId, macAddress));
              }, 300);
            }
          } catch (err) {
            const modalElement = document.querySelector('.modal.show');
            const modalInstance = bootstrap.Modal.getInstance(modalElement);
            if (modalInstance) modalInstance.hide();

            setTimeout(() => {
              ModalService.showError('Unexpected error occurred during mapping.', () => {
                openMapDeviceModal(deviceId, macAddress);
              });
            }, 300);
          }
        });
      }
    });
  }
});
