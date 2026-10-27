// Dine Flash ONLY — Active Booking Selector.

import { getSelectedBooking, setSelectedBooking } from "./selectedBookingService.js?v=20261027_1";
import { isMultiBookingMode } from "./multiBookingModeService.js?v=20261027_1";
import {
    hasUnseen,
    clearUnseen,
    pruneToActiveBookingIds,
} from "./bookingUnseenUpdateService.js?v=20261027_1";

const SELECTOR_ROOT_ID = "dine-flash-active-booking-selector";
const FETCHED_FLAG = "__dineFlashActiveBookingSelectorFetched";
const APPLY_HOME_HOOK = "__dineFlashApplySelectedBookingHomeView";

let dependenciesPromise = null;
let cachedBookings = null;
let selectionInFlight = false;

async function loadDependencies() {
    const base = window.BASE || "/caller_on/";
    const apiVersion =
        typeof window.APP_VERSION === "string" && window.APP_VERSION.trim() !== ""
            ? `?v=${encodeURIComponent(window.APP_VERSION.trim())}`
            : "";
    const [authModule, apiModule] = await Promise.all([
        import(`${base}static/utils/js/services/authFetchService.js`),
        import(`${base}static/utils/js/apiEndpoints.js${apiVersion}`),
    ]);
    return {
        fetchWithAutoRefresh: authModule.fetchWithAutoRefresh,
        API_ENDPOINTS: apiModule.API_ENDPOINTS,
    };
}

function getDependencies() {
    if (!dependenciesPromise) {
        dependenciesPromise = loadDependencies();
    }
    return dependenciesPromise;
}

function getRoot() {
    return document.getElementById(SELECTOR_ROOT_ID);
}

function hideSelector(root) {
    if (!root) return;
    root.hidden = true;
    root.innerHTML = "";
    root.setAttribute("aria-hidden", "true");
}

function readOrderLookupId() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.getOrderLookupId !== "function") {
        return null;
    }
    const value = AppUtils.getOrderLookupId();
    if (value === null || value === undefined) return null;
    const text = String(value).trim();
    return text || null;
}

async function readCurrentBookingId() {
    const selected = getSelectedBooking();
    if (selected && selected.booking_id) return String(selected.booking_id).trim();
    if (typeof AppUtils !== "undefined" && typeof AppUtils.storageGet === "function") {
        const stored = AppUtils.storageGet("activeDineBookingId");
        if (stored) return String(stored).trim();
    }
    return null;
}

async function fetchActiveBookings(orderLookupId) {
    const { fetchWithAutoRefresh, API_ENDPOINTS } = await getDependencies();
    const url =
        `${API_ENDPOINTS.DINE_FLASH_ACTIVE_BOOKINGS}` +
        `?order_lookup_id=${encodeURIComponent(orderLookupId)}`;

    let response;
    try {
        response = await fetchWithAutoRefresh(url, { method: "GET" });
    } catch (e) {
        console.warn("[dine_flash] active_bookings fetch failed:", e);
        return null;
    }

    if (!response || !response.ok) return null;

    let data;
    try {
        data = await response.json();
    } catch (e) {
        return null;
    }

    return Array.isArray(data) ? data : null;
}

function idsMatch(a, b) {
    if (a === null || a === undefined || b === null || b === undefined) return false;
    return String(a).trim() === String(b).trim();
}

function formatCreatedAt(iso) {
    if (!iso) return "";
    try {
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            hour12: true,
        });
    } catch (e) {
        return "";
    }
}

async function resolveCurrentBookingIdForBadges() {
    const homeId = await readCurrentBookingId();
    const selected = getSelectedBooking();

    if (isMultiBookingMode()) {
        if (selected && selected.booking_id) return selected.booking_id;
        return homeId;
    }

    if (selected && homeId && !idsMatch(selected.booking_id, homeId)) {
        const orderLookupId = readOrderLookupId() || selected.order_lookup_id;
        const vendorId =
            (typeof AppUtils !== "undefined" && typeof AppUtils.getActiveVendor === "function"
                ? await AppUtils.getActiveVendor()
                : null) || selected.vendor_id;
        setSelectedBooking({
            order_lookup_id: orderLookupId,
            vendor_id: vendorId,
            booking_id: homeId,
            booking_no: selected.booking_no,
        });
    }
    return homeId;
}

async function applyHomeIdentity({ vendorId, bookingId, bookingNo }) {
    if (typeof AppUtils === "undefined") return;
    if (vendorId && typeof AppUtils.setCurrentVendors === "function") {
        await AppUtils.setCurrentVendors(String(vendorId));
    }
    if (bookingNo && typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(String(bookingNo));
    }
    if (bookingId && typeof AppUtils.storageSet === "function") {
        AppUtils.storageSet("activeDineBookingId", String(bookingId));
    }
}

async function reloadHomeForSelectedBooking(bookingId, bookingNo) {
    const hook = window[APPLY_HOME_HOOK];
    if (typeof hook !== "function") {
        console.warn("[dine_flash] Selected Booking Home reload hook missing");
        return;
    }
    await hook(String(bookingId), bookingNo ? String(bookingNo) : null);
}

