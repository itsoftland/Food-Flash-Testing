import { initCore, loadConfigurations } from './tvConfigCore.js';
import { initEditHandlers } from './tvConfigEdit.js?v=20260818_1';

let ModalService;
let apiEndpoints;
let fetchWithAutoRefresh;
let ConfirmModalService;

async function loadServices() {
    const modal = await import(`${window.BASE}static/utils/js/services/modalService.js`);
    const confirm = await import(`${window.BASE}static/company/js/services/confirmModalService.js`);
    const api = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);
    const auth = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);

    ModalService = modal.ModalService;
    ConfirmModalService = confirm.ConfirmModalService;
    apiEndpoints = api.API_ENDPOINTS || {};
    fetchWithAutoRefresh = auth.fetchWithAutoRefresh;
}

document.addEventListener('DOMContentLoaded', async () => {
    await loadServices();

    const ctx = {
        ModalService,
        apiEndpoints,
        fetchWithAutoRefresh,
        ConfirmModalService
    };

    initCore(ctx);
    initEditHandlers(ctx);
    await loadConfigurations();
});
