/**
 * Dine Flash customer app: bypass browser HTTP cache on API requests.
 * Uses Request.cache "no-store" (Fetch spec) — does not wipe localStorage,
 * IndexedDB, cookies, or Cache Storage (service worker).
 *
 * @param {RequestInfo} input
 * @param {RequestInit} [init]
 */
export function dineFlashFetch(input, init = {}) {
    const next = { ...init };
    if (next.cache === undefined) {
        next.cache = "no-store";
    }
    return fetch(input, next);
}

/**
 * Shared customer bundle: same as fetch everywhere except when the page is
 * the Dine Flash web app (window.BASE === "/dine_flash/").
 */
export function dineFlashCustomerFetch(input, init) {
    if (String(window.BASE || "") === "/dine_flash/") {
        return dineFlashFetch(input, init || {});
    }
    return fetch(input, init);
}
