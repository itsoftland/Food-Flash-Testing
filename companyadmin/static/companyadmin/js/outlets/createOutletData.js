// companyadmin/static/companyadmin/js/createOutletData.js

document.addEventListener('DOMContentLoaded', async () => {

    // Validate BASE exists
    if (!window.BASE) throw new Error('window.BASE is not defined');

    // Import modules once
    const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
    const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);

    const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
    const API_ENDPOINTS = apiModule.API_ENDPOINTS;

    const locationSelect = document.getElementById('location');
    const tvSelect = document.getElementById('tv-select');
    const deviceSelect = document.getElementById('device-select');
    const tvCommunicationSelect = document.getElementById('tv_communication_mode');
    const company = document.getElementById('company');
    const timezoneSelect = document.getElementById('timezone');
    let tvChoices = null;
    let deviceChoices = null;

    try {
        const resp = await fetchWithAutoRefresh(API_ENDPOINTS.GET_COMPANIES, { method: 'GET' });
        if (!resp.ok) throw new Error('Failed to fetch companies');

        const data = await resp.json();
        const companies = data.results || data;
        // console.log("companies", companies);

        if (company) {
            company.innerHTML = '<option value="">Select Company</option>';
            
            // ✅ Filter out companies with authentication_status = "Pending"
            companies
                .filter(comp => comp.authentication_status !== "Pending")
                .forEach(comp => {
                    const option = document.createElement('option');
                    option.value = comp.customer_id;
                    option.textContent = comp.customer_name;
                    company.appendChild(option);
                });
        }
    } catch (error) {
        console.error('Error fetching companies:', error);
    }


    // ✅ When a company is selected, fetch outlet creation data
    if (company) {
        company.addEventListener('change', async (e) => {
            const companyId = e.target.value;
            if (!companyId) return;

            try {
                const response = await fetchWithAutoRefresh(`${API_ENDPOINTS.COMPANYADMIN_OUTLET_CREATION_DATA}${companyId}/`);
                if (!response.ok) throw new Error("Failed to fetch outlet creation data");

                const data = await response.json();
                // console.log("Outlet Creation Data:", data);
                const { locations, android_tvs, keypad_devices, tv_communication_modes, timezones } = data;

                // Populate Location
                if (locationSelect) {
                    locationSelect.innerHTML = '<option value="">Select Location</option>';
                    locations.forEach(loc => {
                        const option = document.createElement('option');
                        option.value = loc.value;
                        option.textContent = loc.key;
                        option.setAttribute('data-location-name', loc.key);
                        locationSelect.appendChild(option);
                    });
                }

                // Populate Android TVs
                if (tvSelect) {
                    // Destroy existing Choices instance before reinitializing
                    if (tvChoices) {
                        tvChoices.destroy();
                    }

                    tvSelect.innerHTML = '';
                    android_tvs.forEach(tv => {
                        const option = document.createElement('option');
                        option.value = tv.mac_address;
                        option.textContent = tv.mac_address;
                        tvSelect.appendChild(option);
                    });

                    tvChoices = new Choices(tvSelect, {
                        removeItemButton: true,
                        classNames: {
                            containerInner: 'choices-inner-foodflash',
                            item: 'choices-item-foodflash',
                        },
                        placeholderValue: 'Select TVs',
                        searchEnabled: true
                    });
                }
                // Populate Keypad Devices
                if (deviceSelect) {
                    if (deviceChoices) {
                        deviceChoices.destroy();
                    }
                    deviceSelect.innerHTML = '';
                    keypad_devices.forEach(device => {
                        const option = document.createElement('option');
                        option.value = device.serial_no;
                        option.textContent = device.serial_no;
                        deviceSelect.appendChild(option);
                    });
                    deviceChoices = new Choices(deviceSelect, {
                        removeItemButton: true,
                        classNames: {
                            containerInner: 'choices-inner-foodflash',
                            item: 'choices-item-foodflash',
                        },
                        placeholderValue: 'Select Devices',
                        searchEnabled: true
                    });
                }
                // Populate TV Communication Mode
                if (tvCommunicationSelect) {
                    tvCommunicationSelect.innerHTML = '<option value="">Select Communication Mode</option>';
                    tv_communication_modes.forEach(mode => {
                        const option = document.createElement('option');
                        option.value = mode.key;
                        option.textContent = mode.value;
                        tvCommunicationSelect.appendChild(option);
                    });
                }
                // ✅ Populate Timezones
                if (timezoneSelect) {
                    timezoneSelect.innerHTML = '';
                    timezones.forEach(tz => {
                        const option = document.createElement('option');
                        option.value = tz.key;
                        option.textContent = tz.value;
                        timezoneSelect.appendChild(option);
                    });
                    // ✅ Preselect "Asia/Kolkata" if it exists
                    const defaultTimezone = "Asia/Kolkata";
                    const matchingOption = Array.from(timezoneSelect.options).find(
                        opt => opt.value === defaultTimezone
                    );
                    if (matchingOption) {
                        timezoneSelect.value = defaultTimezone;
                    }
                }
            } catch (error) {
                console.error('Error fetching outlet creation data:', error);
            }
        });
    }
});