async function handleBookingSelect(booking) {
    if (selectionInFlight || !booking || typeof booking !== "object") return;

    const bookingId =
        booking.booking_id != null ? String(booking.booking_id).trim() : "";
    const bookingNo =
        booking.booking_no != null ? String(booking.booking_no).trim() : "";
    const vendorId =
        booking.vendor_id != null ? String(booking.vendor_id).trim() : "";
    const orderLookupId =
        (booking.order_lookup_id != null ? String(booking.order_lookup_id).trim() : "") ||
        readOrderLookupId() ||
        "";

    if (!bookingId || !bookingNo || !vendorId || !orderLookupId) return;

    const currentId = await resolveCurrentBookingIdForBadges();
    if (idsMatch(bookingId, currentId)) {
        clearUnseen(bookingId);
        const root = getRoot();
        if (root && cachedBookings) {
            renderSelector(root, cachedBookings, currentId);
        }
        return;
    }

    selectionInFlight = true;
    try {
        const selected = setSelectedBooking({
            order_lookup_id: orderLookupId,
            vendor_id: vendorId,
            booking_id: bookingId,
            booking_no: bookingNo,
        });
        if (!selected) return;

        clearUnseen(bookingId);
        await applyHomeIdentity({ vendorId, bookingId, bookingNo });
        await reloadHomeForSelectedBooking(bookingId, bookingNo);

        const root = getRoot();
        if (root && cachedBookings) {
            renderSelector(root, cachedBookings, bookingId);
        }
    } catch (e) {
        console.warn("[dine_flash] Selected Booking switch failed:", e);
    } finally {
        selectionInFlight = false;
    }
}

function buildItemElement(booking, { currentBookingId }) {
    const bookingId = booking.booking_id;
    const bookingNoRaw = booking.booking_no;
    const bookingNo =
        bookingNoRaw !== null && bookingNoRaw !== undefined
            ? String(bookingNoRaw).trim()
            : "";
    const isCurrent = idsMatch(bookingId, currentBookingId);
    const createdLabel = formatCreatedAt(booking.created_at);
    const showUnseen = !isCurrent && hasUnseen(bookingId);

    const item = document.createElement("button");
    item.type = "button";
    item.className = "buffet-aos-item";
    if (isCurrent) {
        item.classList.add("is-current");
        item.classList.add("is-highlighted");
    }
    if (showUnseen) {
        item.classList.add("has-unseen");
    }
    item.setAttribute("aria-pressed", isCurrent ? "true" : "false");

    const accessibleLabel = bookingNo ? `Booking ${bookingNo}` : "Booking";
    item.setAttribute("aria-label", accessibleLabel);
    if (bookingNo) {
        item.title = accessibleLabel;
    }

    const body = document.createElement("span");
    body.className = "buffet-aos-body";

    const title = document.createElement("span");
    title.className = "buffet-aos-title";
    title.textContent = bookingNo || "Booking";
    body.appendChild(title);

    if (createdLabel) {
        const meta = document.createElement("span");
        meta.className = "buffet-aos-meta";
        meta.textContent = createdLabel;
        body.appendChild(meta);
    }

    item.appendChild(body);
    item.addEventListener("click", (event) => {
        event.preventDefault();
        handleBookingSelect(booking);
    });

    return item;
}

function renderSelector(root, bookings, currentBookingId) {
    root.innerHTML = "";

    const panel = document.createElement("div");
    panel.className = "buffet-aos-panel";

    const heading = document.createElement("div");
    heading.className = "buffet-aos-heading";
    heading.textContent = "Active Bookings";
    panel.appendChild(heading);

    const list = document.createElement("div");
    list.className = "buffet-aos-list";
    list.setAttribute("role", "list");

    bookings.forEach((booking) => {
        if (!booking || typeof booking !== "object") return;
        const row = buildItemElement(booking, { currentBookingId });
        row.setAttribute("role", "listitem");
        list.appendChild(row);
    });

    if (!list.children.length) {
        hideSelector(root);
        return;
    }

    panel.appendChild(list);
    root.appendChild(panel);
    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
}

async function initActiveBookingSelector() {
    const root = getRoot();
    if (!root) return;

    if (window[FETCHED_FLAG]) return;
    window[FETCHED_FLAG] = true;

    hideSelector(root);

    const orderLookupId = readOrderLookupId();
    if (!orderLookupId) return;

    const bookings = await fetchActiveBookings(orderLookupId);
    if (!bookings || bookings.length <= 1) {
        hideSelector(root);
        cachedBookings = bookings && bookings.length ? bookings : null;
        if (bookings && bookings.length) {
            pruneToActiveBookingIds(bookings);
        }
        return;
    }

    cachedBookings = bookings;
    pruneToActiveBookingIds(bookings);

    const currentBookingId = await resolveCurrentBookingIdForBadges();
    renderSelector(root, bookings, currentBookingId);
}

async function refreshActiveBookingSelector() {
    window[FETCHED_FLAG] = false;
    try {
        await initActiveBookingSelector();
    } catch (e) {
        console.warn("[dine_flash] active booking selector refresh failed:", e);
    }
}

async function repaintActiveBookingSelector() {
    const root = getRoot();
    if (!root || !cachedBookings || cachedBookings.length <= 1) return;
    const currentBookingId = await resolveCurrentBookingIdForBadges();
    renderSelector(root, cachedBookings, currentBookingId);
}

export {
    initActiveBookingSelector,
    refreshActiveBookingSelector,
    repaintActiveBookingSelector,
};
