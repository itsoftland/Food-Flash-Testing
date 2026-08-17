// ================================================
// 🌐 Global App Initialization Script
// ================================================

// ✅ Import IndexedDB helper (for caching small key-value pairs)
import { get as idbGet, set as idbSet } from "https://cdnjs.cloudflare.com/ajax/libs/idb-keyval/6.2.1/index.min.js";
import { HOSPITAL_MANAGER_PUSH_TYPE } from "./hospital/hospitalCommon.js";

// ⚠️ TEMP DIAGNOSTIC — prove AppUtils availability at Book click (remove after investigation).
// Posts directly to dine_flash_client_diag so breadcrumbs reach orders.log even before
// window.AppUtils exists. No console output. Never throws, never awaits, never blocks.
function tempUtilsClientDiag(step, fields) {
    try {
        const project = String(window.PROJECT_NAME || "").toLowerCase().trim();
        if (project !== "dine_flash" && project !== "dine_flash_buffet") return;
        const base = window.BASE || `/${project}/`;
        const url = `${base}api/dine_flash_client_diag/`;
        let csrf = "";
        try {
            const meta = document.querySelector('meta[name="csrf-token"]');
            csrf = meta ? meta.getAttribute("content") || "" : "";
            if (!csrf) {
                const cookie = document.cookie
                    .split(";")
                    .map((c) => c.trim())
                    .find((c) => c.startsWith("csrftoken="));
                csrf = cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
            }
        } catch (_) { /* ignore */ }
        fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf,
            },
            credentials: "same-origin",
            keepalive: true,
            body: JSON.stringify({
                step,
                source: "page",
                project,
                page: "utils",
                timestamp: Date.now(),
                ...(fields || {}),
            }),
        }).catch(() => {});
    } catch (_) {
        // Diagnostics must never break AppUtils init.
    }
}

function tempUtilsAppUtilsSnapshot() {
    return {
        typeof_app_utils: typeof window.AppUtils,
        typeof_get_browser_id: typeof window.AppUtils?.getBrowserId,
        typeof_handoff_diag: typeof window.AppUtils?.handoffDiag,
    };
}

// 1) Module body evaluation starts. (Static import already resolved if we reach here;
//    if idb-keyval import fails, this breadcrumb never appears — that absence is the signal.)
tempUtilsClientDiag("UTILS_MODULE_EVAL_START", {
    ...tempUtilsAppUtilsSnapshot(),
    reason: "module_body_start",
});

// 2) idb-keyval import completed successfully (proven by module body running).
tempUtilsClientDiag("UTILS_IDB_IMPORT_OK", {
    ...tempUtilsAppUtilsSnapshot(),
    reason: "idb_keyval_import_resolved",
});

