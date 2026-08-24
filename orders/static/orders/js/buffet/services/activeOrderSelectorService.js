// orders/static/orders/js/buffet/services/activeOrderSelectorService.js
//
// Dine Flash Buffet ONLY — Phase 5 Order Selector (Selected Order).
// Fetches GET active_orders once on Home load. When multiple active orders
// exist, selecting a row stores Selected Order and reloads Home status +
// visible conversation for that order (Phase 9 via Home hook). Does not
// touch BuffetOrderLookup, Registry writes, push routing, or recovery.
// Presentation: compact horizontal token cards (Token + 12h time).

import {
    getSelectedOrder,
    setSelectedOrder,
} from "./selectedOrderService.js";
import { isMultiOrderMode } from "./multiOrderModeService.js";
import {
    hasUnseen,
    clearUnseen,
    pruneToActiveTokens,
} from "./orderUnseenUpdateService.js?v=20260824_1";

const SELECTOR_ROOT_ID = "buffet-active-order-selector";
const FETCHED_FLAG = "__buffetActiveOrderSelectorFetched";
const APPLY_HOME_HOOK = "__buffetApplySelectedOrderHomeView";

let dependenciesPromise = null;
/** @type {Array<object>|null} */
let cachedOrders = null;
let selectionInFlight = false;

async function loadDependencies() {
    const base = window.BASE || "/caller_on/";
    const [authModule, apiModule] = await Promise.all([
        import(`${base}static/utils/js/services/authFetchService.js`),
        import(`${base}static/utils/js/apiEndpoints.js`),
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

async function readCurrentToken() {
    if (typeof AppUtils === "undefined" || typeof AppUtils.getToken !== "function") {
        return null;
    }
    try {
        const token = await AppUtils.getToken();
        if (token === null || token === undefined) return null;
        const text = String(token).trim();
        return text || null;
    } catch (e) {
        return null;
    }
}

async function readActiveVendor() {
    if (typeof AppUtils === "undefined") return null;
    try {
        if (typeof AppUtils.getActiveVendor === "function") {
            const vendor = await AppUtils.getActiveVendor();
            if (vendor !== null && vendor !== undefined) {
                const text = String(vendor).trim();
                if (text) return text;
            }
        }
    } catch (e) {
        // fall through
    }
    if (typeof AppUtils.storageGet === "function") {
        const stored = AppUtils.storageGet("activeVendor");
        if (stored !== null && stored !== undefined) {
            const text = String(stored).trim();
            if (text) return text;
        }
    }
    return null;
}

function formatCreatedAt(iso) {
    if (!iso) return "";
    try {
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) return "";
        // Presentation only: 12-hour creation time with AM/PM (e.g. 09:05 AM).
        return date.toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            hour12: true,
        });
    } catch (e) {
        return "";
    }
}

function tokensMatch(a, b) {
    if (a === null || a === undefined || b === null || b === undefined) return false;
    return String(a).trim() === String(b).trim();
}

/**
 * Current badge follows Selected Order.
 *
 * Phase 6: In Multi-Order Mode, Selected Order wins (do not adopt Home/Latest
 * over a deliberate selection). Outside Multi-Order Mode, if storage drifted
 * from Home token (e.g. recovery wrote Latest), adopt Home so recovery wins.
 */
async function resolveCurrentTokenForBadges() {
    const homeToken = await readCurrentToken();
    const selected = getSelectedOrder();

    if (isMultiOrderMode()) {
        if (selected && selected.token_number) {
            return selected.token_number;
        }
        return homeToken;
    }

    if (selected && homeToken && !tokensMatch(selected.token_number, homeToken)) {
        const orderLookupId = readOrderLookupId() || selected.order_lookup_id;
        const vendorId = (await readActiveVendor()) || selected.vendor_id;
        setSelectedOrder({
            order_lookup_id: orderLookupId,
            vendor_id: vendorId,
            token_number: homeToken,
        });
        return homeToken;
    }

    if (selected && selected.token_number) {
        return selected.token_number;
    }

    return homeToken;
}

/**
 * Seed Selected Order from Home identity when none exists yet.
 */
