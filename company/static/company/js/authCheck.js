
import { callProductAuthAPI } from '/food_flash/static/utils/js/services/productAuthService.js';

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
