export function initEditHandlers(ctx) {
  window.addEventListener('tv-config-action', e => {
    const { action, id } = e.detail;

    if (action === 'view') openViewModal(id, ctx);
    if (action === 'edit') openEditModal(id, ctx);
    if (action === 'delete') openDeleteModal(id, ctx);
  });
}

import { loadConfigurations } from './tvConfigCore.js';

function isTvConfigListDineFlash() {
  const el = document.getElementById('tv-config-list-page-flags');
  if (el) {
    try {
      const p = JSON.parse(el.textContent);
      if (p && p.useMacFirstColumn === true) return true;
    } catch {
      /* ignore */
    }
  }
  return String(window.PROJECT_NAME || '').trim().toLowerCase() === 'dine_flash';
}

function isTvConfigListHospitalFlash() {
  const el = document.getElementById('tv-config-list-page-flags');
  if (el) {
    try {
      const p = JSON.parse(el.textContent);
      if (p && p.isHospitalFlash === true) return true;
    } catch {
      /* ignore */
    }
  }
  return String(window.PROJECT_NAME || '').trim().toLowerCase() === 'hospital_flash';
}

function readInputValue(id, fallback = undefined) {
  const el = document.getElementById(id);
  if (!el) return fallback;
  if (el.type === 'checkbox') return Boolean(el.checked);
  const value = el.value;
  if (value === undefined || value === null || value === '') return fallback;
  return value;
}

function readIntValue(id, fallback) {
  const raw = readInputValue(id, undefined);
  if (raw === undefined) return fallback;
  const parsed = parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function populateLinkedTvSelect(configResponse, config) {
  const sel = document.getElementById('edit-mapped-device-select');
  if (!sel || !isTvConfigListDineFlash()) return;
  const devices = Array.isArray(configResponse.linkable_android_devices)
    ? [...configResponse.linkable_android_devices]
    : [];
  const currentIds = Array.isArray(config.mapped_device_ids) ? config.mapped_device_ids : [];
  const currentId = currentIds.length ? String(currentIds[0]) : '';
  const currentMac = String(config.linked_tv_mac || '').trim();

  // Keep currently-linked TV visible even when it is not in linkable pool.
  // Without this, edit form can show a different TV than what was saved.
  if (currentId && !devices.some((d) => String(d.id) === currentId)) {
    devices.unshift({
      id: Number(currentId),
      mac_address: currentMac || `TV #${currentId}`,
      vendor_name: '',
      _currentLinked: true
    });
  }

  if (!devices.length) {
    sel.innerHTML =
      '<option value="" disabled selected>No linkable TVs — link a TV to an outlet on Android TVs first</option>';
    sel.disabled = true;
    sel.removeAttribute('required');
    return;
  }
  sel.setAttribute('required', 'required');
  sel.disabled = false;
  sel.innerHTML = devices
    .map((d) => {
      const mac = escapeHtml(String(d.mac_address || 'Unknown MAC'));
      const vn = d.vendor_name ? escapeHtml(String(d.vendor_name)) : '';
      const labelCore = vn ? `${mac} — ${vn}` : mac;
      const label = d._currentLinked ? `${labelCore} (currently linked)` : labelCore;
      return `<option value="${Number(d.id)}">${label}</option>`;
    })
    .join('');
  if (currentId && devices.some((d) => String(d.id) === currentId)) {
    sel.value = currentId;
  } else {
    sel.selectedIndex = 0;
  }
}

/* ALL your existing edit/view/delete code goes here
   WITHOUT changing logic or names — only moved */

async function openDeleteModal(id, ctx) {
  if (!ctx.ConfirmModalService) {
    console.error('ConfirmModalService not found in context');
    return;
  }

  const confirmed = await ctx.ConfirmModalService.show(
    'Delete Configuration? <br><small>Are you sure you want to delete this configuration? This action cannot be undone.</small>'
  );

  if (!confirmed) return;

  try {
    // Construct URL - handle potential missing trailing slash in base endpoint
    const url = ctx.apiEndpoints.DELETE_TV_CONFIG.replace('{id}', id);

    const res = await ctx.fetchWithAutoRefresh(url, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': window.AppUtils ? window.AppUtils.getCSRFToken() : getCookie('csrftoken') }
    });

    if (res.ok) {
      ctx.ModalService.showSuccess('Configuration deleted successfully', async () => {
        await loadConfigurations();
      });
    } else {
      const data = await res.json();
      ctx.ModalService.showError(data.error || 'Failed to delete configuration');
    }
  } catch (err) {
    console.error('Delete error', err);
    ctx.ModalService.showError('An error occurred during deletion');
  }
}

// Fallback cookie getter if AppUtils is missing
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

