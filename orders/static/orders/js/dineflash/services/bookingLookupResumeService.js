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

import {
    resolveBookingLookupForRelaunch,
    getTempLastHttpStatus,
} from "./bookingLookupService.js";
import BookingMappingService from "./bookingMappingService.js";

let listenersBound = false;
/** True only after we have observed visibilityState === "hidden" on this page. */
let sawHidden = false;
let inFlight = false;
/** Tracks prior visibilityState for TEMP timing diagnostics only. */
let lastVisibilityState =
    typeof document !== "undefined" ? document.visibilityState : "";

const ACTIVE_DINE_BOOKING_KEY = "activeDineBookingId";

function bookingLookupResumeDiag(step, fields) {
    if (typeof AppUtils !== "undefined" && typeof AppUtils.handoffDiag === "function") {
        AppUtils.handoffDiag(step, fields || {});
    }
}

/**
 * ⚠️ TEMP DIAG — iOS PWA resume timing investigation. Remove after analysis.
 * Emits via AppUtils.handoffDiag → /api/dine_flash_client_diag/ (same pipeline as
 * DINE_FLASH_BOOKING_LOOKUP_* / SYNC_* / SW_* breadcrumbs). Server logs only —
 * no console output. Fully fail-safe: never throws into functional control flow.
 */
function bookingLookupTimingDiag(step, fields) {
    try {
        if (
            typeof AppUtils === "undefined" ||
            typeof AppUtils.handoffDiag !== "function"
        ) {
            return;
        }
        const extra = fields || {};
        AppUtils.handoffDiag(step, {
            page: "home",
            standalone: Boolean(window.navigator && window.navigator.standalone),
            iso: new Date().toISOString(),
            perf_now:
                typeof performance !== "undefined" ? performance.now() : "",
            page_url:
                typeof location !== "undefined" ? String(location.href) : "",
            visibility_state:
                typeof document !== "undefined" ? document.visibilityState : "",
            document_hidden:
                typeof document !== "undefined" ? String(document.hidden) : "",
            booking_no:
                extra.booking_no != null
                    ? String(extra.booking_no)
                    : extra.bookingNo != null
                      ? String(extra.bookingNo)
                      : "",
            order_lookup_id:
                extra.order_lookup_id != null
                    ? String(extra.order_lookup_id)
                    : "",
            ...extra,
        });
    } catch (_) {
        /* ignore — diagnostics must never interrupt functional flow */
    }
}

/**
 * ⚠️ TEMP DIAG — read-only storage snapshot. Never calls getBrowserId /
 * getCurrentBrowserId (those can migrate/write). Uses storageGet only.
 * Never throws.
 */
function diagStorageSnapshot() {
    try {
        const read = (key) => {
            try {
                if (
                    typeof AppUtils !== "undefined" &&
                    typeof AppUtils.storageGet === "function"
                ) {
                    return AppUtils.storageGet(key);
                }
            } catch (_) {
                /* ignore */
            }
            return null;
        };
        const order_lookup_id = read("order_lookup_id");
        const browser_id = read("browser_id");
        const booking_id = read(ACTIVE_DINE_BOOKING_KEY);
        const token = read("token");
        return {
            order_lookup_id: order_lookup_id != null ? String(order_lookup_id) : "",
            browser_id: browser_id != null ? String(browser_id) : "",
            booking_id: booking_id != null ? String(booking_id) : "",
            token: token != null ? String(token) : "",
            booking_no: token != null ? String(token) : "",
        };
    } catch (_) {
        return {
            order_lookup_id: "",
            browser_id: "",
            booking_id: "",
            token: "",
            booking_no: "",
        };
    }
}

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
    if (!bookingId || !bookingNo || !vendorId) {
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_NO_REDIRECT_ERROR", {
                reason: "incomplete_resolved_booking",
                booking_id: bookingId,
                booking_no: bookingNo,
                vendor_id: vendorId,
            });
        } catch (_) {
            /* ignore */
        }
        return;
    }

    bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_REPLACE", {
        page: "home",
        booking_id: bookingId,
        booking_no: bookingNo,
        vendor_id: vendorId,
        location_id: locationId,
        standalone: true,
    });

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
    bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_REDIRECT", {
        page: "home",
        booking_id: bookingId,
        booking_no: bookingNo,
        vendor_id: vendorId,
        location_id: locationId,
    });
    try {
        bookingLookupTimingDiag("BOOKING_LOOKUP_REDIRECT_START", {
            destination_url: newUrl.toString(),
            booking_id: bookingId,
            booking_no: bookingNo,
            vendor_id: vendorId,
            location_id: locationId,
        });
    } catch (_) {
        /* ignore */
    }
    window.location.replace(newUrl.toString());
}

