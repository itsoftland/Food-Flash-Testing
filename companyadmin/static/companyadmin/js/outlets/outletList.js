// companyadmin/static/companyadmin/js/outletList.js

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
  const name = esc(o.name || '-');
  const alias_name = esc(o.alias_name || '-');
  const location = esc(o.location || '-');
  const company = esc(o.company_name || '-');
  // edit url pattern - adjust if your route differs
  const editUrl = `/companyadmin/vendors/${o.id}/edit/`;
  return `
    <tr data-outlet-id="${o.id}">
      <td data-label="Vendor ID" style="font-weight: bold; color: #d4af37;">${esc(o.vendor_id || '-')}</td>
      <td data-label="Outlet Name">${name}</td>
      <td data-label="Alias Name">${alias_name}</td>
      <td data-label="Location">${location}</td>
      <td data-label="Company Name">${company}</td>
    </tr>
  `;
}

async function loadOutlets(fetchWithAutoRefresh, API_ENDPOINTS) {
  const tbody = document.getElementById('outlet-table-body');
  if (!tbody) return console.error('Outlet table body not found: #outlet-table-body');

  // show loading row
  tbody.innerHTML = `<tr><td colspan="5" class="text-center p-3">Loading outlets…</td></tr>`;

  try {
    const resp = await fetchWithAutoRefresh(API_ENDPOINTS.COMPANY_OUTLETS, { method: 'GET', credentials: 'include' });
    if (!resp.ok) {
      const txt = await resp.text().catch(() => null);
      throw new Error(`API returned ${resp.status} ${txt ? '- ' + txt.slice(0, 200) : ''}`);
    }

    const data = await resp.json();
    // Expecting an array of outlets
    if (!Array.isArray(data) || data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">No outlets found.</td></tr>`;
      return;
    }

    // build rows
    const html = data.map(o => outletRowHtml(o)).join('');
    tbody.innerHTML = html;

  } catch (err) {
    console.error('Failed to load outlets:', err);
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error loading outlets</td></tr>`;
  }
}


