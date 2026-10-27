/**
 * Node harness for Dine Flash selected-booking restore (no browser).
 * Run: node selectedBookingRestore.harness.mjs
 */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const servicesDir = path.resolve(__dirname, "..");

const storage = new Map();

globalThis.window = {
    PROJECT_NAME: "dine_flash",
    BASE: "/caller_on/",
    __dineFlashSelectedRestoreDone: false,
};
globalThis.sessionStorage = {
    _data: {},
    getItem(k) {
        return this._data[k] ?? null;
    },
    setItem(k, v) {
        this._data[k] = String(v);
    },
    removeItem(k) {
        delete this._data[k];
    },
};
function prefixedKey(key) {
    const project = String(globalThis.window.PROJECT_NAME || "default")
        .toLowerCase()
        .trim();
    return `${project}:${key}`;
}

globalThis.AppUtils = {
    getPrefixedKey: prefixedKey,
    storageGet(key) {
        const pk = prefixedKey(key);
        return storage.has(pk) ? storage.get(pk) : null;
    },
    storageSet(key, value) {
        storage.set(prefixedKey(key), value);
    },
    storageRemove(key) {
        storage.delete(prefixedKey(key));
    },
    setCurrentVendors: async (v) => {
        globalThis.AppUtils.storageSet("activeVendor", String(v));
    },
    setToken: async (t) => {
        globalThis.AppUtils.storageSet("token", String(t));
    },
    getOrderLookupId() {
        return storage.get("order_lookup_id") || null;
    },
};

function importService(name) {
    return import(pathToFileURL(path.join(servicesDir, name)).href);
}

function resetStorage() {
    storage.clear();
    sessionStorage._data = {};
    globalThis.AppUtils.storageSet("multi_booking_mode", "1");
    globalThis.AppUtils.storageSet("order_lookup_id", "lookup-key");
    globalThis.AppUtils.storageSet(
        "selected_dine_booking",
        JSON.stringify({
            order_lookup_id: "lookup-key",
            vendor_id: "100",
            booking_id: "200",
            booking_no: "B-200",
        })
    );
}

async function run() {
    const restoreMod = await importService("selectedBookingRestoreService.js");
    const selectedMod = await importService("selectedBookingService.js");
    const multiMod = await importService("multiBookingModeService.js");

    resetStorage();
    restoreMod.__setTestFetchActiveBookingsImpl(async () => null);
    let result = await restoreMod.tryRestoreSelectedBooking();
    assert.equal(result.outcome, "restored");
    assert.equal(result.validated, false);
    assert.ok(selectedMod.getSelectedBooking());
    assert.equal(
        globalThis.AppUtils.storageGet("activeDineBookingId"),
        "200"
    );
    assert.equal(globalThis.AppUtils.storageGet("token"), "B-200");

    resetStorage();
    restoreMod.__setTestFetchActiveBookingsImpl(async () => []);
    result = await restoreMod.tryRestoreSelectedBooking();
    assert.equal(result.outcome, "fallback");
    assert.equal(result.reason, "selected_not_active");
    assert.equal(selectedMod.getSelectedBooking(), null);

    resetStorage();
    restoreMod.__setTestFetchActiveBookingsImpl(async () => [
        {
            booking_id: "200",
            booking_no: "B-200",
            vendor_id: "100",
            order_lookup_id: "lookup-key",
        },
    ]);
    result = await restoreMod.tryRestoreSelectedBooking();
    assert.equal(result.outcome, "restored");
    assert.equal(result.validated, true);

    globalThis.AppUtils.storageSet("multi_booking_mode", "0");
    result = await restoreMod.tryRestoreSelectedBooking();
    assert.equal(result.outcome, "disabled");

    globalThis.window.PROJECT_NAME = "food_flash";
    assert.equal(multiMod.shouldSubmitAsAdditionalBooking(), false);
    globalThis.window.PROJECT_NAME = "dine_flash";
    sessionStorage.setItem("dine_flash_additional_booking_intent", "1");
    assert.equal(multiMod.shouldSubmitAsAdditionalBooking(), true);

    restoreMod.resetRestoreSettledCycle();
    let settled = false;
    restoreMod.whenRestoreSettled().then(() => {
        settled = true;
    });
    await Promise.resolve();
    assert.equal(settled, false);
    restoreMod.markRestoreSettled();
    await restoreMod.whenRestoreSettled();
    assert.equal(settled, true);

    console.log("selectedBookingRestore.harness: all assertions passed");
}

run().catch((err) => {
    console.error(err);
    process.exit(1);
});
