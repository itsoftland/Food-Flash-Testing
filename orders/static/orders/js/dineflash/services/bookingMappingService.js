console.log("NEW BOOKING MAPPING SERVICE LOADED");
// orders/static/orders/js/dineflash/services/bookingMappingService.js
//
// Dine Flash ONLY. This module is imported by scripts.js and every call site is
// gated by `window.BASE.includes('/dine_flash/')`. It is never reached by
// Dine Flash Buffet ('/dine_flash_buffet/'), Airline Flash, Food Flash,
// Service Flash, or CallerOn.

const BookingMappingService = (function () {

    const STORAGE_KEY = "BOOKING_ID_MAP";

    // -------------------------------------------------------------------------
    // Business-day helpers
    //
    // Booking-number suffixes (e.g. "4" from "TB1-4") are reused across business
    // days because the server resets booking counters at the start of each
    // business day. Old localStorage mappings never expire, so the same suffix
    // bucket could hold entries from multiple business days and falsely trigger
    // the "multiple bookings found" chooser on manual lookup.
    //
    // We stamp each new entry with the business day it was created on, and the
    // manual-lookup readers (getBookingNo / getBookingId) only consider entries
    // from the CURRENT business day. The push-acceptance readers
    // (getAllBookingIds / hasBookingId) intentionally stay lenient.
    // -------------------------------------------------------------------------

    /**
     * Parse window.BUSINESS_DAY_START_HOUR ("HH:MM:SS") into parts.
     * Returns null when unavailable / "00:00:00" so callers fall back to the
     * plain local calendar date (midnight boundary).
     */
    function getBusinessDayStartHour() {
        const raw =
            (typeof window !== "undefined" &&
                typeof window.BUSINESS_DAY_START_HOUR === "string")
                ? window.BUSINESS_DAY_START_HOUR.trim()
                : "";
        if (!raw) return null;

        const parts = raw.split(":");
        const hour = parseInt(parts[0], 10);
        if (Number.isNaN(hour)) return null;

        const minute = parseInt(parts[1], 10);
        const second = parseInt(parts[2], 10);
        const startHour = {
            hour,
            minute: Number.isNaN(minute) ? 0 : minute,
            second: Number.isNaN(second) ? 0 : second,
        };

        // "00:00:00" is equivalent to the plain local-date boundary.
        if (startHour.hour === 0 && startHour.minute === 0 && startHour.second === 0) {
            return null;
        }
        return startHour;
    }

    function formatLocalDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${year}-${month}-${day}`;
    }

    /**
     * Current business day as a "YYYY-MM-DD" string in the browser's local time.
     * Mirrors the server's get_vendor_business_day_range() rule: if the current
     * local time is before the business-day start hour, the day rolls back to
     * the previous calendar date. Write-time and read-time computations use this
     * same function so their stamps always agree.
     */
    function getCurrentBusinessDay() {
        const now = new Date();
        const start = getBusinessDayStartHour();
        if (start) {
            const nowSecs =
                now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
            const startSecs = start.hour * 3600 + start.minute * 60 + start.second;
            if (nowSecs < startSecs) {
                now.setDate(now.getDate() - 1);
            }
        }
        return formatLocalDate(now);
    }

    /**
     * True only for object entries stamped with the current business day.
     * Legacy entries (bare strings, or objects without `business_day`) are
     * treated as stale for manual lookup — historical bookings do not need to be
     * retrievable through manual chat entry.
     */
    function isCurrentBusinessDay(entry) {
        if (!entry || typeof entry !== "object") return false;
        if (!entry.business_day) return false;
        return entry.business_day === getCurrentBusinessDay();
    }

    /**
     * Normalize a stored bucket value into an array of entries, handling the
     * historical object-instead-of-array format.
     */
    function normalizeList(list) {
        if (list === null || list === undefined) return [];
        return Array.isArray(list) ? list : [list];
    }

    /**
     * Derive the BOOKING_ID_MAP bucket key from a Dine Flash booking number.
     * - Prefixed numbers key on the suffix:  "VIP-5" → "5", "TB1-4" → "4"
     * - Non-prefixed numbers key on the whole value: "136" → "136"
     * Previously `bookingNo.split("-")[1]` returned undefined for non-prefixed
     * numbers, bucketing them under the literal key "undefined".
     */
    function getTrimmedKey(bookingNo) {
        if (bookingNo === null || bookingNo === undefined) return null;
        const str = String(bookingNo);
        return str.includes("-") ? str.split("-")[1] : str;
    }

    /**
     * Extract mapping from QR code
     * Example URL: ...?booking_no=TB1-4&booking_id=62
     */
    function processBookingFromQR(booking_no, booking_id) {
        const bookingNo = booking_no;
        const bookingId = Number(booking_id);

        if (!bookingNo || !bookingId) return;

        // Derive bucket key (TB1-4 → "4", VIP-5 → "5", 136 → "136")
        const trimmed = getTrimmedKey(bookingNo);

        const newMappingEntry = {
            booking_no: bookingNo,
            booking_id: bookingId,
            business_day: getCurrentBusinessDay(),
        };

        saveMappings(trimmed, newMappingEntry);
    }


    /**
     * Save mapping:
     * - Supports multiple booking_id under same trimmed number
     * - Prevents duplicates based ONLY on booking_id
     * - Stamps entries with the current business day
     * - Prunes entries from previous business days in the touched bucket so
     *   stale collisions cannot re-trigger the chooser and storage stays bounded
     *
     * @param {string} trimmedNo
     * @param {Object} entry  →  { booking_no, booking_id, business_day }
     */
    function saveMappings(trimmedNo, entry) {
        const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

        // Ensure the entry carries a business-day stamp even if a caller built
        // it without one.
        if (entry && typeof entry === "object" && !entry.business_day) {
            entry.business_day = getCurrentBusinessDay();
        }

        let existingList = normalizeList(existing[trimmedNo]);

        // Drop stale (previous-business-day / unstamped) entries for this bucket.
        existingList = existingList.filter(isCurrentBusinessDay);

        // Check duplicate ONLY by booking_id
        const alreadyExists = existingList.some(
            (item) => item.booking_id === entry.booking_id
        );

        if (!alreadyExists) {
            existingList.push(entry);
        }

        // Save back
        existing[trimmedNo] = existingList;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
    }



    /**
     * Return ONLY the booking_id for the CURRENT business day.
     * If multiple current-day entries exist, return an array of IDs.
     */
    function getBookingId(trimmedNo) {
        const mapData = localStorage.getItem(STORAGE_KEY);
        if (!mapData) return null;

        const mapping = JSON.parse(mapData);
        const list = normalizeList(mapping[trimmedNo]).filter(isCurrentBusinessDay);

        if (list.length === 0) return null;

        const ids = list.map((item) => item.booking_id);

        // If only one ID, return single value
        if (ids.length === 1) {
            return ids[0];
        }

        // If multiple, return list
        return ids;
    }

    /**
     * Return the booking_no for the CURRENT business day.
     * Single current-day match → booking_no string.
     * Multiple current-day matches → array of entry objects (drives chooser).
     */
    function getBookingNo(trimmedNo) {
        const mapData = localStorage.getItem(STORAGE_KEY);
        if (!mapData) return null;

        const mapping = JSON.parse(mapData);
        const list = normalizeList(mapping[trimmedNo]).filter(isCurrentBusinessDay);

        if (list.length === 0) return null;

        // Single entry → return ONLY the booking_no
        if (list.length === 1) {
            const item = list[0];
            if (typeof item === "object" && item.booking_no) {
                return item.booking_no;
            }
            return item;
        }

        // Multiple entries → return full details (objects) for the chooser
        return list;
    }

    /**
     * Return every booking_id known to this browser as normalized strings.
     * Flattens all trimmed-number buckets and handles legacy object entries.
     *
     * NOTE: This is intentionally NOT business-day filtered. It backs inbound
     * push acceptance (scripts.js), and a booking placed just before a
     * business-day rollover must keep receiving its notifications.
     */
    function getAllBookingIds() {
        const mapData = localStorage.getItem(STORAGE_KEY);
        if (!mapData) return [];

        let mapping;
        try {
            mapping = JSON.parse(mapData);
        } catch (e) {
            return [];
        }

        const ids = [];
        Object.values(mapping || {}).forEach((list) => {
            normalizeList(list).forEach((item) => {
                const id =
                    item && typeof item === "object" ? item.booking_id : item;
                if (id !== null && id !== undefined) {
                    ids.push(String(id).trim());
                }
            });
        });

        return ids;
    }

    /**
     * BOOKING_ID_MAP membership check.
     * Returns true when the given booking_id belongs to this browser's
     * known Dine Flash bookings (regardless of which booking is "active"
     * or which business day it belongs to — see getAllBookingIds note).
     */
    function hasBookingId(bookingId) {
        if (bookingId === null || bookingId === undefined) return false;
        const target = String(bookingId).trim();
        if (!target) return false;
        return getAllBookingIds().includes(target);
    }

    function clearMappings() {
        localStorage.removeItem(STORAGE_KEY);
    }

    // -------------------------------------------------------------------------
    // PWA relaunch helpers (Phase 1)
    //
    // Safe, no-throw readers for resolving booking_no + booking_id on iOS Home
    // Screen cold start. Phase 2 wires these into outlet_selection.js.
    // -------------------------------------------------------------------------

    /**
     * Normalize a booking_id for storage comparisons.
     * Mirrors scripts.js normalizeBookingId / hasBookingId string rules.
     */
    function normalizeId(value) {
        if (value === null || value === undefined) return null;
        const s = String(value).trim();
        if (!s || s === "undefined" || s === "NaN") return null;
        return s;
    }

    /**
     * Parse BOOKING_ID_MAP from localStorage without throwing.
     * Returns {} for missing, malformed, or non-object top-level values.
     */
    function loadMapping() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return {};

            const parsed = JSON.parse(raw);
            if (
                parsed === null ||
                typeof parsed !== "object" ||
                Array.isArray(parsed)
            ) {
                return {};
            }
            return parsed;
        } catch (e) {
            return {};
        }
    }

    /**
     * Derive booking_id from a bucket entry.
     * Handles modern objects, legacy unstamped objects, and primitive IDs.
     */
    function extractBookingId(entry) {
        if (entry === null || entry === undefined) return null;
        if (typeof entry === "object" && !Array.isArray(entry)) {
            return normalizeId(entry.booking_id);
        }
        return normalizeId(entry);
    }

    /**
     * Derive booking_no from a bucket entry.
     * Only reads explicit booking_no on objects — never treats a primitive ID
     * as a booking number.
     */
    function extractBookingNo(entry) {
        if (entry === null || entry === undefined) return null;
        if (typeof entry === "object" && !Array.isArray(entry)) {
            if (entry.booking_no === null || entry.booking_no === undefined) {
                return null;
            }
            const s = String(entry.booking_no).trim();
            return s || null;
        }
        return null;
    }

    /**
     * Reverse-scan BOOKING_ID_MAP for a booking_id.
     * Never throws; returns null when not found or on read failure.
     *
     * @param {string|number} bookingId
     * @param {{ currentBusinessDayOnly?: boolean }} [options]
     * @returns {{ booking_id: string, booking_no: string|null, business_day: string|null, isStale: boolean }|null}
     */
    function findEntryByBookingId(bookingId, options) {
        try {
            const currentBusinessDayOnly =
                !options || options.currentBusinessDayOnly !== false;

            const target = normalizeId(bookingId);
            if (!target) return null;

            const mapping = loadMapping();
            const buckets = Object.values(mapping);

            for (let i = 0; i < buckets.length; i++) {
                const list = normalizeList(buckets[i]);
                for (let j = 0; j < list.length; j++) {
                    const entry = list[j];
                    const entryId = extractBookingId(entry);
                    if (!entryId || entryId !== target) continue;

                    const isStale = !isCurrentBusinessDay(entry);
                    if (currentBusinessDayOnly && isStale) continue;

                    return {
                        booking_id: entryId,
                        booking_no: extractBookingNo(entry),
                        business_day:
                            entry &&
                            typeof entry === "object" &&
                            !Array.isArray(entry)
                                ? entry.business_day || null
                                : null,
                        isStale,
                    };
                }
            }
        } catch (e) {
            return null;
        }

        return null;
    }

    /**
     * Build the validated relaunch pair returned to outlet_selection.js.
     * booking_no may be null when only booking_id is known (primitive entries).
     */
    function toRelaunchResult(entry) {
        if (!entry) return null;

        const booking_id = normalizeId(entry.booking_id);
        if (!booking_id) return null;

        let booking_no = null;
        if (entry.booking_no !== null && entry.booking_no !== undefined) {
            const s = String(entry.booking_no).trim();
            booking_no = s || null;
        }

        return { booking_no, booking_id };
    }

    /**
     * Resolve booking_no + booking_id for Dine Flash PWA relaunch.
     * Never throws; returns null when no unambiguous booking can be resolved.
     *
     * Precedence:
     *   1. activeBookingId → current-business-day map entry
     *   2. activeBookingId found but stale → null (no token fallback)
     *   3. bookingNoHint (token) → singular current-day bucket match only
     *
     * @param {{ activeBookingId?: string|number, bookingNoHint?: string|number }} [params]
     * @returns {{ booking_no: string|null, booking_id: string }|null}
     */
    function resolveRelaunchBooking({ activeBookingId, bookingNoHint } = {}) {
        try {
            const normalizedActiveId = normalizeId(activeBookingId);

            // Path 1: activeDineBookingId (session pointer) — wins over token hint.
            if (normalizedActiveId) {
                const current = findEntryByBookingId(normalizedActiveId, {
                    currentBusinessDayOnly: true,
                });
                if (current) {
                    const result = toRelaunchResult(current);
                    if (result) return result;
                }

                const stale = findEntryByBookingId(normalizedActiveId, {
                    currentBusinessDayOnly: false,
                });
                if (stale) {
                    // Stale session — do not redirect and do not token-fallback.
                    return null;
                }

                // activeId present but not in map (corrupt / cleared map).
                return null;
            }

            // Path 2: token hint — only when activeBookingId is absent.
            const hint =
                bookingNoHint === null || bookingNoHint === undefined
                    ? null
                    : String(bookingNoHint).trim() || null;
            if (!hint) return null;

            const trimmed = getTrimmedKey(hint);
            if (!trimmed) return null;

            const ids = getBookingId(trimmed);
            const nos = getBookingNo(trimmed);

            if (Array.isArray(ids) || Array.isArray(nos)) return null;
            if (ids === null || ids === undefined || nos === null || nos === undefined) {
                return null;
            }

            const booking_id = normalizeId(ids);
            if (!booking_id) return null;

            const booking_no =
                typeof nos === "string" || typeof nos === "number"
                    ? String(nos).trim() || null
                    : null;
            if (!booking_no) return null;

            // Pairing check: reject inconsistent map state.
            const verified = findEntryByBookingId(booking_id, {
                currentBusinessDayOnly: true,
            });
            if (
                verified &&
                verified.booking_no &&
                verified.booking_no !== booking_no
            ) {
                return null;
            }

            return { booking_no, booking_id };
        } catch (e) {
            console.warn("[dine_flash] resolveRelaunchBooking failed", e);
            return null;
        }
    }

    return {
        processBookingFromQR,
        saveMappings,
        getBookingId,
        getBookingNo,
        getAllBookingIds,
        hasBookingId,
        clearMappings,
        getCurrentBusinessDay,
        getTrimmedKey,
        findEntryByBookingId,
        resolveRelaunchBooking,
    };

})();

export default BookingMappingService;
