// passengerInfoService.js

const PASSENGER_INFO_KEY = "passenger_info";

/**
 * Save or update a passenger’s info (sequence_code → passenger_name)
 * @param {string} sequenceCode
 * @param {string} passengerName
 */
export function savePassengerInfo(sequenceCode, passengerName) {
    if (!sequenceCode || !passengerName) return;

    // Retrieve existing records
    const existingData = JSON.parse(localStorage.getItem(PASSENGER_INFO_KEY) || "{}");

    // Add / update entry
    existingData[sequenceCode] = passengerName;

    // Save back to localStorage
    localStorage.setItem(PASSENGER_INFO_KEY, JSON.stringify(existingData));
}

/**
 * Retrieve a passenger name by sequence code
 * @param {string} sequenceCode
 * @returns {string|null}
 */
export function getPassengerName(sequenceCode) {
    const data = JSON.parse(localStorage.getItem(PASSENGER_INFO_KEY) || "{}");
    return data[sequenceCode] || null;
}

/**
 * Remove a passenger entry by sequence code
 * @param {string} sequenceCode
 */
export function removePassengerInfo(sequenceCode) {
    const data = JSON.parse(localStorage.getItem(PASSENGER_INFO_KEY) || "{}");
    if (data[sequenceCode]) {
        delete data[sequenceCode];
        localStorage.setItem(PASSENGER_INFO_KEY, JSON.stringify(data));
    }
}

/**
 * Clear all passenger info (if needed)
 */
export function clearAllPassengerInfo() {
    localStorage.removeItem(PASSENGER_INFO_KEY);
}
