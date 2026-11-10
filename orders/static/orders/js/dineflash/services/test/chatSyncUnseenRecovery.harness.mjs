/**
 * Node harness for Dine Flash booking-level blue-dot recovery guards.
 * Run: node chatSyncUnseenRecovery.harness.mjs
 */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const servicesDir = path.resolve(__dirname, "..");
const ordersJsDir = path.resolve(servicesDir, "../..");
const syncPath = path.resolve(ordersJsDir, "services/chatSyncService.js");

const storage = new Map();

function prefixedKey(key) {
    return `dine_flash:${key}`;
}

globalThis.window = {
    PROJECT_NAME: "dine_flash",
    BASE: "/caller_on/dine_flash/",
    location: { pathname: "/caller_on/dine_flash/" },
    navigator: { userAgent: "iPhone", standalone: true },
    isRestoringHistory: false,
    PROJECT_NAME: "dine_flash",
};
globalThis.document = {
    visibilityState: "visible",
    addEventListener() {},
};
globalThis.fetch = () => Promise.resolve({ catch: () => {} });

globalThis.AppUtils = {
    getPrefixedKey: prefixedKey,
    storageGet(key) {
        const pk = prefixedKey(key);
        return storage.has(pk) ? storage.get(pk) : null;
    },
    storageSet(key, value) {
        storage.set(prefixedKey(key), value);
    },
    getBrowserId: () => "browser-test",
    getActiveVendor: async () => 42,
    getStartUrl: () => "/caller_on/",
    getCSRFToken: () => "",
};

function importService(name) {
    return import(pathToFileURL(path.join(servicesDir, name)).href);
}

function reset() {
    storage.clear();
    globalThis.AppUtils.storageSet("multi_booking_mode", "1");
    globalThis.AppUtils.storageSet("activeDineBookingId", "booking-a");
    globalThis.AppUtils.storageSet(
        "selected_dine_booking",
        JSON.stringify({
            order_lookup_id: "lookup-1",
            vendor_id: "42",
            booking_id: "booking-a",
            booking_no: "B-A",
        })
    );
    globalThis.window.isRestoringHistory = false;
}

async function run() {
    const convMod = await importService("selectedBookingConversationService.js");
    const unseenMod = await importService("bookingUnseenUpdateService.js");
    const { ChatSyncService } = await import(pathToFileURL(syncPath).href);

    reset();

    const selectedMsg = {
        type: "dinestatus",
        sender: "server",
        booking_id: "booking-a",
        text: { type: "dinestatus", status: "occupied", booking_id: "booking-a" },
        rendered: "<div>occupied</div>",
    };
    const unselectedMsg = {
        type: "dinestatus",
        sender: "server",
        booking_id: "booking-b",
        text: { type: "dinestatus", status: "occupied", booking_id: "booking-b" },
        rendered: "<div>occupied b</div>",
    };

    assert.equal(convMod.shouldPaintHistoryMessage(selectedMsg), true);
    assert.equal(convMod.shouldPaintHistoryMessage(unselectedMsg), false);

    unseenMod.markUnseen("booking-b");
    assert.equal(unseenMod.hasUnseen("booking-b"), true);
    unseenMod.markUnseen("booking-b");
    assert.equal(unseenMod.hasUnseen("booking-b"), true);
    unseenMod.clearUnseen("booking-b");
    assert.equal(unseenMod.hasUnseen("booking-b"), false);

    ChatSyncService.resetForVendor(42);
    ChatSyncService.seedFromMessages([selectedMsg], 42);
    assert.equal(ChatSyncService.isAlreadyHandled(unselectedMsg, 42), false);
    assert.equal(ChatSyncService.isAlreadyHandled(selectedMsg, 42), true);

    const paintedOnly = [selectedMsg];
    const fullHistory = [selectedMsg, unselectedMsg];
    function messageMatchesSelectedBooking(msg, filter) {
        if (!filter) return true;
        const id = String(msg.booking_id || "").trim();
        if (!id) return true;
        return id === filter;
    }
    const seeded = fullHistory.filter((m) => messageMatchesSelectedBooking(m, "booking-a"));
    assert.deepEqual(seeded, paintedOnly);

    const syncSrc = await import("node:fs/promises").then((fs) =>
        fs.readFile(syncPath, "utf8")
    );
    assert.match(syncSrc, /booking_guard: bookingGuard/);
    assert.match(syncSrc, /!bookingGuard\) continue/);
    assert.match(
        syncSrc,
        /independent of the selected-booking append guard/
    );

    console.log("chatSyncUnseenRecovery.harness: all assertions passed");
}

run().catch((err) => {
    console.error(err);
    process.exit(1);
});
