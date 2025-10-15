import { callProductAuthAPI } from '/food_flash/static/utils/js/services/productAuthService.js';
import { ModalService } from '/food_flash/static/utils/js/services/modalService.js';

document.addEventListener('DOMContentLoaded', async function () {
    const displayElement = document.getElementById('customer_info');
    const customerIdRaw = AppUtils.getCustomerId();
    const customerName = AppUtils.getCustomerName();

    if (!displayElement || !customerIdRaw) return;

    const customerId = parseInt(customerIdRaw, 10);
    const paddedId = !isNaN(customerId) ? customerId.toString().padStart(4, '0') : "Invalid";

    const authResult = await callProductAuthAPI();
    console.log('Auth check result on page load:', authResult);
    console.log(authResult.status, authResult.expiryDays);

    if (authResult.status === false) {
        console.warn('License expired or invalid. Redirecting to login.');
        ModalService.showError(
            "Your license has expired. Please click OK to return to login.",
            () => { window.location.href = '/food_flash/login/'; }
        );
        return;
    }


    // proceed with customer info rendering
    const customerHtml = `<span class="customer-name">${customerName}</span> <span class="customer-id">(ID: ${paddedId})</span>`;
    const licenseHtml = (authResult.status && authResult.expiryDays <= 9)
    ? (authResult.expiryDays > 0
        ? `<span class="license-expiry text-danger fw-bold">License will expire in ${authResult.expiryDays} day${authResult.expiryDays > 1 ? 's' : ''}</span>`
        : `<span class="license-expiry text-danger fw-bold">License will expire today</span>`)
    : '';



    // Detect viewport size
    const isMobile = window.matchMedia("(max-width: 768px)").matches;

    if (!isMobile) {
        // 🖥️ Desktop View: show both together if license info is present
        displayElement.innerHTML = licenseHtml
            ? `${customerHtml} &nbsp;&nbsp;|&nbsp;&nbsp; ${licenseHtml}`
            : customerHtml;
    } else {
        // 📱 Mobile View: alternate between name/id and license info
        if (licenseHtml) {
            startLicenseCountdownSwitcher(displayElement, customerHtml, licenseHtml);
        } else {
            displayElement.innerHTML = customerHtml;
        }
    }

    $(function () {
        $('[data-toggle="tooltip"]').tooltip();
    });
});

/**
 * Alternate text between customer info and license expiry message
 */
function startLicenseCountdownSwitcher(element, customerHtml, licenseHtml) {
    let showLicense = false;
    element.innerHTML = customerHtml;

    setInterval(() => {
        element.innerHTML = showLicense ? customerHtml : licenseHtml;
        showLicense = !showLicense;
    }, 4000); // 4 seconds switch
}


// License expiry showing by switching both data
// import { callProductAuthAPI } from '/food_flash/static/utils/js/services/productAuthService.js';

// document.addEventListener('DOMContentLoaded', async function () {
//     const displayElement = document.getElementById('customer_info');
//     const customerIdRaw = AppUtils.getCustomerId();
//     const customerName = AppUtils.getCustomerName();

//     if (displayElement && customerIdRaw) {
//         let customerId = parseInt(customerIdRaw, 10);
//         let paddedId = !isNaN(customerId) ? customerId.toString().padStart(4, '0') : "Invalid";

//         const nameHtml = `<span class="customer-name">${customerName}</span>`;
//         const idHtml = `<span class="customer-id">(ID: ${paddedId})</span>`;

//         displayElement.innerHTML = `${nameHtml} ${idHtml}`;
//         displayElement.setAttribute("title", `${customerName} (ID: ${paddedId})`);
//     }

//     // 🔍 Call product auth
//     const { success, expiryDays } = await callProductAuthAPI();

//     // Only show countdown message if license is valid and within 9 days of expiry
//     if (success && expiryDays <= 9 && expiryDays > 0) {
//         startLicenseCountdownSwitcher(displayElement, customerName, customerIdRaw, expiryDays);
//     }

//     $(function () {
//         $('[data-toggle="tooltip"]').tooltip();
//     });
// });

// /**
//  * Alternate between customer info and license expiry message every few seconds
//  */
// function startLicenseCountdownSwitcher(element, customerName, customerId, expiryDays) {
//     if (!element) return;

//     const paddedId = customerId.toString().padStart(4, '0');
//     const customerHtml = `<span class="customer-name">${customerName}</span> <span class="customer-id">(ID: ${paddedId})</span>`;
//     const licenseHtml = `<span class="license-expiry text-danger fw-bold">License will expire in ${expiryDays} day${expiryDays > 1 ? 's' : ''}</span>`;

//     let showLicense = false;

//     setInterval(() => {
//         element.innerHTML = showLicense ? customerHtml : licenseHtml;
//         showLicense = !showLicense;
//     }, 2500); // switch every 2.5 seconds
// }



// import { callProductAuthAPI } from '/food_flash/static/utils/js/services/productAuthService.js';

// document.addEventListener('DOMContentLoaded', function () {

//     const displayElement = document.getElementById('customer_info');
//     const customerIdRaw = AppUtils.getCustomerId();
//     const customerName = AppUtils.getCustomerName();

//     if (displayElement && customerIdRaw) {
//         let customerId = parseInt(customerIdRaw, 10);
//         let paddedId = !isNaN(customerId) ? customerId.toString().padStart(4, '0') : "Invalid";

//         // Always show ID, truncate name if needed
//         const nameHtml = `<span class="customer-name">${customerName}</span>`;
//         const idHtml = `<span class="customer-id">(ID: ${paddedId})</span>`;

//         displayElement.innerHTML = nameHtml + ' ' + idHtml;
//         displayElement.setAttribute("title", `${customerName} (ID: ${paddedId})`);
//     }
//     callProductAuthAPI();
//     $(function () {
//         $('[data-toggle="tooltip"]').tooltip();
//     });

// });
