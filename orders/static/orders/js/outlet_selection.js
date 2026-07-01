import BookingMappingService from './dineflash/services/bookingMappingService.js';
import { resolveBookingForRelaunch } from './dineflash/services/pwaRelaunchService.js';
import { IosPwaInstallService } from './services/iosPwaInstallService.js';

// ─────────────────────────────────────
// Base URL Setup
// ─────────────────────────────────────
const base = window.BASE || '/caller_on/';

/** Dine Flash table-booking only — excludes dine_flash_buffet. */
function isDineFlashTableBooking() {
    const name = (window.PROJECT_NAME || '').trim().toLowerCase();
    return name === 'dine_flash';
}

/** Dine Flash Buffet only — excludes dine_flash table-booking. */
function isDineFlashBuffet() {
    const name = (window.PROJECT_NAME || '').trim().toLowerCase();
    return name === 'dine_flash_buffet';
}

// ─────────────────────────────────────
// Dine Flash relaunch staging UI (dine_flash table-booking only)
// ─────────────────────────────────────
// For Dine Flash table-booking the landing page is only a transient PWA
// relaunch staging page; manual outlet selection has no valid downstream flow.
// While the relaunch IIFE runs we hide the outlet-selection UI and surface a
// relaunch status using the app's existing Bootstrap styling. Everything here
// is gated to dine_flash and never runs for other flavours.
const DINE_FLASH_RELAUNCH_FAILED_MSG =
    "We couldn't restore your previous booking. Please scan the restaurant QR code again to continue.";

// Set true just before a successful relaunch redirect so the failed-relaunch
// message is not flashed while the page is navigating away.
let dineFlashRedirecting = false;

function initDineFlashRelaunchUI() {
    const outletList = document.getElementById("outlet-list");
    const continueBtn = document.getElementById("continue-btn");
    const title = document.querySelector(".container .title");

    [outletList, continueBtn, title].forEach((el) => {
        if (el) el.style.display = "none";
    });

    const container = document.querySelector(".container") || document.body;
    const status = document.createElement("div");
    status.id = "dine-flash-relaunch-status";
    status.className = "text-center py-5";
    status.innerHTML = `
        <div class="spinner-border text-warning" role="status" aria-hidden="true"></div>
        <p class="mt-3 mb-0">Restoring your booking...</p>
    `;
    container.appendChild(status);

    return {
        fail(message) {
            status.innerHTML = `<p class="mb-0">${message}</p>`;
        },
    };
}

const dineFlashRelaunchUI = isDineFlashTableBooking() ? initDineFlashRelaunchUI() : null;

// ─────────────────────────────────────
// Dine Flash Buffet relaunch loading state (dine_flash_buffet only)
// ─────────────────────────────────────
// Cosmetic only. While the relaunch IIFE decides whether to redirect to /home/,
// briefly showing the outlet-selection page is jarring for a returning Buffet
// user. Mirror the table-booking staging UI: hide the outlet UI and show a
// simple "Restoring your order..." spinner. Unlike table-booking, Buffet must
// reveal the normal outlet page again when no relaunch occurs, so this helper
// returns hide() which removes the overlay and restores the hidden elements.
// No relaunch, redirect, or storage logic is involved here.
function initBuffetRelaunchUI() {
    const outletList = document.getElementById("outlet-list");
    const continueBtn = document.getElementById("continue-btn");
    const title = document.querySelector(".container .title");
    const hidden = [outletList, continueBtn, title];

    hidden.forEach((el) => {
        if (el) el.style.display = "none";
    });

    const container = document.querySelector(".container") || document.body;
    const status = document.createElement("div");
    status.id = "buffet-relaunch-status";
    status.className = "text-center py-5";
    status.innerHTML = `
        <div class="spinner-border text-warning" role="status" aria-hidden="true"></div>
        <p class="mt-3 mb-0">Restoring your order...</p>
    `;
    container.appendChild(status);

    return {
        hide() {
            status.remove();
            hidden.forEach((el) => {
                if (el) el.style.display = "";
            });
        },
    };
}

const buffetRelaunchUI = isDineFlashBuffet() ? initBuffetRelaunchUI() : null;

