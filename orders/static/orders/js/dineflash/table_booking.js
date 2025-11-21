/**
 * ==========================================================================
 * 📘 Table Booking Script — Full Documentation
 * ==========================================================================
 * Purpose
 * --------------------------------------------------------------------------
 * This script powers the public Table Booking screen (FoodFlash / Dine).
 * It resolves vendor identity reliably (iOS-safe), loads vendor branding,
 * validates form inputs, submits table booking requests to the backend API,
 * and displays success/duplicate modals with redirect links.
 *
 * Key Features
 * --------------------------------------------------------------------------
 * 1) Vendor ID resolution (URL → LocalStorage → IndexedDB → Cookie)
 *    - URL vendor_id has priority. If present, it is persisted to vendorStore.
 *    - If not present, vendorStore.getVendorId() is used.
 *    - Ensures persistent vendor branding and compatibility with iOS Safari.
 *
 * 2) Vendor branding auto-load
 *    - Loads vendor name and logo from VENDOR_LOGOS endpoint using vendor_id.
 *
 * 3) Booking workflow
 *    - Fields collected:
 *        - customer_name (string)
 *        - no_of_guests (integer)
 *        - special_notes (string)        // optional
 *        - vendor_id (resolved)
 *    - Submits payload to API endpoint: apiEndpoints.CREATE_TABLE_BOOKING
 *    - API response handling:
 *        - 201 → New booking created (show successModal)
 *        - 200 → Duplicate booking / already exists (show duplicateModal)
 *        - other → show error via ModalService
 *
 * 4) UX Safeguards
 *    - Prevents double-clicks by disabling button while request in-flight.
 *    - Shows spinner in the button during processing.
 *    - Restores button state after completion/failure.
 *
 * 5) Module & Deployment Notes
 *    - Uses ES6 dynamic imports:
 *         import(`${base}static/utils/js/apiEndpoints.js`);
 *    - Expected support files:
 *         - apiEndpoints.js  (exports API_ENDPOINTS)
 *         - modalService.js  (exports ModalService)
 *         - vendorStore.js   (exports setVendorId, getVendorId)
 *    - Template must include the success and duplicate modals with IDs:
 *         - successModal, duplicateModal
 *      and placeholders:
 *         - #success-details, #success-redirect-btn
 *         - #duplicate-details, #duplicate-redirect-btn
 *
 * ==========================================================================
 */

