// companyadmin/js/outletList.js
import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';

// simple HTML-escape helper
const esc = s => (s === 0 || s) ? String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[m]) : '';

// endpoint (literal to avoid depending on API_ENDPOINTS)
const OUTLETS_API = '/food_flash/companyadmin/api/outlets/';

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
      <td data-label="Outlet Name">${name}</td>
      <td data-label="Alias Name">${alias_name}</td>
      <td data-label="Location">${location}</td>
      <td data-label="Company Name">${company}</td>
    </tr>
  `;
}

async function loadOutlets() {
  const tbody = document.getElementById('outlet-table-body');
  if (!tbody) return console.error('Outlet table body not found: #outlet-table-body');

  // show loading row
  tbody.innerHTML = `<tr><td colspan="4" class="text-center p-3">Loading outlets…</td></tr>`;

  try {
    const resp = await fetchWithAutoRefresh(OUTLETS_API, { method: 'GET', credentials: 'include' });
    if (!resp.ok) {
      const txt = await resp.text().catch(()=>null);
      throw new Error(`API returned ${resp.status} ${txt ? '- ' + txt.slice(0,200) : ''}`);
    }

    const data = await resp.json();
    // Expecting an array of outlets
    if (!Array.isArray(data) || data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted">No outlets found.</td></tr>`;
      return;
    }

    // build rows
    const html = data.map(o => outletRowHtml(o)).join('');
    tbody.innerHTML = html;

  } catch (err) {
    console.error('Failed to load outlets:', err);
    tbody.innerHTML = `<tr><td colspan="4" class="text-center text-danger">Error loading outlets</td></tr>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadOutlets();
});
