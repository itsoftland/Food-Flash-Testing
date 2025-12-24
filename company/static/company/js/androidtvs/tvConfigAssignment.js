/**
 * TV Configuration Assignment Helper
 * Handles assigning TV configurations to Android TV devices.
 */

/**
 * Opens a modal to assign a TV configuration to a device.
 * @param {number} deviceId - The ID of the Android TV device.
 * @param {string} macAddress - The MAC address of the device (for display).
 * @param {object} ctx - Context object containing API dependencies.
 */
export async function openAssignConfigModal(deviceId, macAddress, ctx) {
    const { fetchWithAutoRefresh, API_ENDPOINTS, ModalService } = ctx;

    const modalBodyHTML = `
    <form id="assign-config-form" class="px-4 py-3 mx-auto" style="max-width: 600px;">
      <div class="form-group col-md-12 col-12">
        <label for="config-select">Select Configuration</label>
        <select id="config-select" name="config_id" class="form-control">
          <option disabled selected>Loading configurations...</option>
        </select>
      </div>

      <div class="text-center mt-4">
        <button type="submit" class="btn btn-golden px-4 py-2 shadow-sm">
          <i class="fas fa-cog mr-2"></i> Assign Configuration
        </button>
      </div>
    </form>
  `;

    ModalService.showCustom({
        title: 'Assign Configuration to TV',
        body: modalBodyHTML,
        onShown: async () => {
            const configSelect = document.getElementById('config-select');

            try {
                const res = await fetchWithAutoRefresh(API_ENDPOINTS.GET_TV_CONFIG);
                const data = await res.json();
                const configs = data.configs || [];

                if (!configs.length) {
                    configSelect.innerHTML = `<option disabled>No configurations available</option>`;
                } else {
                    configSelect.innerHTML = configs
                        .map(c => `<option value="${c.id}">${c.config_name || `Config #${c.id}`}</option>`)
                        .join('');
                }
            } catch (err) {
                console.error('Error loading configs:', err);
                configSelect.innerHTML = `<option disabled>Error loading configurations</option>`;
            }

            // Handle form submission
            document.getElementById('assign-config-form').addEventListener('submit', async (e) => {
                e.preventDefault();

                const configId = configSelect.value;
                if (!configId) {
                    ModalService.showError('Please select a configuration.');
                    return;
                }

                try {
                    const res = await fetchWithAutoRefresh(API_ENDPOINTS.ASSIGN_TV_CONFIG, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ device_id: deviceId, config_id: parseInt(configId) }),
                    });

                    const result = await res.json();

                    // Close the current modal
                    const modalElement = document.querySelector('.modal.show');
                    const modalInstance = bootstrap.Modal.getInstance(modalElement);
                    if (modalInstance) modalInstance.hide();

                    if (res.ok) {
                        setTimeout(() => {
                            ModalService.showSuccess(`Configuration assigned to device #${macAddress}.`, () => {
                                location.reload();
                            });
                        }, 300);
                    } else {
                        const msg = result?.error || result?.message || 'Unable to assign configuration.';
                        setTimeout(() => {
                            ModalService.showError(msg, () => openAssignConfigModal(deviceId, macAddress, ctx));
                        }, 300);
                    }
                } catch (err) {
                    console.error('Error assigning config:', err);
                    const modalElement = document.querySelector('.modal.show');
                    const modalInstance = bootstrap.Modal.getInstance(modalElement);
                    if (modalInstance) modalInstance.hide();

                    setTimeout(() => {
                        ModalService.showError('Unexpected error occurred during assignment.', () => {
                            openAssignConfigModal(deviceId, macAddress, ctx);
                        });
                    }, 300);
                }
            });
        }
    });
}
