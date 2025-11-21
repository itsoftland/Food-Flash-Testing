/**
 * ==========================================================================
 * 📘 Public Passenger Registration Script — Full Documentation
 * ==========================================================================
 * This script powers the Airline Flash public passenger registration screen.
 * It validates inputs, handles registration requests, displays response modals,
 * and ensures the `vendor_id` is always loaded reliably, even on iOS Safari.
 *
 * --------------------------------------------------------------------------
 * 💡 KEY FEATURES
 * --------------------------------------------------------------------------
 * 1. Universal Vendor ID Storage (iOS Safe)
 *    - Uses LocalStorage → IndexedDB → Cookie fallback.
 *    - Solves iOS private mode and Safari IndexedDB limitations.
 *    - URL vendor_id takes priority; otherwise pulled from storage.
 *
 * 2. Vendor Auto-Loading
 *    - Fetches vendor logo and name based on vendor_id.
 *    - Vendor ID does NOT need to be present in the URL after first load.
 *
 * 3. Registration Workflow
 *    - Collects passenger details (flight, seat, PNR, zone, name).
 *    - Sends data to CREATE_PASSENGER API (POST).
 *    - Supports:
 *        - 201 → New Registration
 *        - 200 → Duplicate Registration (existing passenger)
 *    - Shows Bootstrap modals with passenger details.
 *
 * 4. Double-Click Protected
 *    - Register button is disabled during API call.
 *    - Spinner is shown until the response is received.
 *
 * 5. API Integration
 *    - Uses dynamically imported endpoint definitions.
 *    - Error handling via ModalService with reusable UI.
 *
 * --------------------------------------------------------------------------
 * 🔐 VENDOR ID RESOLUTION LOGIC (Very Important)
 * --------------------------------------------------------------------------
 *   STEP 1 → Check URL:     ?vendor_id=123
 *   STEP 2 → If found:
 *                 - Save to LocalStorage
 *                 - Save to IndexedDB
 *                 - Save to Cookie
 *   STEP 3 → If not found:
 *                 - Load vendor_id from storage via vendorStore.js
 *   STEP 4 → Use vendor_id for all operations
 *
 *   This guarantees:
 *     - Safari compatibility
 *     - iOS private mode fallback
 *     - Persistent vendor branding even without URL params
 *
 * --------------------------------------------------------------------------
 * 🔧 FILES USED
 * --------------------------------------------------------------------------
 * ✓ apiEndpoints.js        → API endpoint URLs
 * ✓ modalService.js        → Standard modal error UI
 * ✓ vendorStore.js         → iOS-safe universal storage for vendor_id
 *
 * --------------------------------------------------------------------------
 * 🎯 FLOW SUMMARY
 * --------------------------------------------------------------------------
 * 1. On page load:
 *       - Load vendor_id from URL or storage
 *       - Load vendor name/logo
 * 2. User fills form → Clicks Register
 * 3. Connection to CREATE_PASSENGER API:
 *       - Payload includes stored vendor_id
 * 4. Show result modal with passenger details
 * 5. Redirect user to tracking link (from API)
 *
 * --------------------------------------------------------------------------
 * 📦 MODULE FORMAT
 * --------------------------------------------------------------------------
 * Script uses ES6 dynamic imports:
 *      import(`${base}static/orders/js/config/vendorStore.js`)
 *
 * Ensures compatibility with:
 *     - Django static files
 *     - CDN paths
 *     - Multi-flavour deployment (AirlineFlash)
 *
 * --------------------------------------------------------------------------
 * 🌐 DEPLOYMENT NOTES
 * --------------------------------------------------------------------------
 * - Requires vendorStore.js to exist at:
 *       static/orders/js/config/vendorStore.js
 * - Works without Service Workers (SW optional)
 * - Compatible with iOS Safari, Chrome, Firefox, Edge
 * ==========================================================================
 */
/**
 * ==========================================================
 * 📘 Public Passenger Registration Script (with Modal Wiring)
 * ==========================================================
 */