async function openViewModal(id, ctx) {
  try {
    const url = ctx.apiEndpoints.GET_TV_CONFIG_DETAIL.replace('{id}', id);
    const res = await ctx.fetchWithAutoRefresh(url);

    if (!res.ok) {
      throw new Error(`API Error: ${res.status}`);
    }

    const data = await res.json();
    const config = data.config;

    if (!config) {
      throw new Error('Invalid configuration response');
    }

    const container = document.getElementById('view-details-content');
    if (!container) {
      console.error('Element #view-details-content not found');
      return;
    }

    const utilityLookup = await getUtilityLookup(ctx);
    const entries = buildDetailEntries(config, utilityLookup);
    container.innerHTML = entries.map(([label, value]) => `
      <div class="detail-item">
        <div class="detail-label">${escapeHtml(label)}</div>
        <div class="detail-value">${value}</div>
      </div>
    `).join('');

    /* --------- Show Modal --------- */

    const modalEl = document.getElementById('view-modal');
    let modal = bootstrap.Modal.getInstance(modalEl);
    if (!modal) modal = new bootstrap.Modal(modalEl);
    modal.show();

  } catch (err) {
    console.error('View modal error', err);
    ctx.ModalService.showError('Failed to load configuration details');
  }
}

function formatField(f) {
  return String(f || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

let choicesInstance = null;
let editModalBS = null;
let utilityLookupCache = null;
let editCtx = null;
let currentConfigId = null;
let editAdsEventsBound = false;
const MAX_TV_AD_BYTES = 100 * 1024 * 1024;

/** Hospital-only: track original ad assignments and whether the user changed them. */
let hospitalOriginalAdIds = [];
let hospitalAdsSelectionDirty = false;
let hospitalAdsListLoaded = false;

function getOppositeAdPosition(qrPlacement) {
  return String(qrPlacement || '').includes('right') ? 'left' : 'right';
}

function getQrAlignmentFromPlacement(qrPlacement) {
  return String(qrPlacement || '').includes('right') ? 'right' : 'left';
}

function syncEditMaskedPhoneVisibility() {
  const showPhone = document.getElementById('edit-show-phone-number');
  const showMasked = document.getElementById('edit-show-masked-phone-number');
  const maskedGroup = document.getElementById('edit-masked-phone-group');
  if (!showPhone || !showMasked || !maskedGroup) return;
  const canShowMasked = !!showPhone.checked;
  maskedGroup.style.display = canShowMasked ? '' : 'none';
  if (!canShowMasked) {
    showMasked.checked = false;
  }
}

function cleanupBootstrapModalArtifacts() {
  document.querySelectorAll('.modal-backdrop').forEach((backdrop) => backdrop.remove());
  document.body.classList.remove('modal-open');
  document.body.style.removeProperty('overflow');
  document.body.style.removeProperty('padding-right');
}

async function safeJson(res, fallback) {
  if (!res) return fallback;
  try {
    return await res.json();
  } catch (error) {
    return fallback;
  }
}

async function getUtilityLookup(ctx) {
  if (window.PROJECT_NAME !== 'dine_flash') return {};
  if (utilityLookupCache) return utilityLookupCache;

  try {
    const res = await ctx.fetchWithAutoRefresh(ctx.apiEndpoints.GET_UTILITIES);
    if (!res.ok) return {};

    const data = await res.json();
    const utilities = data.utilities || data.results || [];
    utilityLookupCache = utilities.reduce((acc, utility) => {
      if (!utility || utility.id === undefined || utility.id === null) return acc;
      acc[String(utility.id)] = utility.display_name || utility.utility_name || utility.name || utility.display_code || `#${utility.id}`;
      return acc;
    }, {});
    return utilityLookupCache;
  } catch (error) {
    console.error('Utility lookup fetch failed', error);
    return {};
  }
}

async function openEditModal(id, ctx) {
  try {
    editCtx = ctx;
    currentConfigId = id;
    // 1. Fetch data in parallel
    const [configRes, utilsRes, adsRes] = await Promise.all([
      ctx.fetchWithAutoRefresh(ctx.apiEndpoints.GET_TV_CONFIG_DETAIL.replace('{id}', id)),
      ctx.fetchWithAutoRefresh(ctx.apiEndpoints.GET_UTILITIES),
      ctx.fetchWithAutoRefresh(ctx.apiEndpoints.TV_ADS_LIST)
    ]);

    if (!configRes.ok) {
      const errorData = await safeJson(configRes, {});
      throw new Error(errorData.error || errorData.message || `Config fetch failed: ${configRes.status}`);
    }

    const configData = await safeJson(configRes, {});
    const utilsData = utilsRes.ok ? await safeJson(utilsRes, {}) : {};
    const adsData = adsRes.ok ? await safeJson(adsRes, {}) : {};

    const config = configData.config || configData;
    const utilitiesRaw = utilsData.utilities || utilsData.results || [];
    const utilities = Array.isArray(utilitiesRaw)
      ? utilitiesRaw.filter((u) => u && u.id !== undefined && u.id !== null)
      : [];
    const ads = Array.isArray(adsData.ads) ? adsData.ads : [];
    const adsListLoaded = Boolean(adsRes.ok);

    // 2. Populate Utilities / Departments dropdown (Food, Airline, Hospital)
    const utilsSelect = document.getElementById('edit-utilities-list');
    const isDineFlashList = isTvConfigListDineFlash();
    const isHospitalFlashList = isTvConfigListHospitalFlash();
    if (!utilsSelect && !isDineFlashList && !isHospitalFlashList) {
      throw new Error('Edit utilities field is missing from the page.');
    }

    if (isHospitalFlashList) {
      hospitalAdsSelectionDirty = false;
      hospitalAdsListLoaded = adsListLoaded;
      const assignedIds = Array.isArray(config.assigned_advertisement_ids)
        ? config.assigned_advertisement_ids
        : (config.advertisements || []).map((ad) => ad.id);
      hospitalOriginalAdIds = assignedIds
        .map((id) => parseInt(id, 10))
        .filter((id) => Number.isFinite(id));
    } else {
      hospitalOriginalAdIds = [];
      hospitalAdsSelectionDirty = false;
      hospitalAdsListLoaded = false;
    }

    if (utilsSelect) {
      utilsSelect.innerHTML = utilities.map(u => {
        const name = u.display_name || u.utility_name || u.name || `Utility #${u.id}`;
        const code = u.display_code ? ` (${u.display_code})` : '';
        let label = `${name}${code}`;
        if (isHospitalFlashList && u.is_group_department && Array.isArray(u.group_departments) && u.group_departments.length) {
          const includes = u.group_departments
            .map((d) => d.display_name || d.utility_name || d.name)
            .filter(Boolean)
            .join(', ');
          label = includes ? `${name} (Group: ${includes})` : `${name} (Group)`;
        }
        return `<option value="${u.id}">${escapeHtml(label)}</option>`;
      }).join('');
    }
    populateAdsSelect(ads);

    // 3. Set Config Values
    populateForm(config);
    populateLinkedTvSelect(configData, config);
    if (isDineFlashList) {
      const editShowPhoneCheckbox = document.getElementById('edit-show-phone-number');
      if (editShowPhoneCheckbox) {
        editShowPhoneCheckbox.onchange = syncEditMaskedPhoneVisibility;
      }
      syncEditMaskedPhoneVisibility();
    }

    // 4. Init Choices.js
    if (choicesInstance) {
      choicesInstance.destroy();
      choicesInstance = null;
    }
    if (utilsSelect) {
      try {
        choicesInstance = new Choices(utilsSelect, { removeItemButton: true, itemSelectText: '' });
      } catch (error) {
        console.error('Failed to initialize utilities multiselect:', error);
        choicesInstance = null;
      }

      // Set selected utilities
      const selectedIds = (Array.isArray(config.utilities) ? config.utilities : []).map(u => u?.id || u).map(String);
      if (choicesInstance) {
        choicesInstance.setChoiceByValue(selectedIds);
      } else {
        setMultiSelect('edit-utilities-list', selectedIds);
      }
    }
    const selectedAdIds = (
      isHospitalFlashList && hospitalOriginalAdIds.length
        ? hospitalOriginalAdIds
        : (config.advertisements || []).map((ad) => ad.id)
    ).map((id) => String(id));
    refreshEditAdsUI(ads, selectedAdIds);
    // Opening the modal rebuilds the ads UI; keep Hospital dirty=false until the user edits ads.
    if (isHospitalFlashList) {
      hospitalAdsSelectionDirty = false;
    }
    bindEditAdsEvents();

    // 5. Show Modal
    const modalEl = document.getElementById('edit-modal');
    editModalBS = bootstrap.Modal.getOrCreateInstance(modalEl);
    modalEl.addEventListener('hidden.bs.modal', cleanupBootstrapModalArtifacts, { once: true });
    editModalBS.show();

    // 6. Attach Submit Handler
    const form = document.getElementById('edit-form');
    // Remove old listener to avoid duplicates if any
    form.onsubmit = null;
    form.onsubmit = e => handleEditSubmit(e, id, ctx);

  } catch (err) {
    console.error('Edit error', err);
    const details = err?.message ? `Failed to load configuration details: ${err.message}` : 'Failed to load configuration details';
    ctx.ModalService.showError(details);
  }
}

function adDeleteUrl(id) {
  return editCtx?.apiEndpoints?.TV_ADS_DELETE?.replace('{id}', id);
}

function adUpdateUrl(id) {
  return editCtx?.apiEndpoints?.TV_ADS_UPDATE?.replace('{id}', id);
}

function getSelectedAdIds() {
  const adsSelect = document.getElementById('edit-advertisements-list');
  if (!adsSelect) return [];
  return Array.from(adsSelect.selectedOptions).map((opt) => String(opt.value));
}

function populateAdsSelect(ads, selectedIds = null) {
  const adsSelect = document.getElementById('edit-advertisements-list');
  if (!adsSelect) return;
  const selectedSet = new Set(selectedIds || getSelectedAdIds());
  adsSelect.innerHTML = (ads || []).map((ad) => {
    const isSelected = selectedSet.has(String(ad.id)) ? 'selected' : '';
    return `<option value="${ad.id}" ${isSelected}>${escapeHtml(ad.title || `Ad #${ad.id}`)} (${escapeHtml(ad.media_type || 'media')})</option>`;
  }).join('');
}

function renderEditAdList(ads) {
  const adList = document.getElementById('edit-ad-list');
  if (!adList) return;

  if (!ads || ads.length === 0) {
    adList.innerHTML = '<p class="text-muted mb-0">No advertisements uploaded.</p>';
    return;
  }

  const selectedSet = new Set(getSelectedAdIds());
  adList.innerHTML = ads.map((ad) => `
    <div class="d-flex align-items-center justify-content-between border-bottom py-2">
      <div class="d-flex align-items-center gap-2">
        <input type="checkbox" class="form-check-input edit-ad-select" data-id="${ad.id}" ${selectedSet.has(String(ad.id)) ? 'checked' : ''} />
        <span class="badge bg-secondary">${escapeHtml((ad.media_type || 'media').toUpperCase())}</span>
        <input type="number" class="form-control form-control-sm edit-ad-sequence" data-id="${ad.id}" value="${ad.sequence || 1}" min="1" style="width: 80px;" title="Sequence" />
        <a href="${ad.media_url}" target="_blank" rel="noopener noreferrer">${escapeHtml(ad.title || `Ad #${ad.id}`)}</a>
      </div>
      <button type="button" class="btn btn-sm btn-outline-danger edit-ad-remove" data-id="${ad.id}">
        Remove
      </button>
    </div>
  `).join('');
}

async function fetchAds() {
  const res = await editCtx.fetchWithAutoRefresh(editCtx.apiEndpoints.TV_ADS_LIST, { method: 'GET' });
  if (!res.ok) return [];
  const data = await res.json();
  return data.ads || [];
}

async function refreshEditAdsUI(existingAds = null, selectedIds = null) {
  const ads = existingAds || await fetchAds();
  populateAdsSelect(ads, selectedIds);
  renderEditAdList(ads);
}

async function uploadAdsFromEditModal() {
  const adFilesInput = document.getElementById('edit-ad-files');
  const files = adFilesInput?.files;
  if (!files || files.length === 0) {
    editCtx.ModalService.showError('Please choose at least one ad file.');
    return;
  }

  const oversized = Array.from(files).filter((f) => f.size > MAX_TV_AD_BYTES);
  if (oversized.length > 0) {
    editCtx.ModalService.showError(
      `Each file must be 100MB or smaller. Too large: ${oversized.map((f) => f.name).join(', ')}`
    );
    return;
  }

  const body = new FormData();
  Array.from(files).forEach((file) => body.append('ads', file));

  const response = await editCtx.fetchWithAutoRefresh(editCtx.apiEndpoints.TV_ADS_UPLOAD, {
    method: 'POST',
    body
  });
  const result = await response.json();
  if (!response.ok) {
    editCtx.ModalService.showError(result.error || 'Failed to upload advertisements.');
    return;
  }

  adFilesInput.value = '';
  editCtx.ModalService.showSuccess(result.message || 'Advertisements uploaded.');
  await refreshEditAdsUI();
}

function bindEditAdsEvents() {
  if (editAdsEventsBound) return;
  editAdsEventsBound = true;

  const uploadBtn = document.getElementById('edit-upload-ads-btn');
  const adList = document.getElementById('edit-ad-list');
  const adsSelect = document.getElementById('edit-advertisements-list');

  uploadBtn?.addEventListener('click', async () => {
    try {
      await uploadAdsFromEditModal();
    } catch (error) {
      console.error('Error uploading ads from edit modal:', error);
      editCtx.ModalService.showError('Failed to upload advertisements.');
    }
  });

  adsSelect?.addEventListener('change', () => {
    markHospitalAdsSelectionDirty();
    renderEditAdList(Array.from(document.querySelectorAll('#edit-ad-list .edit-ad-select')).map((el) => {
      const adId = parseInt(el.dataset.id, 10);
      const row = el.closest('div.d-flex.align-items-center.justify-content-between');
      const sequenceInput = row?.querySelector('.edit-ad-sequence');
      const titleEl = row?.querySelector('a');
      const typeEl = row?.querySelector('.badge');
      return {
        id: adId,
        sequence: parseInt(sequenceInput?.value, 10) || 1,
        title: titleEl?.textContent || `Ad #${adId}`,
        media_type: (typeEl?.textContent || 'media').toLowerCase(),
        media_url: titleEl?.getAttribute('href') || '#'
      };
    }).filter((ad) => ad.id));
  });

  adList?.addEventListener('change', async (e) => {
    const selectToggle = e.target.closest('.edit-ad-select');
    if (selectToggle) {
      const id = String(selectToggle.dataset.id || '');
      const option = Array.from(adsSelect?.options || []).find((opt) => opt.value === id);
      if (option) option.selected = selectToggle.checked;
      markHospitalAdsSelectionDirty();
      return;
    }

    const seqInput = e.target.closest('.edit-ad-sequence');
    if (!seqInput) return;
    const adId = parseInt(seqInput.dataset.id, 10);
    const sequence = parseInt(seqInput.value, 10);
    if (!adId || !sequence || sequence < 1) return;

    try {
      await editCtx.fetchWithAutoRefresh(adUpdateUrl(adId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sequence })
      });
    } catch (error) {
      console.error('Failed to update ad sequence:', error);
    }
  });

  adList?.addEventListener('click', async (e) => {
    const removeBtn = e.target.closest('.edit-ad-remove');
    if (!removeBtn) return;
    const adId = removeBtn.dataset.id;
    if (!adId) return;

    try {
      const response = await editCtx.fetchWithAutoRefresh(adDeleteUrl(adId), { method: 'DELETE' });
      const result = await response.json();
      if (!response.ok) {
        editCtx.ModalService.showError(result.error || 'Failed to delete advertisement.');
        return;
      }
      await refreshEditAdsUI();
    } catch (error) {
      console.error('Failed to delete ad from edit modal:', error);
      editCtx.ModalService.showError('Failed to delete advertisement.');
    }
  });
}

