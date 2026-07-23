// orders/static/orders/js/dineflash/services/bookingLookupResumeService.js
//
// Dine Flash ONLY — warm resume (iOS standalone already on /home/).
// Reuses resolveBookingLookupForRelaunch. Does not touch browser_id, Push, or Chat.
// Does not call check_status(); on a newer mapped booking it refreshes storage and
// redirects to /home/ so the existing home init runs once.
//
// Critical: only reacts to a genuine hidden → visible transition. Initial /home/
// load (already visible) must not trigger a lookup.
// Independent from Buffet orderLookupResumeService.js.

import { resolveBookingLookupForRelaunch } from "./bookingLookupService.js";
import BookingMappingService from "./bookingMappingService.js";

let listenersBound = false;
/** True only after we have observed visibilityState === "hidden" on this page. */
let sawHidden = false;
let inFlight = false;

const ACTIVE_DINE_BOOKING_KEY = "activeDineBookingId";

function isDineFlashSurface() {
    const project = String(window.PROJECT_NAME || "").trim().toLowerCase();
    if (project === "dine_flash") return true;
    const path = String(window.location?.pathname || "").toLowerCase();
    return path.includes("/dine_flash/") && !path.includes("/dine_flash_buffet");
}

function isStandalonePwa() {
    return Boolean(window.navigator.standalone);
}

function isEnabled() {
    return isDineFlashSurface() && isStandalonePwa();
}

function normalizeId(value) {
    if (value == null) return "";
    return String(value).trim();
}

async function readCurrentBookingIdentity() {
    const bookingId = normalizeId(AppUtils?.storageGet?.(ACTIVE_DINE_BOOKING_KEY));
    const bookingNo =
        typeof AppUtils !== "undefined" && typeof AppUtils.getToken === "function"
            ? normalizeId(await AppUtils.getToken())
            : normalizeId(AppUtils?.storageGet?.("token"));
    const vendor =
        typeof AppUtils !== "undefined" && typeof AppUtils.getActiveVendor === "function"
            ? normalizeId(await AppUtils.getActiveVendor())
            : normalizeId(AppUtils?.storageGet?.("activeVendor"));
    return { bookingId, bookingNo, vendor };
}

function identitiesMatch(current, resolved) {
    const resolvedId = normalizeId(resolved?.booking_id);
    if (resolvedId && current.bookingId) {
        return current.bookingId === resolvedId;
    }
    const resolvedNo = normalizeId(resolved?.booking_no);
    const resolvedVendor = normalizeId(resolved?.vendor_id);
    if (!resolvedNo || !resolvedVendor) return true;
    return (
        current.bookingNo === resolvedNo && current.vendor === resolvedVendor
    );
}

async function applyAndRedirect(resolved) {
    const bookingId = normalizeId(resolved.booking_id);
    const bookingNo = normalizeId(resolved.booking_no);
    const vendorId = normalizeId(resolved.vendor_id);
    const locationId = normalizeId(resolved.location_id);
    if (!bookingId || !bookingNo || !vendorId) return;

    if (locationId && typeof AppUtils.set === "function") {
        await AppUtils.set(locationId);
    }
    if (typeof AppUtils.setCurrentVendors === "function") {
        await AppUtils.setCurrentVendors(String(vendorId));
    }
    if (typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(String(bookingNo));
    }
    if (typeof AppUtils.storageSet === "function") {
        AppUtils.storageSet(ACTIVE_DINE_BOOKING_KEY, bookingId);
    }
    if (
        BookingMappingService &&
        typeof BookingMappingService.processBookingFromQR === "function"
    ) {
        BookingMappingService.processBookingFromQR(bookingNo, bookingId);
    }

    const base = window.BASE || "/caller_on/";
    const newUrl = new URL(`${window.location.origin}${base}home/`);
    if (locationId) {
        newUrl.searchParams.set("location_id", locationId);
    }
    newUrl.searchParams.set("vendor_id", vendorId);
    newUrl.searchParams.set("booking_id", bookingId);
    newUrl.searchParams.set("booking_no", bookingNo);
    if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
        AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_REDIRECT", {
            page: "home",
            booking_id: bookingId,
            booking_no: bookingNo,
            vendor_id: vendorId,
            location_id: locationId,
        });
    }
    window.location.replace(newUrl.toString());
}

async function handleGenuineResume() {
    if (inFlight) return;
    if (!isEnabled()) return;

    const orderLookupId =
        typeof AppUtils !== "undefined" && typeof AppUtils.getOrderLookupId === "function"
            ? AppUtils.getOrderLookupId()
            : null;
    if (!orderLookupId) return;

    inFlight = true;
    try {
        const result = await resolveBookingLookupForRelaunch({
            order_lookup_id: orderLookupId,
        });
        if (result.outcome !== "found" || !result.booking) {
            if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
                AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_SKIP", {
                    page: "home",
                    outcome: result.outcome,
                    reason: result.reason || "",
                });
            }
            return;
        }

        const current = await readCurrentBookingIdentity();
        if (identitiesMatch(current, result.booking)) {
            if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
                AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_UNCHANGED", {
                    page: "home",
                    booking_id: current.bookingId,
                    booking_no: current.bookingNo,
                    vendor_id: current.vendor,
                });
            }
            return;
        }

        await applyAndRedirect(result.booking);
    } catch (e) {
        console.warn("[dine_flash] booking_lookup warm resume failed:", e);
    } finally {
        inFlight = false;
    }
}

/**
 * Bind warm-resume listener. Safe to call once from Dine Flash home.
 * Initial /home/ load does not trigger a lookup (requires prior "hidden").
 */
function init() {
    if (!isEnabled()) return;
    if (listenersBound) return;
    listenersBound = true;

    // Start with sawHidden=false so an already-visible initial load is ignored.
    sawHidden = false;

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") {
            sawHidden = true;
            return;
        }
        if (document.visibilityState === "visible" && sawHidden) {
            // Consume the transition so we only run once per background→foreground.
            sawHidden = false;
            void handleGenuineResume();
        }
    });
}

export { init };
