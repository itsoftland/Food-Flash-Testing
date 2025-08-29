// import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { callProductAuthAPI } from '/static/utils/js//services/productAuthService.js';

// var PRODUCT_AUTH_URL = '/companyadmin/api/product-authentication/';
// var COMPANY_UPDATE_URL = '/api/company-update/';

// function getTodayDateString() {
//     const today = new Date();
//     return today.toISOString().split('T')[0];
// }

// async function callProductAuthAPI() {
//     try {
//         const customerId = localStorage.getItem("customer_id");
//         console.log(customerId);
//         if (!customerId) {
//             console.warn('No customerId found, skipping product auth check.');
//             return;
//         }
//         const response = await fetchWithAutoRefresh(PRODUCT_AUTH_URL, {
//               method: 'POST',
//               headers: {
//                 'Content-Type': 'application/json',
//                 'X-CSRFToken': AppUtils.getCSRFToken()
//             },
//             credentials: 'include',
//             body: JSON.stringify({
//                 CustomerId: customerId
//             })
//         });
//         if (!response.ok) throw new Error('Auth API failed');

//         const result = await response.json();
//         console.log('✅ Product Auth Response:', result);

//         if (result.Authenticationstatus === 'Your licence is expired. Please contact Admin !!!') {
//             await updateCompanyInfo(result);
//             localStorage.clear();
//             window.location.href = "/login/";
//             return;
//         }

//         localStorage.setItem('lastAuthCheck', getTodayDateString());
//         AppUtils.setCustomerId(customerId);
//         // Send the returned data to company update API
//         await updateCompanyInfo(result);

//     } catch (error) {
//         console.error('Auth API call failed:', error);
//     }
// }

// async function updateCompanyInfo(data) {
//     try {
//         const response = await fetchWithAutoRefresh(COMPANY_UPDATE_URL, {
//               method: 'PUT',
//               headers: {
//                 'Content-Type': 'application/json',
//                 'X-CSRFToken': AppUtils.getCSRFToken()
//             },
//             credentials: 'include',
//             body: JSON.stringify({
//                 authentication_status: data.Authenticationstatus,
//                 product_registration_id: data.ProductRegistrationId,
//                 unique_identifier: data.UniqueIDentifier,
//                 customer_id: data.CustomerId,
//                 product_from_date: data.ProductFromDate,
//                 product_to_date: data.ProductToDate,
//                 total_count: data.TotalCount,
//                 project_code: data.ProjectCode,
//                 web_login_count: data.WebLoginCount,
//                 android_tv_count: data.AndroidTvCount,
//                 android_apk_count: data.AndroidApkCount,
//                 keypad_device_count: data.KeypadDeviceCount,
//                 led_display_count: data.LedDisplayCount,
//                 outlet_count: data.OutletCount,
//                 locations: data.Locations  // If stored as JSON string
//             })
//         });

//         const result = await response.json();
//         if (!response.ok) {
//             console.error('❌ Update failed:', result);
//         } else {
//             console.log('✅ Company info updated:', result);
//         }
//     } catch (error) {
//         console.error('Update request failed:', error);
//     }
// }

document.addEventListener('DOMContentLoaded', function () {

    const displayElement = document.getElementById('customer_info');
    const customerIdRaw = AppUtils.getCustomerId();
    const customerName = AppUtils.getCustomerName();

    if (displayElement && customerIdRaw) {
        let customerId = parseInt(customerIdRaw, 10);
        let paddedId = !isNaN(customerId) ? customerId.toString().padStart(4, '0') : "Invalid";

        // Always show ID, truncate name if needed
        const nameHtml = `<span class="customer-name">${customerName}</span>`;
        const idHtml = `<span class="customer-id">(ID: ${paddedId})</span>`;

        displayElement.innerHTML = nameHtml + ' ' + idHtml;
        displayElement.setAttribute("title", `${customerName} (ID: ${paddedId})`);
    }
    callProductAuthAPI();
    $(function () {
    $('[data-toggle="tooltip"]').tooltip();
    });

});