function populateForm(config) {
  setValue('edit-config-name', config.config_name || '');
  const showQrEl = document.getElementById('edit-show-qr');
  if (showQrEl) {
    showQrEl.checked = Boolean(config.show_qr);
  }
  setValue('edit-qr-placement', config.qr_placement || 'bottom-right');
  setValue('edit-qr-base-url', config.qr_base_url || '');
  setValue('edit-qr-expiry-minutes', config.qr_expiry_minutes || 5);

  setValue('edit-items-to-show', config.items_to_show);
  setValue('edit-utility-name-mode', config.utility_name_mode);
  setValue('edit-screen-orientation', config.screen_orientation);
  setValue('edit-display-rows', config.display_rows);
  setValue('edit-display-columns', config.display_columns);
  setValue('edit-token-font-size', config.token_font_size);
  setValue('edit-counter-font-size', config.counter_font_size);
  setValue('edit-utility-font-size', config.utility_font_size);
  setValue('edit-header-font-size', config.header_font_size);
  setValue('edit-header-font-style', config.header_font_style);
  setValue('edit-token-text-color', config.token_text_color || '#000000');
  setValue('edit-counter-text-color', config.counter_text_color || '#000000');
  setValue('edit-utility-text-color', config.utility_text_color || '#000000');
  setValue('edit-header-text-color', config.header_text_color || '#000000');
  setValue('edit-footer-font-size', config.footer_font_size || 16);
  setValue('edit-footer-text-color', config.footer_text_color || '#000000');
  setChecked('edit-show-customer-name', config.show_customer_name);
  setChecked('edit-show-phone-number', config.show_phone_number);
  setChecked('edit-show-masked-phone-number', config.show_partially_masked_phone_number);
  syncEditMaskedPhoneVisibility();
  setChecked('edit-show-order-details', config.show_no_of_packs ?? config.show_order_details);
  setChecked('edit-audio-enabled', config.audio_enabled);
  setValue('edit-announcement-language', config.announcement_language || 'English');
  setChecked('edit-blink-token', config.blink_token);
  setChecked('edit-blink-utility', config.blink_utility);
  setChecked('edit-enable-ads', config.enable_ads);
  setValue('edit-ad-position', config.ad_position || 'right');
  setValue('edit-ad-interval', config.ad_interval || 8);
  setValue('edit-video-ad-mode', config.video_ad_mode || 'play_full');
  setChecked('edit-footer-enabled', config.footer_enabled);
  setValue('edit-footer-texts', Array.isArray(config.footer_texts) ? config.footer_texts.join('\n') : '');
  setMultiSelect('edit-advertisements-list', (config.advertisements || []).map(ad => String(ad.id)));

}

