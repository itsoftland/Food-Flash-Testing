import { ConfirmModalService } from './services/confirmModalService.js';
import { openAssignConfigModal } from './androidtvs/tvConfigAssignment.js';

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  return div.innerHTML;
}

function normalizeMacAddress(mac) {
  return String(mac || '').replace(/[^a-fA-F0-9]/g, '').toLowerCase();
}

/** Dine Flash only: hide configuration column (mapping is on TV Configuration page). */
function isAndroidTvsHideConfigurationColumn() {
  const el = document.getElementById('android-tvs-page-flags');
  if (el) {
    try {
      const parsed = JSON.parse(el.textContent);
      if (parsed && typeof parsed.hideConfigurationColumn === 'boolean') {
        return parsed.hideConfigurationColumn;
      }
    } catch {
      /* ignore */
    }
  }
  const raw = window.PROJECT_NAME != null ? String(window.PROJECT_NAME) : '';
  return raw.trim().toLowerCase() === 'dine_flash';
}

document.addEventListener('DOMContentLoaded', async () => {
  // Validate BASE exists
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

  const tableBody = document.getElementById('android-tvs-table-body');
  const filterDropdown = document.getElementById('deviceFilter');
  const macSuffixSearchInput = document.getElementById('macSuffixSearch');
  let cachedDevices = [];
  let currentDeviceFilter = 'all';

  loadDevices(currentDeviceFilter);

  filterDropdown.addEventListener('change', (e) => {
    currentDeviceFilter = e.target.value;
    loadDevices(currentDeviceFilter);
  });

  if (macSuffixSearchInput) {
    macSuffixSearchInput.addEventListener('input', () => {
      renderDevices(cachedDevices);
    });
  }

  function getMacSuffixSearchTerm() {
    if (!macSuffixSearchInput) return '';
    return String(macSuffixSearchInput.value || '')
      .replace(/[^a-fA-F0-9]/g, '')
      .toLowerCase()
      .slice(0, 3);
  }

  function renderDevices(android_tvs = []) {
    const hideConfigCol = isAndroidTvsHideConfigurationColumn();
    const emptyColspan = hideConfigCol ? 5 : 6;
    const macSuffixTerm = getMacSuffixSearchTerm();
    const shouldApplyMacFilter = hideConfigCol && macSuffixTerm.length >= 2;

    const visibleDevices = shouldApplyMacFilter
      ? android_tvs.filter((device) => normalizeMacAddress(device.mac_address).endsWith(macSuffixTerm))
      : android_tvs;

    tableBody.innerHTML = '';

    if (visibleDevices.length === 0) {
      const emptyMessage = shouldApplyMacFilter
        ? 'No devices match that MAC suffix.'
        : 'No devices found.';
      tableBody.innerHTML = `
          <tr>
            <td colspan="${emptyColspan}" class="text-center text-muted">${emptyMessage}</td>
          </tr>
        `;
      return;
    }

    visibleDevices.forEach((device, index) => {
      const Id = index + 1;
      const isMapped = !!device.vendor;
      const outletName = isMapped ? device.vendor.name : 'Unmapped';
      const createdTime = new Date(device.created_at).toLocaleString();

      const iconClass = isMapped ? 'fa-link-slash' : 'fa-link';
      const iconTitle = isMapped ? 'Unlink Device' : 'Link Device';
      const outletClass = isMapped ? 'name' : 'text-muted';

      const hasConfig = !!device.tv_config;
      const configLabel = hasConfig
        ? (device.tv_config.config_name || `Config #${device.tv_config.id}`)
        : 'Not assigned';
      const configClass = hasConfig ? 'text-success fw-semibold' : 'text-muted fst-italic';
      const safeLabel = escapeHtml(configLabel);

      const configCell = hideConfigCol
        ? ''
        : `<td data-label="Configuration">
              <span class="config-link ${configClass}"
                    style="cursor:pointer; text-decoration:underline;"
                    data-id="${device.id}"
                    data-mac_address="${escapeHtml(device.mac_address)}"
                    data-has_config="${hasConfig}"
                    title="Click to ${hasConfig ? 'change' : 'assign'} configuration">
                ${safeLabel}
              </span>
            </td>`;

      const row = `
        <tr>
            <td class="text-muted text-center" data-label="ID">${Id}</td>
            <td class="name" data-label="MAC Address">${device.mac_address}</td>
            <td class="${outletClass}" data-label="Outlet Name">${outletName}</td>
            ${configCell}
            <td class="text-muted" data-label="Created Time">${createdTime}</td>
            <td class="text-center" data-label="Actions">
            <button class="icon-btn icon-link-toggle ${isMapped ? 'linked' : 'unlinked'}"
                    data-toggle="tooltip"
                    title="${iconTitle}"
                    data-id="${device.id}"
                    data-mac_address="${device.mac_address}"
                    data-outlet_name="${outletName}"
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
    if (!hideConfigCol) {
      attachConfigListeners(); // Assign/change TV configuration (non–Dine Flash only)
    }
  }

  async function loadDevices(filter = 'all') {
    try {
      let url = API_ENDPOINTS.GET_ANDROID_TVS;
      if (filter !== 'all') {
        url += `?filter=${filter}`;
      }

      const res = await fetchWithAutoRefresh(url);
      const data = await res.json();
      cachedDevices = Array.isArray(data.android_tvs) ? data.android_tvs : [];
      renderDevices(cachedDevices);
    } catch (error) {
      console.error('Error loading devices:', error);
    }
  }

  function attachActionListeners() {
    document.querySelectorAll('.icon-link-toggle').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const deviceId = btn.dataset.id;
        const macAddress = btn.dataset.mac_address;
        const outletName = btn.dataset.outlet_name;
        const isMapped = btn.dataset.mapped === 'true';
        // console.log(API_ENDPOINTS.UNMAP_DEVICE);

        if (isMapped) {
          const isDineFlashDeleteFlow = isAndroidTvsHideConfigurationColumn();
          const confirmed = await ConfirmModalService.show(
            isDineFlashDeleteFlow
              ? `Delete device ${macAddress}?<br><small>This will unlink and permanently delete the Android TV from Dine Flash.</small>`
              : `Are you sure you want to unlink device ${macAddress} from ${outletName}?`
          );
          if (!confirmed) return;

          try {
            const endpoint = isDineFlashDeleteFlow
              ? API_ENDPOINTS.UNMAP_AND_DELETE_ANDROID_TVS
              : API_ENDPOINTS.UNMAP_ANDROID_TVS;
            const res = await fetchWithAutoRefresh(`${endpoint}${deviceId}/`, { method: 'POST' });

            if (!res.ok) {
              const err = await res.json();
              const message = err?.error || err?.detail || err?.message
                || (isDineFlashDeleteFlow ? 'Unable to delete device.' : 'Unable to unlink device.');
              ModalService.showError(`Error: ${message}`);
              return;
            }

            const successMessage = isDineFlashDeleteFlow
              ? `Device #${macAddress} deleted successfully.`
              : `Device #${macAddress} unlinked successfully.`;
            ModalService.showSuccess(successMessage, () => {
              loadDevices(filterDropdown.value);
            });
          } catch (err) {
            console.error('Error unlink/delete device:', err);
            ModalService.showError(
              isDineFlashDeleteFlow
                ? 'Unexpected error occurred while deleting device.'
                : 'Unexpected error occurred while unlinking device.'
            );
          }

        } else {
          openMapDeviceModal(deviceId, macAddress);
        }
      });
    });
  }

  function attachConfigListeners() {
    if (isAndroidTvsHideConfigurationColumn()) return;
    document.querySelectorAll('.config-link').forEach((link) => {
      link.addEventListener('click', () => {
        const deviceId = link.dataset.id;
        const macAddress = link.dataset.mac_address;
        const hasConfig = link.dataset.has_config === 'true';

        openAssignConfigModal(deviceId, macAddress, hasConfig, {
          fetchWithAutoRefresh,
          API_ENDPOINTS,
          ModalService
        });
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
          const res = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS);
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
