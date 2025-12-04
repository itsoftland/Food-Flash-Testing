// orders/static/orders/js/dineflash/services/bookingMappingService.js

const BookingMappingService = (function () {

    const STORAGE_KEY = "BOOKING_ID_MAP";

    /**
     * Extract mapping from QR code
     * Example URL: ...?booking_no=TB1-4&booking_id=62
     */
    function processBookingFromQR(booking_no, booking_id) {
        // console.log("Processing booking mapping from QR code...");

        const bookingNo = booking_no;
        const bookingId = Number(booking_id);

        if (!bookingNo || !bookingId) return;

        // Extract trimmed number (TB1-4 → "4")
        const trimmed = bookingNo.split("-")[1];

        const newMappingEntry = {
            booking_no: bookingNo,
            booking_id: bookingId,
        };

        // console.log("Saving booking mapping:", trimmed, newMappingEntry);

        saveMappings(trimmed, newMappingEntry);
    }


    /**
     * Save mapping:
     * - Supports multiple booking_id under same trimmed number
     * - Prevents duplicates based ONLY on booking_id
     *
     * @param {string} trimmedNo
     * @param {Object} entry  →  { booking_no, booking_id }
     */
    function saveMappings(trimmedNo, entry) {
        // console.log("Saving booking mappings for:", trimmedNo, entry);

        const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

        let existingList = existing[trimmedNo] || [];

        // 🟢 FIX: Convert old format (object) → array
        if (!Array.isArray(existingList)) {
            existingList = [existingList];
        }

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

        // console.log("Updated mapping:", existing);
    }



    /**
     * Return ONLY the booking_id
     * If multiple entries exist, return an array of IDs
     */
    function getBookingId(trimmedNo) {
        const mapData = localStorage.getItem(STORAGE_KEY);
        if (!mapData) return null;

        const mapping = JSON.parse(mapData);
        let list = mapping[trimmedNo];

        if (!list) return null;

        // 🟢 Handle backward compatibility (object → array)
        if (!Array.isArray(list)) {
            list = [list];
        }

        // Extract all booking IDs
        const ids = list.map(item => item.booking_id);

        // 🟢 If only one ID, return single value
        if (ids.length === 1) {
            return ids[0];
        }

        // 🟢 If multiple, return list
        return ids;
    }
    
    function getBookingNo(trimmedNo) {
        // console.log("get BookingNo called with:", trimmedNo);
        const mapData = localStorage.getItem(STORAGE_KEY);
        if (!mapData) return null;

        const mapping = JSON.parse(mapData);
        let list = mapping[trimmedNo];

        if (!list) return null;

        // Normalize input:
        // If list is an object (old style), wrap into array
        if (!Array.isArray(list)) {
            list = [list];
        }

        // If only one entry → return ONLY the booking_no
        if (list.length === 1) {
            const item = list[0];

            // Case 1: item is an object → return booking_no
            if (typeof item === "object" && item.booking_no) {
                // console.log("retured booking no type object");
                return item.booking_no;
            }

            // Case 2: item is already a string → return as string
            // console.log("retured booking no type string");
            return item;
        }

        // Multiple entries → return full details (objects)
        // console.log("retured booking no type list");
        return list;
    }

    function clearMappings() {
        localStorage.removeItem(STORAGE_KEY);
    }

    return {
        processBookingFromQR,
        saveMappings,
        getBookingId,
        getBookingNo,
        clearMappings
    };

})();

export default BookingMappingService;
