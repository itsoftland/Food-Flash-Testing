document.addEventListener('DOMContentLoaded', async () => {
  /* ------------------------------------
     DOM references (hospital layout first — no API imports required)
  ------------------------------------ */
  const createUtilityForm = document.getElementById('create-utilities-form');
  const vendorSelect = document.getElementById('vendor-select');
  const utilityNameInput = document.querySelector('input[name="utility_name"]');
  const displayNameInput = document.querySelector('input[name="display_name"]');
  const displayCodeInput = document.querySelector('input[name="display_code"]');
  const tokenModeSelect = document.querySelector('select[name="token_mode"]');
  const prefixInput = document.querySelector('input[name="prefix"]');
  const buffetImageInput = document.querySelector('input[name="buffet_utility_images"]');
  const foodTypeSelect = document.querySelector('select[name="food_type"]');
  const descriptionInput = document.querySelector('textarea[name="description"]');
  const buffetPreAnnouncementInput = document.getElementById('buffet-pre-announcement-input');
  const buffetServiceTimeInput = document.getElementById('buffet-service-time-input');
  const BUFFET_MAX_IMAGES = 3;
  const isActiveCheckbox = document.querySelector('input[name="is_active"]');
  const departmentTypeSelect = document.getElementById('department-type-select');
  const isHospital = Boolean(departmentTypeSelect);
  const groupDepartmentsSection = document.getElementById('group-departments-section');
  const groupDepartmentsCheckboxes = document.getElementById('group-departments-checkboxes');
  const displayCodeLabel = document.getElementById('display-code-label');
  const tokenModeField = document.getElementById('token-mode-field');
  const prefixField = document.getElementById('prefix-field');
  const serviceTimeField = document.getElementById('service-time-field');
  const preAnnouncementField = document.getElementById('pre-announcement-field');
  const displayOrderInput = document.getElementById('display-order-input');
  const serviceTimeInput = document.getElementById('service-time-input');
  const preAnnouncementInput = document.getElementById('pre-announcement-input');
  const priorityPrefixInput = document.getElementById('priority-prefix-input');

  function getSelectedDepartmentType() {
    if (!departmentTypeSelect) return 'INDIVIDUAL';
    return departmentTypeSelect.value || 'INDIVIDUAL';
  }

  function updateHospitalFormLayout() {
    if (!isHospital) return;

    const isGroup = getSelectedDepartmentType() === 'GROUP';

    if (groupDepartmentsSection) {
      groupDepartmentsSection.style.display = isGroup ? 'flex' : 'none';
    }
    if (displayCodeLabel) {
      displayCodeLabel.textContent = isGroup ? 'Package Code' : 'Display Code';
    }
    if (utilityNameInput) {
      utilityNameInput.placeholder = isGroup
        ? 'e.g. Executive Health Package 1'
        : 'e.g. Laboratory';
    }
    if (tokenModeField) {
      tokenModeField.style.display = isGroup ? 'none' : '';
    }
    if (prefixField) {
      prefixField.style.display = isGroup ? 'none' : '';
    }
    if (serviceTimeField) {
      serviceTimeField.style.display = isGroup ? 'none' : '';
    }
    if (preAnnouncementField) {
      preAnnouncementField.style.display = isGroup ? 'none' : '';
    }
  }

  if (isHospital && departmentTypeSelect) {
    departmentTypeSelect.addEventListener('change', updateHospitalFormLayout);
    updateHospitalFormLayout();
  }

  if (!createUtilityForm || !vendorSelect) return;

  if (!window.BASE) {
    throw new Error('window.BASE is not defined');
  }

  /* ------------------------------------
     Dynamic imports
  ------------------------------------ */
  const authModule = await import(
    `${window.BASE}static/utils/js/services/authFetchService.js`
  );
  const apiModule = await import(
    `${window.BASE}static/utils/js/apiEndpoints.js`
  );
  const modalModule = await import(
    `${window.BASE}static/utils/js/services/modalService.js`
  );
  const groupDepartmentsUiModule = isHospital
    ? await import(`${window.BASE}static/company/js/utilities/hospitalGroupDepartmentsUi.js`)
    : null;

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;
  const {
    renderGroupDepartmentCheckboxes,
    getSelectedGroupDepartmentIds,
    setGroupDepartmentCheckboxMessage,
  } = groupDepartmentsUiModule || {};

  /* ------------------------------------
     Token Mode Choices (from Utility model)
  ------------------------------------ */
  const TOKEN_MODE_CHOICES = [
    { value: 'continuous', label: 'Continuous' },
    { value: 'utility_specific', label: 'Utility Specific' }
  ];

  // Populate token mode dropdown
  if (tokenModeSelect) {
    TOKEN_MODE_CHOICES.forEach(choice => {
      const option = document.createElement('option');
      option.value = choice.value;
      option.textContent = choice.label;
      tokenModeSelect.appendChild(option);
    });
  }

  async function loadIndividualDepartmentsForGroup(vendorId, selectedIds = []) {
    if (!isHospital || !groupDepartmentsCheckboxes || !vendorId) return;

    setGroupDepartmentCheckboxMessage(groupDepartmentsCheckboxes, 'Loading departments...');

    try {
      const response = await fetchWithAutoRefresh(
        `${API_ENDPOINTS.GET_UTILITIES}?vendor_id=${encodeURIComponent(vendorId)}`,
        { method: 'GET' }
      );
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result?.error || 'Failed to load departments');
      }

      const departments = (result.utilities || []).filter(
        (utility) => utility.department_type !== 'GROUP' && utility.is_active
      );

      renderGroupDepartmentCheckboxes(groupDepartmentsCheckboxes, departments, selectedIds);
    } catch (error) {
      console.error('Failed to load individual departments:', error);
      setGroupDepartmentCheckboxMessage(groupDepartmentsCheckboxes, 'Unable to load departments');
    }
  }

  if (isHospital && departmentTypeSelect) {
    departmentTypeSelect.addEventListener('change', () => {
      if (getSelectedDepartmentType() === 'GROUP' && vendorSelect.value) {
        loadIndividualDepartmentsForGroup(vendorSelect.value);
      }
    });
  }

  vendorSelect.addEventListener('change', () => {
    if (isHospital) {
      loadIndividualDepartmentsForGroup(vendorSelect.value);
    }
  });

  /* ------------------------------------
     Fetch vendors & populate outlets
  ------------------------------------ */
  let vendorsData = [];
  try {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS, {
      method: 'GET'
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result?.message || 'Failed to fetch vendors');
    }

    if (Array.isArray(result.vendors)) {
      vendorsData = result.vendors;
      
      // Populate vendor select with plain HTML options
      vendorSelect.innerHTML = '<option value="">Select outlet</option>';
      result.vendors.forEach(vendor => {
        const option = document.createElement('option');
        option.value = vendor.vendor_id;
        option.textContent = `${vendor.name} (${vendor.location})`;
        vendorSelect.appendChild(option);
      });
    }

  } catch (error) {
    console.error('Vendor fetch failed:', error);
    ModalService.showError(
      'Unable to load outlet list. Please refresh the page.'
    );
    return;
  }

  // Build a map of vendors for quick lookup
  const vendorsMap = new Map();
  vendorsData.forEach(vendor => {
    vendorsMap.set(String(vendor.vendor_id), vendor);
  });

  /* ------------------------------------
     Form submission handler
  ------------------------------------ */
  createUtilityForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Get vendor selection
    const vendorId = vendorSelect.value;
    if (!vendorId) {
      ModalService.showError('Please select an outlet.');
      return;
    }

    // Get form values
    const utilityName = utilityNameInput.value.trim();
    const displayName = displayNameInput.value.trim();
    const isBuffet = window.PROJECT_NAME === 'dine_flash_buffet';
    const departmentType = getSelectedDepartmentType();
    const isGroupDepartment = isHospital && departmentType === 'GROUP';
    const displayCode = isBuffet ? "" : (displayCodeInput ? displayCodeInput.value.trim() : '');
    const tokenMode = isBuffet || isGroupDepartment
      ? 'continuous'
      : (tokenModeSelect ? tokenModeSelect.value.trim() : '');
    const prefix = isBuffet || isGroupDepartment
      ? null
      : (prefixInput ? prefixInput.value.trim() : '');
    const isActive = isActiveCheckbox.checked;

    // Basic validation
    if (!utilityName) {
      ModalService.showError('Utility Name is required.');
      return;
    }
    if (!displayName) {
      ModalService.showError('Display Name is required.');
      return;
    }
    if (!isBuffet && !isGroupDepartment && !displayCode) {
      ModalService.showError('Display Code is required.');
      return;
    }
    if (!isBuffet && !isGroupDepartment && !tokenMode) {
      ModalService.showError('Token Mode is required.');
      return;
    }

    if (isHospital) {
      const displayOrder = displayOrderInput ? parseInt(displayOrderInput.value, 10) : 0;
      const serviceTime = serviceTimeInput ? parseInt(serviceTimeInput.value, 10) : 0;
      const preAnnouncement = preAnnouncementInput ? parseInt(preAnnouncementInput.value, 10) : 0;
      const priorityPrefix = priorityPrefixInput ? priorityPrefixInput.value.trim() : '';

      if ([displayOrder, serviceTime, preAnnouncement].some((value) => Number.isNaN(value) || value < 0)) {
        ModalService.showError('Display order, service time, and pre-announcement count must be 0 or greater.');
        return;
      }

      if (isGroupDepartment) {
        const selectedGroupIds = getSelectedGroupDepartmentIds(groupDepartmentsCheckboxes);
        if (!selectedGroupIds.length) {
          ModalService.showError('Please select at least one included department.');
          return;
        }
      }

      if (prefix && priorityPrefix && prefix.toUpperCase() === priorityPrefix.toUpperCase()) {
        ModalService.showError('Priority prefix cannot be the same as prefix.');
        return;
      }
    }

    const foodType = isBuffet && foodTypeSelect ? foodTypeSelect.value.trim() : '';

    if (isBuffet && !foodType) {
      ModalService.showError('Food type is required.');
      return;
    }
    if (isBuffet && !['veg', 'non_veg'].includes(foodType)) {
      ModalService.showError('Please select Veg or Non Veg.');
      return;
    }

    if (isBuffet && buffetPreAnnouncementInput) {
      const buffetPreAnnouncement = parseInt(buffetPreAnnouncementInput.value, 10);
      if (Number.isNaN(buffetPreAnnouncement) || buffetPreAnnouncement < 0) {
        ModalService.showError('Pre-announcement count must be 0 or greater.');
        return;
      }
    }

    if (isBuffet && buffetServiceTimeInput) {
      const buffetServiceTime = parseInt(buffetServiceTimeInput.value, 10);
      if (Number.isNaN(buffetServiceTime) || buffetServiceTime < 0) {
        ModalService.showError('Service time must be 0 or greater.');
        return;
      }
    }

    if (isBuffet && buffetImageInput && buffetImageInput.files.length > BUFFET_MAX_IMAGES) {
      ModalService.showError(`You can upload at most ${BUFFET_MAX_IMAGES} images per utility.`);
      return;
    }

    const description = isBuffet && descriptionInput
      ? descriptionInput.value.trim()
      : '';
    if (isBuffet && description.length > 500) {
      ModalService.showError('Description must be at most 500 characters.');
      return;
    }

    // Prepare request (buffet: multipart with optional image files)
    let fetchOptions = {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': AppUtils.getCSRFToken()
      },
      body: JSON.stringify({
        vendor_id: vendorId,
        utility_name: utilityName,
        display_name: displayName,
        display_code: displayCode,
        token_mode: tokenMode,
        prefix: prefix,
        is_active: isActive,
        ...(isHospital ? {
          department_type: departmentType,
          display_order: displayOrderInput ? parseInt(displayOrderInput.value, 10) || 0 : 0,
          approximate_service_time: serviceTimeInput ? parseInt(serviceTimeInput.value, 10) || 0 : 0,
          pre_announcement_count: preAnnouncementInput ? parseInt(preAnnouncementInput.value, 10) || 0 : 0,
          priority_prefix: priorityPrefixInput ? priorityPrefixInput.value.trim() : '',
          group_department_ids: isGroupDepartment
            ? getSelectedGroupDepartmentIds(groupDepartmentsCheckboxes)
            : [],
        } : {}),
      })
    };

    if (isBuffet) {
      const fd = new FormData();
      fd.append('vendor_id', vendorId);
      fd.append('utility_name', utilityName);
      fd.append('display_name', displayName);
      fd.append('display_code', displayCode);
      fd.append('token_mode', tokenMode);
      fd.append('prefix', prefix === null || prefix === undefined ? '' : prefix);
      fd.append('is_active', isActive ? 'true' : 'false');
      fd.append('food_type', foodType);
      if (description) {
        fd.append('description', description);
      }
      fd.append(
        'pre_announcement_count',
        String(
          buffetPreAnnouncementInput
            ? parseInt(buffetPreAnnouncementInput.value, 10) || 0
            : 0
        )
      );
      fd.append(
        'approximate_service_time',
        String(
          buffetServiceTimeInput
            ? parseInt(buffetServiceTimeInput.value, 10) || 0
            : 0
        )
      );
      if (buffetImageInput && buffetImageInput.files && buffetImageInput.files.length) {
        Array.from(buffetImageInput.files)
          .slice(0, BUFFET_MAX_IMAGES)
          .forEach((file) => fd.append('buffet_utility_images', file));
      }
      fetchOptions = {
        method: 'POST',
        headers: {
          'X-CSRFToken': AppUtils.getCSRFToken()
        },
        body: fd
      };
    }

    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.CREATE_UTILITY, fetchOptions);

      const result = await response.json();

      if (response.ok) {
        ModalService.showSuccess(
          isHospital ? 'Department created successfully!' : 'Utility created successfully!',
          () => {
            createUtilityForm.reset();
            // Reset vendor select to default
            vendorSelect.innerHTML = '<option value="">Select outlet</option>';
            vendorsData.forEach(vendor => {
              const option = document.createElement('option');
              option.value = vendor.vendor_id;
              option.textContent = `${vendor.name} (${vendor.location})`;
              vendorSelect.appendChild(option);
            });
            // form.reset() does not fire change; re-sync Hospital Flash layout to Individual defaults
            if (isHospital) {
              updateHospitalFormLayout();
              if (groupDepartmentsCheckboxes && setGroupDepartmentCheckboxMessage) {
                setGroupDepartmentCheckboxMessage(
                  groupDepartmentsCheckboxes,
                  'Select an outlet first to load departments'
                );
              }
            }
          }
        );
        return;
      }

      let message = 'Failed to create utility.';

      if (result?.error) {
        message = result.error;
        // Hospital Flash Group Department: field is labelled Package Code
        if (
          isHospital &&
          isGroupDepartment &&
          result.error === 'Display code already exists for this vendor'
        ) {
          message = 'Package code already exists for this branch';
        }
      } else if (result?.message) {
        message = result.message;
      }

      ModalService.showError(message);

    } catch (error) {
      console.error('Create utility failed:', error);
      ModalService.showError(
        'Unexpected error occurred. Please try again.'
      );
    }
  });
});
