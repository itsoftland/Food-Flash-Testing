import { fetchWithAutoRefresh } from '/food_flash/static/utils/js/services/authFetchService.js';
import { API_ENDPOINTS } from '/food_flash/static/utils/js/apiEndpoints.js';
export async function callProductAuthAPI() {
    try {
        const customerId = localStorage.getItem("customer_id");
        if (!customerId) {
            console.warn('No customerId found, skipping product auth check.');
            return { success: false };
        }

        const response = await fetchWithAutoRefresh(API_ENDPOINTS.PRODUCT_AUTH_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken()
            },
            credentials: 'include',
            body: JSON.stringify({ CustomerId: customerId })
        });

        if (!response.ok) throw new Error('Auth API failed');
        const result = await response.json();

        // 🗓️ Calculate license expiry days
        const expiryDays = calculateDaysLeft(result.ProductToDate);

        console.log('✅ Product Auth Response:', result, `License expires in ${expiryDays} days`);

        // Handle expired license
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

/**
 * Helper to calculate remaining days from today to given expiry date
 */
function calculateDaysLeft(expiryDateStr) {
    if (!expiryDateStr) return 0;

    const expiryDate = new Date(expiryDateStr);
    const today = new Date();

    // Normalize both to midnight for accurate date-only comparison
    expiryDate.setHours(0, 0, 0, 0);
    today.setHours(0, 0, 0, 0);

    const diffTime = expiryDate - today;
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    // Returns positive, 0, or negative depending on expiry
    return diffDays;
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
        if (!response.ok) {
            console.error('❌ Update failed:', result);
        } else {
            console.log('✅ Company info updated:', result);
        }
    } catch (error) {
        console.error('Update request failed:', error);
    }
}

/**
 * Returns today's date in YYYY-MM-DD format.
 */
function getTodayDateString() {
    const today = new Date();
    return today.toISOString().split('T')[0];
}