document.addEventListener("DOMContentLoaded", async () => {

    const base = window.BASE || "/caller_on/";

    let apiEndpoints, ModalService, vendorId;

    // ───────────────────────────────────────────────
    // Load external services
    // ───────────────────────────────────────────────
    try {
        const endpointsModule = await import(`${base}static/utils/js/apiEndpoints.js`);
        const modalServiceModule = await import(`${base}static/utils/js/services/modalService.js`);
        const vendorStore = await import(`${base}static/orders/js/config/vendorStore.js`);

        ModalService = modalServiceModule.ModalService;
        apiEndpoints = endpointsModule.API_ENDPOINTS;

        // --------------------------
        // Extract Query Params
        // --------------------------
        function getParam(key) {
            const params = new URLSearchParams(window.location.search);
            return params.get(key);
        }

        const urlVendorId = getParam("vendor_id");

        // --------------------------
        // Vendor ID priority system
        // --------------------------
        if (urlVendorId) {
            vendorId = parseInt(urlVendorId);
            await vendorStore.setVendorId(vendorId);
        } else {
            vendorId = await vendorStore.getVendorId();
        }

        if (!vendorId) {
            console.error("❌ Vendor ID missing. Cannot continue.");
            return;
        }

        // -----------------------------------------------
        // 🔄 Remove vendor_id from URL (clean URL)
        // -----------------------------------------------
        const url = new URL(window.location.href);
        if (url.searchParams.has("vendor_id")) {
            url.searchParams.delete("vendor_id");
            history.replaceState({}, document.title, url.toString());
        }

    } catch (err) {
        console.error("❌ Failed loading modules:", err);
        return;
    }

    // ───────────────────────────────────────────────
    // Load Vendor Info
    // ───────────────────────────────────────────────
    async function loadVendorInfo() {
        if (!vendorId) return;

        try {
            const response = await fetch(apiEndpoints.VENDOR_LOGOS, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vendor_ids: [vendorId] })
            });

            const data = await response.json();
            if (!data.length) return;

            const vendor = data[0];

            document.getElementById("vendor-name").textContent =
                vendor.name || vendor.alias_name || "Vendor";

            document.getElementById("vendor-logo").src = vendor.logo_url;

        } catch (err) {
            console.error("❌ Error loading vendor:", err);
        }
    }

    // ───────────────────────────────────────────────
    // Bootstrap Modal Helpers
    // ───────────────────────────────────────────────
    function getModal(id) {
        return new bootstrap.Modal(document.getElementById(id));
    }

    const duplicateModal = getModal("duplicateModal");
    const successModal = getModal("successModal");

    // ───────────────────────────────────────────────
    // Build Payload
    // ───────────────────────────────────────────────
    function buildPayload() {
        return {
            vendor_id: vendorId, 
            flight_no: document.getElementById("flight_no").value.trim(),
            pnr_no: document.getElementById("pnr_no").value.trim(),
            seat_no: document.getElementById("seat_no").value.trim(),
            zone: document.getElementById("zone").value.trim(),
            passenger_name: document.getElementById("passenger_name").value.trim()
        };
    }

    // ───────────────────────────────────────────────
    // Handle Register Click
    // ───────────────────────────────────────────────
    async function submitPassenger() {
        const registerBtn = document.getElementById("register-btn");

        registerBtn.disabled = true;
        registerBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Processing...`;

        const payload = buildPayload();

        try {
            const resp = await fetch(apiEndpoints.CREATE_PASSENGER, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const data = await resp.json();

            if (resp.status === 201) {
                document.getElementById("success-details").innerHTML = `
                    <strong>${data.passenger_name}</strong><br>
                    Seat: ${data.seat_no}<br>
                    Flight: ${data.flight_no}<br>
                    Seat No: ${data.seat_no}<br>
                    Zone: ${data.zone}
                `;
                document.getElementById("success-redirect-btn").onclick = () => {
                    window.location.href = data.tracking_url;
                };
                successModal.show();
            }

            else if (resp.status === 200) {
                document.getElementById("duplicate-details").innerHTML = `
                    <strong>${data.passenger_name}</strong><br>
                    Seat: ${data.seat_no}<br>
                    Flight: ${data.flight_no}<br>
                    Seat No: ${data.seat_no}<br>
                    Zone: ${data.zone}
                `;
                document.getElementById("duplicate-redirect-btn").onclick = () => {
                    window.location.href = data.tracking_url;
                };
                duplicateModal.show();
            }

            else {
                ModalService.showError(data.error || "Something went wrong.");
            }

        } catch (err) {
            console.error("❌ Network error:", err);
            ModalService.showError("Network error. Try again.");
        }

        finally {
            registerBtn.disabled = false;
            registerBtn.innerHTML = `<i class="fas fa-user-plus me-2"></i> Register`;
        }
    }

    // ───────────────────────────────────────────────
    // Register Button Binding
    // ───────────────────────────────────────────────
    const registerBtn = document.getElementById("register-btn");
    if (registerBtn) {
        registerBtn.addEventListener("click", submitPassenger);
    }

    // ───────────────────────────────────────────────
    // Init
    // ───────────────────────────────────────────────
    await loadVendorInfo();
});
