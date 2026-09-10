/**
 * Hospital Flash only — fire-and-forget Called-flow diagnostic breadcrumbs.
 * POSTs to /api/hospital_flash_client_diag/ so steps persist in orders.log.
 * Logging only: never throws, never blocks UI, no DB/business side effects.
 */
import { hospitalOnly } from "./hospitalCommon.js";

const MAX_VALUE_LEN = 200;

function sanitizeFields(fields) {
    const out = {};
    if (!fields || typeof fields !== "object") return out;
    for (const [key, value] of Object.entries(fields)) {
        if (value === null || value === undefined || value === "") continue;
        out[key] = String(value).slice(0, MAX_VALUE_LEN);
    }
    return out;
}

/**
 * @param {string} step - Stable step name for server-side grep.
 * @param {Record<string, unknown>} [fields]
 */
export function hospitalFlashClientDiag(step, fields) {
    if (!hospitalOnly()) return;
    try {
        const browserId =
            (typeof window.AppUtils !== "undefined" &&
                typeof window.AppUtils.getCurrentBrowserId === "function" &&
                window.AppUtils.getCurrentBrowserId()) ||
            null;
        const base =
            (typeof window.AppUtils !== "undefined" &&
                typeof window.AppUtils.getStartUrl === "function" &&
                window.AppUtils.getStartUrl()) ||
            (typeof window.BASE === "string" ? window.BASE : "/hospital_flash/");
        const url = `${base}api/hospital_flash_client_diag/`;
        const csrf =
            (typeof window.AppUtils !== "undefined" &&
                typeof window.AppUtils.getCSRFToken === "function" &&
                window.AppUtils.getCSRFToken()) ||
            "";
        fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...(csrf ? { "X-CSRFToken": csrf } : {}),
            },
            credentials: "same-origin",
            keepalive: true,
            body: JSON.stringify({
                step,
                source: "page",
                project: "hospital_flash",
                browser_id: browserId,
                timestamp: Date.now(),
                ...sanitizeFields(fields),
            }),
        }).catch(() => {});
    } catch (_e) {
        // Diagnostics must never break the page.
    }
}
