document.addEventListener('DOMContentLoaded', async function () {
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;

  // DOM references
  const form = document.getElementById('tv-config-form');
  const showQrCheckbox = document.getElementById('show-qr');
  const qrAlignmentSelect = document.getElementById('qr-alignment');
  const itemsToShowSelect = document.getElementById('items-to-show');
  const bookingFieldsCheckboxes = document.querySelectorAll('input[name="booking_fields"]');
  const utilityNameModeSelect = document.getElementById('utility-name-mode');
  const screenOrientationSelect = document.getElementById('screen-orientation');
  const utilitiesSelect = document.getElementById('utilities-select');

  let choicesInstance = null; // Store Choices.js instance

  /* ------------------------------------
     Initialize Choices.js for utilities
  ------------------------------------ */
  function initializeChoices() {
    if (choicesInstance) {
      choicesInstance.destroy();
    }
    choicesInstance = new Choices(utilitiesSelect, {
      removeItemButton: true,
      itemSelectText: 'Click to select',
      placeholder: true,
      placeholderValue: 'Click to select utilities...',
      shouldSort: false,
      searchFields: ['label', 'value'],
    });
  }

  /* ------------------------------------
     Load active utilities from API
  ------------------------------------ */
  async function loadActiveUtilities() {
    try {
      const response = await fetchWithAutoRefresh(
        API_ENDPOINTS.GET_UTILITIES || '/company/api/get_utilities/',
        {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        // Handle both array and object with results property
        let utilities = [];
        if (Array.isArray(data)) {
          utilities = data;
        } else if (data.utilities && Array.isArray(data.utilities)) {
          utilities = data.utilities;
        } else if (data.results && Array.isArray(data.results)) {
          utilities = data.results;
        }

        // Populate utilities select options
        utilitiesSelect.innerHTML = '';
        utilities.forEach((utility) => {
          const option = document.createElement('option');
          option.value = utility.id;
          option.textContent = utility.display_name || utility.utility_name || utility.name || `Utility ${utility.id}`;
          utilitiesSelect.appendChild(option);
        });

        // Initialize Choices.js after populating utilities
        initializeChoices();
      } else {
        console.error('Failed to load utilities:', response.status);
      }
    } catch (error) {
      console.error('Error loading utilities:', error);
    }
  }

  // /* ------------------------------------
  //    Load existing configuration
  // ------------------------------------ */
  // async function loadConfiguration() {
  //   try {
  //     // Attempt to load existing TV configuration
  //     const response = await fetchWithAutoRefresh(
  //       API_ENDPOINTS.GET_TV_CONFIG || '/company/api/tv_config_list/',
  //       {
  //         method: 'GET',
  //         headers: {
  //           'Content-Type': 'application/json',
  //         },
  //       }
  //     );

  //     if (response.ok) {
  //       const data = await response.json();
  //       // Get the first (most recent) config from the list
  //       let configs = [];
  //       if (Array.isArray(data)) {
  //         configs = data;
  //       } else if (data.configs && Array.isArray(data.configs)) {
  //         configs = data.configs;
  //       } else if (data.results && Array.isArray(data.results)) {
  //         configs = data.results;
  //       }

  //       if (configs.length > 0) {
  //         populateFormWithConfig(configs[0]);
  //       } else {
  //         // If no config exists, set reasonable defaults
  //         setDefaultValues();
  //       }
  //     } else {
  //       // If no config exists, set reasonable defaults
  //       setDefaultValues();
  //     }
  //   } catch (error) {
  //     console.error('Error loading configuration:', error);
  //     setDefaultValues();
  //   }
  // }

  /* ------------------------------------
     Set default form values
  ------------------------------------ */
  function setDefaultValues() {
    showQrCheckbox.checked = true;
    qrAlignmentSelect.value = 'right';
    qrAlignmentSelect.disabled = false;
    itemsToShowSelect.value = '3';
    utilityNameModeSelect.value = 'display_name';
    screenOrientationSelect.value = 'landscape';
    bookingFieldsCheckboxes.forEach((checkbox) => {
      checkbox.checked = ['name', 'guest_count'].includes(checkbox.value);
    });
    // Don't pre-select utilities; let user choose
  }

  /* ------------------------------------
     Populate form with fetched configuration
  ------------------------------------ */
  function populateFormWithConfig(config) {
    // Populate Show QR checkbox
    showQrCheckbox.checked = config.show_qr || false;

    // Populate QR Alignment
    if (config.qr_alignment) {
      qrAlignmentSelect.value = config.qr_alignment;
    }
    qrAlignmentSelect.disabled = !config.show_qr;

    // Populate Items to Show
    if (config.items_to_show) {
      itemsToShowSelect.value = config.items_to_show.toString();
    }

    // Populate Booking Fields
    const bookingFields = config.booking_fields || [];
    bookingFieldsCheckboxes.forEach((checkbox) => {
      checkbox.checked = bookingFields.includes(checkbox.value);
    });

    // Populate Utility Name Mode
    if (config.utility_name_mode) {
      utilityNameModeSelect.value = config.utility_name_mode;
    }

    // Populate Screen Orientation
    if (config.screen_orientation) {
      screenOrientationSelect.value = config.screen_orientation;
    }

    // Populate Utilities List (multi-select)
    const selectedUtilityIds = config.utilities || [];
    Array.from(utilitiesSelect.options).forEach((option) => {
      option.selected = selectedUtilityIds.includes(parseInt(option.value));
    });

    // Update Choices.js if initialized
    if (choicesInstance) {
      choicesInstance.setChoiceByValue(selectedUtilityIds.map(id => id.toString()));
    }
  }

  /* ------------------------------------
     Validate form inputs
  ------------------------------------ */
  function validateForm() {
    const errors = [];

    // Validate show_qr and qr_alignment
    if (showQrCheckbox.checked && !qrAlignmentSelect.value) {
      errors.push('QR Alignment is required when Show QR Code is enabled');
    }

    // Validate items_to_show
    if (!itemsToShowSelect.value) {
      errors.push('Items to Show is required');
    } else {
      const itemsValue = parseInt(itemsToShowSelect.value);
      if (itemsValue < 1 || itemsValue > 5) {
        errors.push('Items to Show must be between 1 and 5');
      }
    }

    // Validate screen_orientation
    if (!screenOrientationSelect.value) {
      errors.push('Screen Orientation is required');
    }

    // Validate utility_name_mode
    if (!utilityNameModeSelect.value) {
      errors.push('Utility Name Mode is required');
    }

    // Validate at least one utility is selected
    // Handle both standard select and Choices.js
    let selectedUtilities = [];
    if (choicesInstance) {
      selectedUtilities = choicesInstance.getValue().map((item) => item.value);
    } else {
      selectedUtilities = Array.from(utilitiesSelect.selectedOptions).map((opt) => opt.value);
    }
    if (selectedUtilities.length === 0) {
      errors.push('Please select at least one utility');
    }

    return errors;
  }

  /* ------------------------------------
     Handle form submission
  ------------------------------------ */
  form.addEventListener('submit', async function (e) {
    e.preventDefault();

    // Validate form
    const errors = validateForm();
    if (errors.length > 0) {
      ModalService.showError(errors.join('\n'));
      return;
    }

    try {
      // Prepare payload
      // Get selected utilities from Choices.js or standard select
      let selectedUtilityValues = [];
      if (choicesInstance) {
        selectedUtilityValues = choicesInstance.getValue().map((item) => parseInt(item.value));
      } else {
        selectedUtilityValues = Array.from(utilitiesSelect.selectedOptions).map((opt) => parseInt(opt.value));
      }

      const payload = {
        config_name: document.getElementById('config-name').value,
        show_qr: showQrCheckbox.checked,
        qr_alignment: qrAlignmentSelect.value || null,
        items_to_show: parseInt(itemsToShowSelect.value),
        booking_fields: Array.from(bookingFieldsCheckboxes)
          .filter((checkbox) => checkbox.checked)
          .map((checkbox) => checkbox.value),
        utility_name_mode: utilityNameModeSelect.value,
        screen_orientation: screenOrientationSelect.value,
        utilities: selectedUtilityValues,
      };

      // Add CSRF token
      const csrfToken = window.AppUtils.getCSRFToken();

      const response = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_TV_CONFIG || '/company/api/tv_config_create/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json();

      if (response.ok) {
        ModalService.showSuccess(result.message || 'Configuration saved successfully!', () => {
          // loadConfiguration();
          window.location.reload();
        });
      } else {
        const error = result?.error || result?.message || 'Failed to save configuration.';
        ModalService.showError(error);
      }
    } catch (error) {
      console.error('Error saving configuration:', error);
      ModalService.showError('An error occurred while saving configuration.');
    }
  });

  /* ------------------------------------
     Handle alignment dropdown enable/disable
  ------------------------------------ */
  showQrCheckbox.addEventListener('change', (e) => {
    if (e.target.checked) {
      qrAlignmentSelect.disabled = false;
      qrAlignmentSelect.setAttribute('required', 'required');
    } else {
      qrAlignmentSelect.disabled = true;
      qrAlignmentSelect.removeAttribute('required');
      qrAlignmentSelect.value = '';
    }
  });

  /* ------------------------------------
     Handle form reset
  ------------------------------------ */
  form.addEventListener('reset', () => {
    setTimeout(() => loadConfiguration(), 0);
  });

  /* ------------------------------------
     Initialize
  ------------------------------------ */
  await loadActiveUtilities();
  // await loadConfiguration();
});
