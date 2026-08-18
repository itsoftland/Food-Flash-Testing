import { ConfirmModalService } from './services/confirmModalService.js';

document.addEventListener('DOMContentLoaded', async () => {
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

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const ModalService = modalModule.ModalService;

  /* ------------------------------------
     DOM references
  ------------------------------------ */
  const configForm = document.getElementById('configuration-form');
  const outletsSelect = document.getElementById('outlets');
  const phoneNumberEnabledEl = document.getElementById('phone_number_enabled');
  const utilitiesEnabledEl = document.getElementById('utilities_enabled');
  const mrNumberEnabledEl = document.getElementById('mr_number_enabled');
  const billNumberEnabledEl = document.getElementById('bill_number_enabled');
  const qrExpiryMinutesEl = document.getElementById('qr_expiry_minutes');
  const announcementRoot = document.getElementById('hospital-announcement-templates');
  const calledChatSection = document.getElementById('hospital-called-chat-template-section');
  const calledChatSelectEl = document.getElementById('called-chat-select');
  const calledChatCustomEl = document.getElementById('called-chat-custom');
  const calledChatPreviewEl = document.getElementById('called-chat-preview');
  const calledChatCustomWrap = document.getElementById('called-chat-custom-wrap');

  if (!configForm || !outletsSelect) return;

  const announcementCatalog = window.HOSPITAL_ANNOUNCEMENT_CATALOG || null;
  const isHospitalAnnouncementUi = Boolean(
    announcementRoot &&
    announcementCatalog &&
    Array.isArray(announcementCatalog.types)
  );

  const isHospitalCalledChatUi = Boolean(
    calledChatSection &&
    calledChatSelectEl &&
    calledChatCustomEl &&
    calledChatPreviewEl
  );
  const CALLED_CHAT_DEFAULT_TEMPLATE = 'Please move to {department}';
  const CALLED_CHAT_PREVIEW_DEPARTMENT = 'Cardiology';

  const previewToken = announcementCatalog?.preview_token || '101';
  const previewDepartment = announcementCatalog?.preview_department || 'Lab';

  const applyPlaceholders = (template) => {
    if (!template) return '';
    return String(template)
      .replace(/\{token\}/g, previewToken)
      .replace(/\{department\}/g, previewDepartment);
  };

  const getOptionText = (typeDef, selection, customText) => {
    if (selection === 'custom') {
      return customText || '';
    }
    const option = (typeDef.options || []).find((o) => o.id === selection);
    return option?.text || '';
  };

  const updateAnnouncementPreview = (typeId) => {
    if (!isHospitalAnnouncementUi) return;
    const typeDef = announcementCatalog.types.find((t) => t.id === typeId);
    if (!typeDef) return;

    const selectEl = document.getElementById(`ann-select-${typeId}`);
    const customEl = document.getElementById(`ann-custom-${typeId}`);
    const previewEl = document.getElementById(`ann-preview-${typeId}`);
    const customWrap = document.getElementById(`ann-custom-wrap-${typeId}`);
    if (!selectEl || !previewEl) return;

    const selected = selectEl.value || 'default';
    if (customWrap) {
      customWrap.classList.toggle('is-visible', selected === 'custom');
    }
    const raw = getOptionText(typeDef, selected, customEl?.value || '');
    previewEl.textContent = applyPlaceholders(raw) || '—';
  };

  const renderAnnouncementTemplatesUi = () => {
    if (!isHospitalAnnouncementUi) return;

    announcementRoot.innerHTML = announcementCatalog.types
      .map((typeDef) => {
        const optionsHtml = (typeDef.options || [])
          .map(
            (opt) =>
              `<option value="${opt.id}">${opt.label}</option>`
          )
          .join('');

        return `
          <div class="announcement-type-card" data-announcement-type="${typeDef.id}">
            <h6>${typeDef.label}</h6>
            <div class="mb-2">
              <div class="announcement-preview-label">Current announcement text</div>
              <div class="announcement-preview" id="ann-preview-${typeDef.id}"></div>
            </div>
            <div class="mb-2">
              <label class="form-label" for="ann-select-${typeDef.id}">
                <strong>Template</strong>
              </label>
              <select class="form-select form-select-sm" id="ann-select-${typeDef.id}" data-ann-type="${typeDef.id}">
                ${optionsHtml}
              </select>
            </div>
            <div class="announcement-custom-wrap" id="ann-custom-wrap-${typeDef.id}">
              <label class="form-label" for="ann-custom-${typeDef.id}">
                <strong>Custom text</strong>
              </label>
              <textarea
                class="form-control form-control-sm"
                id="ann-custom-${typeDef.id}"
                data-ann-type="${typeDef.id}"
                rows="3"
                placeholder="Token {token}. Please proceed to the {department} department."
              ></textarea>
              <small class="text-muted">Use {token} and {department} placeholders.</small>
            </div>
          </div>
        `;
      })
      .join('');

    announcementCatalog.types.forEach((typeDef) => {
      const selectEl = document.getElementById(`ann-select-${typeDef.id}`);
      const customEl = document.getElementById(`ann-custom-${typeDef.id}`);
      if (selectEl) {
        selectEl.addEventListener('change', () => updateAnnouncementPreview(typeDef.id));
      }
      if (customEl) {
        customEl.addEventListener('input', () => updateAnnouncementPreview(typeDef.id));
      }
      updateAnnouncementPreview(typeDef.id);
    });
  };

  const loadAnnouncementTemplates = (vendorConfig) => {
    if (!isHospitalAnnouncementUi) return;

    const saved = vendorConfig?.announcement_templates;
    const savedMap = saved && typeof saved === 'object' ? saved : {};

    announcementCatalog.types.forEach((typeDef) => {
      const entry = savedMap[typeDef.id] || {};
      const selectEl = document.getElementById(`ann-select-${typeDef.id}`);
      const customEl = document.getElementById(`ann-custom-${typeDef.id}`);
      if (!selectEl) return;

      const selected = String(entry.selected || 'default').toLowerCase();
      const validIds = (typeDef.options || []).map((o) => o.id);
      selectEl.value = validIds.includes(selected) ? selected : 'default';
      if (customEl) {
        customEl.value = entry.custom_text ? String(entry.custom_text) : '';
      }
      updateAnnouncementPreview(typeDef.id);
    });
  };

  const collectAnnouncementTemplates = () => {
    if (!isHospitalAnnouncementUi) return null;

    const payload = {};
    announcementCatalog.types.forEach((typeDef) => {
      const selectEl = document.getElementById(`ann-select-${typeDef.id}`);
      const customEl = document.getElementById(`ann-custom-${typeDef.id}`);
      if (!selectEl) return;

      const selected = selectEl.value || 'default';
      const customText = (customEl?.value || '').trim();
      if (selected === 'default' && !customText) {
        return;
      }
      payload[typeDef.id] = {
        selected,
        custom_text: customText,
      };
    });
    return payload;
  };

  const applyCalledChatPreviewPlaceholders = (template) => {
    if (!template) return '';
    return String(template).split('{department}').join(CALLED_CHAT_PREVIEW_DEPARTMENT);
  };

  const updateCalledChatPreview = () => {
    if (!isHospitalCalledChatUi) return;
    const selected = calledChatSelectEl.value || 'default';
    if (calledChatCustomWrap) {
      calledChatCustomWrap.classList.toggle('is-visible', selected === 'custom');
    }
    const raw =
      selected === 'custom'
        ? (calledChatCustomEl.value || '').trim()
        : CALLED_CHAT_DEFAULT_TEMPLATE;
    calledChatPreviewEl.textContent = applyCalledChatPreviewPlaceholders(raw) || '—';
  };

  const loadCalledChatTemplate = (vendorConfig) => {
    if (!isHospitalCalledChatUi) return;
    const saved = (vendorConfig?.called_chat_template || '').trim();
    if (saved) {
      calledChatSelectEl.value = 'custom';
      calledChatCustomEl.value = saved;
    } else {
      calledChatSelectEl.value = 'default';
      calledChatCustomEl.value = '';
    }
    updateCalledChatPreview();
  };

  if (isHospitalAnnouncementUi) {
    renderAnnouncementTemplatesUi();
  }
  if (isHospitalCalledChatUi) {
    calledChatSelectEl.addEventListener('change', updateCalledChatPreview);
    calledChatCustomEl.addEventListener('input', updateCalledChatPreview);
    updateCalledChatPreview();
  }

  /* ------------------------------------
     Initialize Choices (ONCE)
  ------------------------------------ */
  const outletsChoices = new Choices(outletsSelect, {
    searchEnabled: true,
    shouldSort: false,
    placeholderValue: 'Select Outlet',
    classNames: {
      containerInner: 'choices-inner-foodflash',
      item: 'choices-item-foodflash',
    }
  });

  /* ------------------------------------
     Fetch vendors & populate outlets
  ------------------------------------ */
  let result = null;
  try {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.GET_VENDORS, {
      method: 'GET'
    });

    result = await response.json();

    if (!response.ok) {
      throw new Error(result?.message || 'Failed to fetch vendors');
    }

    if (Array.isArray(result.vendors)) {
      const choicesData = result.vendors.map(vendor => ({
        value: vendor.id,
        label: `${vendor.name} (${vendor.location})`
      }));

      outletsChoices.setChoices(choicesData, 'value', 'label', true);
    }

  } catch (error) {
    console.error('Vendor fetch failed:', error);
    ModalService.showError(
      'Unable to load outlet list. Please refresh the page.'
    );
    return;
  }

  // Build a map of vendors returned by GET_VENDORS so we can populate the form
  // without making an extra network request for details.
  const vendorsMap = new Map();
  if (Array.isArray(result.vendors)) {
    result.vendors.forEach(v => {
      // normalize key as string for consistent lookup
      vendorsMap.set(String(v.id), v);
    });
  }

  const loadVendorConfigFromMap = (vendorId) => {
    if (!vendorId) {
      phoneNumberEnabledEl.checked = false;
      utilitiesEnabledEl.checked = false;
      if (mrNumberEnabledEl) mrNumberEnabledEl.checked = false;
      if (billNumberEnabledEl) billNumberEnabledEl.checked = false;
      if (qrExpiryMinutesEl) qrExpiryMinutesEl.value = 5;
      loadAnnouncementTemplates(null);
      loadCalledChatTemplate(null);
      return;
    }

    const vendor = vendorsMap.get(String(vendorId)) || null;
    const vendorConfig = vendor?.config || vendor?.vendor_config || null;

    if (vendorConfig && Object.prototype.hasOwnProperty.call(vendorConfig, 'phone_number_enabled')) {
      phoneNumberEnabledEl.checked = Boolean(vendorConfig.phone_number_enabled);
    } else {
      phoneNumberEnabledEl.checked = false;
    }

    if (vendorConfig && Object.prototype.hasOwnProperty.call(vendorConfig, 'use_utilities')) {
      utilitiesEnabledEl.checked = Boolean(vendorConfig.use_utilities);
    } else {
      utilitiesEnabledEl.checked = false;
    }

    if (mrNumberEnabledEl) {
      if (vendorConfig && Object.prototype.hasOwnProperty.call(vendorConfig, 'mr_number_enabled')) {
        mrNumberEnabledEl.checked = Boolean(vendorConfig.mr_number_enabled);
      } else {
        mrNumberEnabledEl.checked = false;
      }
    }

    if (billNumberEnabledEl) {
      if (vendorConfig && Object.prototype.hasOwnProperty.call(vendorConfig, 'bill_number_enabled')) {
        billNumberEnabledEl.checked = Boolean(vendorConfig.bill_number_enabled);
      } else {
        billNumberEnabledEl.checked = false;
      }
    }

    if (qrExpiryMinutesEl) {
      const value = Number.parseInt(vendorConfig?.qr_expiry_minutes, 10);
      qrExpiryMinutesEl.value = Number.isFinite(value) && value > 0 ? value : 5;
    }

    loadAnnouncementTemplates(vendorConfig);
    loadCalledChatTemplate(vendorConfig);
  };

  // Listen for selection changes on the underlying select element
  outletsSelect.addEventListener('change', () => {
    const sel = outletsChoices.getValue(true);
    const id = Array.isArray(sel) ? (sel[0] || null) : (sel || null);
    loadVendorConfigFromMap(id);
  });

  // If a default selection exists after populating choices, load its config
  const initialValue = outletsChoices.getValue(true);
  const initialId = Array.isArray(initialValue) ? (initialValue[0] || null) : (initialValue || null);
  if (initialId) {
    loadVendorConfigFromMap(initialId);
  }

  /* ------------------------------------
     Submit configuration
  ------------------------------------ */
  configForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    let selected = outletsChoices.getValue(true); // may be string or array
    const vendorId = Array.isArray(selected) ? (selected[0] || null) : (selected || null);

    if (!vendorId) {
      ModalService.showError('Please select an outlet.');
      return;
    }

    if (isHospitalCalledChatUi && calledChatSelectEl.value === 'custom') {
      const customText = (calledChatCustomEl.value || '').trim();
      if (!customText.includes('{department}')) {
        ModalService.showError(
          'Called chat template must include the {department} placeholder.'
        );
        return;
      }
    }

    const confirmed = await ConfirmModalService.show(
      'Are you sure you want to update these configurations? This action will immediately affect system behavior.'
    );

    if (!confirmed) return;

    const payload = {
      vendor_id: vendorId,
      phone_number_enabled: Boolean(phoneNumberEnabledEl.checked),
      use_utilities: Boolean(utilitiesEnabledEl.checked)
    };
    if (mrNumberEnabledEl) {
      payload.mr_number_enabled = Boolean(mrNumberEnabledEl.checked);
    }
    if (billNumberEnabledEl) {
      payload.bill_number_enabled = Boolean(billNumberEnabledEl.checked);
    }
    if (qrExpiryMinutesEl) {
      payload.qr_expiry_minutes = Math.min(
        1440,
        Math.max(1, Number.parseInt(qrExpiryMinutesEl.value || '5', 10) || 5)
      );
    }

    if (isHospitalAnnouncementUi) {
      const templates = collectAnnouncementTemplates();
      if (templates) {
        payload.announcement_templates = templates;
      }
    }
    if (isHospitalCalledChatUi) {
      payload.called_chat_template =
        calledChatSelectEl.value === 'custom'
          ? (calledChatCustomEl.value || '').trim()
          : '';
    }

    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.CONFIG, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': AppUtils.getCSRFToken()
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json();

      if (response.ok) {
        ModalService.showSuccess(
          'Configurations updated successfully.',
          () => window.location.reload()
        );
        return;
      }

      let message = 'Something went wrong.';

      if (result?.details) {
        message = Object.entries(result.details)
          .map(([key, value]) =>
            `${key}: ${Array.isArray(value) ? value.join(', ') : value}`
          )
          .join('\n');
      } else if (result?.message) {
        message = result.message;
      }

      ModalService.showError(message);

    } catch (error) {
      console.error('Configuration update failed:', error);
      ModalService.showError(
        'Unexpected error occurred. Please try again.'
      );
    }
  });
});
