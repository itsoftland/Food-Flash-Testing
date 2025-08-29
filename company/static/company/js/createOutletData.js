import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';

document.addEventListener('DOMContentLoaded', async () => {

  const locationSelect = document.getElementById('location');
  const tvSelect = document.getElementById('tv-select');
  const deviceSelect = document.getElementById('device-select');

  try {
    const response = await fetchWithAutoRefresh(`/company/api/get_outlet_creation_data/`);
    if (!response.ok) throw new Error("Failed to fetch outlet creation data");

    const data = await response.json();
    const { locations, android_tvs, keypad_devices } = data;

    // 1️⃣ Populate Location Dropdown
    if (locationSelect) {
      locationSelect.innerHTML = ''; // Clear existing
      locations.forEach(loc => {
        const option = document.createElement('option');
        option.value = loc.value;
        option.textContent = loc.key;
        option.setAttribute('data-location-name', loc.key);
        locationSelect.appendChild(option);
      });
    }

    // 2️⃣ Populate Android TV Dropdown
    if (tvSelect) {
      tvSelect.innerHTML = ''; // Clear existing
      android_tvs.forEach(tv => {
        const option = document.createElement('option');
        option.value = tv.mac_address;
        option.textContent = tv.mac_address;
        tvSelect.appendChild(option);
      });
      new Choices(tvSelect, {
        removeItemButton: true,
        classNames: {
          containerInner: 'choices-inner-foodflash',
          item: 'choices-item-foodflash',
        },
        placeholderValue: 'Select TVs',
        searchEnabled: true
      });
    }

    // 3️⃣ Populate Keypad Devices Dropdown
    if (deviceSelect) {
      deviceSelect.innerHTML = ''; // Clear existing
      keypad_devices.forEach(device => {
        const option = document.createElement('option');
        option.value = device.serial_no;
        option.textContent = device.serial_no;
        deviceSelect.appendChild(option);
      });
      new Choices(deviceSelect, {
        removeItemButton: true,
        classNames: {
          containerInner: 'choices-inner-foodflash',
          item: 'choices-item-foodflash',
        },
        placeholderValue: 'Select Devices',
        searchEnabled: true
      });
    }
  } catch (error) {
    console.error('Error while populating create outlet form:', error);
  }
});
