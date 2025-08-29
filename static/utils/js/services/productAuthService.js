
import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { API_ENDPOINTS} from '/static/utils/js/apiEndpoints.js';

/**
 * Main function to check product authentication and update company info accordingly.
 */
export async function callProductAuthAPI() {
    try {
        const customerId = localStorage.getItem("customer_id");
        
        console.log('Customer ID for auth check:', customerId);
        if (!customerId) {
            console.warn('No customerId found, skipping product auth check.');
            return false;
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

        console.log('✅ Product Auth Response:', result);

        // Check for license expiration
        if (result.Authenticationstatus === 'Your licence is expired. Please contact Admin !!!') {
            await updateCompanyInfo({
                ...result,
                CustomerId: customerId
            });
            localStorage.clear();
            return false; 
        }

        localStorage.setItem('lastAuthCheck', getTodayDateString());
        AppUtils.setCustomerId(customerId);
        await updateCompanyInfo(result);
        // updateConfig(result);
        return true; // license valid

    } catch (error) {
        console.error('Auth API call failed:', error);
        return false;
    }
}


// async function updateConfig(data) {
//     try {
//         const response = await fetchWithAutoRefresh(API_ENDPOINTS.CONFIG, {
//             method: 'PUT',
//             headers: {
//                 'Content-Type': 'application/json',
//                 'X-CSRFToken': AppUtils.getCSRFToken()
//             },
//             credentials: 'include',
//             body: JSON.stringify({
//                 display_mode: data.DisplayMode,  
//             })
//         });

//         const result = await response.json();
//         if (!response.ok) {
//             console.error('❌ Config update failed:', result);
//         } else {
//             console.log('✅ Config updated:', result);
//         }
//     } catch (error) {
//         console.error('Config update request failed:', error);
//     }
// }

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
