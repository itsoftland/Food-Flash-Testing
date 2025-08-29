import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { MenuFileManagerService } from './services/menuService.js';
import { OutletUpdateService } from './services/updateOutletService.js';
import { ModalService } from '/static/utils/js/services/modalService.js';
import getFriendlyFieldLabels from '/static/utils/js/formFieldLabelService.js';

document.addEventListener('DOMContentLoaded', async () => {
  const urlParams = new URLSearchParams(window.location.search);
  const vendorId = urlParams.get('vendor_id');

  const locationSelect = document.getElementById('location');
  const tvSelect = document.getElementById('tv-select');
  const deviceSelect = document.getElementById('device-select');
  const name = document.getElementById('name');
  const alias = document.getElementById('alias_name');
  const placeId = document.getElementById('place_id');
  const outletForm = document.getElementById('outlet_update_form');
  const logoInput = document.getElementById('logo');
  const menuFilesInput = document.getElementById('menu_files');

  let vendorData = {};
  let unmappedVendorData = {};
  let vendorDetails = {};

  try {
    // 1️⃣ Fetch vendor details (current data)
    const vendorRes = await fetchWithAutoRefresh(`/company/api/get_vendor_details?vendor_id=${vendorId}`);
    if (!vendorRes.ok) throw new Error("Vendor details fetch failed");
    vendorDetails = await vendorRes.json();
    vendorData = vendorDetails.vendor_data;
    unmappedVendorData = vendorDetails.unmapped_data;

    } catch (error) {
    console.error("Fetch error:", error);
    return;
  }

    // 3️⃣ Prefill text inputs
  name.value = vendorData.name || '';
  alias.value = vendorData.alias_name || '';
  placeId.value = vendorData.place_id || '';
  console.log(vendorData);

  const { unmapped_locations, unmapped_android_tvs, unmapped_keypad_devices } = unmappedVendorData;
  const currentLocation = vendorData.location_id;
  if (locationSelect) {
    locationSelect.innerHTML = '';
    unmapped_locations.forEach(loc => {
      const option = document.createElement('option');
      option.value = loc.value;
      option.textContent = loc.key;
      if (loc.value === currentLocation) {
        option.selected = true;
      }
      locationSelect.appendChild(option);
    });
  }

  //Populate & Preselect Android TVs
  const selectedTVs = (vendorData.android_tvs || []).map(tv => tv.mac_address);
  if (tvSelect) {
    tvSelect.innerHTML = '';
    
    unmapped_android_tvs.forEach(tv => {
      const option = document.createElement('option');
      option.value = tv.mac_address;
      option.textContent = tv.mac_address;
      tvSelect.appendChild(option);
    });
    const android_tvsChoices = new Choices(tvSelect, {
      removeItemButton: true,
      classNames: {
        containerInner: 'choices-inner-foodflash',
        item: 'choices-item-foodflash',
      },
      placeholderValue: 'Select TVs',
      searchEnabled: true
    });
    // Set selected values after initialization
    android_tvsChoices.setChoiceByValue(selectedTVs);
  }
  const selectedKeypadDevices = (vendorData.keypad_devices || []).map(device => device.serial_no);
  if (deviceSelect) {
    deviceSelect.innerHTML = '';

    unmapped_keypad_devices.forEach(keypad => {
      const option = document.createElement('option');
      option.value = keypad.serial_no;
      option.textContent = keypad.serial_no;
      deviceSelect.appendChild(option);
    });

    const keypadDeviceChoices = new Choices(deviceSelect, {
      removeItemButton: true,
      classNames: {
        containerInner: 'choices-inner-foodflash',
        item: 'choices-item-foodflash',
      },
      placeholderValue: 'Select TVs',
      searchEnabled: true
    });

    // Set selected values after initialization
    keypadDeviceChoices.setChoiceByValue(selectedKeypadDevices);
  }

  if (vendorData.logo_url) {
    const img = document.querySelector('#logo + p img');
    img.src = vendorData.logo_url;
  }
  if (vendorData.menu_files && Array.isArray(vendorData.menu_files)) {
    MenuFileManagerService.init(vendorData.menu_files)
  }
  // 🔁 Handle form submission
  outletForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const locationValue = locationSelect.selectedOptions[0].text;
    const nameVal = name.value.trim();
    const aliasVal = alias.value.trim();
    const location_id = locationSelect.value;
    const location_key = locationValue;
    const placeIdVal = placeId.value.trim();
    const logoFile = logoInput?.files?.[0] || null;
    const menuFiles = Array.from(menuFilesInput?.files || []);
    const selectedTVs = Array.from(tvSelect.selectedOptions).map(opt => opt.value);
    const selectedDevices = Array.from(deviceSelect.selectedOptions).map(opt => opt.value);
    
    console.log(menuFiles);
    
    const formData = OutletUpdateService.buildFormData({
      vendor_id: vendorId,
      name: nameVal,
      alias_name: aliasVal,
      location_id: location_id,
      location: location_key,
      place_id: placeIdVal,
      logoFile:logoFile,
      menuFiles:menuFiles,
      deviceMapping: selectedDevices,
      tvMapping: selectedTVs,
    });

    try {
      const result = await OutletUpdateService.updateOutlet(formData);
      if (result.success) {
        ModalService.showSuccess("Outlet Updated Successfully", () => {
          // Callback on OK button click
          outletForm.reset();
          window.location.href = "/company/outlets/";
        });
      } else {
        const userFriendlyMessage = getFriendlyFieldLabels(result);
        ModalService.showError(userFriendlyMessage);
      }
    } catch (err) {
      ModalService.showError(err);
    }
  });
});