function markHospitalAdsSelectionDirty() {
  if (isTvConfigListHospitalFlash()) {
    hospitalAdsSelectionDirty = true;
  }
}

function getHospitalSelectableAdIds() {
  const adsSelect = document.getElementById('edit-advertisements-list');
  if (!adsSelect) return new Set();
  return new Set(
    Array.from(adsSelect.options)
      .map((opt) => parseInt(opt.value, 10))
      .filter((id) => Number.isFinite(id))
  );
}

function buildHospitalAdvertisementIdsForSave() {
  // Do not touch M2M unless the user explicitly changed ad selection.
  if (!hospitalAdsSelectionDirty) {
    return undefined;
  }
  // If the outlet ads list never loaded, never send a replacement list.
  if (!hospitalAdsListLoaded) {
    return undefined;
  }

  const adsSelect = document.getElementById('edit-advertisements-list');
  const selectedIds = adsSelect
    ? Array.from(adsSelect.selectedOptions)
        .map((opt) => parseInt(opt.value, 10))
        .filter((id) => Number.isFinite(id))
    : [];

  // Keep originally assigned ads that are not currently selectable (inactive / missing from list).
  const selectableIds = getHospitalSelectableAdIds();
  const preservedUnavailable = hospitalOriginalAdIds.filter((id) => !selectableIds.has(id));
  return Array.from(new Set([...selectedIds, ...preservedUnavailable]));
}

