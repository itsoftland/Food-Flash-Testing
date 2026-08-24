import BookingMappingService from './dineflash/services/bookingMappingService.js';
import { resolveBookingForRelaunch } from './dineflash/services/pwaRelaunchService.js';
import { resolveBookingLookupForRelaunch } from './dineflash/services/bookingLookupService.js';
import { resolveOrderLookupForRelaunch } from './buffet/services/orderLookupService.js';
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
    const fromPushParam = urlParams.get("from_push");
    const standalone = Boolean(window.navigator.standalone);
    // launch_mode is inferred only from signals already present in this flow.
    const launchMode = fromPushParam
        ? "resume_from_push"
        : standalone
            ? "cold_or_homescreen_pwa"
            : "browser";

    if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
        AppUtils.handoffDiag("HANDOFF_PAGE_LOAD", {
            page: "landing_page",
            standalone,
            from_push: fromPushParam || "",
            launch_mode: launchMode,
            has_location: urlParams.has("location_id"),
            branch: "outlet_selection",
        });
    }

    // Dine Flash Buffet: adopt Safari pending handoff before reading storage.
    // Surface gate (standalone) lives inside adoptPendingHandoffIfPresent.
    if (isDineFlashBuffet()) {
        AppUtils.handoffDiag("HANDOFF_ADOPT_CALLER", {
            page: "outlet_selection",
            branch: "buffet_adopt_before_storage_read",
            standalone,
            launch_mode: launchMode,
        });
        const adopted = await AppUtils.adoptPendingHandoffIfPresent();
        AppUtils.handoffDiag("HANDOFF_ADOPT_CALLER_RESULT", {
            page: "outlet_selection",
            branch: adopted ? "adopted" : "not_adopted",
            standalone,
            launch_mode: launchMode,
        });

        // Approved insertion point: resolve order_lookup_id → refresh storage,
        // then continue the existing getToken() / redirect / check_status path.
        // Does not create a second restore flow or call check_status().
        //
        // Phase 6: Multi-Order Mode only — try Selected Order restore first.
        // Flag is a prefixed localStorage latch set only after successful "+".
        // Single-order users (flag absent) take the identical Latest path below
        // with no restore API calls.
        const orderLookupId =
            typeof AppUtils.getOrderLookupId === "function"
                ? AppUtils.getOrderLookupId()
                : null;
        if (orderLookupId) {
            let restoredSelected = false;
            const multiOrderFlag =
                typeof AppUtils.storageGet === "function"
                    ? AppUtils.storageGet("multi_order_mode")
                    : null;
            const inMultiOrderMode =
                multiOrderFlag === "1" || multiOrderFlag === "true";

            if (inMultiOrderMode) {
                try {
                    const restoreMod = await import(
                        "./buffet/services/selectedOrderRestoreService.js"
                    );
                    if (restoreMod && typeof restoreMod.tryRestoreSelectedOrder === "function") {
                        const restoreResult = await restoreMod.tryRestoreSelectedOrder();
                        if (restoreResult && restoreResult.outcome === "restored") {
                            restoredSelected = true;
                            AppUtils.handoffDiag("BUFFET_SELECTED_ORDER_RESTORED", {
                                page: "outlet_selection",
                                token_no: String(restoreResult.order?.token_number ?? ""),
                                vendor_id: String(restoreResult.order?.vendor_id ?? ""),
                                branch: "multi_order_mode",
                            });
                        } else if (
                            restoreResult &&
                            restoreResult.outcome === "fallback"
                        ) {
                            AppUtils.handoffDiag("BUFFET_SELECTED_ORDER_FALLBACK", {
                                page: "outlet_selection",
                                reason: restoreResult.reason || "",
                                branch: "multi_order_mode",
                            });
                        }
                    }
                } catch (e) {
                    console.warn("[buffet] selected_order restore failed:", e);
                }
            }

            if (!restoredSelected) {
                try {
                    const lookupResult = await resolveOrderLookupForRelaunch({
                        order_lookup_id: orderLookupId,
                    });
                    if (lookupResult.outcome === "found" && lookupResult.order) {
                        const resolved = lookupResult.order;
                        if (resolved.location_id) {
                            await AppUtils.set(String(resolved.location_id));
                        }
                        if (resolved.vendor_id != null && String(resolved.vendor_id).trim() !== "") {
                            await AppUtils.setCurrentVendors(String(resolved.vendor_id));
                        }
                        if (resolved.token_no != null && String(resolved.token_no).trim() !== "") {
                            await AppUtils.setToken(String(resolved.token_no));
                        }
                        // Multi-Order fallback only: align Selected Order with Latest
                        // so Current badge matches Home after recovery fallback.
                        if (inMultiOrderMode) {
                            try {
                                const selectedMod = await import(
                                    "./buffet/services/selectedOrderService.js"
                                );
                                if (
                                    selectedMod &&
                                    typeof selectedMod.setSelectedOrder === "function" &&
                                    resolved.token_no != null &&
                                    resolved.vendor_id != null
                                ) {
                                    selectedMod.setSelectedOrder({
                                        order_lookup_id: orderLookupId,
                                        vendor_id: resolved.vendor_id,
                                        token_number: resolved.token_no,
                                    });
                                }
                            } catch (e) {
                                // Non-fatal — Latest storage already applied.
                            }
                        }
                        AppUtils.handoffDiag("BUFFET_ORDER_LOOKUP_APPLIED", {
                            page: "outlet_selection",
                            token_no: String(resolved.token_no ?? ""),
                            vendor_id: String(resolved.vendor_id ?? ""),
                            location_id: String(resolved.location_id ?? ""),
                        });
                    } else {
                        // stale: orderLookupService already cleared token/selected_order
                        // (keeps order_lookup_id). not_found / preserve: keep storage.
                        AppUtils.handoffDiag("BUFFET_ORDER_LOOKUP_SKIP", {
                            page: "outlet_selection",
                            outcome: lookupResult.outcome,
                            reason: lookupResult.reason || "",
                        });
                    }
                } catch (e) {
                    console.warn("[buffet] order_lookup resolve failed:", e);
                }
            }
        }
    } else if (isDineFlashTableBooking()) {
        // Dine Flash table-booking: adopt Safari pending handoff, then resolve
        // latest booking via order_lookup_id before the existing relaunch path.
        AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_OUTLET_BRANCH", {
            page: "outlet_selection",
            branch: "dine_flash_entered",
            standalone,
            launch_mode: launchMode,
        });
        AppUtils.handoffDiag("HANDOFF_ADOPT_CALLER", {
            page: "outlet_selection",
            branch: "dine_flash_adopt_before_storage_read",
            standalone,
            launch_mode: launchMode,
        });
        // Pending-handoff detection logs live inside adoptPendingHandoffIfPresent
        // (HANDOFF_ADOPT_COOKIE_LOOKUP / HANDOFF_ADOPT_SKIP).
        const adopted = await AppUtils.adoptPendingHandoffIfPresent();
        AppUtils.handoffDiag("HANDOFF_ADOPT_CALLER_RESULT", {
            page: "outlet_selection",
            branch: adopted ? "adopted" : "not_adopted",
            standalone,
            launch_mode: launchMode,
        });
        AppUtils.handoffDiag(
            adopted
                ? "DINE_FLASH_BOOKING_LOOKUP_ADOPT_EXECUTED"
                : "DINE_FLASH_BOOKING_LOOKUP_PENDING_HANDOFF",
            {
                page: "outlet_selection",
                branch: adopted ? "adopted" : "not_adopted",
                has_cookie: adopted,
                standalone,
                reason: adopted ? "adopted" : "not_adopted_see_HANDOFF_ADOPT",
            }
        );

        const orderLookupId =
            typeof AppUtils.getOrderLookupId === "function"
                ? AppUtils.getOrderLookupId()
                : null;
        AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_STORED_ID", {
            page: "outlet_selection",
            has_order_lookup_id: Boolean(orderLookupId),
            order_lookup_id: orderLookupId != null ? String(orderLookupId) : "",
            standalone,
        });
        if (orderLookupId) {
            try {
                AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_RESOLVE_START", {
                    page: "outlet_selection",
                    order_lookup_id: String(orderLookupId),
                    has_order_lookup_id: true,
                    standalone,
                });
                const lookupResult = await resolveBookingLookupForRelaunch({
                    order_lookup_id: orderLookupId,
                });
                AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_RESOLVE_RESULT", {
                    page: "outlet_selection",
                    outcome: lookupResult.outcome || "",
                    reason: lookupResult.reason || "",
                    booking_id:
                        lookupResult.booking && lookupResult.booking.booking_id != null
                            ? String(lookupResult.booking.booking_id)
                            : "",
                    booking_no:
                        lookupResult.booking && lookupResult.booking.booking_no != null
                            ? String(lookupResult.booking.booking_no)
                            : "",
                    vendor_id:
                        lookupResult.booking && lookupResult.booking.vendor_id != null
                            ? String(lookupResult.booking.vendor_id)
                            : "",
                    location_id:
                        lookupResult.booking && lookupResult.booking.location_id != null
                            ? String(lookupResult.booking.location_id)
                            : "",
                });
                if (lookupResult.outcome === "found" && lookupResult.booking) {
                    const resolved = lookupResult.booking;
                    if (resolved.location_id) {
                        await AppUtils.set(String(resolved.location_id));
                    }
                    if (resolved.vendor_id != null && String(resolved.vendor_id).trim() !== "") {
                        await AppUtils.setCurrentVendors(String(resolved.vendor_id));
                    }
                    if (resolved.booking_no != null && String(resolved.booking_no).trim() !== "") {
                        await AppUtils.setToken(String(resolved.booking_no));
                    }
                    if (resolved.booking_id != null && String(resolved.booking_id).trim() !== "") {
                        AppUtils.storageSet(
                            "activeDineBookingId",
                            String(resolved.booking_id).trim()
                        );
                        if (
                            BookingMappingService &&
                            typeof BookingMappingService.processBookingFromQR === "function" &&
                            resolved.booking_no
                        ) {
                            AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_MAPPING_SERVICE", {
                                page: "outlet_selection",
                                booking_id: String(resolved.booking_id),
                                booking_no: String(resolved.booking_no),
                                reason: "processBookingFromQR",
                            });
                            BookingMappingService.processBookingFromQR(
                                String(resolved.booking_no),
                                resolved.booking_id
                            );
                        }
                    }
                    AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_STORAGE_REFRESHED", {
                        page: "outlet_selection",
                        booking_id: String(resolved.booking_id ?? ""),
                        booking_no: String(resolved.booking_no ?? ""),
                        vendor_id: String(resolved.vendor_id ?? ""),
                        location_id: String(resolved.location_id ?? ""),
                    });
                    AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_APPLIED", {
                        page: "outlet_selection",
                        booking_id: String(resolved.booking_id ?? ""),
                        booking_no: String(resolved.booking_no ?? ""),
                        vendor_id: String(resolved.vendor_id ?? ""),
                        location_id: String(resolved.location_id ?? ""),
                    });
                } else {
                    AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_SKIP", {
                        page: "outlet_selection",
                        outcome: lookupResult.outcome,
                        reason: lookupResult.reason || "",
                    });
                }
            } catch (e) {
                AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_EXCEPTION", {
                    page: "outlet_selection",
                    reason: "exception",
                    error: e && e.message ? String(e.message) : String(e),
                });
            }
        }
    } else {
        if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
            AppUtils.handoffDiag("HANDOFF_ADOPT_CALLER_SKIP", {
                page: "outlet_selection",
                reason: "not_buffet_or_dine_flash",
            });
        }
    }

    const hasLocationParam = urlParams.has("location_id");
    const hasVendorId = await AppUtils.getActiveVendor();
    const hasTokenNo = await AppUtils.getToken();
    console.log("[dine_flash] IIFE vendor", hasVendorId);
    console.log("[dine_flash] IIFE token", hasTokenNo);

    if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
        AppUtils.handoffDiag("HANDOFF_OUTLET_STORAGE_READ", {
            page: "outlet_selection",
            has_vendor: Boolean(hasVendorId),
            has_token: Boolean(hasTokenNo),
            has_location: hasLocationParam,
            vendor_id: hasVendorId != null ? String(hasVendorId) : "",
            token_no: hasTokenNo != null ? String(hasTokenNo) : "",
            launch_mode: launchMode,
        });
    }

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
            if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
                AppUtils.handoffDiag("HANDOFF_OUTLET_REDIRECT_SKIP", {
                    page: "outlet_selection",
                    reason: "missing_location_id",
                    has_vendor: Boolean(hasVendorId),
                    has_token: Boolean(hasTokenNo),
                });
            }
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

                AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_REDIRECT", {
                    page: "outlet_selection",
                    branch: "local_booking_mapping",
                    booking_id: booking.booking_id != null ? String(booking.booking_id) : "",
                    booking_no: booking.booking_no != null ? String(booking.booking_no) : "",
                    vendor_id: hasVendorId != null ? String(hasVendorId) : "",
                    location_id: locationId != null ? String(locationId) : "",
                    reason: "redirect_home_from_mapping",
                });
                dineFlashRedirecting = true;
                window.location.replace(newUrl.toString());
                return;
            }

            AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_RESOLVE_BOOKING", {
                page: "outlet_selection",
                branch: "backend_resolve_booking",
                vendor_id: hasVendorId != null ? String(hasVendorId) : "",
                booking_no: hasTokenNo != null ? String(hasTokenNo) : "",
                location_id: locationId != null ? String(locationId) : "",
                reason: "local_mapping_miss",
            });
            const relaunchResult = await resolveBookingForRelaunch({
                vendor_id: hasVendorId,
                booking_no: hasTokenNo,
                location_id: locationId,
            });
            AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_RESOLVE_BOOKING_RESULT", {
                page: "outlet_selection",
                outcome: relaunchResult.outcome || "",
                reason: relaunchResult.reason || "",
                booking_id:
                    relaunchResult.booking && relaunchResult.booking.booking_id != null
                        ? String(relaunchResult.booking.booking_id)
                        : "",
                booking_no:
                    relaunchResult.booking && relaunchResult.booking.booking_no != null
                        ? String(relaunchResult.booking.booking_no)
                        : "",
            });

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

                AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_REDIRECT", {
                    page: "outlet_selection",
                    branch: "backend_resolve_booking",
                    booking_id: String(resolvedBooking.booking_id ?? ""),
                    booking_no: String(resolvedBooking.booking_no ?? ""),
                    vendor_id: String(resolvedBooking.vendor_id ?? ""),
                    location_id: String(resolvedBooking.location_id ?? ""),
                    reason: "redirect_home_from_resolve_booking",
                });
                dineFlashRedirecting = true;
                window.location.replace(newUrl.toString());
                return;
            }

            AppUtils.handoffDiag("DINE_FLASH_BOOKING_LOOKUP_REDIRECT", {
                page: "outlet_selection",
                branch: "stay_on_outlet",
                outcome: relaunchResult.outcome || "",
                reason:
                    relaunchResult.outcome === "preserve"
                        ? relaunchResult.reason || "preserve"
                        : "no_resolvable_booking",
            });
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
        if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
            AppUtils.handoffDiag("HANDOFF_OUTLET_REDIRECT_HOME", {
                page: "outlet_selection",
                branch: "vendor_or_token_present",
                vendor_id: hasVendorId != null ? String(hasVendorId) : "",
                token_no: hasTokenNo != null ? String(hasTokenNo) : "",
                location_id: locationId != null ? String(locationId) : "",
                from_push: urlParams.get("from_push") || "",
                launch_mode: launchMode,
            });
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
            if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
                AppUtils.handoffDiag("HANDOFF_OUTLET_REDIRECT_SELF", {
                    page: "outlet_selection",
                    branch: "inject_location_id",
                    location_id: String(locationIdFromStorage),
                    launch_mode: launchMode,
                });
            }
            window.location.replace(newUrl.toString());
        } else {
            console.warn("No location_id found in URL or storage.");
            if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
                AppUtils.handoffDiag("HANDOFF_OUTLET_STAY", {
                    page: "outlet_selection",
                    reason: "no_vendor_token_or_location",
                    launch_mode: launchMode,
                });
            }
        }
    } else if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
        AppUtils.handoffDiag("HANDOFF_OUTLET_STAY", {
            page: "outlet_selection",
            reason: "has_location_param_no_vendor_or_token",
            launch_mode: launchMode,
        });
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
