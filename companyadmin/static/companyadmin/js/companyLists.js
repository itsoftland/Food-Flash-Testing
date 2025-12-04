// companyadmin/static/companyadmin/js/companyList.js

document.addEventListener('DOMContentLoaded', async () => {
  // Validate BASE exists
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const tableBody = document.querySelector('#companyTable tbody');

  try {
    // call once on page load
    const companies = await loadCompanyList(fetchWithAutoRefresh,API_ENDPOINTS);
    let payload = {}

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
        // alert('Company data not available.');
        return;
      }
      // console.log("company Details",company)
      // console.log("Starting license flow for company ID:", company.id);

      // 1) Register product
      try {
        const regJson = await registerProduct(company, btn, fetchWithAutoRefresh, API_ENDPOINTS);
        if (!regJson || regJson.status !== 'Success' || !regJson.CustomerId) {
          throw new Error('Registration did not return success or CustomerId.');
        }
        // console.log('Registration successful:', regJson);

        // 2) Start polling authentication
        const customerId = regJson.CustomerId;
        const saveCustomerID = await fetchWithAutoRefresh(`${API_ENDPOINTS.UPDATE_COMPANY_ID}${company.id}/`, { 
          method: 'PUT',
          headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken()
            },
          credentials: 'include',
          body: JSON.stringify({
            customer_id: customerId,
          })  
        });
        if (!saveCustomerID.ok) {
            console.error('❌ Update failed:', result);
        }
        const authData = await pollAuthentication(customerId, btn, fetchWithAutoRefresh, API_ENDPOINTS);

        // 3) Update UI to show verified
        if (authData.Authenticationstatus === 'Your licence is expired. Please contact Admin !!!') {
          updateCellToVerified(row,"Expired"); // mark as verified anyway
          payload = JSON.stringify({
            authentication_status: "Expired",
            customer_id: customerId
          });
        }
        if (authData.Authenticationstatus === 'Block') {
          updateCellToVerified(row,"Blocked"); // mark as verified anyway
          payload = JSON.stringify({
            authentication_status: "Blocked",
            customer_id: customerId
          });
        }
        if (authData.Authenticationstatus === 'Approve') {
          updateCellToVerified(row,"Validated");
          payload = JSON.stringify({
            authentication_status: authData.Authenticationstatus,
            product_registration_id: authData.ProductRegistrationId,
            unique_identifier: authData.UniqueIDentifier,
            customer_id: authData.CustomerId,
            product_from_date: authData.ProductFromDate,
            product_to_date: authData.ProductToDate,
            total_count: authData.TotalCount,
            project_code: authData.ProjectCode,
            web_login_count: authData.WebLoginCount,
            android_tv_count: authData.AndroidTvCount,
            android_apk_count: authData.AndroidApkCount,
            keypad_device_count: authData.KeypadDeviceCount,
            led_display_count: authData.LedDisplayCount,
            outlet_count: authData.OutletCount,
            locations: authData.Locations,
            displaymode: authData.DisplayMode, 
          });
        }
        // console.log("Payload to update company:", payload);
        // 4) Update company info in our backend
        const resp = await fetchWithAutoRefresh(API_ENDPOINTS.UPDATE_COMPANY, { 
          method: 'PUT',
          headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken()
            },
          credentials: 'include',
          body: payload
        });
        const result = await resp.json();
        if (!resp.ok) {
            console.error('❌ Update failed:', result);
            // alert('Failed to update company info after authentication.');
        } else {
          setTimeout ( async () => {
            await loadCompanyList(fetchWithAutoRefresh,API_ENDPOINTS);
          }, 3000);
          // console.log('✅ Company info updated:', result);
        }

      } catch (err) {
        console.error('License flow error:', err);
        // alert('License action failed: ' + (err.message || err));
        restore(btn);
      }
    });

  } catch (err) {
    console.error('Failed to load companies:', err);
    tableBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Error loading company data</td></tr>`;
  }
});


// small helpers
const esc = s => s ? String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : '';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const company_status = {
  'Pending': 'Pending',
  'Approve': 'Approved',
  'Expired': 'Expired',
  'Block': 'Blocked'
};

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
  if (statusText === "Validated"){
    btn.classList.add('verified');
  }
  else if (statusText === "Expired"){
    btn.classList.add('expired');
  }
  
  btn.disabled = true;
  btn.innerText = statusText;
  setTimeout(() => {
    btn.disabled = false;
    btn.classList.remove('verified');
    btn.classList.remove('expired');
    btn.innerText = 'License Validate';
  }, 3000);
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
    Version: `${window.PROJECT_NAME} ${window.APP_VERSION}`,
    ProjectName: window.PROJECT_NAME 
  };
}

// POST to product-registration and return parsed JSON
async function registerProduct(company, btn,fetchWithAutoRefresh,API_ENDPOINTS) {
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
async function pollAuthentication(customerId, btn,fetchWithAutoRefresh, API_ENDPOINTS, timeoutMs = 5 * 60 * 1000, intervalMs = 3000) {
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
    // console.log('Auth poll response:', data);

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

async function loadCompanyList(fetchWithAutoRefresh,API_ENDPOINTS) {
  const tableBody = document.querySelector('#companyTable tbody');
  if (!tableBody) throw new Error('Table body element not found: #companyTable tbody');

  // clear existing rows
  tableBody.innerHTML = '';

  try {
    const resp = await fetchWithAutoRefresh(API_ENDPOINTS.GET_COMPANIES, { method: 'GET' });
    if (!resp.ok) throw new Error('Failed to fetch companies');

    const data = await resp.json();
    const companies = data.results || data;

    if (!companies || companies.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="6" class="text-center">No companies registered yet.</td></tr>`;
      return companies || [];
    }

    // render rows
    companies.forEach(company => {
      const id = company.id;
      const raw = company.authentication_status || 'Pending';
      const statusLabel = esc(company_status[raw] || 'Pending');

      // pick badge class from raw backend status (not the mapped label)
      const badgeClass = raw === 'Approve' ? 'badge-success'
        : raw === 'Pending' ? 'badge-warning'
        : raw === 'Expired' ? 'badge-danger'
        : raw === 'Block' ? 'badge-danger'
        : 'badge-light';

      const row = document.createElement('tr');
      row.dataset.companyId = id;
      row.innerHTML = `
        <td data-label="Company Name">${esc(company.customer_name || '-')}</td>
        <td data-label="Customer ID">${esc(company.customer_id ?? 'NIL')}</td>
        <td data-label="Contact Person">${esc(company.customer_contact_person || '-')}</td>
        <td data-label="Phone">${esc(company.phone_number || '-')}</td>
        <td data-label="Status"><span class="badge ${badgeClass}">${statusLabel}</span></td>
        <td class="license-cell" data-label="Licence">
          <button class="license-btn" data-company-id="${id}">License Validate</button>
        </td>
      `;
      tableBody.appendChild(row);
    });

    return companies;
  } catch (err) {
    console.error('Failed to load companies:', err);
    tableBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Error loading company data</td></tr>`;
    return [];
  }
}

// Exported reusable loader