function buildHospitalEditPayload() {
  const footerTextsValue = readInputValue('edit-footer-texts', '') || '';
  const footerTexts = footerTextsValue.split('\n').map((t) => t.trim()).filter(Boolean);
  const advertisementIds = buildHospitalAdvertisementIdsForSave();

  const payload = {
    config_name: (readInputValue('edit-config-name', '') || '').trim(),
    show_qr: false,
    booking_fields: [],
    items_to_show: readIntValue('edit-items-to-show'),
    utility_name_mode: readInputValue('edit-utility-name-mode'),
    screen_orientation: readInputValue('edit-screen-orientation'),
    display_rows: readIntValue('edit-display-rows'),
    display_columns: readIntValue('edit-display-columns'),
    token_font_size: readInputValue('edit-token-font-size'),
    counter_font_size: readInputValue('edit-counter-font-size'),
    utility_font_size: readInputValue('edit-utility-font-size'),
    header_font_size: readInputValue('edit-header-font-size'),
    header_font_style: readInputValue('edit-header-font-style'),
    token_text_color: readInputValue('edit-token-text-color'),
    counter_text_color: readInputValue('edit-counter-text-color'),
    utility_text_color: readInputValue('edit-utility-text-color'),
    header_text_color: readInputValue('edit-header-text-color'),
    footer_font_size: readInputValue('edit-footer-font-size'),
    footer_text_color: readInputValue('edit-footer-text-color'),
    audio_enabled: Boolean(document.getElementById('edit-audio-enabled')?.checked),
    announcement_language: readInputValue('edit-announcement-language'),
    blink_token: Boolean(document.getElementById('edit-blink-token')?.checked),
    blink_utility: Boolean(document.getElementById('edit-blink-utility')?.checked),
    enable_ads: Boolean(document.getElementById('edit-enable-ads')?.checked),
    ad_position: readInputValue('edit-ad-position'),
    ad_interval: readIntValue('edit-ad-interval'),
    video_ad_mode: readInputValue('edit-video-ad-mode'),
    footer_enabled: Boolean(document.getElementById('edit-footer-enabled')?.checked),
    footer_texts: footerTexts,
  };

  if (advertisementIds !== undefined) {
    payload.advertisement_ids = advertisementIds;
  }

  const utilsSelectEl = document.getElementById('edit-utilities-list');
  if (utilsSelectEl) {
    payload.utilities = choicesInstance
      ? choicesInstance.getValue(true).map((id) => parseInt(id, 10)).filter((id) => Number.isFinite(id))
      : Array.from(utilsSelectEl.selectedOptions || [])
          .map((opt) => parseInt(opt.value, 10))
          .filter((id) => Number.isFinite(id));
  }

  Object.keys(payload).forEach((key) => {
    if (payload[key] === undefined) {
      delete payload[key];
    }
  });

  return payload;
}

