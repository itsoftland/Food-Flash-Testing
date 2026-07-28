const base = AppUtils.getStartUrl();
const apiModulePath = `${base}static/utils/js/apiEndpoints.js`;
let apiEndpoints;

try {
    const endpointsModule = await import(apiModulePath);
    apiEndpoints = endpointsModule.API_ENDPOINTS;
} catch (error) {
    console.error("Failed to import apiEndpoints:", error);
}

export const AddOutletService = (() => {
    let locationId = null;
    let selectedVendorIds = new Set();
    
    const fetchOutlets = async () => {
        try {
            const response = await fetch(
                `${apiEndpoints.FETCH_OUTLETS}?location_id=${locationId}`
            );
            return response.ok ? await response.json() : [];
        } catch (err) {
            console.error("Fetch error:", err);
            return [];
        }
    };

    const toggleSelection = (tile, vendorId) => {
        tile.classList.toggle("selected");
        tile.classList.contains("selected")
            ? selectedVendorIds.add(vendorId)
            : selectedVendorIds.delete(vendorId);
    };

    const renderOutlets = (outlets) => {
        const outletList = document.getElementById("outlet-list");
        outletList.innerHTML = outlets.length
            ? ""
            : "<p class='text-center'>No outlets found</p>";

        outlets.forEach(outlet => {
            const tile = document.createElement("div");
            tile.className = "outlet-tile";
            tile.dataset.vendorId = outlet.vendor_id;
            tile.dataset.name = outlet.name;
            tile.dataset.location = outlet.location || "";

            tile.innerHTML = `
                <img src="${outlet.logo}" alt="${outlet.name}">
                <p class="outlet-name">${outlet.name}</p>
                <p class="outlet-location">${outlet.location || ''}</p>
            `;

            if (selectedVendorIds.has(String(outlet.vendor_id))) {
                tile.classList.add("selected");
            }

            tile.addEventListener("click", () => {
                toggleSelection(tile, String(outlet.vendor_id));
            });

            outletList.appendChild(tile);
        });
    };

    const isDineFlashBuffet = () =>
        String(window.PROJECT_NAME || "").trim().toLowerCase() === "dine_flash_buffet";

    /**
     * Dine Flash Buffet ONLY: Home "+" → Multi-Order additional-order funnel.
     *
     * Lifecycle (must not skip table_booking):
     *   markAdditionalOrderIntent (session)
     *   → buffet/table_booking?vendor_id=...  (manual table entry)
     *   → utility_selection → combined_options
     *   → submit is_additional_order=true → registry / Multi-Order Mode
     *   → Home → Active Order Selector
     *
     * Intent is marked here and survives table_booking → utility → combined
     * via sessionStorage. table_booking must not clear it and does not need
     * to re-mark (QR entry is Order-1; "+" is the additional-order entry).
     * Same vendor source as order_confirmation "Place Another Order".
     */
    const startBuffetAdditionalOrder = async (event) => {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }
        // Primary: same key as order_confirmation / table_booking.
        // Fallback: Home identity (set by Order-1 redirect, restore, selector, PWA
        // handoff). buffet_vendor_id is only written on table_booking and is not
        // rehydrated by restore/handoff — so it can be missing while "+" is usable.
        const vendorId =
            localStorage.getItem("buffet_vendor_id") ||
            (typeof AppUtils.storageGet === "function"
                ? AppUtils.storageGet("activeVendor")
                : null);
        if (!vendorId) {
            AppUtils.showToast("Vendor is missing. Please scan the table QR again.");
            return;
        }
        try {
            const mod = await import("../buffet/services/multiOrderModeService.js");
            if (!mod || typeof mod.markAdditionalOrderIntent !== "function") {
                console.error("[buffet] markAdditionalOrderIntent unavailable; staying on Home");
                AppUtils.showToast("Unable to start another order. Please try again.");
                return;
            }
            mod.markAdditionalOrderIntent();
        } catch (err) {
            console.error("[buffet] markAdditionalOrderIntent failed; staying on Home:", err);
            AppUtils.showToast("Unable to start another order. Please try again.");
            return;
        }
        // Fresh draft for the additional order: force manual table re-entry and
        // a clean utility selection. Do not clear buffet_additional_order_intent.
        try {
            sessionStorage.removeItem("buffet_table_number");
            sessionStorage.removeItem("buffet_selected_utilities");
        } catch (e) {
            // ignore
        }
        // No QR / table_no query params — table_booking stays editable for manual entry.
        window.location.href = `${base}buffet/table_booking/?vendor_id=${vendorId}`;
    };

    const openModal = async () => {
        locationId = await AppUtils.get(); // from utils.js
    
        if (!locationId) {
            AppUtils.showToast("Location ID is missing. Please scan or provide location");
            return;
        }
    
        selectedVendorIds.clear();
    
        // Ensure vendor IDs are stored as strings
        const storedVendorIds = AppUtils.getStoredVendors().map(String);
        storedVendorIds.forEach(id => selectedVendorIds.add(id));
    
        const outlets = await fetchOutlets();
        renderOutlets(outlets);
    
        // ✅ Use Bootstrap API to show the modal properly
        const modalElement = document.getElementById("addOutletModal");
        if (modalElement) {
            const bsModal = new bootstrap.Modal(modalElement, {
                backdrop: 'static',
                keyboard: true
            });
            bsModal.show();
        }
    };

    const onAddOutletClick = async (event) => {
        if (isDineFlashBuffet()) {
            await startBuffetAdditionalOrder(event);
            return;
        }
        await openModal();
    };
    
    const bindEvents = () => {
        const addBtn = document.getElementById("add-outlet-btn");
        // Avoid stacking handlers when init runs more than once on the same node
        // (e.g. scripts.js + VendorUIService). Recreated buttons bind normally.
        if (addBtn && addBtn.dataset.addOutletBound !== "1") {
            addBtn.dataset.addOutletBound = "1";
            // Buffet: strip Bootstrap modal attrs so data-api cannot open Add Outlet.
            if (isDineFlashBuffet()) {
                addBtn.removeAttribute("data-bs-toggle");
                addBtn.removeAttribute("data-bs-target");
            }
            addBtn.addEventListener("click", onAddOutletClick);
        }

        document.getElementById("continue-btn")?.addEventListener("click", () => {
            if (selectedVendorIds.size === 0) {
                AppUtils.showToast("Please select at least one outlet");
                return;
            }

            const vendorIdArray = Array.from(selectedVendorIds);
            const finalVendorIds = vendorIdArray.join(",");

            // ✅ Get the last selected outlet's vendor ID
            const lastVendorId = vendorIdArray[vendorIdArray.length - 1];

            // ✅ Find that tile and get its name
            const selectedTile = document.querySelector(`.outlet-tile[data-vendor-id="${lastVendorId}"]`);
            const selectedOutletName = selectedTile?.dataset?.name || "Outlet";

            // ✅ Save to localStorage
            AppUtils.setSelectedOutletName(selectedOutletName);
            window.location.href = `${base}home/?location_id=${locationId}&vendor_id=${finalVendorIds}`;
        });
    };

    return {
        init: bindEvents
    };
})();
