export function initEditHandlers(ctx) {
  window.addEventListener('tv-config-action', e => {
    const { action, id } = e.detail;

    if (action === 'view') openViewModal(id, ctx);
    if (action === 'edit') openEditModal(id, ctx);
    if (action === 'delete') openDeleteModal(id, ctx);
  });
}

import { loadConfigurations } from './tvConfigCore.js';

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
    const res = await ctx.fetchWithAutoRefresh(ctx.apiEndpoints.GET_TV_CONFIG_DETAIL.replace('{id}', id));
    const data = await res.json();
    const config = data.config || data;

    // Populate basic fields
    setText('view-show-qr', config.show_qr ? 'Yes' : 'No');
    setText('view-qr-align', config.qr_alignment ? capitalizeFirst(config.qr_alignment) : '-');
    setText('view-orientation', capitalizeFirst(config.screen_orientation));
    setText('view-items-show', config.items_to_show);
    setText('view-name-mode', config.utility_name_mode === 'display_name' ? 'Display Name' : 'Display Code');

    // Populate Arrays
    // Utilities
    const utilsContainer = document.getElementById('view-utilities');
    utilsContainer.innerHTML = (config.utilities && config.utilities.length)
      ? config.utilities.map(u =>
        `<span class="badge bg-secondary" style="font-size:0.85rem; padding: 0.5em 0.8em; font-weight:500;">
                ${escapeHtml(u.utility_name)} <small class="opacity-75">(${u.display_code})</small>
             </span>`
      ).join('')
      : '<span class="text-muted fst-italic">No utilities assigned</span>';

    // Booking Fields
    const fieldsContainer = document.getElementById('view-booking-fields');
    fieldsContainer.innerHTML = (config.booking_fields && config.booking_fields.length)
      ? config.booking_fields.map(f =>
        `<span class="badge bg-light text-dark border" style="font-size:0.85rem; padding: 0.5em 0.8em; font-weight:500;">
                ${formatField(f)}
             </span>`
      ).join('')
      : '<span class="text-muted fst-italic">No fields selected</span>';

    // Show Modal
    const modalEl = document.getElementById('view-modal');
    const modal = new bootstrap.Modal(modalEl);
    modal.show();

  } catch (err) {
    console.error('View error', err);
    ctx.ModalService.showError('Failed to load details');
  }
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function capitalizeFirst(s) {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatField(f) {
  // simple capitalize words
  return f.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

let choicesInstance = null;
let editModalBS = null;

async function openEditModal(id, ctx) {
  try {
    // 1. Fetch data in parallel
    const [configRes, utilsRes] = await Promise.all([
      ctx.fetchWithAutoRefresh(ctx.apiEndpoints.GET_TV_CONFIG_DETAIL.replace('{id}', id)),
      ctx.fetchWithAutoRefresh(ctx.apiEndpoints.GET_UTILITIES)
    ]);

    const configData = await configRes.json();
    const utilsData = await utilsRes.json();

    const config = configData.config || configData;
    const utilities = utilsData.utilities || [];

    // 2. Populate Utilities Dropdown
    const utilsSelect = document.getElementById('edit-utilities-list');
    utilsSelect.innerHTML = utilities.map(u =>
      `<option value="${u.id}">${escapeHtml(u.utility_name)} (${u.display_code})</option>`
    ).join('');

    // 3. Set Config Values
    populateForm(config);

    // 4. Init Choices.js
    if (choicesInstance) {
      choicesInstance.destroy();
      choicesInstance = null;
    }
    choicesInstance = new Choices(utilsSelect, { removeItemButton: true, itemSelectText: '' });

    // Set selected utilities
    const selectedIds = config.utilities.map(u => u.id || u).map(String);
    choicesInstance.setChoiceByValue(selectedIds);

    // 5. Show Modal
    const modalEl = document.getElementById('edit-modal');
    editModalBS = new bootstrap.Modal(modalEl);
    editModalBS.show();

    // 6. Attach Submit Handler
    const form = document.getElementById('edit-form');
    // Remove old listener to avoid duplicates if any
    form.onsubmit = null;
    form.onsubmit = e => handleEditSubmit(e, id, ctx);

  } catch (err) {
    console.error('Edit error', err);
    ctx.ModalService.showError('Failed to load configuration details');
  }
}

function populateForm(config) {
  document.getElementById('edit-show-qr').checked = config.show_qr;
  document.getElementById('edit-qr-alignment').value = config.qr_alignment || '';
  document.getElementById('edit-qr-alignment').disabled = !config.show_qr;

  // Toggle QR alignment based on checkbox
  document.getElementById('edit-show-qr').onchange = e => {
    document.getElementById('edit-qr-alignment').disabled = !e.target.checked;
  };

  document.getElementById('edit-items-to-show').value = config.items_to_show;
  document.getElementById('edit-utility-name-mode').value = config.utility_name_mode;
  document.getElementById('edit-screen-orientation').value = config.screen_orientation;

  // Checkboxes for booking_fields
  const fields = config.booking_fields || []; // e.g. ['name', 'token']
  document.querySelectorAll('input[name="booking_fields"]').forEach(cb => {
    cb.checked = fields.includes(cb.value);
  });
}

async function handleEditSubmit(e, id, ctx) {
  e.preventDefault();
  const form = e.target;
  // Basic formatting for FormData if needed, or manual JSON build
  // Since we have multi-select and checkboxes, JSON build is often safer/clearer

  const showQr = document.getElementById('edit-show-qr').checked;
  const qrAlign = document.getElementById('edit-qr-alignment').value;
  const itemsToShow = document.getElementById('edit-items-to-show').value;
  const utilNameMode = document.getElementById('edit-utility-name-mode').value;
  const orientation = document.getElementById('edit-screen-orientation').value;

  const utils = choicesInstance.getValue(true); // array of values

  const bookingFields = Array.from(document.querySelectorAll('input[name="booking_fields"]:checked'))
    .map(cb => cb.value);

  const payload = {
    show_qr: showQr,
    qr_alignment: qrAlign,
    items_to_show: parseInt(itemsToShow),
    utility_name_mode: utilNameMode,
    screen_orientation: orientation,
    utilities: utils, // list of IDs
    booking_fields: bookingFields
  };

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

function escapeHtml(t) {
  return t?.replace(/[&<>"']/g, m =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m])
  );
}