// ─────────────────────────────────────
// Early Redirect: Ensure ?location_id is in URL
// ─────────────────────────────────────
const dineFlashRelaunchFlow = (async function redirectIfMissingLocationId() {

    const currentUrl = new URL(window.location.href);
    const urlParams = currentUrl.searchParams;

    const hasLocationParam = urlParams.has("location_id");
    const hasVendorId = await AppUtils.getActiveVendor();
    const hasTokenNo = await AppUtils.getToken();
    console.log("[dine_flash] IIFE vendor", hasVendorId);
    console.log("[dine_flash] IIFE token", hasTokenNo);

    // ✅ Condition 1: If vendor_id and/or token are present → redirect to /home/
    if (hasVendorId || hasTokenNo) {
        const locationId = hasLocationParam ? urlParams.get("location_id") : await AppUtils.get();
        console.log("[dine_flash] IIFE location", locationId);
        console.log("[dine_flash] IIFE hasLocationParam", hasLocationParam);

        // Buffet iOS PWA relaunch: allow the redirect without location_id ONLY when a
        // valid activeVendor exists (token + vendor are required downstream by check_status).
        const buffetRelaunchBypass = isDineFlashBuffet() && !!hasVendorId;
        if (!locationId && !buffetRelaunchBypass) {
            console.warn("Missing location_id for home redirect.");
            return;
        }

        if (isDineFlashTableBooking()) {
            const booking = BookingMappingService.resolveRelaunchBooking({
                activeBookingId: AppUtils.storageGet("activeDineBookingId"),
                bookingNoHint: hasTokenNo,
            });

            if (booking) {
                const newUrl = new URL(`${window.location.origin}${base}home/`);
                newUrl.searchParams.set("location_id", locationId);
                if (hasVendorId) {
                    newUrl.searchParams.set("vendor_id", hasVendorId);
                }
                newUrl.searchParams.set("booking_id", booking.booking_id);
                if (booking.booking_no) {
                    newUrl.searchParams.set("booking_no", booking.booking_no);
                }
                if (urlParams.has("from_push")) {
                    newUrl.searchParams.set("from_push", urlParams.get("from_push"));
                }
                if (urlParams.has("standalone")) {
                    newUrl.searchParams.set("standalone", urlParams.get("standalone"));
                }
                if (urlParams.has("v")) {
                    newUrl.searchParams.set("v", urlParams.get("v"));
                }

                dineFlashRedirecting = true;
                window.location.replace(newUrl.toString());
                return;
            }

            console.log("[dine_flash] relaunch: entering backend fallback", {
                vendor_id: hasVendorId,
                booking_no: hasTokenNo,
                location_id: locationId,
            });
            const relaunchResult = await resolveBookingForRelaunch({
                vendor_id: hasVendorId,
                booking_no: hasTokenNo,
                location_id: locationId,
            });
            console.log("[dine_flash] relaunch result", relaunchResult);

            if (relaunchResult.outcome === "found") {
                const resolvedBooking = relaunchResult.booking;
                const newUrl = new URL(`${window.location.origin}${base}home/`);
                newUrl.searchParams.set("location_id", resolvedBooking.location_id);
                if (resolvedBooking.vendor_id) {
                    newUrl.searchParams.set("vendor_id", resolvedBooking.vendor_id);
                }
                newUrl.searchParams.set("booking_id", resolvedBooking.booking_id);
                if (resolvedBooking.booking_no) {
                    newUrl.searchParams.set("booking_no", resolvedBooking.booking_no);
                }
                if (urlParams.has("from_push")) {
                    newUrl.searchParams.set("from_push", urlParams.get("from_push"));
                }
                if (urlParams.has("standalone")) {
                    newUrl.searchParams.set("standalone", urlParams.get("standalone"));
                }
                if (urlParams.has("v")) {
                    newUrl.searchParams.set("v", urlParams.get("v"));
                }

                dineFlashRedirecting = true;
                window.location.replace(newUrl.toString());
                return;
            }

            console.warn(
                "[dine_flash] PWA relaunch:",
                relaunchResult.outcome === "preserve"
                    ? relaunchResult.reason
                    : "no resolvable booking; staying on outlet selection."
            );
            return;
        }

        const newUrl = new URL(`${window.location.origin}${base}home/`);
        if (locationId) {
            newUrl.searchParams.set("location_id", locationId);
        }
        if (hasVendorId) {
            newUrl.searchParams.set("vendor_id", hasVendorId);
        }
        if (hasTokenNo) {
            newUrl.searchParams.set("token_no", hasTokenNo);
        }
        if (urlParams.has("from_push")) {
            newUrl.searchParams.set("from_push", urlParams.get("from_push"));
        }

        // Buffet only: signal that a relaunch redirect is in flight so the
        // DOMContentLoaded location check can skip the false "Location ID is
        // missing" toast while navigation completes. Flag only; redirect URL
        // and destination are unchanged. Other flavours (food/airline) fall
        // through here without setting it, preserving their behaviour.
        if (isDineFlashBuffet()) {
            dineFlashRedirecting = true;
        }
        window.location.replace(newUrl.toString());
        return;
    }

    // 🚨 Condition 2: If location_id is missing, try to retrieve and redirect
    if (!hasLocationParam) {
        const locationIdFromStorage = await AppUtils.get();
        if (locationIdFromStorage) {
            const newUrl = new URL(window.location.href);
            newUrl.searchParams.set("location_id", locationIdFromStorage);
            dineFlashRedirecting = true;
            window.location.replace(newUrl.toString());
        } else {
            console.warn("No location_id found in URL or storage.");
        }
    }
})();