async function handleEditSubmit(e, id, ctx) {
  e.preventDefault();
  const form = e.target;
  // Basic formatting for FormData if needed, or manual JSON build
  // Since we have multi-select and checkboxes, JSON build is often safer/clearer

  let payload;
  if (isTvConfigListHospitalFlash()) {
    payload = buildHospitalEditPayload();
    if (!payload.config_name) {
      ctx.ModalService.showError('Configuration name is required.');
      return;
    }
    if (payload.footer_enabled && (!payload.footer_texts || payload.footer_texts.length === 0)) {
      ctx.ModalService.showError('Add at least one footer text when footer is enabled.');
      return;
    }
  } else {
    const showQr = document.getElementById('edit-show-qr').checked;
    const qrPlacement = document.getElementById('edit-qr-placement')?.value || 'bottom-right';
    const itemsToShow = document.getElementById('edit-items-to-show').value;
    const utilNameMode = document.getElementById('edit-utility-name-mode').value;
    const orientation = document.getElementById('edit-screen-orientation').value;
    const adSelectEl = document.getElementById('edit-advertisements-list');
    const footerTextsValue = document.getElementById('edit-footer-texts')?.value || '';

    const utilsSelectEl = document.getElementById('edit-utilities-list');
    const utils = choicesInstance
      ? choicesInstance.getValue(true)
      : Array.from(utilsSelectEl?.selectedOptions || []).map((opt) => opt.value);

    const advertisementIds = adSelectEl
      ? Array.from(adSelectEl.selectedOptions).map(opt => parseInt(opt.value, 10)).filter(Boolean)
      : [];
    const footerTexts = footerTextsValue.split('\n').map(t => t.trim()).filter(Boolean);

    payload = {
      config_name: document.getElementById('edit-config-name')?.value?.trim() || '',
      show_qr: showQr,
      qr_alignment: getQrAlignmentFromPlacement(qrPlacement),
      qr_placement: qrPlacement,
      qr_base_url: document.getElementById('edit-qr-base-url')?.value?.trim() || null,
      qr_expiry_minutes: parseInt(document.getElementById('edit-qr-expiry-minutes')?.value, 10) || 5,
      items_to_show: parseInt(itemsToShow),
      utility_name_mode: utilNameMode,
      screen_orientation: orientation,
      // Dine Flash display is controlled by visibility toggles in UI.
      booking_fields: ['token'],
      display_rows: parseInt(document.getElementById('edit-display-rows')?.value, 10) || 1,
      display_columns: parseInt(document.getElementById('edit-display-columns')?.value, 10) || 1,
      token_font_size: document.getElementById('edit-token-font-size')?.value || 'large',
      counter_font_size: 'medium',
      utility_font_size: document.getElementById('edit-utility-font-size')?.value || 'small',
      header_font_size: document.getElementById('edit-header-font-size')?.value || 'large',
      header_font_style: document.getElementById('edit-header-font-style')?.value || 'bold',
      token_text_color: document.getElementById('edit-token-text-color')?.value || '#000000',
      counter_text_color: '#000000',
      utility_text_color: document.getElementById('edit-utility-text-color')?.value || '#000000',
      header_text_color: document.getElementById('edit-header-text-color')?.value || '#000000',
      footer_font_size: document.getElementById('edit-footer-font-size')?.value || '16',
      footer_text_color: document.getElementById('edit-footer-text-color')?.value || '#000000',
      show_customer_name: Boolean(document.getElementById('edit-show-customer-name')?.checked),
      show_phone_number: Boolean(document.getElementById('edit-show-phone-number')?.checked),
      show_partially_masked_phone_number: Boolean(document.getElementById('edit-show-phone-number')?.checked) &&
        Boolean(document.getElementById('edit-show-masked-phone-number')?.checked),
      show_order_details: Boolean(document.getElementById('edit-show-order-details')?.checked),
      audio_enabled: Boolean(document.getElementById('edit-audio-enabled')?.checked),
      announcement_language: document.getElementById('edit-announcement-language')?.value || 'English',
      blink_token: Boolean(document.getElementById('edit-blink-token')?.checked),
      blink_utility: Boolean(document.getElementById('edit-blink-utility')?.checked),
      enable_ads: Boolean(document.getElementById('edit-enable-ads')?.checked),
      ad_position: getOppositeAdPosition(document.getElementById('edit-qr-placement')?.value || 'bottom-right'),
      ad_interval: parseInt(document.getElementById('edit-ad-interval')?.value, 10) || 8,
      video_ad_mode: document.getElementById('edit-video-ad-mode')?.value || 'play_full',
      footer_enabled: Boolean(document.getElementById('edit-footer-enabled')?.checked),
      footer_texts: footerTexts,
      advertisement_ids: advertisementIds
    };

    if (utilsSelectEl) {
      payload.utilities = utils.map(v => parseInt(v, 10)).filter(Boolean);
    }

    if (isTvConfigListDineFlash()) {
      const sel = document.getElementById('edit-mapped-device-select');
      if (sel) {
        if (sel.disabled || !String(sel.value || '').trim()) {
          ctx.ModalService.showError(
            'No linkable Android TVs. Link a TV to an outlet on Android TVs first, then try again.'
          );
          return;
        }
        const vid = parseInt(sel.value, 10);
        if (!Number.isFinite(vid)) {
          ctx.ModalService.showError('Please select an Android TV to link.');
          return;
        }
        payload.device_ids = [vid];
      }
    }
  }

  try {
    const url = ctx.apiEndpoints.UPDATE_TV_CONFIG.replace('{id}', id);
    const res = await ctx.fetchWithAutoRefresh(url, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.AppUtils ? window.AppUtils.getCSRFToken() : getCookie('csrftoken')
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok) {
      editModalBS.hide();
      cleanupBootstrapModalArtifacts();
      ctx.ModalService.showSuccess('Configuration updated successfully', async () => {
        await loadConfigurations();
      });
    } else {
      // Show error in alert div if exists, or modal service
      const alertDiv = document.getElementById('edit-alert');
      if (alertDiv) {
        alertDiv.style.display = 'block';
        alertDiv.className = 'alert alert-danger';
        alertDiv.textContent = data.error || 'Update failed';
      } else {
        ctx.ModalService.showError(data.error || 'Update failed');
      }
    }
  } catch (err) {
    console.error('Update error', err);
    ctx.ModalService.showError('An error occurred while updating');
  }
}

