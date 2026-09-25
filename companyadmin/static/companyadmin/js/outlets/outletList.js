// companyadmin/static/companyadmin/js/outletList.js

function getOutletListPageLabels() {
  const labels = window.OUTLET_LIST_PAGE_LABELS || {};
  return {
    vendorId: labels.vendorId || 'Vendor ID',
    name: labels.name || 'Outlet Name',
    aliasName: labels.aliasName || 'Alias Name',
    location: labels.location || 'Location',
    companyName: labels.companyName || 'Company Name',
    loading: labels.loading || 'Loading outlets…',
    empty: labels.empty || 'No outlets found.',
    error: labels.error || 'Error loading outlets',
  };
}

document.addEventListener('DOMContentLoaded', async () => {
  // Validate BASE exists
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  loadOutlets(fetchWithAutoRefresh, API_ENDPOINTS);
});

// simple HTML-escape helper
const esc = s => (s === 0 || s) ? String(s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]) : '';

// create a single table-row HTML for an outlet object
function outletRowHtml(o) {
  const labels = getOutletListPageLabels();
  const name = esc(o.name || '-');
  const alias_name = esc(o.alias_name || '-');
  const location = esc(o.location || '-');
  const company = esc(o.company_name || '-');
  // edit url pattern - adjust if your route differs
  const editUrl = `/companyadmin/vendors/${o.id}/edit/`;
  return `
    <tr data-outlet-id="${o.id}">
      <td data-label="${esc(labels.vendorId)}" style="font-weight: bold; color: #d4af37;">${esc(o.vendor_id || '-')}</td>
      <td data-label="${esc(labels.name)}">${name}</td>
      <td data-label="${esc(labels.aliasName)}">${alias_name}</td>
      <td data-label="${esc(labels.location)}">${location}</td>
      <td data-label="${esc(labels.companyName)}">${company}</td>
    </tr>
  `;
}

async function loadOutlets(fetchWithAutoRefresh, API_ENDPOINTS) {
  const tbody = document.getElementById('outlet-table-body');
  if (!tbody) return console.error('Outlet table body not found: #outlet-table-body');

  const labels = getOutletListPageLabels();

  // show loading row
  tbody.innerHTML = `<tr><td colspan="5" class="text-center p-3">${esc(labels.loading)}</td></tr>`;

  try {
    const resp = await fetchWithAutoRefresh(API_ENDPOINTS.COMPANY_OUTLETS, { method: 'GET', credentials: 'include' });
    if (!resp.ok) {
      const txt = await resp.text().catch(() => null);
      throw new Error(`API returned ${resp.status} ${txt ? '- ' + txt.slice(0, 200) : ''}`);
    }

    const data = await resp.json();
    // Expecting an array of outlets
    if (!Array.isArray(data) || data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">${esc(labels.empty)}</td></tr>`;
      return;
    }

    // build rows
    const html = data.map(o => outletRowHtml(o)).join('');
    tbody.innerHTML = html;

  } catch (err) {
    console.error('Failed to load outlets:', err);
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">${esc(labels.error)}</td></tr>`;
  }
}