// 3) Catch any exception during the rest of module evaluation.
try {

// ✅ Detect if running as a standalone (PWA) app
if (window.navigator.standalone) {
    console.log("Running in standalone mode");
}

// ==================================================
// 🔧 Project Configuration (Safe Defaults + Globals)
// ==================================================

// Safely read project variables from the global window object with fallbacks
const projectName = (
    typeof window.PROJECT_NAME === "string" && window.PROJECT_NAME.trim() !== ""
)
    ? window.PROJECT_NAME.trim()
    : "calleron"; // Fallback project name

const projectDisplayName = (
    typeof window.PROJECT_DISPLAY_NAME === "string" && window.PROJECT_DISPLAY_NAME.trim() !== ""
)
    ? window.PROJECT_DISPLAY_NAME.trim()
    : "Caller On"; // Fallback display name

const appVersion = (
    typeof window.APP_VERSION === "string" && window.APP_VERSION.trim() !== ""
)
    ? window.APP_VERSION.trim()
    : "1.0.0"; // Fallback version

// ==================================================
// 🌍 Base Path Setup
// ==================================================

// Define a global base URL (e.g., /airline_flash/)
window.BASE = `/${projectName}/`;

// Reassign globals for consistent access across modules
window.PROJECT_NAME = projectName;
window.PROJECT_DISPLAY_NAME = projectDisplayName;
window.APP_VERSION = appVersion;

// (Optional) Debug Logs
// console.log("🔗 BASE URL:", window.BASE);
// console.log(`🚀 Project: ${projectDisplayName}`);
// console.log(`🧩 Version: ${appVersion}`);

// ==================================================
// 🧱 Static Assets Configuration
// ==================================================

// Compute the base URL for static images (handles subdirectory deployments)
const staticBase = `${window.location.origin}/${projectName ? projectName + '/' : ''}static/orders/images/`;

// Define project-to-favicon mapping
const faviconMap = {
    "food_flash": "food-flash-logo.ico",
    "airline_flash": "airline-flash-logo.ico",
    "service_flash": "service-flash-logo.ico",
    "dine_flash": "dine-flash-logo.ico",
    "calleron": "calleron-logo.ico",
};

// Select favicon based on current project
const iconFile = faviconMap[projectName] || "default-logo.ico";
const faviconUrl = `${staticBase}${iconFile}`;

// Dynamically insert favicon into <head>
const link = document.createElement("link");
link.rel = "icon";
link.type = "image/x-icon";
link.href = faviconUrl;
document.head.appendChild(link);

// ==================================================
// 🔔 Notification Audio Placeholder
// ==================================================

// This variable will later hold the unlocked notification sound reference
let unlockedNotificationAudio = null;

/** True only on Hospital Flash deployments — isolates TTS from other flavours. */
function isHospitalFlashProject() {
    return String(projectName || "").toLowerCase().trim() === "hospital_flash";
}

/**
 * Normalize a value for spoken Hospital Flash announcements.
 * Returns "" when the value would produce broken speech (undefined/null/empty/placeholders).
 */
function hospitalSpeechValue(value) {
    if (value == null) return "";
    const text = String(value).trim();
    if (!text) return "";
    const lower = text.toLowerCase();
    if (
        lower === "undefined" ||
        lower === "null" ||
        text === "-" ||
        text === "--" ||
        lower === "n/a"
    ) {
        return "";
    }
    return text;
}

function hospitalSpeechToken(pushData) {
    if (!pushData || typeof pushData !== "object") return "";
    // Prefer patient-facing token (e.g. LAB-12) over internal token_no.
    return (
        hospitalSpeechValue(pushData.booking_no) ||
        hospitalSpeechValue(pushData.token_no)
    );
}

function hospitalSpeechDepartment(pushData) {
    if (!pushData || typeof pushData !== "object") return "";
    return (
        hospitalSpeechValue(pushData.department_name) ||
        hospitalSpeechValue(pushData.utility_name)
    );
}

const HOSPITAL_TTS_STATUS_SUMMARY =
    "Your registration status has been updated. Please review the details on your mobile.";

/**
 * Built-in Hospital Flash spoken templates (non-default).
 * Must stay aligned with vendors/hospital_announcement_templates.py.
 * "default" is intentionally absent — runtime uses the original hardcoded branches.
 */
const HOSPITAL_ANNOUNCEMENT_BUILTINS = {
    called: {
        template_a: "Patient {token}, kindly proceed to the {department}.",
        template_b: "Now serving token {token}. Please visit the {department}.",
    },
    waiting: {
        template_a:
            "Patient {token}, you are in the queue for {department}. Please wait for your turn.",
        template_b:
            "Token {token} is waiting for {department}. We will announce when it is your turn.",
    },
    completed: {
        template_a:
            "Patient {token}, your consultation at {department} is complete. Thank you.",
        template_b: "Token {token} completed. Thank you for visiting {department}.",
    },
    cancelled: {
        template_a:
            "Patient {token}, your visit for {department} has been cancelled. Please contact hospital staff.",
        template_b:
            "Token {token} cancelled for {department}. Please speak with hospital staff for assistance.",
    },
    pre_announcement: {
        template_a:
            "Patient {token}, your turn for {department} is approaching. Please be ready.",
        template_b:
            "Token {token} will be called soon at {department}. Please stay nearby.",
    },
};

/**
 * Replace {token}/{department} in a template. Unknown placeholders are left as-is
 * only when they are not our known keys; known keys with empty values become "".
 */
function applyHospitalAnnouncementPlaceholders(template, token, department) {
    if (template == null) return "";
    let text = String(template);
    text = text.replace(/\{token\}/gi, token || "");
    text = text.replace(/\{department\}/gi, department || "");
    // Collapse awkward double spaces from empty placeholders; keep sentence readable.
    return text.replace(/[ \t]{2,}/g, " ").replace(/\s+([.,!?])/g, "$1").trim();
}

/**
 * Resolve configured spoken template for a hospital announcement type.
 * Returns null when Default / missing config — caller must use hardcoded path.
 */
function resolveHospitalConfiguredTemplate(pushData, announcementType, token, department) {
    if (!pushData || typeof pushData !== "object" || !announcementType) {
        return null;
    }
    const configs = pushData.announcement_templates;
    if (!configs || typeof configs !== "object") {
        return null;
    }
    const entry = configs[announcementType];
    if (!entry || typeof entry !== "object") {
        return null;
    }

    const selected = String(entry.selected || "default").trim().toLowerCase();
    if (!selected || selected === "default") {
        return null;
    }

    let template = null;
    if (selected === "custom") {
        template = entry.custom_text != null ? String(entry.custom_text).trim() : "";
        if (!template) {
            return null; // empty custom → fall back to hardcoded defaults
        }
    } else if (selected === "template_a" || selected === "template_b") {
        const builtins = HOSPITAL_ANNOUNCEMENT_BUILTINS[announcementType] || {};
        template = builtins[selected] || null;
        if (!template) {
            return null;
        }
    } else {
        return null;
    }

    const spoken = applyHospitalAnnouncementPlaceholders(template, token, department);
    return spoken || null;
}

/**
 * Hospital Flash–only spoken messages for notifyOrderReady.
 * Other flavours never call this.
 */
function buildHospitalFlashSpokenMessage(pushData) {
    if (!pushData || typeof pushData !== "object") {
        return HOSPITAL_TTS_STATUS_SUMMARY;
    }

    const type = hospitalSpeechValue(pushData.type);
    const status = hospitalSpeechValue(pushData.status).toLowerCase();
    const token = hospitalSpeechToken(pushData);
    const department = hospitalSpeechDepartment(pushData);
    const isBatch =
        Array.isArray(pushData.departments) && pushData.departments.length > 0;

    // Manager chat: type first — payload.status holds free-text chat body.
    if (type === HOSPITAL_MANAGER_PUSH_TYPE || type === "hospital_manager") {
        return "You have a new message from the hospital staff. Please check your mobile.";
    }

    // Pre-announcement (must win over status === "waiting").
    if (type === "hospital_pre_announcement") {
        const configured = resolveHospitalConfiguredTemplate(
            pushData,
            "pre_announcement",
            token,
            department
        );
        if (configured) {
            return configured;
        }
        if (token && department) {
            return (
                `Token ${token}. Your turn is approaching. ` +
                `Please be ready to proceed to the ${department} department.`
            );
        }
        if (token) {
            return `Token ${token}. Your turn is approaching. Please be ready.`;
        }
        if (department) {
            return (
                `Your turn is approaching. Please be ready to proceed to the ${department} department.`
            );
        }
        return "Your turn is approaching. Please review the details on your mobile.";
    }

    // Multi-department registration snapshot — never interpolate missing token fields.
    if (isBatch) {
        return HOSPITAL_TTS_STATUS_SUMMARY;
    }

    const statusToAnnouncementType = {
        waiting: "waiting",
        registered: "waiting",
        called: "called",
        completed: "completed",
        cancelled: "cancelled",
    };
    const announcementType = statusToAnnouncementType[status];
    if (announcementType) {
        const configured = resolveHospitalConfiguredTemplate(
            pushData,
            announcementType,
            token,
            department
        );
        if (configured) {
            return configured;
        }
    }

    switch (status) {
        case "waiting":
        case "registered":
            if (token && department) {
                return (
                    `Token ${token}. You are waiting for the ${department} department. ` +
                    `We will notify you when your turn is near.`
                );
            }
            if (token) {
                return (
                    `Token ${token}. You are waiting in the queue. ` +
                    `We will notify you when your turn is near.`
                );
            }
            if (department) {
                return (
                    `You are waiting for the ${department} department. ` +
                    `We will notify you when your turn is near.`
                );
            }
            return HOSPITAL_TTS_STATUS_SUMMARY;

        case "called":
            if (token && department) {
                return (
                    `Token ${token}. Please proceed to the ${department} department. ` +
                    `Your token is now being called.`
                );
            }
            if (token) {
                return `Token ${token}. Your token is now being called. Please proceed.`;
            }
            if (department) {
                return (
                    `Please proceed to the ${department} department. ` +
                    `Your token is now being called.`
                );
            }
            return HOSPITAL_TTS_STATUS_SUMMARY;

        case "completed":
            if (token) {
                return `Token ${token}. Your consultation is complete. Thank you.`;
            }
            return "Your consultation is complete. Thank you.";

        case "cancelled":
            if (token) {
                return (
                    `Token ${token}. This visit has been cancelled. ` +
                    `Please contact the hospital staff for assistance.`
                );
            }
            return (
                "This visit has been cancelled. " +
                "Please contact the hospital staff for assistance."
            );

        default:
            if (token) {
                return (
                    `Token ${token}. Your status has been updated. ` +
                    `Please review the details on your mobile.`
                );
            }
            return HOSPITAL_TTS_STATUS_SUMMARY;
    }
}

// 4) Immediately before assigning window.AppUtils
tempUtilsClientDiag("UTILS_APPUTILS_BEFORE_ASSIGN", {
    ...tempUtilsAppUtilsSnapshot(),
    reason: "before_window_AppUtils_assign",
});

window.AppUtils = {
    // ─────────────────────────────────────
    // CSRF Token
    // ─────────────────────────────────────
    getCSRFToken: function () {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    },
    // ─────────────────────────────────────
    // Global Chat Flags
    // ─────────────────────────────────────
    getPrefixedKey: function(key) {
        const project = (window.PROJECT_NAME || 'default').toLowerCase().trim();
        return `${project}:${key}`;
    },

    storageGet: function(key) {
        return localStorage.getItem(this.getPrefixedKey(key));
    },

    storageSet: function(key, value) {
        localStorage.setItem(this.getPrefixedKey(key), value);
    },

    storageRemove: function(key) {
        localStorage.removeItem(this.getPrefixedKey(key));
    },

    /**
     * Opaque recovery key (not browser_id).
     * Used for Safari → installed PWA order/booking recovery.
     * Call sites: Dine Flash Buffet and Dine Flash table-booking only.
     */
    getOrderLookupId: function () {
        const value = this.storageGet("order_lookup_id");
        if (value == null) return null;
        const text = String(value).trim();
        return text || null;
    },

    /**
     * Persist order_lookup_id permanently under its own prefixed key.
     * Never writes browser_id / PushSubscription identity.
     * Call sites: Dine Flash Buffet and Dine Flash table-booking only.
     */
    setOrderLookupId: function (id) {
        if (id == null) return;
        const text = String(id).trim();
        if (!text) return;
        this.storageSet("order_lookup_id", text);
    },

    /**
     * 🚀 Migration: One-time copy of old unprefixed keys to new project-prefixed keys.
     * This ensures users don't lose their session identity (tokens, etc.)
     */
    migrateOldStorage: function() {
        const project = (window.PROJECT_NAME || 'default').toLowerCase().trim();
        if (project === 'default') return;

        const keysToMigrate = [
            'token', 'activeVendor', 'selectedVendors', 'customer_id', 
            'customer_name', 'activeLocation', 'browser_id', 
            'pushSubscription', 'notification_order_states', 'role',
            'activeVendorLogo', 'selectedOutletName'
        ];

        keysToMigrate.forEach(key => {
            const oldVal = localStorage.getItem(key);
            const prefixedKey = this.getPrefixedKey(key);
            const newVal = localStorage.getItem(prefixedKey);

            // Only migrate if old exists and new doesn't
            if (oldVal !== null && newVal === null) {
                console.log(`[AppUtils] Migrated legacy key: ${key} -> ${prefixedKey}`);
                localStorage.setItem(prefixedKey, oldVal);
            }
        });
    },

    isReplyMode: false,
    key: 'activeLocation',
    async get() {
        const prefixedKey = this.getPrefixedKey(this.key);
        // 1️⃣ Try localStorage
        let locationId = localStorage.getItem(prefixedKey);
        if (locationId) {
            return locationId;
        }

        // 2️⃣ Try IndexedDB (using prefixed key)
        try {
            locationId = await idbGet(prefixedKey);
            if (locationId) {
                localStorage.setItem(prefixedKey, locationId); // Rehydrate
                return locationId;
            }
        } catch (e) {
            console.warn("[LocationStore] IndexedDB read failed:", e);
        }

        // 3️⃣ Try Cookie (using prefixed key)
        await new Promise(resolve => setTimeout(resolve, 200));
        locationId = this.getCookie(prefixedKey);
        if (locationId) {
            localStorage.setItem(prefixedKey, locationId); // Rehydrate
            try { await idbSet(prefixedKey, locationId); } catch { }
            return locationId;
        }

        console.warn("[LocationStore] No activeLocation found in any storage.");
        return null;
    },
    async set(locationId) {
        if (!locationId) return;
        const prefixedKey = this.getPrefixedKey(this.key);

        // 1️⃣ Set in localStorage
        localStorage.setItem(prefixedKey, locationId);

        // 2️⃣ Set in IndexedDB
        try {
            await idbSet(prefixedKey, locationId);
        } catch (e) {
            console.warn("[LocationStore] IndexedDB write failed:", e);
        }

        // 3️⃣ Set in cookie
        this.setCookie(prefixedKey, locationId);
    },

    setCookie(name, value, days = 365) {
        const expires = new Date(Date.now() + days * 864e5).toUTCString();
        document.cookie = `${name}=${encodeURIComponent(value)}; path=/; expires=${expires}; SameSite=Lax`;
    },

    getCookie(name) {
        const cookieStr = `; ${document.cookie}`;
        const parts = cookieStr.split(`; ${name}=`);
        if (parts.length >= 2) {
            return decodeURIComponent(parts.pop().split(';')[0]);
        }
        return null;
    },

    // ─────────────────────────────────────
    // Vendor Helpers
    // ─────────────────────────────────────
    getStoredVendors: function () {
        const prefixedKey = this.getPrefixedKey('selectedVendors');
        const storedVendors = localStorage.getItem(prefixedKey);
        return storedVendors ? JSON.parse(storedVendors) : [];
    },
    setSelectedOutletName: function (name) {
        const trimmed = name == null ? "" : String(name).trim();
        if (!trimmed || trimmed.toLowerCase() === "undefined") return;
        const prefixedKey = this.getPrefixedKey('selectedOutletName');
        localStorage.setItem(prefixedKey, trimmed);
    },
    getSelectedOutletName: function () {
        const prefixedKey = this.getPrefixedKey('selectedOutletName');
        const outletName = localStorage.getItem(prefixedKey);
        if (!outletName) return null;
        const trimmed = outletName.trim();
        if (!trimmed || trimmed.toLowerCase() === "undefined") return null;
        return trimmed;
    },
    setCurrentVendors: async function (vendorInput) {
        let newVendors = [];

        if (typeof vendorInput === 'string') {
            newVendors = vendorInput.split(',').map(v => parseInt(v.trim(), 10));
        } else if (Array.isArray(vendorInput)) {
            newVendors = vendorInput.map(v => parseInt(v, 10));
        }

        const updatedList = Array.from(new Set(newVendors));
        const lastVendor = updatedList[updatedList.length - 1];

        const vendorsKey = this.getPrefixedKey('selectedVendors');
        const activeKey = this.getPrefixedKey('activeVendor');

        // Store in localStorage
        localStorage.setItem(vendorsKey, JSON.stringify(updatedList));
        if (lastVendor) {
            localStorage.setItem(activeKey, lastVendor);
        }

        // Store in IndexedDB
        try {
            await idbSet(vendorsKey, updatedList);
            if (lastVendor) {
                await idbSet(activeKey, lastVendor);
            }
        } catch (e) {
            console.warn("[VendorStore] Failed to write to IndexedDB:", e);
        }

        // Store in cookies
        this.setCookie(vendorsKey, JSON.stringify(updatedList));
        if (lastVendor) {
            this.setCookie(activeKey, lastVendor);
        }
    },
    getActiveVendor: async function () {
        const activeKey = this.getPrefixedKey('activeVendor');
        let vendorId = localStorage.getItem(activeKey);
        if (vendorId) {
            return parseInt(vendorId, 10);
        }

        try {
            vendorId = await idbGet(activeKey);
            if (vendorId) {
                localStorage.setItem(activeKey, vendorId);
                return parseInt(vendorId, 10);
            }
        } catch (e) {
            console.warn("[VendorStore] IndexedDB read failed:", e);
        }

        await new Promise(resolve => setTimeout(resolve, 200));
        vendorId = this.getCookie(activeKey);
        if (vendorId) {
            localStorage.setItem(activeKey, vendorId);
            try { await idbSet(activeKey, vendorId); } catch { }
            return parseInt(vendorId, 10);
        }

        console.warn("[VendorStore] No activeVendor found.");
        return null;
    },

    appendVendorIfNotExists: async function (vendorId) {
        const vendorsKey = this.getPrefixedKey('selectedVendors');
        const activeKey = this.getPrefixedKey('activeVendor');

        let selectedVendors = JSON.parse(localStorage.getItem(vendorsKey)) || [];
        selectedVendors.push(vendorId);

        const updatedList = Array.from(new Set(selectedVendors));
        localStorage.setItem(vendorsKey, JSON.stringify(updatedList));
        localStorage.setItem(activeKey, updatedList[updatedList.length - 1]);

        try {
            await idbSet(vendorsKey, updatedList);
            await idbSet(activeKey, updatedList[updatedList.length - 1]);
        } catch (e) {
            console.warn("[VendorStore] IndexedDB write failed:", e);
        }

        this.setCookie(vendorsKey, JSON.stringify(updatedList));
        this.setCookie(activeKey, updatedList[updatedList.length - 1]);
    },
    // ─────────────────────────────────────
    // Token Management
    // ─────────────────────────────────────
    getToken: async function () {
        const tokenKey = this.getPrefixedKey('token');
        let token = localStorage.getItem(tokenKey);
        if (token) {
            return token;
        }

        try {
            token = await idbGet(tokenKey);
            if (token) {
                localStorage.setItem(tokenKey, token);
                return token;
            }
        } catch (e) {
            console.warn("[TokenStore] IndexedDB read failed:", e);
        }

        await new Promise(resolve => setTimeout(resolve, 200));
        token = this.getCookie(tokenKey);
        if (token) {
            localStorage.setItem(tokenKey, token);
            try { await idbSet(tokenKey, token); } catch { }
            return token;
        }

        console.warn("[TokenStore] No token found.");
        return null;
    },

    setToken: async function (token) {
        if (!token) return;
        const tokenKey = this.getPrefixedKey('token');
        localStorage.setItem(tokenKey, token);
        try { await idbSet(tokenKey, token); } catch (e) {
            console.warn("[TokenStore] IndexedDB write failed:", e);
        }
        this.setCookie(tokenKey, token);
    },

    // ─────────────────────────────────────
    // Safari → installed PWA pending handoff
    // (dine_flash_buffet + dine_flash call sites; surface gated here)
    // ─────────────────────────────────────

    /**
     * Fire-and-forget HANDOFF diagnostic breadcrumb via dine_flash_client_diag.
     * Server logs only — no console output. Never throws, never awaits, never
     * blocks. Dine Flash / Dine Flash Buffet only. Instrumentation only.
     */
    handoffDiag: function (step, fields) {
        const project = (window.PROJECT_NAME || "").toLowerCase().trim();
        if (project !== "dine_flash" && project !== "dine_flash_buffet") return;
        try {
            const browserId =
                (typeof this.getCurrentBrowserId === "function" && this.getCurrentBrowserId()) ||
                null;
            const url = `${this.getStartUrl()}api/dine_flash_client_diag/`;
            fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken":
                        (typeof this.getCSRFToken === "function" && this.getCSRFToken()) || "",
                },
                credentials: "same-origin",
                keepalive: true,
                body: JSON.stringify({
                    step,
                    source: "page",
                    browser_id: browserId,
                    project,
                    timestamp: Date.now(),
                    ...(fields || {}),
                }),
            }).catch(() => {});
        } catch (e) {
            // Diagnostics must never break handoff.
        }
    },

    clearPendingHandoffCookie: function () {
        this.setCookie(this.getPrefixedKey('pending_handoff'), '', -1);
    },

    /**
     * Safari-only: persist a short-lived handoff cookie so the installed PWA
     * can adopt this order session on next open. Callers gate by project.
     */
    writePendingHandoff: function (token, vendorId, locationId) {
        const standalone = Boolean(window.navigator.standalone);
        this.handoffDiag("HANDOFF_WRITE_ENTER", {
            standalone,
            token_no: token != null ? String(token).trim() : "",
            vendor_id: vendorId != null ? String(vendorId).trim() : "",
            location_id:
                locationId != null && typeof locationId !== "object"
                    ? String(locationId).trim()
                    : "",
            page: "home",
        });

        // Surface gate: browser context only (not installed PWA).
        if (window.navigator.standalone) {
            this.handoffDiag("HANDOFF_WRITE_SKIP", {
                reason: "standalone",
                standalone: true,
                page: "home",
            });
            return;
        }

        const tokenStr = token != null ? String(token).trim() : '';
        const vendorStr = vendorId != null ? String(vendorId).trim() : '';
        if (!tokenStr || !vendorStr) {
            this.handoffDiag("HANDOFF_WRITE_SKIP", {
                reason: "missing_token_or_vendor",
                has_token: Boolean(tokenStr),
                has_vendor: Boolean(vendorStr),
                standalone: false,
                page: "home",
            });
            return;
        }

        const payload = {
            token_no: tokenStr,
            vendor_id: vendorStr,
        };
        // Skip Promises / non-scalars (e.g. unresolved AppUtils.get()).
        if (
            locationId != null &&
            typeof locationId !== 'object' &&
            String(locationId).trim() !== ''
        ) {
            payload.location_id = String(locationId).trim();
        }

        // Buffet recovery key: prefer permanently stored order_lookup_id, else
        // current surface browser_id value (Safari S). Never overwrites browser_id.
        const orderLookupId =
            (typeof this.getOrderLookupId === "function" && this.getOrderLookupId()) ||
            (typeof this.getBrowserId === "function" && this.getBrowserId()) ||
            null;
        if (orderLookupId) {
            payload.order_lookup_id = String(orderLookupId).trim();
        }

        this.handoffDiag("HANDOFF_WRITE_PAYLOAD", {
            token_no: payload.token_no,
            vendor_id: payload.vendor_id,
            location_id: payload.location_id || "",
            order_lookup_id: payload.order_lookup_id || "",
            has_location: Boolean(payload.location_id),
            has_order_lookup_id: Boolean(payload.order_lookup_id),
            page: "home",
        });

        try {
            this.setCookie(this.getPrefixedKey('pending_handoff'), JSON.stringify(payload), 1);
            this.handoffDiag("HANDOFF_WRITE_OK", {
                token_no: payload.token_no,
                vendor_id: payload.vendor_id,
                location_id: payload.location_id || "",
                page: "home",
            });

            // Same-page readback: confirm cookie is readable in Safari immediately
            // after write (diagnostics only — does not affect handoff behavior).
            const readbackRaw = this.getCookie(this.getPrefixedKey('pending_handoff'));
            if (!readbackRaw) {
                this.handoffDiag("HANDOFF_WRITE_READBACK_MISSING", {
                    token_no: payload.token_no,
                    vendor_id: payload.vendor_id,
                    cookie_present: false,
                    page: "home",
                });
            } else {
                try {
                    const readbackParsed = JSON.parse(readbackRaw);
                    const parsedToken =
                        readbackParsed && readbackParsed.token_no != null
                            ? String(readbackParsed.token_no).trim()
                            : "";
                    const parsedVendor =
                        readbackParsed && readbackParsed.vendor_id != null
                            ? String(readbackParsed.vendor_id).trim()
                            : "";
                    const parsedLocation =
                        readbackParsed && readbackParsed.location_id != null
                            ? String(readbackParsed.location_id).trim()
                            : "";
                    const expectedLocation = payload.location_id || "";
                    const payloadMatches =
                        parsedToken === payload.token_no &&
                        parsedVendor === payload.vendor_id &&
                        parsedLocation === expectedLocation;
                    this.handoffDiag("HANDOFF_WRITE_READBACK_OK", {
                        token_no: payload.token_no,
                        vendor_id: payload.vendor_id,
                        cookie_present: true,
                        cookie_length: readbackRaw.length,
                        parse_ok: true,
                        parsed_token_no: parsedToken,
                        parsed_vendor_id: parsedVendor,
                        parsed_location_id: parsedLocation,
                        payload_matches: payloadMatches,
                        page: "home",
                    });
                } catch (parseErr) {
                    this.handoffDiag("HANDOFF_WRITE_READBACK_PARSE_FAIL", {
                        cookie_length: readbackRaw.length,
                        parse_error:
                            parseErr && parseErr.message
                                ? String(parseErr.message)
                                : String(parseErr),
                        page: "home",
                    });
                }
            }
        } catch (e) {
            console.warn('[PendingHandoff] write failed:', e);
            this.handoffDiag("HANDOFF_WRITE_FAIL", {
                error: e && e.message ? String(e.message) : String(e),
                token_no: payload.token_no,
                vendor_id: payload.vendor_id,
                location_id: payload.location_id || "",
                page: "home",
            });
        }
    },

    /**
     * Installed-PWA only: if a pending handoff cookie exists, hydrate existing
     * storage and consume the cookie. Idempotent — subsequent calls no-op.
     * Never throws into the relaunch flow.
     */
    adoptPendingHandoffIfPresent: async function () {
        try {
            const standalone = Boolean(window.navigator.standalone);
            this.handoffDiag("HANDOFF_ADOPT_ENTER", {
                standalone,
                page: "outlet_selection",
            });

            // Surface gate: installed PWA only.
            if (!window.navigator.standalone) {
                this.handoffDiag("HANDOFF_ADOPT_SKIP", {
                    reason: "not_standalone",
                    standalone: false,
                    page: "outlet_selection",
                });
                return false;
            }

            const cookieKey = this.getPrefixedKey('pending_handoff');
            const raw = this.getCookie(cookieKey);
            this.handoffDiag("HANDOFF_ADOPT_COOKIE_LOOKUP", {
                has_cookie: Boolean(raw),
                standalone: true,
                page: "outlet_selection",
            });
            if (!raw) {
                this.handoffDiag("HANDOFF_ADOPT_SKIP", {
                    reason: "no_cookie",
                    has_cookie: false,
                    page: "outlet_selection",
                });
                return false;
            }

            let payload;
            try {
                payload = JSON.parse(raw);
                this.handoffDiag("HANDOFF_ADOPT_PARSE_OK", {
                    page: "outlet_selection",
                });
            } catch (e) {
                console.warn('[PendingHandoff] malformed JSON:', e);
                this.handoffDiag("HANDOFF_ADOPT_PARSE_FAIL", {
                    reason: "malformed_json",
                    error: e && e.message ? String(e.message) : String(e),
                    page: "outlet_selection",
                });
                this.clearPendingHandoffCookie();
                this.handoffDiag("HANDOFF_ADOPT_COOKIE_CLEARED", {
                    reason: "malformed_json",
                    page: "outlet_selection",
                });
                return false;
            }

            if (!payload || typeof payload !== 'object') {
                this.handoffDiag("HANDOFF_ADOPT_SKIP", {
                    reason: "invalid_payload_shape",
                    page: "outlet_selection",
                });
                this.clearPendingHandoffCookie();
                this.handoffDiag("HANDOFF_ADOPT_COOKIE_CLEARED", {
                    reason: "invalid_payload_shape",
                    page: "outlet_selection",
                });
                return false;
            }

            const token = payload.token_no != null ? String(payload.token_no).trim() : '';
            const vendorId = payload.vendor_id != null ? String(payload.vendor_id).trim() : '';
            const locationId =
                payload.location_id != null ? String(payload.location_id).trim() : '';
            const orderLookupId =
                payload.order_lookup_id != null
                    ? String(payload.order_lookup_id).trim()
                    : '';

            this.handoffDiag("HANDOFF_ADOPT_VALIDATE", {
                token_no: token,
                vendor_id: vendorId,
                location_id: locationId,
                order_lookup_id: orderLookupId,
                has_token: Boolean(token),
                has_vendor: Boolean(vendorId),
                has_location: Boolean(locationId),
                has_order_lookup_id: Boolean(orderLookupId),
                page: "outlet_selection",
            });

            if (!token || !vendorId) {
                this.handoffDiag("HANDOFF_ADOPT_SKIP", {
                    reason: "missing_token_or_vendor",
                    has_token: Boolean(token),
                    has_vendor: Boolean(vendorId),
                    page: "outlet_selection",
                });
                this.clearPendingHandoffCookie();
                this.handoffDiag("HANDOFF_ADOPT_COOKIE_CLEARED", {
                    reason: "missing_token_or_vendor",
                    page: "outlet_selection",
                });
                return false;
            }

            try {
                if (locationId) {
                    this.handoffDiag("HANDOFF_ADOPT_STORAGE_BEFORE", {
                        branch: "set_location",
                        location_id: locationId,
                        page: "outlet_selection",
                    });
                    await this.set(locationId);
                    this.handoffDiag("HANDOFF_ADOPT_STORAGE_AFTER", {
                        branch: "set_location",
                        location_id: locationId,
                        page: "outlet_selection",
                    });
                }
                // Must pass a string — numeric input yields an empty vendor list.
                this.handoffDiag("HANDOFF_ADOPT_STORAGE_BEFORE", {
                    branch: "set_current_vendors",
                    vendor_id: vendorId,
                    page: "outlet_selection",
                });
                await this.setCurrentVendors(String(vendorId));
                this.handoffDiag("HANDOFF_ADOPT_STORAGE_AFTER", {
                    branch: "set_current_vendors",
                    vendor_id: vendorId,
                    page: "outlet_selection",
                });
                this.handoffDiag("HANDOFF_ADOPT_STORAGE_BEFORE", {
                    branch: "set_token",
                    token_no: token,
                    page: "outlet_selection",
                });
                await this.setToken(token);
                this.handoffDiag("HANDOFF_ADOPT_STORAGE_AFTER", {
                    branch: "set_token",
                    token_no: token,
                    page: "outlet_selection",
                });
                // Permanently store recovery key under its own key — do not touch browser_id.
                if (orderLookupId && typeof this.setOrderLookupId === "function") {
                    this.handoffDiag("HANDOFF_ADOPT_STORAGE_BEFORE", {
                        branch: "set_order_lookup_id",
                        order_lookup_id: orderLookupId,
                        page: "outlet_selection",
                    });
                    this.setOrderLookupId(orderLookupId);
                    this.handoffDiag("HANDOFF_ADOPT_STORAGE_AFTER", {
                        branch: "set_order_lookup_id",
                        order_lookup_id: orderLookupId,
                        page: "outlet_selection",
                    });
                }
            } catch (e) {
                // Retain cookie so adoption can retry after a transient storage failure.
                console.warn('[PendingHandoff] storage update failed:', e);
                this.handoffDiag("HANDOFF_ADOPT_SKIP", {
                    reason: "storage_update_failed_cookie_retained",
                    error: e && e.message ? String(e.message) : String(e),
                    token_no: token,
                    vendor_id: vendorId,
                    page: "outlet_selection",
                });
                return false;
            }

            this.clearPendingHandoffCookie();
            this.handoffDiag("HANDOFF_ADOPT_COOKIE_CLEARED", {
                reason: "adopt_success",
                page: "outlet_selection",
            });
            this.handoffDiag("HANDOFF_ADOPT_OK", {
                token_no: token,
                vendor_id: vendorId,
                location_id: locationId,
                order_lookup_id: orderLookupId,
                page: "outlet_selection",
            });
            return true;
        } catch (e) {
            console.warn('[PendingHandoff] unexpected error:', e);
            this.handoffDiag("HANDOFF_ADOPT_FAIL", {
                reason: "unexpected_exception",
                error: e && e.message ? String(e.message) : String(e),
                page: "outlet_selection",
            });
            return false;
        }
    },

    setCustomerId: function (id) {
        const key = this.getPrefixedKey('customer_id');
        localStorage.setItem(key, id);
        this.setCookie(key, id);
    },
    setCustomerName: function (name) {
        const key = this.getPrefixedKey('customer_name');
        localStorage.setItem(key, name);
        this.setCookie(key, name);
    },
    getCustomerName: function () {
        const key = this.getPrefixedKey('customer_name');
        let name = localStorage.getItem(key);
        if (!name) {
            name = this.getCookie(key);
        }
        return name;
    },
    // ─────────────────────────────────────
    // Notification Sound
    // ─────────────────────────────────────
    // ============================================
    // Unlock Notification Sound + Preferred Voice (iOS + Android)
    // ============================================
    unlockNotificationSound: async function () {
        // console.log("[Unlock] Unlocking notification sound and TTS...");

        // 🔊 Unlock notification sound
        unlockedNotificationAudio = new Audio(`${BASE}static/orders/audio/0112.mp3`);
        unlockedNotificationAudio.volume = 1.0;
        unlockedNotificationAudio.muted = false;
        unlockedNotificationAudio.playsInline = true;

        unlockedNotificationAudio.play().then(() => {
            unlockedNotificationAudio.pause();
            unlockedNotificationAudio.currentTime = 0;
            // console.log('🔓 Notification sound unlocked.');
        }).catch(err => {
            console.warn('🔇 Sound unlock failed:', err);
        });

        // 🗣 Unlock speech synthesis
        try {
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
            const isAndroid = /Android/i.test(navigator.userAgent);

            const iosPreferredNames = ["Samantha", "Karen", "Moira"];
            const androidPreferredNames = ["Assamese India", "Google US English", "English (United States)"];

            let voices = window.speechSynthesis.getVoices();

            // ✅ Wait for voices to load only on Android if none yet
            if (isAndroid && voices.length === 0) {
                // console.log("[TTS] Waiting for voices to load on Android...");
                voices = await new Promise(resolve => {
                    window.speechSynthesis.onvoiceschanged = () => {
                        const loadedVoices = window.speechSynthesis.getVoices();
                        if (loadedVoices.length) {
                            // console.log(`[TTS] Voices loaded: ${loadedVoices.length}`);
                            resolve(loadedVoices);
                        }
                    };
                });
            }

            // 1️⃣ Try platform preferred names first
            let preferredVoice = voices.find(v =>
                v.lang.startsWith("en") &&
                (isIOS
                    ? iosPreferredNames.includes(v.name)
                    : androidPreferredNames.includes(v.name))
            );

            // 2️⃣ If no match, try any English female voice
            if (!preferredVoice) {
                preferredVoice = voices.find(v =>
                    v.lang.startsWith("en") &&
                    (/female/i.test(v.name) ||
                        /(Karen|Samantha|Moira)/i.test(v.name) ||
                        /Google.*English.*Female/i.test(v.name))
                );
            }

            // 3️⃣ If no match, try any English voice
            if (!preferredVoice) {
                preferredVoice = voices.find(v => v.lang.startsWith("en"));
            }

            // 4️⃣ If still no match, fallback to first available
            if (!preferredVoice) {
                preferredVoice = voices[0];
            }

            // console.log(`[TTS] Unlocking with preferred voice: ${preferredVoice?.name || "default"}`);

            // Unlock utterance (silent but valid speech)
            const unlockUtterance = new SpeechSynthesisUtterance("Voice ready");
            unlockUtterance.voice = preferredVoice;
            unlockUtterance.volume = 0; // Silent but still counts
            window.speechSynthesis.speak(unlockUtterance);

            // console.log("🔓 Speech synthesis unlocked and preferred voice preloaded.");
        } catch (e) {
            console.warn("🔇 Speech synthesis unlock failed:", e);
        }
    },


    // Use this in your existing method
    playNotificationSound: function (pattern, duration, volume = 1.0) {
        if (unlockedNotificationAudio) {
            unlockedNotificationAudio.volume = Math.max(0, Math.min(volume, 1));
            unlockedNotificationAudio.currentTime = 0;
            unlockedNotificationAudio.play().catch(err =>
                console.error('Error playing notification sound:', err)
            );
        } else {
            console.warn('🔕 Notification sound is not unlocked yet.');
        }
        // Start vibration using reusable controller
        VibrationManager.start(pattern, duration);
    },
    /**
     * Plays a flavour-specific welcome message using Text-to-Speech (TTS).
     *
     * Logic:
     * 1. Defines message sets for each project flavour.
     * 2. Detects current PROJECT_NAME and selects appropriate messages.
     * 3. Combines messages into a single TTS utterance.
     * 4. Ensures a clean, natural voice output across browsers.
     */
    playWelcomeMessage: function () {

        // -------------------------------------------------------------
        // 1️⃣ Define all welcome messages (flavour-based)
        // -------------------------------------------------------------
        const WELCOME_MESSAGES = {
            default: [
                "Hi, Good Day! Welcome.",
                "Kindly enter the Bill Number and Send so that we can track your order."
            ],

            food_flash: [
                "Hi, Good Day! Welcome to our outlet.",
                "Kindly enter the Bill Number and Send so that we can track your order."
            ],

            airline_flash: [
                "Hi, Good Day! Welcome to our airlines.",
                "Enter your Sequence Code to stay updated on your boarding schedule and gate announcements."
            ],

            dine_flash: [
                "Hi, Good Day! Welcome to our restaurant.",
                "Kindly enter your booking number to check your table allocation status."
            ],

            hospital_flash: [
                "Good day. Welcome to the hospital.",
                "Enter your token details to track your queue status."
            ]
        };

        // -------------------------------------------------------------
        // 2️⃣ Detect active flavour
        // -------------------------------------------------------------
        const projectKey = (window.PROJECT_NAME || "default").toLowerCase();
        const selectedMessages = WELCOME_MESSAGES[projectKey] || WELCOME_MESSAGES.default;

        // console.log("WelcomeMessageService: Project:", projectKey);
        // console.log("Selected TTS welcome messages:", selectedMessages);

        // -------------------------------------------------------------
        // 3️⃣ Prepare Text-to-Speech output
        // -------------------------------------------------------------
        const fullMessage = selectedMessages.join(" ");

        const utterance = new SpeechSynthesisUtterance(fullMessage);
        utterance.pitch = 1;
        utterance.rate = 1;
        utterance.volume = 1;

        // Cancel any previous TTS before speaking
        const synth = window.speechSynthesis;
        synth.cancel();

        // -------------------------------------------------------------
        // 4️⃣ Speak welcome message
        // -------------------------------------------------------------
        synth.speak(utterance);
    },
    // ─────────────────────────────────────
    // Viewport Utility
    // ─────────────────────────────────────
    adjustChatResponsePadding: function () {
        const chatResponse = document.querySelector('.chat-response');
        const chatFooter = document.querySelector('.chat-footer');
        const premiumFooter = document.querySelector('.premium-footer');

        if (!chatResponse) return;

        const chatFooterHeight = chatFooter?.offsetHeight || 0;
        const premiumFooterHeight = premiumFooter?.offsetHeight || 0;

        const viewportHeight = window.visualViewport?.height || window.innerHeight;
        const keyboardOffset = window.innerHeight - viewportHeight;

        const totalBottomOffset = chatFooterHeight + premiumFooterHeight + keyboardOffset;

        chatResponse.style.paddingBottom = `${totalBottomOffset}px`; // Add safe spacing

        // Optional: Dynamically limit height if needed
        const topOffset = 120; // Same as your padding-top
        const calculatedHeight = viewportHeight - chatFooterHeight - premiumFooterHeight - 20;
        chatResponse.style.maxHeight = `${calculatedHeight}px`;
    },
    initPaddingAdjustmentListeners: function () {
        const self = this;
        const adjust = () => self.adjustChatResponsePadding();

        window.addEventListener('load', adjust);
        window.addEventListener('resize', adjust);
        window.visualViewport?.addEventListener('resize', adjust);
        window.addEventListener('focusin', adjust);
        window.addEventListener('focusout', adjust);
    },

    showToast: function (message) {
        const toast = document.getElementById('customToast');
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000); // 3 seconds
    },
    // ─────────────────────────────────────
    // Notification State (Persistent)
    // ─────────────────────────────────────
    getNotificationStorageKey: function() {
        return this.getPrefixedKey("notification_order_states");
    },

    saveOrderStates: function (orderStates) {
        try {
            const key = this.getNotificationStorageKey();
            localStorage.setItem(key, JSON.stringify(orderStates));
        } catch (e) {
            console.error("Failed to save orderStates to storage", e);
        }
    },

    loadOrderStates: function () {
        try {
            const key = this.getNotificationStorageKey();
            const stored = localStorage.getItem(key);
            return stored ? JSON.parse(stored) : {};
        } catch (e) {
            console.error("Failed to load orderStates from storage", e);
            return {};
        }
    },
    // ============================================
    // Unlock Notification Sound + Preferred Voice (iOS + Android)
    // ============================================
    notifyOrderReady: function (pushData) {
        try {
            // console.log(`[TTS] Speaking order ready message: Order ${pushData.token_no} - Counter ${pushData.counter_no}`);
            const synth = window.speechSynthesis;

            // --- ✈️ Helper: Make flight numbers sound natural ---
            function formatFlightNoForSpeech(flightNo) {
                if (!flightNo) return '';

                const numberWords = {
                    '0': 'zero', '1': 'one', '2': 'two', '3': 'three',
                    '4': 'four', '5': 'five', '6': 'six', '7': 'seven',
                    '8': 'eight', '9': 'nine'
                };

                return flightNo
                    .replace(/[-_]/g, ' ') // treat hyphen/underscore as pause
                    .split('')
                    .map(ch => {
                        if (/[0-9]/.test(ch)) {
                            return numberWords[ch];
                        } else if (/[A-Za-z]/.test(ch)) {
                            return ch.toUpperCase();
                        } else if (/\s/.test(ch)) {
                            return ', '; // gentle pause
                        } else {
                            return ch;
                        }
                    })
                    .join(' ')
                    .replace(/\s+,/g, ',') // clean spacing
                    .trim();
            }

            /**
             * Text-to-Speech (TTS) voice messages for each order or flight status.
             *
             * The logic below ensures voice announcements are consistent with
             * notification modal messages defined in `statusMessages.js`.
             *
             * Supports both Food Flash (order-based) and Airline Flash (flight-based) projects.
             * Hospital Flash uses a dedicated builder so Food/Dine wording never leaks.
             */
            let message;

            // Hospital Flash only — early return path keeps all other flavours identical.
            if (isHospitalFlashProject()) {
                message = buildHospitalFlashSpokenMessage(pushData);
                if (!message) {
                    return;
                }
            } else if (pushData.status === 'ready') {
                // 🍴 Food Flash (Buffet flavour uses a simpler “token ready” line)
                if (projectName === "dine_flash_buffet") {
                    message = `Your order ${pushData.token_no} is now ready. Please collect it.`;
                } else {
                    message = `Your order number ${pushData.token_no} is ready at counter ${pushData.counter_no}. Please collect it.`;
                }

            } else if (pushData.status === 'cancelled') {
                message = `Unfortunately, your order number ${pushData.token_no} has been cancelled. Please contact the staff for assistance.`;

            } else if (pushData.status === 'delivered') {
                message = `Your order number ${pushData.token_no} has been delivered. Thank you for choosing us.`;

            } else if (pushData.status === 'preparing') {
                message = `Your order number ${pushData.token_no} is currently being prepared. Please wait while we finish it.`;

            } else if (pushData.status === 'checked_in') {
                // ✈️ Airline Flash
                const flightSpeech = formatFlightNoForSpeech(pushData.flight_no);
                message = `You have successfully checked in for flight ${flightSpeech}.`;

            } else if (pushData.status === 'boarding_shortly') {
                const flightSpeech = formatFlightNoForSpeech(pushData.flight_no);
                message = `Your flight ${flightSpeech} will be ready for boarding shortly. Kindly wait for the next announcement.`;

            } else if (pushData.status === 'boarding_announced') {
                const flightSpeech = formatFlightNoForSpeech(pushData.flight_no);
                message = `Flight ${flightSpeech} is ready for boarding. Kindly proceed through the boarding gate.`;

            } else if (pushData.status === 'rescheduled') {
                const flightSpeech = formatFlightNoForSpeech(pushData.flight_no);
                message = `Flight ${flightSpeech} has been rescheduled. Please contact the airline staff for updated information.`;

            } else if (pushData.status === 'gate_change') {
                message = `Attention passenger. The gate number has changed. The revised gate number will be announced shortly.`;

            } else if (pushData.status === 'flightcancel') {
                message = `Attention passenger. Please contact the airline staff for assistance.`;

            } else if (projectName === 'airline_flash' && pushData.type === 'airline_manager') {
                // 📩 Manager broadcast messages
                message = `You have a new message. Please check the app for details.`;
            }
            // 🍽️ Dine Flash
            else if (pushData.status === 'waiting') {
                const DineSpeech = formatFlightNoForSpeech(pushData.booking_no);
                message = `Your booking ${DineSpeech} is waiting for table allocation. Please wait while we assign your table.`;

            } else if (pushData.status === 'allocated') {
                const DineSpeech = formatFlightNoForSpeech(pushData.booking_no);
                message = `Your booking ${DineSpeech} has been allocated an available area. Please proceed to your assigned area.`;

            } else if (pushData.status === 'operation_closed') {
                message = "Thank you for choosing us today. We hope you enjoyed your meal. Have a great day ahead."

            } else if (pushData.status === 'booking_cancelled') {
                const DineSpeech = formatFlightNoForSpeech(pushData.booking_no);
                message = `Unfortunately, your booking ${DineSpeech} has been cancelled. Please contact the restaurant staff for assistance.`;

            } else if (pushData.type === 'dine_manager') {
                // 📩 Manager broadcast messages
                message = `You have a new message. Please check the app for details.`;
            } else if (pushData.type === HOSPITAL_MANAGER_PUSH_TYPE) {
                message = `You have a new message. Please check the app for details.`;
            } else if (pushData.type === 'buffet_manager') {
                message = `You have a new message. Please check the app for details.`;
            }
            else {
                // 🧾 Default fallback
                message = `Your order number ${pushData.token_no} has a new update. Please check the app for details.`;
            }


            // console.log(`[TTS] Message to speak: ${message}`);
            const utterance = new SpeechSynthesisUtterance(message);

            // --- 🔊 Voice setup ---
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
            const iosPreferredNames = ["Samantha", "Karen", "Moira"];
            const androidPreferredNames = ["Google US English", "English (United States)"];

            const voices = synth.getVoices();
            // console.log(`[TTS] Voices available: ${voices.length}`);

            const preferredVoice = voices.find(v =>
                v.lang.startsWith("en") &&
                (isIOS
                    ? iosPreferredNames.includes(v.name)
                    : androidPreferredNames.includes(v.name))
            ) || voices[0]; // fallback

            if (preferredVoice) {
                utterance.voice = preferredVoice;
                // console.log(`[TTS] Using preferred voice: ${preferredVoice.name}`);
            } else {
                // console.log("[TTS] Using default system voice.");
            }

            utterance.pitch = 1;
            utterance.rate = 1;
            utterance.volume = 1;

            synth.cancel();
            synth.speak(utterance);

        } catch (e) {
            console.error("[TTS] Failed to notify order readiness:", e);
        }
    },

    /**
         * Convert a base64 VAPID public key to a Uint8Array
         * for use with the PushManager.subscribe() method.
         */
    urlBase64ToUint8Array: function (base64String) {
        const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    },

    /**
     * Get or generate a unique browser identifier.
     * Unified with project-prefixed storage.
     */
    getBrowserId: function () {
        // 1️⃣ Try the new project-prefixed storage first
        let browserId = this.storageGet("browser_id");

        if (!browserId) {
            // 2️⃣ Fallback for legacy keys (e.g., 'browser_id_food_flash')
            const projectKey = (() => {
                const pn = (window.PROJECT_NAME || '').toString().toLowerCase().trim();
                if (pn) return pn;
                const path = (window.location?.pathname || '').toLowerCase();
                const parts = path.split('/').filter(Boolean);
                return parts[0] || 'default';
            })();
            const legacyKey = `browser_id_${projectKey}`;
            browserId = localStorage.getItem(legacyKey);

            if (browserId) {
                // Migrate to new prefixed storage
                this.storageSet("browser_id", browserId);
            }
        }

        if (!browserId) {
            // 3️⃣ Generate new if still missing
            browserId = crypto.randomUUID();
            this.storageSet("browser_id", browserId);
        }
        return browserId;
    },

    /**
     * Retrieves the current browser ID if it exists, without generating a new one.
     */
    getCurrentBrowserId: function () {
        let browserId = this.storageGet("browser_id");

        if (!browserId) {
            const projectKey = (() => {
                const pn = (window.PROJECT_NAME || '').toString().toLowerCase().trim();
                if (pn) return pn;
                const path = (window.location?.pathname || '').toLowerCase();
                const parts = path.split('/').filter(Boolean);
                return parts[0] || 'default';
            })();
            const legacyKey = `browser_id_${projectKey}`;
            browserId = localStorage.getItem(legacyKey);

            if (browserId) {
                this.storageSet("browser_id", browserId);
            }
        }

        if (!browserId) {
            console.warn("[AppUtils] No browser ID found.");
            return null;
        }
        return browserId;
    },
    // ─────────────────────────────────────
    // Device Detection
    // ─────────────────────────────────────
    getDeviceName: function () {
        const ua = navigator.userAgent;
        let deviceName = '';

        const isMobile = {
            Android: () => /Android/i.test(ua),
            iOS: () => /iPhone|iPad|iPod/i.test(ua),
            Windows: () => /IEMobile/i.test(ua),
            Zebra: () => /TC70|TC55/i.test(ua),
            Datalogic: () => /DL-AXIS/i.test(ua),
            Bluebird: () => /EF500/i.test(ua),
            Honeywell: () => /CT50/i.test(ua),
            BlackBerry: () => /BlackBerry/i.test(ua),
            any: function () {
                return (
                    this.Android() || this.iOS() || this.Windows() ||
                    this.Zebra() || this.Datalogic() || this.Bluebird() ||
                    this.Honeywell() || this.BlackBerry()
                );
            }
        };

        if (isMobile.Zebra()) deviceName = 'Zebra';
        else if (isMobile.Datalogic()) deviceName = 'Datalogic';
        else if (isMobile.Bluebird()) deviceName = 'Bluebird';
        else if (isMobile.Honeywell()) deviceName = 'Honeywell';
        else if (isMobile.BlackBerry()) deviceName = 'BlackBerry';
        else if (isMobile.iOS()) deviceName = 'iOS';
        else if (isMobile.Android()) {
            const match = ua.match(/\((?:Linux; )?Android [^;]+; ([^)]+)\)/);
            if (match && match[1]) {
                deviceName = match[1].trim(); // Example: "Redmi Note 10", "SM-G991B"
            } else {
                deviceName = 'Android';
            }
        } else if (isMobile.Windows()) {
            deviceName = 'Windows';
        }

        // console.log('Device Name:', deviceName);
        return deviceName;
    },
    getNotificationHelpPath: function () {
        const model = this.getDeviceName();

        if (/Samsung|SM-/i.test(model)) {
            return "Settings > Apps > Your App > Notifications";
        } else if (/Redmi|Mi|Xiaomi/i.test(model)) {
            return "Settings > Notifications > Manage Notifications > Your App";
        } else if (/Vivo/i.test(model)) {
            return "Settings > Notifications and status bar > Notification management";
        } else if (/Realme/i.test(model)) {
            return "Settings > App Management > Your App > Notifications";
        } else if (/Oppo/i.test(model)) {
            return "Settings > App Management > Your App > Notification management";
        } else if (/iPhone|iPad/i.test(model)) {
            return "Settings > Notifications > Your App";
        }

        return "Please check device Settings > Apps > Your App > Notifications";
    },

    warnBackgroundRestrictions: function () {
        const model = this.getDeviceName();

        if (/Redmi|Mi|Xiaomi/i.test(model)) {
            this.showToast("Set 'Battery Saver' to 'No restrictions' for this app under Battery & Performance.");
        } else if (/Vivo|Oppo|Realme/i.test(model)) {
            this.showToast("Enable 'Auto Start' and allow background activity for this app in system settings.");
        }
    },

    openBrowserNotificationSettings: function () {
        this.showToast("To enable notifications, go to your browser > Site Settings > Notifications.");
    },
    getStartUrl: function () {
        const base = window.BASE || '/caller_on/'
        return base
    }

};

// 5) Immediately after assigning window.AppUtils
tempUtilsClientDiag("UTILS_APPUTILS_AFTER_ASSIGN", {
    ...tempUtilsAppUtilsSnapshot(),
    reason: "after_window_AppUtils_assign",
});

// 🚀 Immediately run migration on script load to avoid race conditions
if (typeof window !== 'undefined') {
    window.AppUtils.migrateOldStorage();
}

} catch (__tempUtilsModuleErr) {
    tempUtilsClientDiag("UTILS_MODULE_EVAL_EXCEPTION", {
        ...tempUtilsAppUtilsSnapshot(),
        error: String(
            __tempUtilsModuleErr && __tempUtilsModuleErr.message
                ? __tempUtilsModuleErr.message
                : __tempUtilsModuleErr
        ).slice(0, 200),
        reason: "module_eval_exception",
    });
    throw __tempUtilsModuleErr;
}

export const AppUtils = window.AppUtils;

