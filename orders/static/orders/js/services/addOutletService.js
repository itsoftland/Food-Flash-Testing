export const AddOutletService = (() => {
    let locationId = null;
    let selectedVendorIds = new Set();

    const fetchOutlets = async () => {
        try {
            console.log("LocationId2",locationId)
            const response = await fetch(`/api/outlets/?location_id=${locationId}`);
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
                <img src="${outlet.logo || '/static/default-logo.png'}" alt="${outlet.name}">
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

    const openModal = async () => {
        locationId = await AppUtils.get(); // from utils.js
        console.log("LocationId",locationId)
    
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
    

    const bindEvents = () => {
        document.getElementById("add-outlet-btn")?.addEventListener("click", openModal);

        document.getElementById("continue-btn")?.addEventListener("click", () => {
            if (selectedVendorIds.size === 0) {
                AppUtils.showToast("Please select at least one outlet");
                return;
            }

            const vendorIdArray = Array.from(selectedVendorIds);
            const finalVendorIds = vendorIdArray.join(",");

            // ✅ Get the last selected outlet's vendor ID
            const lastVendorId = vendorIdArray[vendorIdArray.length - 1];
            console.log("last vendor_id",)

            // ✅ Find that tile and get its name
            const selectedTile = document.querySelector(`.outlet-tile[data-vendor-id="${lastVendorId}"]`);
            const selectedOutletName = selectedTile?.dataset?.name || "Outlet";

            // ✅ Save to localStorage
            AppUtils.setSelectedOutletName(selectedOutletName);
            window.location.href = `/home/?location_id=${locationId}&vendor_id=${finalVendorIds}`;
        });
    };

    return {
        init: bindEvents
    };
})();
