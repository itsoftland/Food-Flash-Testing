import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';
import { API_ENDPOINTS } from '/food_flash/static/utils/js/apiEndpoints.js';

export async function callProductAuthAPI() {
    try {
        const customerId = localStorage.getItem("customer_id");
        if (!customerId) {
            console.warn('No customerId found, skipping product auth check.');
            return { status: false, expiryDays: 0 };
        }

        // First, call external product auth API
        const response = await fetchWithAutoRefresh(API_ENDPOINTS.PRODUCT_AUTH_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken()
            },
            credentials: 'include',
            body: JSON.stringify({ CustomerId: customerId })
        });
        let expiryDays = 0;
        if (!response.ok) {
            // Fallback: call internal LICENSE_CHECK API
            const licence = await fetchWithAutoRefresh(`${API_ENDPOINTS.LICENSE_CHECK}?customer_id=${customerId}`, {
                method: 'GET',
            });

            if (!licence.ok) throw new Error('License Check Failed');

            const licenceData = await licence.json();

            if (licenceData.status === 'success') {
                console.log('✅ Internal license check passed.');
                expiryDays = calculateDaysLeft(licenceData.data);
                return { status: true, expiryDays: expiryDays };
            } else {
                console.warn('⚠️ License expired according to internal check.');
                return { status: false, expiryDays: 0 };
            }
        }

        const result = await response.json();
        expiryDays = calculateDaysLeft(result.ProductToDate);

        console.log('✅ Product Auth Response:', result, `License expires in ${expiryDays} days`);

        if (result.Authenticationstatus === 'Your licence is expired. Please contact Admin !!!') {
            await updateCompanyInfo({ ...result, CustomerId: customerId });
            localStorage.clear();
            return { status: false, expiryDays: 0 };
        }

        localStorage.setItem('lastAuthCheck', getTodayDateString());
        AppUtils.setCustomerId(customerId);
        await updateCompanyInfo(result);

        return { status: true, expiryDays };

    } catch (error) {
        console.error('Auth API call failed:', error);
        return { status: false, expiryDays: 0 };
    }
}

// Helper functions unchanged
function calculateDaysLeft(expiryDateStr) {
    if (!expiryDateStr) return 0;
    const expiryDate = new Date(expiryDateStr);
    const today = new Date();
    expiryDate.setHours(0, 0, 0, 0);
    today.setHours(0, 0, 0, 0);
    return Math.floor((expiryDate - today) / (1000 * 60 * 60 * 24));
}

async function updateCompanyInfo(data) {
    try {
        const response = await fetchWithAutoRefresh(API_ENDPOINTS.COMPANY_UPDATE_URL, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken()
            },
            credentials: 'include',
            body: JSON.stringify({
                authentication_status: data.Authenticationstatus,
                product_registration_id: data.ProductRegistrationId,
                unique_identifier: data.UniqueIDentifier,
                customer_id: data.CustomerId,
                product_from_date: data.ProductFromDate,
                product_to_date: data.ProductToDate,
                total_count: data.TotalCount,
                project_code: data.ProjectCode,
                web_login_count: data.WebLoginCount,
                android_tv_count: data.AndroidTvCount,
                android_apk_count: data.AndroidApkCount,
                keypad_device_count: data.KeypadDeviceCount,
                led_display_count: data.LedDisplayCount,
                outlet_count: data.OutletCount,
                locations: data.Locations,
                displaymode: data.DisplayMode, 
            })
        });
        const result = await response.json();
        if (!response.ok) console.error('❌ Update failed:', result);
        else console.log('✅ Company info updated:', result);
    } catch (error) {
        console.error('Update request failed:', error);
    }
}

function getTodayDateString() {
    return new Date().toISOString().split('T')[0];
}
