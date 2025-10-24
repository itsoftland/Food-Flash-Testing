document.addEventListener('DOMContentLoaded', async function () {
    if (!window.BASE) throw new Error('window.BASE is not defined');

    // Import modules once
    const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
    const modalModule = await import(`${window.BASE}static/utils/js/services/modalService.js`);
    const productAuthModule = await import(`${window.BASE}static/utils/js/services/productAuthService.js`);

    const WEB_ENDPOINTS = apiModule.WEB_ENDPOINTS;
    const ModalService = modalModule.ModalService;
    const callProductAuthAPI = productAuthModule.callProductAuthAPI;

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
            () => { window.location.href = WEB_ENDPOINTS.LOGIN; }
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

