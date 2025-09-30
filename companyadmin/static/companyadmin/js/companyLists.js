import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';
import { API_ENDPOINTS } from '/food_flash/static/utils/js/apiEndpoints.js';

// small helpers
const esc = s => s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : '';
const sleep = ms => new Promise(r => setTimeout(r, ms));

function setProcessing(btn, text = 'Processing...') {
  btn.dataset._orig = btn.innerText;
  btn.disabled = true;
  btn.innerText = text;
}
function restore(btn) {
  btn.disabled = false;
  if (btn.dataset._orig) btn.innerText = btn.dataset._orig;
}
function markVerified(btn,statusText) {
  btn.classList.remove('btn-outline-primary');
  if (statusText === "Verified"){
    btn.classList.add('verified');
  }
  else if (statusText === "Expired"){
    btn.classList.add('expired');
  }
  btn.disabled = true;
  btn.innerText = statusText;
}

// Build payload expected by product-registration endpoint using company object
function buildRegistrationPayload(company) {
  return {
    CustomerName: company.customer_name || '',
    PhoneNumber: company.phone_number || '',
    CustomerEmail: company.customer_email || '',
    GSTNumber: company.gst_number || '',
    CustomerContactPerson: company.customer_contact_person || '',
    CustomerContact: company.customer_contact || '',
    CustomerAddress: company.customer_address || '',
    CustomerAddress2: company.customer_address2 || '',
    CustomerState: company.customer_state || '',
    CustomerCity: company.customer_city || '',
    DeviceModel: "Windows",
    DeviceIdentifier1: company.customer_name,
    DeviceType: 1,
    Version: "FoodFlash 1.00",
    ProjectName: "FoodFlash 1.00"
  };
}

// POST to product-registration and return parsed JSON
async function registerProduct(company, btn) {
  const payload = buildRegistrationPayload(company);
  setProcessing(btn, 'Registering...');
  const resp = await fetchWithAutoRefresh(API_ENDPOINTS.PRODUCT_REGISTRATION, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(()=>null);
    throw new Error(`Registration failed (${resp.status}) ${txt || ''}`);
  }
  const json = await resp.json();
  return json; // expected { status: "Success", CustomerId: ... }
}

// Poll product-authentication until Authenticationstatus === "Approve" or timeout
async function pollAuthentication(customerId, btn, timeoutMs = 5 * 60 * 1000, intervalMs = 3000) {
  const start = Date.now();
  const payload = { CustomerId: customerId };
  setProcessing(btn, 'Waiting for approval...');

  while (Date.now() - start < timeoutMs) {
    const resp = await fetchWithAutoRefresh(API_ENDPOINTS.PRODUCT_AUTH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(()=>null);
      throw new Error(`Auth poll failed (${resp.status}) ${txt || ''}`);
    }

    const data = await resp.json();
    console.log('Auth poll response:', data);

    // If Authenticationstatus is Approve -> done
    if (data && data.Authenticationstatus === 'Approve') {
      return data;
    }

    if (data && data.Authenticationstatus === 'Waiting for response !!!'){
        // still waiting → just continue polling
        await sleep(intervalMs);
        continue;
    }

    if (data && data.Authenticationstatus === 'Your licence is expired. Please contact Admin !!!') {
      return data;
    }
    // If explicit rejection or error status, throw so UI can show error (optional)
    if (data && data.Authenticationstatus && data.Authenticationstatus !== 'Pending') {
      // treat non-Pending, non-Approve as terminal (you can relax this behavior if portal uses other statuses)
      throw new Error(`Authentication returned status: ${data.Authenticationstatus}`);
    }
    // wait and continue polling
    await sleep(intervalMs);
  }

  throw new Error('Authentication timed out.');
}

// update DOM cell to show Verified (minimal)
function updateCellToVerified(row,statusText) {
  const btn = row.querySelector('button.license-btn');
  if (btn) markVerified(btn,statusText);
}

document.addEventListener('DOMContentLoaded', async () => {
  const tableBody = document.querySelector('#companyTable tbody');

  try {
    const resp = await fetchWithAutoRefresh(API_ENDPOINTS.GET_COMPANIES, { method: 'GET' });
    if (!resp.ok) throw new Error('Failed to fetch companies');

    const data = await resp.json();
    const companies = data.results || data;

    if (!companies.length) {
      tableBody.innerHTML = `<tr><td colspan="6" class="text-center">No companies registered yet.</td></tr>`;
      return;
    }
    const company_status = {
      'Pending': 'Pending',
      'Approve': 'Approved',
      'Expired': 'Expired',
      'Block': 'Blocked'
    }

    // render rows (adds simple license button)
    companies.forEach(company => {
      const id = company.id;
      const status = esc(company_status[company.authentication_status] || 'Pending');
      // const status = esc(company.authentication_status || 'Pending');
      const row = document.createElement('tr');
      row.dataset.companyId = id;
      row.innerHTML = `
        <td>${esc(company.customer_name || '-')}</td>
        <td>${esc(company.customer_id || 'NIL')}</td>
        <td>${esc(company.customer_contact_person || '-')}</td>
        <td>${esc(company.phone_number || '-')}</td>
        <td><span class="badge ${status.toLowerCase() === 'approved' ? 'badge-success' : status.toLowerCase() === 'pending' ? 'badge-warning' : 'badge-danger'}">${status}</span></td>
        <td class="license-cell">
          <button class="license-btn" data-company-id="${id}">License Verify</button>
        </td>
      `;
      tableBody.appendChild(row);
    });

    // single event delegation for license buttons
    tableBody.addEventListener('click', async (e) => {
      const btn = e.target.closest('button.license-btn');
      if (!btn) return;

      const companyId = btn.dataset.companyId;
      if (!companyId) return;

      // find company object (from initial fetch)
      const row = btn.closest('tr');
      const company = companies.find(c => String(c.id) === String(companyId));
      if (!company) {
        alert('Company data not available.');
        return;
      }

      // 1) Register product
      try {
        const regJson = await registerProduct(company, btn);
        if (!regJson || regJson.status !== 'Success' || !regJson.CustomerId) {
          throw new Error('Registration did not return success or CustomerId.');
        }
        console.log('Registration successful:', regJson);

        // 2) Start polling authentication
        const customerId = regJson.CustomerId;

        const authData = await pollAuthentication(customerId, btn);
        if (authData.Authenticationstatus === 'Your licence is expired. Please contact Admin !!!') {
          updateCellToVerified(row,"Expired"); // mark as verified anyway
          return;
        }
        // 3) Update UI to show verified
        updateCellToVerified(row,"Verified");

        // Optionally: persist authData to backend by calling your finalize/register-company endpoint later
        // (Not implemented now — you asked to keep minimal)

      } catch (err) {
        console.error('License flow error:', err);
        alert('License action failed: ' + (err.message || err));
        restore(btn);
      }
    });

  } catch (err) {
    console.error('Failed to load companies:', err);
    tableBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Error loading company data</td></tr>`;
  }
});
