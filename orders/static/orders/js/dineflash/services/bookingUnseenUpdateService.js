// Dine Flash ONLY — booking-level unseen indicator for Multi-Booking Mode.

import { isMultiBookingMode } from "./multiBookingModeService.js?v=20261027_1";

const STORAGE_KEY = "booking_unseen_updates";

function isDineFlashSurface() {
    return String(window.PROJECT_NAME || "").trim().toLowerCase() === "dine_flash";
}

function normalizeId(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
}

function canTrackUnseen() {
    return isDineFlashSurface() && isMultiBookingMode();
}

function readMap() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageGet !== "function") {
        return {};
    }
    try {
        const raw = AppUtils.storageGet(STORAGE_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
        const out = {};
        Object.keys(parsed).forEach((key) => {
            const id = normalizeId(key);
            if (id && parsed[key]) out[id] = true;
        });
        return out;
    } catch (e) {
        return {};
    }
}

function writeMap(map) {
    if (!canTrackUnseen()) return;
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageSet !== "function") return;
    try {
        AppUtils.storageSet(STORAGE_KEY, JSON.stringify(map || {}));
    } catch (e) {
        /* ignore */
    }
}

function markUnseen(bookingId) {
    if (!canTrackUnseen()) return;
    const id = normalizeId(bookingId);
    if (!id) return;
    const map = readMap();
    map[id] = true;
    writeMap(map);
}

function clearUnseen(bookingId) {
    const id = normalizeId(bookingId);
    if (!id) return;
    const map = readMap();
    if (!map[id]) return;
    delete map[id];
    writeMap(map);
}

function hasUnseen(bookingId) {
    if (!canTrackUnseen()) return false;
    const map = readMap();
    return Boolean(map[normalizeId(bookingId)]);
}

function pruneToActiveBookingIds(activeBookings) {
    if (!canTrackUnseen() || !Array.isArray(activeBookings)) return;
    const allowed = new Set(
        activeBookings.map((b) => normalizeId(b && b.booking_id)).filter(Boolean)
    );
    const map = readMap();
    let changed = false;
    Object.keys(map).forEach((key) => {
        if (!allowed.has(key)) {
            delete map[key];
            changed = true;
        }
    });
    if (changed) writeMap(map);
}

export { markUnseen, clearUnseen, hasUnseen, pruneToActiveBookingIds };