function setValue(id, value) {
  const el = document.getElementById(id);
  if (el && value !== undefined && value !== null) {
    el.value = value;
  }
}

function setChecked(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.checked = Boolean(value);
  }
}

function setMultiSelect(id, values) {
  const el = document.getElementById(id);
  if (!el) return;
  const set = new Set(values || []);
  Array.from(el.options).forEach((opt) => {
    opt.selected = set.has(opt.value);
  });
}

function formatBool(value) {
  return value ? 'Yes' : 'No';
}

function formatList(values, formatter = (v) => v) {
  if (!Array.isArray(values) || values.length === 0) return '<span class="text-muted fst-italic">-</span>';
  return values.map((v) => `<span class="badge bg-light text-dark border me-1 mb-1">${escapeHtml(formatter(v))}</span>`).join('');
}

function buildDetailEntries(config, utilityLookup = {}) {
  const utilities = normalizeDineFlashUtilities(config.utilities, utilityLookup);
  const advertisements = (config.advertisements || []).map((ad) => ad.title || `Ad #${ad.id}`);
  const footerTexts = Array.isArray(config.footer_texts) ? config.footer_texts : [];

  return [
    ['Configuration Name', escapeHtml(config.config_name || '-')],
    ['Show QR', escapeHtml(formatBool(config.show_qr))],
    ['QR Alignment', escapeHtml(config.qr_alignment || '-')],
    ['QR Placement', escapeHtml(config.qr_placement || '-')],
    ['QR Base URL', escapeHtml(config.qr_base_url || '-')],
    ['Screen Orientation', escapeHtml(formatField(config.screen_orientation || '-'))],
    ['Items to Show', escapeHtml(String(config.items_to_show ?? '-'))],
    ['Utility Name Mode', escapeHtml(formatField(config.utility_name_mode || '-'))],
    ['Utilities', formatList(utilities)],
    ['Display Rows', escapeHtml(String(config.display_rows ?? '-'))],
    ['Display Columns', escapeHtml(String(config.display_columns ?? '-'))],
    ['Token Font Size', escapeHtml(formatField(config.token_font_size || '-'))],
    ['Utility Font Size', escapeHtml(formatField(config.utility_font_size || '-'))],
    ['Header Font Size', escapeHtml(formatField(config.header_font_size || '-'))],
    ['Header Font Style', escapeHtml(formatField(config.header_font_style || '-'))],
    ['Token Text Color', escapeHtml(config.token_text_color || '-')],
    ['Utility Text Color', escapeHtml(config.utility_text_color || '-')],
    ['Header Text Color', escapeHtml(config.header_text_color || '-')],
    ['Footer Font Size', escapeHtml(formatField(config.footer_font_size || '-'))],
    ['Footer Text Color', escapeHtml(config.footer_text_color || '-')],
    ['Show Customer Name', escapeHtml(formatBool(config.show_customer_name))],
    ['Show Phone Number', escapeHtml(formatBool(config.show_phone_number))],
    ['Show Partially Masked Phone Number', escapeHtml(formatBool(config.show_partially_masked_phone_number))],
    ['Show No of Packs', escapeHtml(formatBool(config.show_no_of_packs ?? config.show_order_details))],
    ['Audio Enabled', escapeHtml(formatBool(config.audio_enabled))],
    ['Announcement Language', escapeHtml(config.announcement_language || '-')],
    ['Blink Token', escapeHtml(formatBool(config.blink_token))],
    ['Blink Utility', escapeHtml(formatBool(config.blink_utility))],
    ['Enable Ads', escapeHtml(formatBool(config.enable_ads))],
    ['Ad Position', escapeHtml(formatField(config.ad_position || '-'))],
    ['Ad Interval (seconds)', escapeHtml(String(config.ad_interval ?? '-'))],
    ['Video Ad Mode', escapeHtml(formatField(config.video_ad_mode || '-'))],
    ['Advertisements', formatList(advertisements)],
    ['Footer Enabled', escapeHtml(formatBool(config.footer_enabled))],
    ['Footer Texts', formatList(footerTexts)],
  ];
}

function normalizeDineFlashUtilities(utilities, utilityLookup = {}) {
  if (!Array.isArray(utilities)) return [];

  if (window.PROJECT_NAME !== 'dine_flash') {
    return utilities.map((u) => u?.display_name || u?.utility_name || u?.display_code || `#${u?.id}`);
  }

  return utilities
    .filter((utility) => utility !== null && utility !== undefined)
    .map((utility) => {
      if (typeof utility === 'object') {
        return utility.display_name || utility.utility_name || utility.display_code || (utility.id ? `#${utility.id}` : null);
      }

      if (typeof utility === 'string') {
        const trimmed = utility.trim();
        if (!trimmed || trimmed.toLowerCase() === 'undefined') return null;
        return Number.isFinite(Number(trimmed)) ? (utilityLookup[trimmed] || `#${trimmed}`) : trimmed;
      }

      if (Number.isFinite(Number(utility))) {
        const id = String(utility);
        return utilityLookup[id] || `#${id}`;
      }
      return null;
    })
    .filter(Boolean);
}

function escapeHtml(t) {
  return t?.replace(/[&<>"']/g, m =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m])
  );
}
