// orders/static/orders/js/dineflash/services/bookingMappingService.js

const BookingMappingService = (function () {

    const STORAGE_KEY = "BOOKING_ID_MAP";
    /**
     * Process URL parameters to extract booking mapping from QR code
     * Example URL: ...?booking_no=TB1-4&booking_id=62
     */
    function processBookingFromQR(booking_no,booking_id) {
        console.log("Processing booking mapping from QR code...");

        const bookingNo = booking_no  // TB1-4
        const bookingId = booking_id  // 62

        console.log("Extracted from URL:", { bookingNo, bookingId });

        if (!bookingNo || !bookingId) return;

        // Extract trimmed number: "4"
        const trimmed = bookingNo.split("-")[1];

        const mapping = {
            [trimmed]: {
                booking_no: bookingNo,
                booking_id: Number(bookingId),
            }
        };
        console.log("Saving booking mapping:", mapping);

        BookingMappingService.saveMappings(mapping);
    }

    /**
        * Save mapping of trimmed booking numbers → booking IDs
        * @param {Object} newMapping - e.g., { "4": { booking_no: "TB1-4", booking_id: 62 } }
        * Save to localStorage
    */

    function saveMappings(newMapping) {
        console.log("Saving booking mappings...", newMapping);

        // Load existing mapping
        const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");

        // Merge new → existing
        const updated = { ...existing, ...newMapping };

        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    }

    /**
     * Return ONLY the booking_id for a given trimmed number
     * Example: input "1001" → returns booking_id (number)
     * @param {string} trimmedNo
     */
    function getBookingId(trimmedNo) {
        const mapData = localStorage.getItem(STORAGE_KEY);

        if (!mapData) return null;

        const mapping = JSON.parse(mapData);
        const entry = mapping[trimmedNo];

        if (!entry) return null;   // No match found

        return entry.booking_id;   // ✅ Return only booking_id
    }


    /**
     * Clear stored mapping
     */
    function clearMappings() {
        localStorage.removeItem(STORAGE_KEY);
    }

    return {
        processBookingFromQR,
        saveMappings,
        getBookingId,
        clearMappings
    };

})();

export default BookingMappingService;



