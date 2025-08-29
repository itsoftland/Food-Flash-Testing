// ─────────────────────────────────────
// Early Redirect: Ensure ?location_id is in URL
// ─────────────────────────────────────
(async function redirectIfMissingLocationId() {
    console.log("Checking for redirect conditions...");

    const currentUrl = new URL(window.location.href);
    const urlParams = currentUrl.searchParams;

    const hasLocationParam = urlParams.has("location_id");
    const hasVendorId = await AppUtils.getActiveVendor();
    console.log('ActiveVendorid',hasVendorId)
    const hasTokenNo = await AppUtils.getToken();

    // ✅ Condition 1: If vendor_id and token_no are present → redirect to /home/
    if (hasVendorId || hasTokenNo) {
        console.log("Detected vendor_id or token_no in URL. Redirecting to /home/");

        const locationId = hasLocationParam ? urlParams.get("location_id") : await AppUtils.get();

        if (locationId) {
            const newUrl = new URL(`${window.location.origin}/home/`);
            newUrl.searchParams.set("location_id", locationId);
            newUrl.searchParams.set("vendor_id",hasVendorId);
            newUrl.searchParams.set("token_no", hasTokenNo);
            // ✅ Preserve from_push if present
            if (urlParams.has("from_push")) {
                newUrl.searchParams.set("from_push", urlParams.get("from_push"));
            }

            window.location.replace(newUrl.toString());
        } else {
            console.warn("Missing location_id for home redirect.");
        }

        return;
    }

    // 🚨 Condition 2: If location_id is missing, try to retrieve and redirect
    if (!hasLocationParam) {
        const locationIdFromStorage = await AppUtils.get();
        if (locationIdFromStorage) {
            const newUrl = new URL(window.location.href);
            newUrl.searchParams.set("location_id", locationIdFromStorage);
            console.log("Redirecting with stored location_id:", locationIdFromStorage);
            window.location.replace(newUrl.toString());
        } else {
            console.warn("No location_id found in URL or storage.");
        }
    }
})();



// ─────────────────────────────────────
// Main Logic: Run after DOM is ready
// ─────────────────────────────────────
import { IosPwaInstallService } from './services/iosPwaInstallService.js';

let locationId = null;

document.addEventListener("DOMContentLoaded", async function () {
    // iOS A2HS prompt setup
    IosPwaInstallService.init();

    const agreeBtn = document.getElementById("ios-a2hs-agree");
    const denyBtn = document.getElementById("ios-a2hs-deny");

    if (agreeBtn) {
        agreeBtn.addEventListener("click", () => {
            localStorage.setItem("iosA2HS", "true");
            IosPwaInstallService.dismiss();
        });
    }

    if (denyBtn) {
        denyBtn.addEventListener("click", () => {
            localStorage.setItem("iosA2HS", "false");
            IosPwaInstallService.dismiss();
        });
    }

    // Get location_id from URL
    const urlParams = new URLSearchParams(window.location.search);
    locationId = urlParams.get("location_id");

    // Save to localStorage and cookie if present in URL
    if (locationId) {
        AppUtils.set(locationId); // Stores in both localStorage and cookie
    } else {
        // Try to get from fallback (this path usually won't run due to early redirect)
        locationId = await AppUtils.get();

        if (!locationId) {
            AppUtils.showToast("Location ID is missing. Please scan or provide location.");
            return; // Stop further logic
        }
    }

    // ─────────────────────────────────────
    // Fetch and Render Outlets
    // ─────────────────────────────────────
    fetch(`/api/outlets/?location_id=${locationId}`)
        .then(response => response.json())
        .then(data => {
            const outletList = document.getElementById("outlet-list");
            outletList.innerHTML = "";

            if (data.length === 0) {
                outletList.innerHTML = "<p class='text-center'>No outlets found</p>";
                return;
            }

            data.forEach(outlet => {
                const tile = document.createElement("div");
                tile.className = "outlet-tile";
                tile.dataset.vendorId = outlet.vendor_id;
                tile.dataset.name = outlet.name;
                tile.dataset.location = outlet.location || '';

                tile.innerHTML = `
                    <img src="${outlet.logo || '/static/default-logo.png'}" alt="${outlet.name}">
                    <p class="outlet-name">${outlet.name}</p>
                    <p class="outlet-location">${outlet.location || ''}</p>
                `;

                tile.addEventListener("click", function () {
                    tile.classList.toggle("selected");
                });

                outletList.appendChild(tile);
            });
        })
        .catch(error => console.error("Error fetching outlets:", error));
});

// ─────────────────────────────────────
// Continue Button Logic
// ─────────────────────────────────────
document.getElementById("continue-btn").addEventListener("click", function () {
    const selectedOutlets = document.querySelectorAll(".outlet-tile.selected");

    if (selectedOutlets.length === 0) {
        AppUtils.showToast("Please select at least one outlet");
        return;
    }

    const selectedData = [...selectedOutlets].map(tile => ({
        vendor_id: tile.dataset.vendorId,
        name: tile.dataset.name,
        location: tile.dataset.location,
    }));

    console.log("Selected Outlet Data:", selectedData);

    const vendorIds = selectedData.map(outlet => outlet.vendor_id).join(",");
    window.location.href = `/home/?location_id=${locationId}&vendor_id=${vendorIds}`;
});