// Dine Flash table-booking only: when the relaunch IIFE settles without
// redirecting to /home/, the previous booking could not be restored. Keep the
// outlet-selection UI hidden and replace the loading message with guidance to
// rescan. .finally() preserves the original (non-dine) promise behaviour,
// including rejection propagation, since the callback is a no-op there.
if (isDineFlashTableBooking()) {
    dineFlashRelaunchFlow.finally(() => {
        if (!dineFlashRedirecting) {
            dineFlashRelaunchUI?.fail(DINE_FLASH_RELAUNCH_FAILED_MSG);
        }
    });
}

// Dine Flash Buffet only: when the relaunch IIFE settles WITHOUT redirecting,
// no relaunch is possible — hide the "Restoring your order..." loading state and
// reveal the normal outlet-selection page (existing behaviour). When a redirect
// is in flight we leave the overlay up so navigation to /home/ stays seamless.
// Cosmetic only; the IIFE's relaunch/redirect logic is untouched.
if (isDineFlashBuffet()) {
    dineFlashRelaunchFlow.finally(() => {
        if (!dineFlashRedirecting) {
            buffetRelaunchUI?.hide();
        }
    });
}

// ─────────────────────────────────────
// Main Logic: Run after DOM is ready
// ─────────────────────────────────────
let locationId = null;

document.addEventListener("DOMContentLoaded", async function () {
    // iOS A2HS prompt setup
    IosPwaInstallService.init();

    const agreeBtn = document.getElementById("ios-a2hs-agree");
    const denyBtn = document.getElementById("ios-a2hs-deny");

    if (agreeBtn) {
        agreeBtn.addEventListener("click", () => {
            AppUtils.storageSet("iosA2HS", "true");
            IosPwaInstallService.dismiss();
        });
    }

    if (denyBtn) {
        denyBtn.addEventListener("click", () => {
            AppUtils.storageSet("iosA2HS", "false");
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
        // Dine Flash Buffet PWA relaunch only: the relaunch IIFE
        // (redirectIfMissingLocationId) may still be resolving activeVendor /
        // token / location from IndexedDB / cookie. Each fallback tier adds a
        // ~200ms timer, so the IIFE reaches location.replace() AFTER this branch
        // would otherwise show the "Location ID is missing" toast — producing a
        // false flash right before the redirect. Wait for the relaunch decision
        // first so the toast can only appear when no redirect will occur.
        // Gated to buffet so no other flavour's timing changes.
        if (isDineFlashBuffet()) {
            try {
                await dineFlashRelaunchFlow;
            } catch (err) {
                console.warn("[dine_flash_buffet] relaunch flow failed:", err);
            }
            if (dineFlashRedirecting) {
                return; // Redirect in progress; page is unloading.
            }
        }

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
    fetch(`${base}api/outlets/?location_id=${locationId}`)
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
                    <img src="${outlet.logo}" alt="${outlet.name}">
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

    const vendorIds = selectedData.map(outlet => outlet.vendor_id).join(",");
    window.location.href = `${base}home/?location_id=${locationId}&vendor_id=${vendorIds}`;
});
