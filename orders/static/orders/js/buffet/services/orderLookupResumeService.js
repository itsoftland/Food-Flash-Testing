// orders/static/orders/js/buffet/services/orderLookupResumeService.js
//
// Dine Flash Buffet ONLY — warm resume (iOS standalone already on /home/).
// Reuses resolveOrderLookupForRelaunch. Does not touch browser_id, Push, or Chat.
// Does not call check_status(); on a newer mapped order it refreshes storage and
// redirects to /home/ so the existing home init runs once.
//
// Critical: only reacts to a genuine hidden → visible transition. Initial /home/
// load (already visible) must not trigger a lookup.

import { resolveOrderLookupForRelaunch } from "./orderLookupService.js";

let listenersBound = false;
/** True only after we have observed visibilityState === "hidden" on this page. */
let sawHidden = false;
let inFlight = false;

function isBuffetSurface() {
    const project = String(window.PROJECT_NAME || "").trim().toLowerCase();
    if (project === "dine_flash_buffet") return true;
    return String(window.location?.pathname || "")
        .toLowerCase()
        .includes("/dine_flash_buffet");
}

function isStandalonePwa() {
    return Boolean(window.navigator.standalone);
}

function isEnabled() {
    return isBuffetSurface() && isStandalonePwa();
}

function normalizeId(value) {
    if (value == null) return "";
    return String(value).trim();
}

async function readCurrentTokenVendor() {
    const token =
        typeof AppUtils !== "undefined" && typeof AppUtils.getToken === "function"
            ? normalizeId(await AppUtils.getToken())
            : normalizeId(AppUtils?.storageGet?.("token"));
    const vendor =
        typeof AppUtils !== "undefined" && typeof AppUtils.getActiveVendor === "function"
            ? normalizeId(await AppUtils.getActiveVendor())
            : normalizeId(AppUtils?.storageGet?.("activeVendor"));
    return { token, vendor };
}

function identitiesMatch(current, resolved) {
    const resolvedToken = normalizeId(resolved?.token_no);
    const resolvedVendor = normalizeId(resolved?.vendor_id);
    if (!resolvedToken || !resolvedVendor) return true;
    return (
        current.token === resolvedToken && current.vendor === resolvedVendor
    );
}

async function applyAndRedirect(resolved) {
    const token = normalizeId(resolved.token_no);
    const vendorId = normalizeId(resolved.vendor_id);
    const locationId = normalizeId(resolved.location_id);
    if (!token || !vendorId) return;

    if (locationId && typeof AppUtils.set === "function") {
        await AppUtils.set(locationId);
    }
    if (typeof AppUtils.setCurrentVendors === "function") {
        await AppUtils.setCurrentVendors(String(vendorId));
    }
    if (typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(String(token));
    }

    const base = window.BASE || "/caller_on/";
    const newUrl = new URL(`${window.location.origin}${base}home/`);
    if (locationId) {
        newUrl.searchParams.set("location_id", locationId);
    }
    newUrl.searchParams.set("vendor_id", vendorId);
    newUrl.searchParams.set("token_no", token);
    if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
        AppUtils.handoffDiag("BUFFET_ORDER_LOOKUP_RESUME_REDIRECT", {
            page: "home",
            token_no: token,
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
        const result = await resolveOrderLookupForRelaunch({
            order_lookup_id: orderLookupId,
        });
        if (result.outcome !== "found" || !result.order) {
            if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
                AppUtils.handoffDiag("BUFFET_ORDER_LOOKUP_RESUME_SKIP", {
                    page: "home",
                    outcome: result.outcome,
                    reason: result.reason || "",
                });
            }
            return;
        }

        const current = await readCurrentTokenVendor();
        if (identitiesMatch(current, result.order)) {
            if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
                AppUtils.handoffDiag("BUFFET_ORDER_LOOKUP_RESUME_UNCHANGED", {
                    page: "home",
                    token_no: current.token,
                    vendor_id: current.vendor,
                });
            }
            return;
        }

        await applyAndRedirect(result.order);
    } catch (e) {
        console.warn("[buffet] order_lookup warm resume failed:", e);
    } finally {
        inFlight = false;
    }
}

/**
 * Bind warm-resume listener. Safe to call once from Buffet home.
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
