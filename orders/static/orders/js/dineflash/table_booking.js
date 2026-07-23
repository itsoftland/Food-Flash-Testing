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
 *        - 201 → New booking created (show successModal — page-local, before ffGlobalSuccessModal in DOM)
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
 *         - successModal, duplicateModal (if present)
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
    // Hard guard: this script must only run for Dine Flash.
    // Even if another variant accidentally includes this file/template,
    // exit immediately to avoid side effects.
    const path = String(window.location?.pathname || "").toLowerCase();
    const project = String(window.PROJECT_NAME || "").toLowerCase();
    const hasDineFlashQrTimer = Boolean(document.getElementById("qr-expiry-timer"));
    if (!path.includes("/dine_flash/") && project !== "dine_flash" && !hasDineFlashQrTimer) {
        return;
    }

    // console.log("UTILITY ENABLED:",window.UTILITIES_ENABLED);
    const base = window.BASE || "/caller_on/";

    let apiEndpoints, ModalService, vendorId;
    let PermissionService = null;
    let qrDate = null;
    let qrTime = null;
    let qrSession = null;
    let qrExpiresAtEpoch = null;
    let expiryTimerInterval = null;

    function getParam(key) {
        const params = new URLSearchParams(window.location.search);
        return params.get(key);
    }

    // --------------------------
    // Load required modules
    // --------------------------
    try {
        const [endpointsModule, modalServiceModule, vendorStore, permissionModule] = await Promise.all([
            import(`${base}static/utils/js/apiEndpoints.js`),
            import(`${base}static/utils/js/services/modalService.js`),
            import(`${base}static/orders/js/config/vendorStore.js`),
            import(`${base}static/orders/js/services/permissionService.js`),
        ]);

        apiEndpoints = endpointsModule.API_ENDPOINTS;
        ModalService = modalServiceModule.ModalService;
        PermissionService = permissionModule.PermissionService;

        const urlVendorId = getParam("vendor_id");
        const resolvedVendorId =
            typeof window.RESOLVED_VENDOR_ID === "string" ? window.RESOLVED_VENDOR_ID.trim() : "";
        qrDate = getParam("qr_date") || (typeof window.QR_DATE === "string" ? window.QR_DATE.trim() : "") || null;
        qrTime = getParam("qr_time") || (typeof window.QR_TIME === "string" ? window.QR_TIME.trim() : "") || null;
        qrSession = getParam("qr_session");

        // Vendor ID priority: URL -> server-resolved (hashed QR) -> stored
        const effectiveVendorId = urlVendorId || resolvedVendorId;
        if (effectiveVendorId) {
            vendorId = parseInt(effectiveVendorId, 10);
            // persist for future loads (handles iOS fallback)
            if (!isNaN(vendorId)) {
                await vendorStore.setVendorId(vendorId);
            } else {
                console.warn("Invalid vendor_id in URL:", effectiveVendorId);
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

        // Seed QR state from server-rendered globals (no network): correct countdown for qr_session links.
        const tmplEpoch = Number(window.QR_EXPIRES_AT_EPOCH);
        if (Number.isFinite(tmplEpoch) && tmplEpoch > 0) {
            qrExpiresAtEpoch = tmplEpoch;
        }
        const tmplSession = typeof window.QR_SESSION === "string" ? window.QR_SESSION.trim() : "";
        if (!qrSession && tmplSession) {
            qrSession = tmplSession;
        }

        // Keep vendor_id in URL for Dine Flash QR-gated workflow.
        // Backend validation requires vendor_id + qr_date + qr_time.

    } catch (err) {
        console.error("Failed loading modules:", err);
        return;
    }

    function formatCountdown(secondsLeft) {
        const s = Math.max(0, Math.floor(secondsLeft));
        const mm = String(Math.floor(s / 60)).padStart(2, "0");
        const ss = String(s % 60).padStart(2, "0");
        return `${mm}:${ss}`;
    }

    function startExpiryCountdown() {
        const expiryMinutes = Number(window.QR_EXPIRY_MINUTES || 0);
        const banner = document.getElementById("qr-expiry-banner");
        const timerEl = document.getElementById("qr-expiry-timer");
        if (!banner || !timerEl) return;
        if (!expiryMinutes || expiryMinutes <= 0) {
            banner.classList.add("d-none");
            banner.setAttribute("aria-hidden", "true");
            return;
        }

        // Prefer server-issued expiry when available (qr_session exchange),
        // otherwise fall back to local parse from qr_date/qr_time.
        let expiryAtMs = null;
        if (qrExpiresAtEpoch) {
            expiryAtMs = Number(qrExpiresAtEpoch) * 1000;
        } else {
            // Session expiry is scan/load time + window (server: _create_dine_flash_qr_session),
            // not TV qr_date/qr_time + window. Approximate until QR_EXPIRES_AT_EPOCH / exchange.
            expiryAtMs = Date.now() + expiryMinutes * 60 * 1000;
        }

        const tick = () => {
            const now = Date.now();
            const leftMs = expiryAtMs - now;
            const leftSec = leftMs / 1000;
            timerEl.textContent = formatCountdown(leftSec);
            if (leftMs <= 0) {
                clearInterval(expiryTimerInterval);
                expiryTimerInterval = null;
                banner.classList.remove("alert-warning");
                banner.classList.add("alert-danger");
                banner.textContent = "QR expired. Please scan the new QR code on the TV.";
                const btn = document.getElementById("register-btn");
                if (btn) btn.disabled = true;
            }
        };

        tick();
        expiryTimerInterval = setInterval(tick, 1000);
    }

    function restartExpiryCountdownFromServerEpoch(epochSec) {
        const n = Number(epochSec);
        if (!Number.isFinite(n) || n <= 0) return;
        qrExpiresAtEpoch = n;
        if (expiryTimerInterval) {
            clearInterval(expiryTimerInterval);
            expiryTimerInterval = null;
        }
        startExpiryCountdown();
    }

    /** Stop countdown and hide the banner once booking succeeded (or duplicate handled). */
    function stopQrExpiryCountdown() {
        if (expiryTimerInterval) {
            clearInterval(expiryTimerInterval);
            expiryTimerInterval = null;
        }
        const banner = document.getElementById("qr-expiry-banner");
        if (banner) {
            banner.classList.add("d-none");
            banner.setAttribute("aria-hidden", "true");
        }
        const timerEl = document.getElementById("qr-expiry-timer");
        if (timerEl) {
            timerEl.textContent = "";
        }
    }

    async function exchangeQrToSession() {
        // If we already have a session token, nothing to do.
        if (qrSession) return;
        if (!vendorId || !qrDate || !qrTime) return;
        if (!apiEndpoints?.DINE_FLASH_QR_EXCHANGE) return;

        try {
            const url = new URL(apiEndpoints.DINE_FLASH_QR_EXCHANGE, window.location.origin);
            url.searchParams.set("vendor_id", String(vendorId));
            url.searchParams.set("qr_date", String(qrDate));
            url.searchParams.set("qr_time", String(qrTime));

            const resp = await fetch(url.toString(), { method: "GET" });
            const data = await resp.json();
            if (!resp.ok) {
                ModalService?.showError?.(data?.error || "QR expired. Please scan the new QR code on the TV.");
                return;
            }
            qrSession = data.qr_session;
            restartExpiryCountdownFromServerEpoch(data.expires_at_epoch);

            // Encrypt URL (opaque token) after load
            try {
                const current = new URL(window.location.href);
                current.searchParams.set("qr_session", qrSession);
                current.searchParams.delete("qr_date");
                current.searchParams.delete("qr_time");
                history.replaceState({}, document.title, current.toString());
            } catch (e) {
                // ignore
            }
        } catch (e) {
            // ignore network errors; backend will still enforce on submit
        }
    }

    void exchangeQrToSession();

    // --------------------------
    // Load vendor branding
    // --------------------------
    async function loadVendorInfo() {
        if (!vendorId) return;

        try {
            const nameEl = document.getElementById("vendor-name");
            const logoEl = document.getElementById("vendor-logo");

            const response = await fetch(apiEndpoints.VENDOR_LOGOS, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vendor_ids: [vendorId] })
            });

            const data = await response.json();
            if (!data || !data.length) return;

            const vendor = data[0];

            // Dine Flash requirement: show alias name first on table booking page.
            if (nameEl) nameEl.textContent = vendor.alias_name || vendor.name || "Vendor";
            if (logoEl) {
                // Avoid empty-src fetch to current page (shows broken icon)
                logoEl.removeAttribute("src");

                const rawUrl = vendor.logo_url ? String(vendor.logo_url) : "";
                if (!rawUrl) return;

                // Ensure URL is safely encoded (spaces etc.)
                const safeUrl = rawUrl.replace(/ /g, "%20");

                // Fallback: some deployments serve media at /media instead of /<project>/media
                const project = (window.PROJECT_NAME || "dine_flash").trim();
                const altUrl = safeUrl.includes(`/${project}/media/`)
                    ? safeUrl.replace(`/${project}/media/`, "/media/")
                    : safeUrl;

                logoEl.onerror = () => {
                    if (logoEl.src !== altUrl) {
                        logoEl.src = altUrl;
                    }
                };
                logoEl.src = safeUrl;
            }

        } catch (err) {
            console.error("Error loading vendor info:", err);
        }
    }

    // --------------------------
    // Load utilities (utility_list API)
    // --------------------------
    async function loadUtilities() {
        const utilitiesEnabled = window.UTILITIES_ENABLED === true || window.UTILITIES_ENABLED === "true";
        if (!utilitiesEnabled) return;
        if (!vendorId || !apiEndpoints || !apiEndpoints.UTILITY_LIST) {
            console.warn("Missing vendorId or UTILITY_LIST endpoint.");
            return;
        }

        const grid = document.getElementById("utility-grid");
        if (grid && !grid.dataset.loaded) {
            grid.innerHTML =
                '<div class="col-12 text-muted small text-center py-2" id="utility-grid-loading">Loading areas…</div>';
        }

        try {
            const url = `${apiEndpoints.UTILITY_LIST}?vendor_id=${encodeURIComponent(vendorId)}`;

            const response = await fetch(url, {
                method: "GET",
                headers: { "Accept": "application/json" }
            });

            const data = await response.json();

            if (!response.ok) {
                ModalService.showError(data.error || "Unable to load utilities.");
                return;
            }
            // console.log("Utility Data:",data)

            renderUtilities(data.utilities || []);
            if (grid) grid.dataset.loaded = "1";
        }
        catch (err) {
            console.error("Error loading utilities:", err);
            ModalService.showError("Network error while loading utilities.");
        }
    }

    /* --------------------------------------------------
    Render Utility List (Premium Two-Column Blocks)
    -------------------------------------------------- */
    function renderUtilities(utilities) {
        const container = document.getElementById("utility-grid");
        if (!container) return;

        container.innerHTML = ""; // clear previous (removes loading placeholder)

        container.classList.add("utility-grid-2col");

        utilities.forEach(util => {
            const item = document.createElement("div");
            item.className = "utility-item premium-utility-card";
            item.dataset.id = util.id;

            item.innerHTML = `
                <div class="utility-display">
                    ${escapeHtml(util.display_name)}
                </div>
            `;

            // Single-select logic
            item.addEventListener("click", () => {
                document
                    .querySelectorAll(".utility-item.selected")
                    .forEach(el => el.classList.remove("selected"));

                item.classList.add("selected");
            });

            container.appendChild(item);
        });
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
    let bookingBlinkInterval = null;

    function stopBookingIdentifierBlink() {
        if (bookingBlinkInterval) {
            clearInterval(bookingBlinkInterval);
            bookingBlinkInterval = null;
        }
        document.querySelectorAll(".booking-identifier-blink").forEach((el) => {
            el.style.setProperty("visibility", "visible", "important");
            el.style.setProperty("opacity", "1", "important");
        });
    }

    function startBookingIdentifierBlink(container) {
        stopBookingIdentifierBlink();
        if (!container) return;
        const elements = container.querySelectorAll(".booking-identifier-blink");
        if (!elements.length) return;

        elements.forEach((el) => {
            el.style.setProperty("visibility", "visible", "important");
            el.style.setProperty("opacity", "1", "important");
        });

        let dimmed = false;
        bookingBlinkInterval = setInterval(() => {
            dimmed = !dimmed;
            elements.forEach((el) => {
                el.style.setProperty("opacity", dimmed ? "0.45" : "1", "important");
            });
        }, 700);
    }

    function forceWrapIdentifierForBlink(detailsEl) {
        if (!detailsEl) return;
        const html = detailsEl.innerHTML;
        if (!html) return;

        let updated = html.replace(
            /(Token\s*No\s*:\s*)(<strong\b[^>]*>.*?<\/strong>)/i,
            (_m, label, strongTag) => `${label}${strongTag.replace("<strong", '<strong class="booking-identifier-blink"')}`
        );
        updated = updated.replace(
            /(Booking\s*ID\s*:\s*)(<strong\b[^>]*>.*?<\/strong>)/i,
            (_m, label, strongTag) => `${label}${strongTag.replace("<strong", '<strong class="booking-identifier-blink"')}`
        );

        if (updated !== html) {
            detailsEl.innerHTML = updated;
        }
    }

    // --------------------------
    // Build booking payload
    // --------------------------
    function buildPayload() {
        const customerNameEl = document.getElementById("customer_name");
        const guestsEl = document.getElementById("no_of_packs");
        const notesEl = document.getElementById("remarks");
        const selectedItem = document.querySelector(".utility-item.selected");

        let utilityId = null;

        if (window.UTILITIES_ENABLED == "true" && selectedItem) {

            utilityId = selectedItem.dataset.id;
        }

        const payload = {
            vendor_id: vendorId,
            customer_name: customerNameEl ? customerNameEl.value.trim() : "",
            no_of_guests: guestsEl ? parseInt(guestsEl.value, 10) || 0 : 0,
            special_notes: notesEl ? notesEl.value.trim() : "",
            utility_id: utilityId,
            // Dine Flash QR gate: carry opaque qr_session so user can't tamper.
            qr_session: qrSession,
        };

        // Send policy: stored order_lookup_id if present, else getBrowserId().
        // Never overwrites browser_id; recovery key is a separate field/key.
        const storedLookupId =
            typeof AppUtils !== "undefined" && typeof AppUtils.getOrderLookupId === "function"
                ? AppUtils.getOrderLookupId()
                : null;
        const orderLookupId =
            storedLookupId ||
            (typeof AppUtils !== "undefined" && typeof AppUtils.getBrowserId === "function"
                ? AppUtils.getBrowserId()
                : null);
        if (orderLookupId) {
            payload.order_lookup_id = orderLookupId;
            if (typeof AppUtils.setOrderLookupId === "function") {
                AppUtils.setOrderLookupId(orderLookupId);
            }
        }

        // console.log(payload)
        return payload;
    }

    function cleanAndFormatName(name) {
        if (!name) return "";

        // Remove leading/trailing spaces + collapse multiple spaces to one
        name = name.trim().replace(/\s+/g, " ");

        // Auto-capitalize each word: john doe → John Doe
        name = name.split(" ")
            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
            .join(" ");

        return name;
    }

    function getCSRFToken() {
        const cookie = document.cookie
            .split(";")
            .map((c) => c.trim())
            .find((c) => c.startsWith("csrftoken="));
        return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    }

    function extractReadableError(err) {
        if (!err) return null;
        if (typeof err === "string") return err;
        if (Array.isArray(err)) {
            const parts = err.map(extractReadableError).filter(Boolean);
            return parts.length ? parts.join(", ") : null;
        }
        if (typeof err === "object") {
            const entries = Object.entries(err);
            if (!entries.length) return null;
            const first = entries[0];
            const field = String(first[0] || "error");
            const message = extractReadableError(first[1]);
            if (!message) return null;
            return field === "non_field_errors" || field === "error"
                ? message
                : `${field}: ${message}`;
        }
        return String(err);
    }

    function escapeHtml(str) {
        if (!str && str !== 0) return "";
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    /** True when public booking ref is the same value as internal token (e.g. int 90 vs string "90"). */
    function bookingRefMatchesToken(tokenRaw, bookingRaw) {
        if (tokenRaw === undefined || tokenRaw === null) return false;
        if (bookingRaw === undefined || bookingRaw === null) return false;
        const t = String(tokenRaw).trim();
        const b = String(bookingRaw).trim();
        if (t === b) return true;
        const tn = Number(t);
        const bn = Number(b);
        return Number.isFinite(tn) && Number.isFinite(bn) && tn === bn;
    }

    /** Either "Token No" or "Booking ID", never both (same underlying value → token label only). */
    function buildTableBookingIdentifierLine(data) {
        const blinkValue = (value) => `<strong class="booking-identifier-blink">${escapeHtml(String(value).trim())}</strong>`;
        const bookingNo = data.table_booking_no;
        const tokenRaw = data.token_no;
        if (bookingRefMatchesToken(tokenRaw, bookingNo)) {
            const disp =
                tokenRaw !== undefined && tokenRaw !== null && String(tokenRaw).trim() !== ""
                    ? String(tokenRaw).trim()
                    : String(bookingNo).trim();
            return `Token No: ${blinkValue(disp)}<br>`;
        }
        if (bookingNo !== undefined && bookingNo !== null && String(bookingNo).trim() !== "") {
            return `Booking ID: ${blinkValue(bookingNo)}<br>`;
        }
        if (tokenRaw !== undefined && tokenRaw !== null && String(tokenRaw).trim() !== "") {
            return `Token No: ${blinkValue(tokenRaw)}<br>`;
        }
        return "";
    }

    // --------------------------
    // client-side validation
    // --------------------------
    function validatePayload(payload) {

        // ------------------------------
        // 1. Customer Name Validations
        // ------------------------------

        // Clean & auto-format the name BEFORE validation
        payload.customer_name = cleanAndFormatName(payload.customer_name);

        if (!payload.customer_name) {
            ModalService.showError("Customer name is required.");
            return false;
        }
        if (payload.customer_name.length < 2) {
            ModalService.showError("Name is too short.");
            return false;
        }
        if (payload.customer_name.length > 40) {
            ModalService.showError("Name cannot exceed 40 characters.");
            return false;
        }

        // ❌ Only alphabets + spaces allowed (fine-dine standard)
        const namePattern = /^[A-Za-z ]+$/;
        if (!namePattern.test(payload.customer_name)) {
            ModalService.showError("Name can contain only letters and spaces.");
            return false;
        }

        // ------------------------------
        // 2. Pax Count Validations
        // ------------------------------
        if (!payload.no_of_guests || payload.no_of_guests <= 0) {
            ModalService.showError("Please enter a valid number of pax.");
            return false;
        }
        if (payload.no_of_guests > 20) {
            ModalService.showError("Maximum 20 pax can be booked online.");
            return false;
        }

        // ------------------------------
        // 3. Utility Area Selection
        // ------------------------------
        if (window.UTILITIES_ENABLED === true || window.UTILITIES_ENABLED === "true") {
            if (!payload.utility_id) {
                ModalService.showError("Please select your preferred area.");
                return false;
            }
        }

        // ------------------------------
        // 4. Special Notes Limit (Optional)
        // ------------------------------
        if (payload.special_notes && payload.special_notes.length > 200) {
            ModalService.showError("Special instructions cannot exceed 200 characters.");
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
            await exchangeQrToSession();
            if ((qrDate && qrTime || (window.QR_DATE && window.QR_TIME)) && !qrSession) {
                ModalService.showError(
                    "Unable to verify your QR session. Check your connection, refresh the page, or scan the TV code again."
                );
                return;
            }

            const payload = buildPayload();
            // console.log("Payload:",payload)

            if (!validatePayload(payload)) {
                return;
            }

            const resp = await fetch(apiEndpoints.TABLE_BOOKING, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCSRFToken(),
                },
                credentials: "same-origin",
                body: JSON.stringify(payload)
            });

            const data = await resp.json();

            if (resp.status === 201) {
                stopQrExpiryCountdown();
                // New booking
                const finalCustomerName = data.customer_name || payload.customer_name;
                AppUtils.setCustomerName(finalCustomerName);

                const detailsEl = document.querySelector(
                    "#successModal.register-modal #success-details"
                );
                if (detailsEl) {
                    const idLine = buildTableBookingIdentifierLine(data);
                    detailsEl.innerHTML = `
                        <strong>${escapeHtml(data.customer_name || payload.customer_name)}</strong><br>
                        Pax: ${escapeHtml(String(data.no_of_guests || payload.no_of_guests))}<br>
                        ${idLine}
                        ${data.special_notes ? `Notes: ${escapeHtml(data.special_notes)}` : ""}
                    `;
                    forceWrapIdentifierForBlink(detailsEl);
                    startBookingIdentifierBlink(detailsEl);
                }
                const redirectBtn = document.querySelector(
                    "#successModal.register-modal #success-redirect-btn"
                );
                if (redirectBtn) {
                    redirectBtn.onclick = () => {
                        if (data.tracking_url) window.location.href = data.tracking_url;
                    };
                }
                successModal && successModal.show();
            }

            else if (resp.status === 200) {
                stopQrExpiryCountdown();
                // Duplicate or existing booking
                const detailsEl = document.getElementById("duplicate-details");
                if (detailsEl) {
                    detailsEl.innerHTML = `
                        <strong>${escapeHtml(data.customer_name || payload.customer_name)}</strong><br>
                        Pax: ${escapeHtml(String(data.no_of_guests || payload.no_of_guests))}<br>
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
                const backendError =
                    extractReadableError(data?.error) ||
                    extractReadableError(data?.detail) ||
                    extractReadableError(data);
                ModalService.showError(backendError || "Something went wrong while booking the table.");
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
    // Event binding
    // --------------------------
    const registerBtn = document.getElementById("register-btn");
    if (registerBtn) {
        registerBtn.addEventListener("click", async (e) => {
            e.preventDefault();
            await submitBooking();
        });
    }

    const successModalEl = document.getElementById("successModal");
    if (successModalEl) {
        successModalEl.addEventListener("shown.bs.modal", () => {
            const detailsEl = successModalEl.querySelector("#success-details");
            forceWrapIdentifierForBlink(detailsEl);
            startBookingIdentifierBlink(detailsEl);
        });
        successModalEl.addEventListener("hidden.bs.modal", stopBookingIdentifierBlink);
    }

    // --------------------------
    // Initialize page: expiry + permissions first; network work in parallel
    // --------------------------
    startExpiryCountdown();
    if (PermissionService) {
        PermissionService.init({ dineFlashFastPermissionUX: true });

        const permissionModalEl = document.getElementById("permissionModal");
        if (permissionModalEl) {
            permissionModalEl.addEventListener(
                "shown.bs.modal",
                () => {
                    try {
                        const ss = window.speechSynthesis;
                        if (!ss) return;
                        ss.getVoices();
                        ss.addEventListener("voiceschanged", () => ss.getVoices(), { once: true });
                    } catch (_) {
                        /* noop */
                    }
                },
                false,
            );
        }

        const openPermissionWhenIdle = () => {
            if (typeof requestIdleCallback === "function") {
                requestIdleCallback(() => PermissionService.showModal(), { timeout: 300 });
            } else {
                setTimeout(() => PermissionService.showModal(), 1);
            }
        };
        openPermissionWhenIdle();
    }
    void loadVendorInfo();
    void loadUtilities();
});
