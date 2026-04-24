/**
 * TV Configuration Assignment Helper
 * Handles assigning TV configurations to Android TV devices.
 */

/**
 * Opens a modal to assign a TV configuration to a device.
 * @param {number} deviceId - The ID of the Android TV device.
 * @param {string} macAddress - The MAC address of the device (for display).
 * @param {boolean} hasConfig - Whether device already has config mapped.
 * @param {object} ctx - Context object containing API dependencies.
 */
export async function openAssignConfigModal(deviceId, macAddress, hasConfig, ctx) {
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
        ${hasConfig ? `
          <button type="button" id="clear-config-btn" class="btn btn-outline-danger px-4 py-2 shadow-sm ms-2">
            <i class="fas fa-unlink mr-2"></i> Unmap Configuration
          </button>
        ` : ''}
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
                let configs = data.configs || [];
                if (window.PROJECT_NAME === 'dine_flash') {
                    configs = configs.filter((c) => {
                        const mapped = c.mapped_device_ids;
                        if (!mapped || mapped.length === 0) return true;
                        return mapped.length === 1 && Number(mapped[0]) === Number(deviceId);
                    });
                }

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
                            ModalService.showError(msg, () => openAssignConfigModal(deviceId, macAddress, hasConfig, ctx));
                        }, 300);
                    }
                } catch (err) {
                    console.error('Error assigning config:', err);
                    const modalElement = document.querySelector('.modal.show');
                    const modalInstance = bootstrap.Modal.getInstance(modalElement);
                    if (modalInstance) modalInstance.hide();

                    setTimeout(() => {
                        ModalService.showError('Unexpected error occurred during assignment.', () => {
                            openAssignConfigModal(deviceId, macAddress, hasConfig, ctx);
                        });
                    }, 300);
                }
            });

            if (hasConfig) {
                const clearBtn = document.getElementById('clear-config-btn');
                clearBtn?.addEventListener('click', async () => {
                    try {
                        const res = await fetchWithAutoRefresh(API_ENDPOINTS.CLEAR_TV_CONFIG, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ device_id: parseInt(deviceId) }),
                        });

                        const result = await res.json();

                        const modalElement = document.querySelector('.modal.show');
                        const modalInstance = bootstrap.Modal.getInstance(modalElement);
                        if (modalInstance) modalInstance.hide();

                        if (res.ok) {
                            setTimeout(() => {
                                ModalService.showSuccess(`Configuration unmapped from device #${macAddress}.`, () => {
                                    location.reload();
                                });
                            }, 300);
                        } else {
                            const msg = result?.error || result?.message || 'Unable to unmap configuration.';
                            setTimeout(() => {
                                ModalService.showError(msg, () => openAssignConfigModal(deviceId, macAddress, hasConfig, ctx));
                            }, 300);
                        }
                    } catch (err) {
                        console.error('Error clearing config:', err);
                        const modalElement = document.querySelector('.modal.show');
                        const modalInstance = bootstrap.Modal.getInstance(modalElement);
                        if (modalInstance) modalInstance.hide();

                        setTimeout(() => {
                            ModalService.showError('Unexpected error occurred while unmapping configuration.', () => {
                                openAssignConfigModal(deviceId, macAddress, hasConfig, ctx);
                            });
                        }, 300);
                    }
                });
            }
        }
    });
}
