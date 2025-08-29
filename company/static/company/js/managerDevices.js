import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { API_ENDPOINTS } from '/static/utils/js/apiEndpoints.js';
import { ConfirmModalService } from './services/confirmModalService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';

document.addEventListener('DOMContentLoaded', async () => {
  $(function () {
    $('[data-toggle="tooltip"]').tooltip();
  });

  const tableBody = document.getElementById('manager-devices-table-body');
  const filterDropdown = document.getElementById('deviceFilter');

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
          </td>
      </tr>
      `;

      tableBody.insertAdjacentHTML('beforeend', row);
    });

    $('[data-toggle="tooltip"]').tooltip('dispose').tooltip();

    attachActionListeners(); // Rebind link/unlink handlers
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
            const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.UNMAP_ANDROID_TVS}${deviceId}/`, {
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

  async function openMapDeviceModal(deviceId, macAddress) {
    const modalBodyHTML = `
      <form id="map-device-form" class="px-4 py-3 mx-auto" style="max-width: 600px;">
        <div class="form-group col-md-12 col-12">
          <label for="vendor-select">Select Outlet</label>
          <select id="vendor-select" name="vendor_id" class="form-control">
            <option disabled selected>Loading outlets...</option>
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
      title: 'Link Device to Outlet',
      body: modalBodyHTML,
      onShown: async () => {
        const vendorSelect = document.getElementById('vendor-select');
        try {
          const res = await fetchWithAutoRefresh('/company/api/get_vendors/');
          const data = await res.json();
          const vendors = data.vendors || [];

          if (!vendors.length) {
            vendorSelect.innerHTML = `<option disabled>No outlets available</option>`;
          } else {
            vendorSelect.innerHTML = vendors
              .map(v => `<option value="${v.id}">${v.name} (${v.location})</option>`)
              .join('');
          }
        } catch (err) {
          vendorSelect.innerHTML = `<option disabled>Error loading outlets</option>`;
        }

        // Handle form submission
        document.getElementById('map-device-form').addEventListener('submit', async (e) => {
          e.preventDefault();

          const vendorId = vendorSelect.value;
          if (!vendorId) {
            ModalService.showError('Please select an outlet.');
            return;
          }

          try {
            const res = await fetchWithAutoRefresh(`${API_ENDPOINTS.MAP_ANDROID_TVS}${deviceId}/`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ vendor_id: vendorId }),
            });

            const result = await res.json();

            const modalElement = document.querySelector('.modal.show');
            const modalInstance = bootstrap.Modal.getInstance(modalElement);
            if (modalInstance) modalInstance.hide();

            if (res.ok) {
              setTimeout(() => {
                ModalService.showSuccess(`Device #${macAddress} linked to selected outlet.`, () => {
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
