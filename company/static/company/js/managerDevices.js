import { ConfirmModalService } from './services/confirmModalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;

  $(function () {
    $('[data-toggle="tooltip"]').tooltip();
  });

  const tableBody = document.getElementById('manager-devices-table-body');
  const filterDropdown = document.getElementById('deviceFilter');
  const showReleaseDevice = (window.PROJECT_NAME || '').trim().toLowerCase() === 'dine_flash';

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
    let url = API_ENDPOINTS.GET_MANAGER_DEVICES;
    if (filter !== 'all') {
      url += `?filter=${filter}`;
    }

    const res = await fetchWithAutoRefresh(url);
    const data = await res.json();
    const manager_devices = data.devices;

    tableBody.innerHTML = '';

    if (!manager_devices || manager_devices.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-muted">No devices found.</td>
        </tr>
      `;
      return;
    }

    manager_devices.forEach((device, index) => {
      const Id = index + 1;
      const isMapped = !!device.user_profile;
      const managerName = isMapped ? device.user_profile.name : 'Unmapped';
      const createdTime = new Date(device.created_at).toLocaleString();

      const iconClass = isMapped ? 'fa-link-slash' : 'fa-link';
      const iconTitle = isMapped ? 'Unlink Device' : 'Link Device';
      const outletClass = isMapped ? 'name' : 'text-muted';
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
            <td class="text-muted text-center" data-label="ID">${Id}</td>
            <td class="name" data-label="MAC Address">${device.mac_address}</td>
            <td class="${outletClass}" data-label="Manager Name">${managerName}</td>
            <td class="text-muted" data-label="Created Time">${createdTime}</td>
            <td class="text-center" data-label="Actions">
              <button class="icon-btn icon-link-toggle ${isMapped ? 'linked' : 'unlinked'}"
                      data-toggle="tooltip"
                      title="${iconTitle}"
                      data-id="${device.id}"
                      data-mac_address="${device.mac_address}"
                      data-manager_name="${managerName}"
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

    attachActionListeners(); // Rebind link/unlink handlers
    if (showReleaseDevice) {
      attachReleaseListeners();
    }
  } catch (error) {
    console.error('Error loading devices:', error);
  }
}

function attachActionListeners() {
    document.querySelectorAll('.icon-link-toggle').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const deviceId = btn.dataset.id;
        const macAddress = btn.dataset.mac_address;
        const managerName = btn.dataset.manager_name; // updated
        const isMapped = btn.dataset.mapped === 'true';

        if (isMapped) {
          const confirmed = await ConfirmModalService.show(
            `Are you sure you want to unlink device ${macAddress} from ${managerName}?`
          );
          if (!confirmed) return;

          try {
            const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.UNMAP_MANAGER_DEVICES}${deviceId}/`, {
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
            console.error('Error unlinking device:', err);
            ModalService.showError(`Unexpected error occurred while unlinking device.`);
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
          console.error('Error releasing device:', err);
          ModalService.showError('Unexpected error occurred while releasing device.');
        }
      });
    });
  }

  async function openMapDeviceModal(deviceId, macAddress) {
    const modalBodyHTML = `
      <form id="map-device-form" class="px-4 py-3 mx-auto" style="max-width: 600px;">
        <div class="form-group col-md-12 col-12">
          <label for="manager-select">Choose Manager</label>
          <select id="manager-select" name="manager_id" class="form-control">
            <option disabled selected>Loading managers...</option>
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
      title: 'Link Device to Manager',
      body: modalBodyHTML,
      onShown: async () => {
        const managerSelect = document.getElementById('manager-select');
        try {
          const res = await fetchWithAutoRefresh(API_ENDPOINTS.GET_USERS);
          const data = await res.json();
          const managers = data.users || [];

          if (!managers.length) {
            managerSelect.innerHTML = `<option disabled>No managers available</option>`;
          } else {
            managerSelect.innerHTML = managers
              .map(v => `<option value="${v.id}">${v.name}</option>`)
              .join('');
          }
        } catch (err) {
          managerSelect.innerHTML = `<option disabled>Error loading managers</option>`;
        }

        // Handle form submission
        document.getElementById('map-device-form').addEventListener('submit', async (e) => {
          e.preventDefault();

          const managerId = managerSelect.value;
          if (!managerId) {
            ModalService.showError('Please select a manager.');
            return;
          }

          try {
            const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.MAP_MANAGER_DEVICES}${deviceId}/`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ manager_id: managerId }),
            });

            const result = await res.json();

            const modalElement = document.querySelector('.modal.show');
            const modalInstance = bootstrap.Modal.getInstance(modalElement);
            if (modalInstance) modalInstance.hide();

            if (res.ok) {
              setTimeout(() => {
                ModalService.showSuccess(`Device #${macAddress} linked to selected manager.`, () => {
                  location.reload(); // Or call loadDevices()
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
              ModalService.showError("Unexpected error occurred during mapping.", () => {
                openMapDeviceModal(deviceId, macAddress);
              });
            }, 300);
          }
        });
      }
    });
  }
});
