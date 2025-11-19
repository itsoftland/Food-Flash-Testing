/**
 * ==========================================================
 * 📘 Public Passenger Registration Script (with Modal Wiring)
 * ==========================================================
 */

document.addEventListener("DOMContentLoaded", async () => {

    const base = window.BASE || "/caller_on/";
    const projectName = (window.PROJECT_NAME || "caller_on").toLowerCase();

    let apiEndpoints,ModalService;

    // Import API endpoints
    try {
        const endpointsModule = await import(`${base}static/utils/js/apiEndpoints.js`);
        const modalServiceModule = await import(`${base}static/utils/js/services/modalService.js`);
        ModalService = modalServiceModule.ModalService;
        apiEndpoints = endpointsModule.API_ENDPOINTS;
    } catch (err) {
        console.error("❌ Failed to import apiEndpoints:", err);
        return;
    }
    // Get the modal instance
    const confirmationModalEl = document.getElementById('confirmationModal');
    const confirmationModal = bootstrap.Modal.getInstance(confirmationModalEl);

    // Hide the modal
    if (confirmationModal) {
        console.log("modal hided")
        confirmationModal.hide();
    } else {
        // If the instance doesn't exist yet, create one and hide it
        bootstrap.Modal.getOrCreateInstance(confirmationModalEl).hide();
    }

    // Disable Scan button (coming soon)
    // const scanBtn = document.getElementById("scan-btn");
    // if (scanBtn) scanBtn.classList.add("disabled-feature");

    // --------------------------
    // Extract Query Params
    // --------------------------
    function getParam(key) {
        const params = new URLSearchParams(window.location.search);
        return params.get(key);
    }

    const vendorId = getParam("vendor_id");

    // --------------------------
    // Load Vendor Info
    // --------------------------
    async function loadVendorInfo() {
        if (!vendorId) return;

        try {
            const response = await fetch(apiEndpoints.VENDOR_LOGOS, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vendor_ids: [parseInt(vendorId)] })
            });

            const data = await response.json();
            if (!data.length) return;

            const vendor = data[0];

            document.getElementById("vendor-name").textContent =
                vendor.name || vendor.alias_name || "Vendor";

            document.getElementById("vendor-logo").src =
                vendor.logo_url;
        } catch (err) {
            console.error("❌ Error loading vendor:", err);
        }
    }

    // --------------------------
    // Bootstrap Modal Helpers
    // --------------------------
    function getModal(id) {
        return new bootstrap.Modal(document.getElementById(id));
    }

    const duplicateModal = getModal("duplicateModal");
    const successModal = getModal("successModal");

    // --------------------------
    // Build Payload
    // --------------------------
    function buildPayload() {
        return {
            vendor_id: parseInt(vendorId),
            flight_no: document.getElementById("flight_no").value.trim(),
            pnr_no: document.getElementById("pnr_no").value.trim(),
            seat_no: document.getElementById("seat_no").value.trim(),
            zone: document.getElementById("zone").value.trim(),
            passenger_name: document.getElementById("passenger_name").value.trim()
        };
    }

    // --------------------------
    // Handle Register Click
    // --------------------------
    async function submitPassenger() {
        const registerBtn = document.getElementById("register-btn");

        // Prevent double-click
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

            // ------------------------------
            // SUCCESS (201)
            // ------------------------------
            if (resp.status === 201) {
                document.getElementById("success-details").innerHTML = `
                    <strong>${data.passenger_name}</strong><br>
                    Seat: ${data.seat_no}<br>
                    Flight: ${data.flight_no}
                `;
                document.getElementById("success-redirect-btn").onclick = () => {
                    window.location.href = data.tracking_url;
                };
                successModal.show();
            }

            // ------------------------------
            // DUPLICATE (200)
            // ------------------------------
            else if (resp.status === 200) {
                document.getElementById("duplicate-details").innerHTML = `
                    <strong>${data.passenger_name}</strong><br>
                    Seat: ${data.seat_no}<br>
                    Flight: ${data.flight_no}
                `;
                document.getElementById("duplicate-redirect-btn").onclick = () => {
                    window.location.href = data.tracking_url;
                };
                duplicateModal.show();
            }

            else {
                ModalService.showError(data.error || "Something went wrong.");
            }
        }

        catch (err) {
            console.error("❌ Network error:", err);
            ModalService.showError("Network error. Try again.");
        }

        finally {
            // Re-enable only if modal is *not* shown
            // (Only needed if API returns error)
            registerBtn.disabled = false;
            registerBtn.innerHTML = `<i class="fas fa-user-plus me-2"></i> Register`;
        }
    }


    // --------------------------
    // Register Button Binding
    // --------------------------
    const registerBtn = document.getElementById("register-btn");
    if (registerBtn) {
        registerBtn.addEventListener("click", submitPassenger);
    }

    // // Coming soon scanning
    // if (scanBtn) {
    //     scanBtn.addEventListener("click", () => {
    //         alert("Boarding Pass Scanning Coming Soon!");
    //     });
    // }

    // Init
    await loadVendorInfo();
});
