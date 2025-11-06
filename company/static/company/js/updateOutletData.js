import { MenuFileManagerService } from './services/menuService.js';
import { OutletUpdateService } from './services/updateOutletService.js';

document.addEventListener('DOMContentLoaded', async () => {
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
  const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
  const labelModule = await import(`${window.BASE}static/utils/js/formFieldLabelService.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const WEB_ENDPOINTS = apiModule.WEB_ENDPOINTS;
  const ModalService = modalModule.ModalService;
  const getFriendlyFieldLabels = labelModule.default;

  const urlParams = new URLSearchParams(window.location.search);
  const vendorId = urlParams.get('vendor_id');

  const locationSelect = document.getElementById('location');
  const nameInput = document.getElementById('name');
  const aliasInput = document.getElementById('alias_name');
  const placeIdInput = document.getElementById('place_id');
  const outletForm = document.getElementById('outlet_update_form');
  const logoInput = document.getElementById('logo');
  const menuFilesInput = document.getElementById('menu_files');
  const businessHourInput = document.getElementById('business_day_start_hour');
  const autoDeleteSelect = document.getElementById('auto_delete_time');

  let vendorData = {};
  let unmappedVendorData = {};
  let vendorDetails = {};

  try {
    // Fetch vendor details
    const vendorRes = await fetchWithAutoRefresh(`${API_ENDPOINTS.GET_VENDORS_DETAILS}?vendor_id=${vendorId}`);
    if (!vendorRes.ok) throw new Error("Vendor details fetch failed");
    vendorDetails = await vendorRes.json();
    vendorData = vendorDetails.vendor_data || {};
    unmappedVendorData = vendorDetails.unmapped_data || {};
  } catch (error) {
    console.error("Fetch error:", error);
    return;
  }

  // Prefill auto-delete hours from vendor config
  if (autoDeleteSelect) {
    const autoDeleteValue = vendorData?.vendor_config?.auto_delete_hours;
    autoDeleteSelect.value = autoDeleteValue != null ? String(autoDeleteValue) : 0;
  }

  // 2️⃣ Prefill text inputs
  nameInput.value = vendorData.name || '';
  aliasInput.value = vendorData.alias_name || '';
  placeIdInput.value = vendorData.place_id || '';

  

  // 3️⃣ Populate locations dropdown safely
  const { unmapped_locations = [] } = unmappedVendorData;
  const currentLocation = vendorData.location_id;
  if (locationSelect) {
    locationSelect.innerHTML = '';
    unmapped_locations.forEach(loc => {
      const option = document.createElement('option');
      option.value = loc.value;
      option.textContent = loc.key;
      if (loc.value === currentLocation) option.selected = true;
      locationSelect.appendChild(option);
    });
  }

  // 4️⃣ Set business start hour (HH:MM)
  // 🕓 Set business hour safely
  if (businessHourInput) {
    let raw = vendorData?.vendor_config?.business_day_start_hour || '';
    // console.log("Raw from API:", raw);

    if (raw) {
      // normalize to valid HTML5 time format (HH:MM)
      const [h, m] = raw.split(':');
      const hh = h.padStart(2, '0');
      const mm = (m || '00').padStart(2, '0');
      businessHourInput.value = `${hh}:${mm}`;
    } else {
      businessHourInput.value = '';
    }

    // console.log("Final set value to input:", businessHourInput.value);
  }


  // 5️⃣ Set logo if available
  if (vendorData.logo_url) {
    const img = document.querySelector('#logo + p img');
    if (img) img.src = vendorData.logo_url;
  }
  // console.log(vendorData.menu_files)
  // 6️⃣ Initialize menu files if available
  if (Array.isArray(vendorData.menu_files) && vendorData.menu_files.length > 0) {
    MenuFileManagerService.init(vendorData.menu_files,window.BASE);
  }
  // console.log("Businesss Hour",businessHourInput);
  // 7️⃣ Handle form submission
  outletForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const locationValue = locationSelect.selectedOptions?.[0]?.text || '';
    const nameVal = nameInput.value.trim();
    const aliasVal = aliasInput.value.trim();
    const locationIdVal = locationSelect.value;
    const placeIdVal = placeIdInput.value.trim();
    const logoFile = logoInput?.files?.[0] || null;
    const menuFiles = Array.from(menuFilesInput?.files || []);
    const rawAutoDelete = autoDeleteSelect.value;
    const autoDeleteHours = parseInt(rawAutoDelete, 10);
    const businessHourVal = businessHourInput?.value?.trim() || "";
    // console.log("Captured business hour before submit:", businessHourVal);
    
    const formData = OutletUpdateService.buildFormData({
      vendor_id: vendorId,
      name: nameVal,
      alias_name: aliasVal,
      location_id: locationIdVal,
      location: locationValue,
      place_id: placeIdVal,
      logoFile: logoFile,
      menuFiles: menuFiles,
      auto_delete_hours: autoDeleteHours,  // ✅ correct key name
      business_day_start_hour : businessHourVal
    });

    for (const pair of formData.entries()) {
      console.log(pair[0], pair[1]);
    }

    try {
      const result = await OutletUpdateService.updateOutlet(formData,fetchWithAutoRefresh,API_ENDPOINTS);
      if (result.success) {
        ModalService.showSuccess("Outlet Updated Successfully", () => {
          outletForm.reset();
          window.location.href = WEB_ENDPOINTS.OUTLETS;
        });
      } else {
        const userFriendlyMessage = getFriendlyFieldLabels(result);
        ModalService.showError(userFriendlyMessage);
      }
    } catch (err) {
      ModalService.showError(err.message || err);
    }
  });
});