async function handleGenuineResume() {
    try {
        bookingLookupTimingDiag(
            "BOOKING_LOOKUP_HANDLE_RESUME_ENTER",
            diagStorageSnapshot()
        );
    } catch (_) {
        /* ignore */
    }
    if (inFlight) {
        bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_SKIP", {
            page: "home",
            reason: "already_running",
            in_flight: true,
            standalone: true,
        });
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_NO_REDIRECT_ERROR", {
                reason: "already_running",
                in_flight: true,
            });
        } catch (_) {
            /* ignore */
        }
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_HANDLE_RESUME_EXIT", {
                reason: "already_running",
            });
        } catch (_) {
            /* ignore */
        }
        return;
    }
    if (!isEnabled()) {
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_HANDLE_RESUME_EXIT", {
                reason: "not_enabled",
            });
        } catch (_) {
            /* ignore */
        }
        return;
    }

    try {
        bookingLookupTimingDiag("BOOKING_LOOKUP_READ_STORAGE_START", {});
    } catch (_) {
        /* ignore */
    }
    const orderLookupId =
        typeof AppUtils !== "undefined" && typeof AppUtils.getOrderLookupId === "function"
            ? AppUtils.getOrderLookupId()
            : null;
    // Read-only snapshots for TEMP diagnostics only (never mutate storage).
    let storageSnap = {
        order_lookup_id: "",
        browser_id: "",
        booking_id: "",
        token: "",
        booking_no: "",
    };
    try {
        storageSnap = diagStorageSnapshot();
    } catch (_) {
        /* ignore */
    }
    try {
        bookingLookupTimingDiag("BOOKING_LOOKUP_READ_STORAGE_END", {
            ...storageSnap,
            order_lookup_id: orderLookupId != null ? String(orderLookupId) : "",
        });
    } catch (_) {
        /* ignore */
    }

    if (!orderLookupId) {
        bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_SKIP", {
            page: "home",
            reason: "no_lookup_id",
            has_order_lookup_id: false,
            standalone: true,
        });
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_NO_REDIRECT_NO_LOOKUP", {
                has_order_lookup_id: false,
            });
        } catch (_) {
            /* ignore */
        }
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_HANDLE_RESUME_EXIT", {
                reason: "no_lookup_id",
            });
        } catch (_) {
            /* ignore */
        }
        return;
    }

    inFlight = true;
    bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_STARTED", {
        page: "home",
        order_lookup_id: String(orderLookupId),
        has_order_lookup_id: true,
        standalone: true,
    });
    try {
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_REQUEST_START", {
                order_lookup_id: String(orderLookupId),
                booking_no: storageSnap.booking_no,
            });
        } catch (_) {
            /* ignore */
        }
        let requestStartedAt = 0;
        try {
            requestStartedAt =
                typeof performance !== "undefined" ? performance.now() : Date.now();
        } catch (_) {
            requestStartedAt = Date.now();
        }
        const result = await resolveBookingLookupForRelaunch({
            order_lookup_id: orderLookupId,
        });
        try {
            let requestElapsedMs = 0;
            try {
                requestElapsedMs =
                    (typeof performance !== "undefined"
                        ? performance.now()
                        : Date.now()) - requestStartedAt;
            } catch (_) {
                requestElapsedMs = 0;
            }
            let httpStatus = "";
            try {
                const status = getTempLastHttpStatus();
                httpStatus = status != null ? String(status) : "";
            } catch (_) {
                httpStatus = "";
            }
            bookingLookupTimingDiag("BOOKING_LOOKUP_REQUEST_END", {
                order_lookup_id: String(orderLookupId),
                http_status: httpStatus,
                elapsed_request_ms: requestElapsedMs,
                outcome: result.outcome || "",
                reason: result.reason || "",
                resolved_booking_id: result.booking
                    ? String(result.booking.booking_id ?? "")
                    : "",
                resolved_booking_no: result.booking
                    ? String(result.booking.booking_no ?? "")
                    : "",
                resolved_vendor_id: result.booking
                    ? String(result.booking.vendor_id ?? "")
                    : "",
                resolved_location_id: result.booking
                    ? String(result.booking.location_id ?? "")
                    : "",
                current_booking_id: storageSnap.booking_id,
                current_booking_no: storageSnap.booking_no,
                booking_no:
                    (result.booking && result.booking.booking_no != null
                        ? String(result.booking.booking_no)
                        : storageSnap.booking_no) || "",
                booking_id: storageSnap.booking_id,
            });
        } catch (_) {
            /* ignore */
        }
        bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_COMPLETED", {
            page: "home",
            outcome: result.outcome || "",
            reason: result.reason || "",
            booking_id:
                result.booking && result.booking.booking_id != null
                    ? String(result.booking.booking_id)
                    : "",
            booking_no:
                result.booking && result.booking.booking_no != null
                    ? String(result.booking.booking_no)
                    : "",
            vendor_id:
                result.booking && result.booking.vendor_id != null
                    ? String(result.booking.vendor_id)
                    : "",
        });
        if (result.outcome !== "found" || !result.booking) {
            bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_SKIP", {
                page: "home",
                outcome: result.outcome,
                reason: result.reason || "",
            });
            try {
                bookingLookupTimingDiag("BOOKING_LOOKUP_NO_REDIRECT_ERROR", {
                    order_lookup_id: String(orderLookupId),
                    outcome: result.outcome || "",
                    reason: result.reason || "not_found_or_no_booking",
                });
            } catch (_) {
                /* ignore */
            }
            try {
                bookingLookupTimingDiag("BOOKING_LOOKUP_HANDLE_RESUME_EXIT", {
                    reason: "lookup_not_found",
                    outcome: result.outcome || "",
                });
            } catch (_) {
                /* ignore */
            }
            return;
        }

        const current = await readCurrentBookingIdentity();
        const identitiesMatchResult = identitiesMatch(current, result.booking);
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_COMPARE", {
                order_lookup_id: String(orderLookupId),
                current_booking_id: current.bookingId,
                current_booking_no: current.bookingNo,
                current_vendor_id: current.vendor,
                resolved_booking_id: String(result.booking.booking_id ?? ""),
                resolved_booking_no: String(result.booking.booking_no ?? ""),
                resolved_vendor_id: String(result.booking.vendor_id ?? ""),
                resolved_location_id: String(result.booking.location_id ?? ""),
                identities_match: String(Boolean(identitiesMatchResult)),
                booking_id: current.bookingId,
                booking_no: String(
                    result.booking.booking_no ?? current.bookingNo ?? ""
                ),
                vendor_id: current.vendor,
            });
        } catch (_) {
            /* ignore */
        }
        if (identitiesMatchResult) {
            bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_SAME", {
                page: "home",
                same_booking: true,
                booking_id: current.bookingId,
                booking_no: current.bookingNo,
                vendor_id: current.vendor,
            });
            bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_UNCHANGED", {
                page: "home",
                booking_id: current.bookingId,
                booking_no: current.bookingNo,
                vendor_id: current.vendor,
            });
            try {
                bookingLookupTimingDiag("BOOKING_LOOKUP_NO_REDIRECT_IDENTICAL", {
                    order_lookup_id: String(orderLookupId),
                    booking_id: current.bookingId,
                    booking_no: current.bookingNo,
                    vendor_id: current.vendor,
                });
            } catch (_) {
                /* ignore */
            }
            try {
                bookingLookupTimingDiag("BOOKING_LOOKUP_HANDLE_RESUME_EXIT", {
                    reason: "identical",
                });
            } catch (_) {
                /* ignore */
            }
            return;
        }

        bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_NEWER", {
            page: "home",
            same_booking: false,
            booking_id: String(result.booking.booking_id ?? ""),
            booking_no: String(result.booking.booking_no ?? ""),
            vendor_id: String(result.booking.vendor_id ?? ""),
            location_id: String(result.booking.location_id ?? ""),
            reason: "newer_than_current",
        });
        await applyAndRedirect(result.booking);
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_HANDLE_RESUME_EXIT", {
                reason: "after_apply_and_redirect",
                order_lookup_id: String(orderLookupId),
                booking_no: String(result.booking.booking_no ?? ""),
            });
        } catch (_) {
            /* ignore */
        }
    } catch (e) {
        bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_EXCEPTION", {
            page: "home",
            reason: "exception",
            error: e && e.message ? String(e.message) : String(e),
        });
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_NO_REDIRECT_ERROR", {
                order_lookup_id: String(orderLookupId),
                reason: "exception",
                error: e && e.message ? String(e.message) : String(e),
            });
        } catch (_) {
            /* ignore */
        }
        try {
            bookingLookupTimingDiag("BOOKING_LOOKUP_HANDLE_RESUME_EXIT", {
                reason: "exception",
            });
        } catch (_) {
            /* ignore */
        }
    } finally {
        inFlight = false;
    }
}