async function ensureSelectedOrderSeeded() {
    if (getSelectedOrder()) return getSelectedOrder();

    const orderLookupId = readOrderLookupId();
    const tokenNumber = await readCurrentToken();
    const vendorId = await readActiveVendor();
    if (!orderLookupId || !tokenNumber || !vendorId) return null;

    return setSelectedOrder({
        order_lookup_id: orderLookupId,
        vendor_id: vendorId,
        token_number: tokenNumber,
    });
}

/**
 * GET active orders for the current order_lookup_id.
 * Returns an array on success, or null on any failure / invalid response.
 * Never throws.
 */
async function fetchActiveOrders(orderLookupId) {
    const { fetchWithAutoRefresh, API_ENDPOINTS } = await getDependencies();
    const url =
        `${API_ENDPOINTS.BUFFET_ACTIVE_ORDERS}` +
        `?order_lookup_id=${encodeURIComponent(orderLookupId)}`;

    let response;
    try {
        response = await fetchWithAutoRefresh(url, { method: "GET" });
    } catch (e) {
        console.warn("[buffet] active_orders fetch failed:", e);
        return null;
    }

    if (!response || !response.ok) {
        return null;
    }

    let data;
    try {
        data = await response.json();
    } catch (e) {
        return null;
    }

    if (!Array.isArray(data)) {
        return null;
    }

    return data;
}

async function applyHomeIdentity({ vendorId, tokenNumber }) {
    if (typeof AppUtils === "undefined") return;

    if (vendorId && typeof AppUtils.setCurrentVendors === "function") {
        await AppUtils.setCurrentVendors(String(vendorId));
    }
    if (tokenNumber && typeof AppUtils.setToken === "function") {
        await AppUtils.setToken(String(tokenNumber));
    }
}

async function reloadHomeForSelectedOrder(tokenNumber) {
    const hook = window[APPLY_HOME_HOOK];
    if (typeof hook !== "function") {
        console.warn("[buffet] Selected Order Home reload hook missing");
        return;
    }
    await hook(String(tokenNumber));
}

async function handleOrderSelect(order) {
    if (selectionInFlight || !order || typeof order !== "object") return;

    const tokenNumber =
        order.token_number !== null && order.token_number !== undefined
            ? String(order.token_number).trim()
            : "";
    const vendorId =
        order.vendor_id !== null && order.vendor_id !== undefined
            ? String(order.vendor_id).trim()
            : "";
    const orderLookupId =
        (order.order_lookup_id !== null && order.order_lookup_id !== undefined
            ? String(order.order_lookup_id).trim()
            : "") || readOrderLookupId() || "";

    if (!tokenNumber || !vendorId || !orderLookupId) return;

    const currentToken = await resolveCurrentTokenForBadges();
    if (tokensMatch(tokenNumber, currentToken)) {
        // Already viewing this order — clear unseen (idempotent) and refresh UI.
        clearUnseen(tokenNumber);
        const root = getRoot();
        if (root && cachedOrders) {
            renderSelector(root, cachedOrders, currentToken);
        }
        return;
    }

    selectionInFlight = true;
    try {
        const selected = setSelectedOrder({
            order_lookup_id: orderLookupId,
            vendor_id: vendorId,
            token_number: tokenNumber,
        });
        if (!selected) return;

        clearUnseen(tokenNumber);

        await applyHomeIdentity({ vendorId, tokenNumber });
        await reloadHomeForSelectedOrder(tokenNumber);

        const root = getRoot();
        if (root && cachedOrders) {
            renderSelector(root, cachedOrders, tokenNumber);
        }
    } catch (e) {
        console.warn("[buffet] Selected Order switch failed:", e);
    } finally {
        selectionInFlight = false;
    }
}