/* ==========================================================
   Table Booking Script (table_booking.js)
   ==========================================================
*/
document.addEventListener("DOMContentLoaded", async () => {
    const base = window.BASE || "/caller_on/";

    let apiEndpoints, ModalService, vendorId;

    // --------------------------
    // Load required modules
    // --------------------------
    try {
        const endpointsModule = await import(`${base}static/utils/js/apiEndpoints.js`);
        const modalServiceModule = await import(`${base}static/utils/js/services/modalService.js`);
        const vendorStore = await import(`${base}static/orders/js/config/vendorStore.js`);

        apiEndpoints = endpointsModule.API_ENDPOINTS;
        ModalService = modalServiceModule.ModalService;

        // Helper: read query param
        function getParam(key) {
            const params = new URLSearchParams(window.location.search);
            return params.get(key);
        }

        const urlVendorId = getParam("vendor_id");

        // Vendor ID priority: URL -> stored
        if (urlVendorId) {
            vendorId = parseInt(urlVendorId, 10);
            // persist for future loads (handles iOS fallback)
            if (!isNaN(vendorId)) {
                await vendorStore.setVendorId(vendorId);
            } else {
                console.warn("Invalid vendor_id in URL:", urlVendorId);
                vendorId = await vendorStore.getVendorId();
            }
        } else {
            vendorId = await vendorStore.getVendorId();
        }

        if (!vendorId) {
            console.error("Vendor ID missing. Cannot continue.");
            ModalService && ModalService.showError && ModalService.showError("Missing vendor information.");
            return;
        }

        // Clean URL: remove vendor_id param (keeps UX clean)
        try {
            const url = new URL(window.location.href);
            if (url.searchParams.has("vendor_id")) {
                url.searchParams.delete("vendor_id");
                history.replaceState({}, document.title, url.toString());
            }
        } catch (err) {
            // ignore history.replace errors
            console.warn("Could not clean URL:", err);
        }

    } catch (err) {
        console.error("Failed loading modules:", err);
        return;
    }

    // --------------------------
    // Load vendor branding
    // --------------------------
    async function loadVendorInfo() {
        if (!vendorId) return;

        try {
            const response = await fetch(apiEndpoints.VENDOR_LOGOS, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vendor_ids: [vendorId] })
            });

            const data = await response.json();
            if (!data || !data.length) return;

            const vendor = data[0];

            const nameEl = document.getElementById("vendor-name");
            const logoEl = document.getElementById("vendor-logo");

            if (nameEl) nameEl.textContent = vendor.name || vendor.alias_name || "Vendor";
            if (logoEl && vendor.logo_url) logoEl.src = vendor.logo_url;

        } catch (err) {
            console.error("Error loading vendor info:", err);
        }
    }

    // --------------------------
    // Modal helpers
    // --------------------------
    function getModal(id) {
        const el = document.getElementById(id);
        return el ? new bootstrap.Modal(el) : null;
    }

    const successModal = getModal("successModal");
    const duplicateModal = getModal("duplicateModal");

    // --------------------------
    // Build booking payload
    // --------------------------
    function buildPayload() {
        const customerNameEl = document.getElementById("customer_name");
        const guestsEl = document.getElementById("no_of_guests");
        const notesEl = document.getElementById("special_notes");

        const payload = {
            vendor_id: vendorId,
            customer_name: customerNameEl ? customerNameEl.value.trim() : "",
            no_of_guests: guestsEl ? parseInt(guestsEl.value, 10) || 0 : 0,
            special_notes: notesEl ? notesEl.value.trim() : ""
        };

        return payload;
    }

    // --------------------------
    // Simple client-side validation
    // --------------------------
    function validatePayload(payload) {
        if (!payload.customer_name) {
            ModalService.showError("Customer name is required.");
            return false;
        }
        if (!payload.no_of_guests || payload.no_of_guests <= 0) {
            ModalService.showError("Please enter a valid number of guests.");
            return false;
        }
        return true;
    }

    // --------------------------
    // Submit booking
    // --------------------------
    async function submitBooking() {
        const registerBtn = document.getElementById("register-btn");
        if (!registerBtn) return;

        // disable & show spinner
        registerBtn.disabled = true;
        const originalHTML = registerBtn.innerHTML;
        registerBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Processing...`;

        try {
            const payload = buildPayload();

            if (!validatePayload(payload)) {
                return;
            }

            const resp = await fetch(apiEndpoints.CREATE_TABLE_BOOKING, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await resp.json();

            if (resp.status === 201) {
                // New booking
                const detailsEl = document.getElementById("success-details");
                if (detailsEl) {
                    detailsEl.innerHTML = `
                        <strong>${escapeHtml(data.customer_name || payload.customer_name)}</strong><br>
                        Guests: ${escapeHtml(String(data.no_of_guests || payload.no_of_guests))}<br>
                        ${data.special_notes ? `Notes: ${escapeHtml(data.special_notes)}` : ""}
                    `;
                }
                const redirectBtn = document.getElementById("success-redirect-btn");
                if (redirectBtn) {
                    redirectBtn.onclick = () => {
                        if (data.tracking_url) window.location.href = data.tracking_url;
                    };
                }
                successModal && successModal.show();
            }

            else if (resp.status === 200) {
                // Duplicate or existing booking
                const detailsEl = document.getElementById("duplicate-details");
                if (detailsEl) {
                    detailsEl.innerHTML = `
                        <strong>${escapeHtml(data.customer_name || payload.customer_name)}</strong><br>
                        Guests: ${escapeHtml(String(data.no_of_guests || payload.no_of_guests))}<br>
                        ${data.special_notes ? `Notes: ${escapeHtml(data.special_notes)}` : ""}
                    `;
                }
                const redirectBtn = document.getElementById("duplicate-redirect-btn");
                if (redirectBtn) {
                    redirectBtn.onclick = () => {
                        if (data.tracking_url) window.location.href = data.tracking_url;
                    };
                }
                duplicateModal && duplicateModal.show();
            }

            else {
                ModalService.showError(data.error || "Something went wrong while booking the table.");
            }

        } catch (err) {
            console.error("Network error:", err);
            ModalService.showError("Network error. Please try again.");
        } finally {
            // restore button state
            const registerBtnFinal = document.getElementById("register-btn");
            if (registerBtnFinal) {
                registerBtnFinal.disabled = false;
                registerBtnFinal.innerHTML = originalHTML || `<i class="fas fa-user-plus me-2"></i> Book Table`;
            }
        }
    }

    // --------------------------
    // Escape helper for innerHTML insertion
    // --------------------------
    function escapeHtml(str) {
        if (!str && str !== 0) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // --------------------------
    // Event binding
    // --------------------------
    const registerBtn = document.getElementById("register-btn");
    if (registerBtn) {
        registerBtn.addEventListener("click", async (e) => {
            e.preventDefault();
            await submitBooking();
        });
    }

    // --------------------------
    // Initialize page
    // --------------------------
    await loadVendorInfo();
});