/**
 * Bind warm-resume listener. Safe to call once from Dine Flash home.
 * Initial /home/ load does not trigger a lookup (requires prior "hidden").
 */
function init() {
    if (!isEnabled()) {
        bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_INIT_SKIP", {
            page: "home",
            reason: !isDineFlashSurface()
                ? "not_dine_flash_surface"
                : "not_standalone",
            standalone: isStandalonePwa(),
        });
        return;
    }
    if (listenersBound) {
        bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_INIT_SKIP", {
            page: "home",
            reason: "already_bound",
            standalone: true,
        });
        return;
    }
    listenersBound = true;

    // Start with sawHidden=false so an already-visible initial load is ignored.
    sawHidden = false;

    bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_LISTENER", {
        page: "home",
        reason: "registered",
        standalone: true,
    });

    try {
        bookingLookupTimingDiag("BOOKING_LOOKUP_RESUME_INIT", {
            saw_hidden: String(Boolean(sawHidden)),
            listeners_bound: String(Boolean(listenersBound)),
        });
    } catch (_) {
        /* ignore */
    }

    document.addEventListener("visibilitychange", () => {
        // Best-effort visibility timing log — fully isolated from functional path.
        try {
            const previousVisibilityState = lastVisibilityState;
            const currentVisibilityState = document.visibilityState;
            bookingLookupTimingDiag("BOOKING_LOOKUP_VISIBILITY_CHANGE", {
                previous_visibility_state: previousVisibilityState,
                current_visibility_state: currentVisibilityState,
                saw_hidden: String(Boolean(sawHidden)),
                ...diagStorageSnapshot(),
            });
            lastVisibilityState = currentVisibilityState;
        } catch (_) {
            /* ignore */
        }

        if (document.visibilityState === "hidden") {
            sawHidden = true;
            bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_HIDDEN", {
                page: "home",
                standalone: true,
            });
            return;
        }
        if (document.visibilityState === "visible" && sawHidden) {
            // Log BEFORE consuming sawHidden so a diag failure cannot sit between
            // state clear and handleGenuineResume().
            try {
                bookingLookupTimingDiag("BOOKING_LOOKUP_GENUINE_RESUME_DETECTED", {
                    previous_visibility_state: lastVisibilityState,
                    current_visibility_state: document.visibilityState,
                    saw_hidden: "true",
                    ...diagStorageSnapshot(),
                });
            } catch (_) {
                /* ignore */
            }
            // Consume the transition so we only run once per background→foreground.
            // Functional sequence matches original: clear → existing diag → resume.
            sawHidden = false;
            bookingLookupResumeDiag("DINE_FLASH_BOOKING_LOOKUP_RESUME_VISIBLE", {
                page: "home",
                standalone: true,
            });
            void handleGenuineResume();
        }
    });

    try {
        bookingLookupTimingDiag("BOOKING_LOOKUP_RESUME_LISTENERS_REGISTERED", {
            saw_hidden: String(Boolean(sawHidden)),
            listeners_bound: String(Boolean(listenersBound)),
        });
    } catch (_) {
        /* ignore */
    }
}

try {
    bookingLookupTimingDiag("BOOKING_LOOKUP_RESUME_MODULE_LOADED", {
        ...diagStorageSnapshot(),
    });
} catch (_) {
    /* ignore — must never prevent module export */
}

export { init };