function buildItemElement(order, { currentToken }) {
    const tokenNumber = order.token_number;
    const isCurrent = tokensMatch(tokenNumber, currentToken);
    const createdLabel = formatCreatedAt(order.created_at);
    const showUnseen = !isCurrent && hasUnseen(tokenNumber);

    const item = document.createElement("button");
    item.type = "button";
    item.className = "buffet-aos-item";
    if (isCurrent) {
        item.classList.add("is-current");
        item.classList.add("is-highlighted");
    }
    if (showUnseen) {
        item.classList.add("has-unseen");
        item.setAttribute(
            "aria-label",
            tokenNumber !== null && tokenNumber !== undefined
                ? `Token ${tokenNumber}, new update`
                : "Token, new update"
        );
        item.title = "New update";
    }
    item.setAttribute("aria-pressed", isCurrent ? "true" : "false");

    // Identity for selection — no internal booking/order ids beyond selector payload.
    item.dataset.tokenNumber =
        tokenNumber !== null && tokenNumber !== undefined ? String(tokenNumber) : "";
    item.dataset.vendorId =
        order.vendor_id !== null && order.vendor_id !== undefined
            ? String(order.vendor_id)
            : "";
    item.dataset.orderLookupId =
        order.order_lookup_id !== null && order.order_lookup_id !== undefined
            ? String(order.order_lookup_id)
            : "";

    // Compact card: Token + creation time; optional unseen class (CSS dot).
    const body = document.createElement("span");
    body.className = "buffet-aos-body";

    const title = document.createElement("span");
    title.className = "buffet-aos-title";
    title.textContent =
        tokenNumber !== null && tokenNumber !== undefined
            ? `Token ${tokenNumber}`
            : "Token";
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
        handleOrderSelect(order);
    });

    return item;
}

function renderSelector(root, orders, currentToken) {
    root.innerHTML = "";

    const panel = document.createElement("div");
    panel.className = "buffet-aos-panel";

    const heading = document.createElement("div");
    heading.className = "buffet-aos-heading";
    heading.textContent = "Active Orders";
    panel.appendChild(heading);

    const list = document.createElement("div");
    list.className = "buffet-aos-list";
    list.setAttribute("role", "list");

    orders.forEach((order) => {
        if (!order || typeof order !== "object") return;
        const row = buildItemElement(order, { currentToken });
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

/**
 * One-shot Home init. Safe to call multiple times; fetches at most once per page load.
 * Failures hide the selector and never block Home.
 */
async function initActiveOrderSelector() {
    const root = getRoot();
    if (!root) return;

    if (window[FETCHED_FLAG]) return;
    window[FETCHED_FLAG] = true;

    hideSelector(root);

    const orderLookupId = readOrderLookupId();
    if (!orderLookupId) {
        return;
    }

    const orders = await fetchActiveOrders(orderLookupId);
    if (!orders || orders.length <= 1) {
        hideSelector(root);
        cachedOrders = orders && orders.length ? orders : null;
        if (orders && orders.length) {
            pruneToActiveTokens(orders);
        }
        return;
    }

    cachedOrders = orders;
    pruneToActiveTokens(orders);

    try {
        await ensureSelectedOrderSeeded();
        const currentToken = await resolveCurrentTokenForBadges();
        renderSelector(root, orders, currentToken);
    } catch (e) {
        console.warn("[buffet] active_orders render failed:", e);
        hideSelector(root);
    }
}

/**
 * Lightweight re-render from cached active orders (no API refetch).
 * Used after mark/clear unseen so the selector dot updates immediately.
 */
async function repaintActiveOrderSelector() {
    const root = getRoot();
    if (!root || !cachedOrders || cachedOrders.length <= 1) return;
    try {
        const currentToken = await resolveCurrentTokenForBadges();
        renderSelector(root, cachedOrders, currentToken);
    } catch (e) {
        console.warn("[buffet] active order selector repaint failed:", e);
    }
}

/**
 * Phase 7: re-fetch selector after Registry lifecycle changes.
 * Safe to call from push handlers; failures never block Home.
 */
async function refreshActiveOrderSelector() {
    window[FETCHED_FLAG] = false;
    cachedOrders = null;
    try {
        await initActiveOrderSelector();
    } catch (e) {
        console.warn("[buffet] active order selector refresh failed:", e);
    }
}

export {
    initActiveOrderSelector,
    refreshActiveOrderSelector,
    repaintActiveOrderSelector,
};
