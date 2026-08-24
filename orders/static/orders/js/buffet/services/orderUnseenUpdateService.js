// orders/static/orders/js/buffet/services/orderUnseenUpdateService.js
//
// Dine Flash Buffet ONLY — order-level “unseen update” indicator for
// Multi-Order Mode. Separate from ChatSync handledFingerprints (dedupe).
//
// Storage: prefixed localStorage via AppUtils (same convention as
// selected_order / multi_order_mode). Shape: { [token_number]: true }.
//
// Does not import ChatSyncService or activeOrderSelectorService.

import { isMultiOrderMode } from "./multiOrderModeService.js";

const STORAGE_KEY = "order_unseen_updates";

function isDineFlashBuffetSurface() {
    if (
        typeof window.PROJECT_NAME === "string" &&
        window.PROJECT_NAME.trim().toLowerCase() === "dine_flash_buffet"
    ) {
        return true;
    }
    const base = window.BASE || "";
    if (base.includes("/dine_flash_buffet/")) return true;
    const path = (window.location?.pathname || "").toLowerCase();
    return path.includes("/dine_flash_buffet") || path.includes("/dineflashbuffet");
}

function normalizeToken(value) {
    if (value === null || value === undefined) return "";
    return String(value).trim();
}

function canTrackUnseen() {
    return isDineFlashBuffetSurface() && isMultiOrderMode();
}

/**
 * @returns {Record<string, boolean>}
 */
function readMap() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageGet !== "function") {
        return {};
    }
    try {
        const raw = AppUtils.storageGet(STORAGE_KEY);
        if (!raw) return {};
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            return {};
        }
        const out = {};
        Object.keys(parsed).forEach((key) => {
            const token = normalizeToken(key);
            if (token && parsed[key]) {
                out[token] = true;
            }
        });
        return out;
    } catch (e) {
        return {};
    }
}

/**
 * @param {Record<string, boolean>} map
 */
function writeMap(map) {
    if (typeof AppUtils === "undefined" || typeof AppUtils.storageSet !== "function") {
        return;
    }
    try {
        AppUtils.storageSet(STORAGE_KEY, JSON.stringify(map || {}));
    } catch (e) {
        console.warn("[buffet] order_unseen_updates write failed:", e);
    }
}

/**
 * Mark token as having an unseen update. Idempotent.
 * No-op outside Buffet Multi-Order Mode or without a token.
 *
 * @param {string|number} tokenNumber
 * @returns {boolean} true when state is (now) unseen for that token
 */
function markUnseen(tokenNumber) {
    if (!canTrackUnseen()) return false;
    const token = normalizeToken(tokenNumber);
    if (!token) return false;

    const map = readMap();
    if (map[token]) return true;

    map[token] = true;
    writeMap(map);
    return true;
}

/**
 * @param {string|number} tokenNumber
 * @returns {boolean}
 */
function hasUnseen(tokenNumber) {
    if (!canTrackUnseen()) return false;
    const token = normalizeToken(tokenNumber);
    if (!token) return false;
    return Boolean(readMap()[token]);
}

/**
 * Clear unseen for one order. Idempotent.
 *
 * @param {string|number} tokenNumber
 */
function clearUnseen(tokenNumber) {
    const token = normalizeToken(tokenNumber);
    if (!token) return;

    const map = readMap();
    if (!map[token]) return;

    delete map[token];
    writeMap(map);
}

/**
 * Drop unseen entries whose tokens are not in the active-orders list.
 *
 * @param {Array<{ token_number?: * }|string|number>} activeOrdersOrTokens
 */
function pruneToActiveTokens(activeOrdersOrTokens) {
    if (!Array.isArray(activeOrdersOrTokens)) return;

    const allowed = new Set();
    activeOrdersOrTokens.forEach((entry) => {
        if (entry === null || entry === undefined) return;
        if (typeof entry === "object") {
            const token = normalizeToken(entry.token_number);
            if (token) allowed.add(token);
            return;
        }
        const token = normalizeToken(entry);
        if (token) allowed.add(token);
    });

    const map = readMap();
    let changed = false;
    Object.keys(map).forEach((token) => {
        if (!allowed.has(token)) {
            delete map[token];
            changed = true;
        }
    });
    if (changed) {
        writeMap(map);
    }
}

export {
    markUnseen,
    hasUnseen,
    clearUnseen,
    pruneToActiveTokens,
};
