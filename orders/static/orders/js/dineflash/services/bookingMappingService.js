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
     * Extract mapping from QR code
     * Example URL: ...?booking_no=TB1-4&booking_id=62
     */
    function processBookingFromQR(booking_no, booking_id) {
        const bookingNo = booking_no;
        const bookingId = Number(booking_id);

        if (!bookingNo || !bookingId) return;

        // Extract trimmed number (TB1-4 → "4")
        const trimmed = bookingNo.split("-")[1];

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

    return {
        processBookingFromQR,
        saveMappings,
        getBookingId,
        getBookingNo,
        getAllBookingIds,
        hasBookingId,
        clearMappings,
        getCurrentBusinessDay,
    };

})();

export default BookingMappingService;
