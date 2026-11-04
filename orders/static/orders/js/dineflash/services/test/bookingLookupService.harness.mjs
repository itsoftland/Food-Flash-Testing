/**
 * Node harness for Dine Flash booking lookup stale handling (no browser).
 * Run: node bookingLookupService.harness.mjs
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
    navigator: { standalone: true },
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
    setCookie() {},
    handoffDiag() {},
};

function importService(name) {
    return import(pathToFileURL(path.join(servicesDir, name)).href);
}

function seedStaleIdentity() {
    storage.clear();
    globalThis.AppUtils.storageSet("order_lookup_id", "lookup-persist");
    globalThis.AppUtils.storageSet("activeVendor", "920001");
    globalThis.AppUtils.storageSet("token", "OLD-BOOKING");
    globalThis.AppUtils.storageSet("activeDineBookingId", "999");
    globalThis.AppUtils.storageSet(
        "selected_dine_booking",
        JSON.stringify({
            order_lookup_id: "lookup-persist",
            vendor_id: "920001",
            booking_id: "999",
            booking_no: "OLD-BOOKING",
        })
    );
    globalThis.AppUtils.storageSet("browser_id", "browser-should-remain");
}

async function run() {
    const lookupMod = await importService("bookingLookupService.js");

    seedStaleIdentity();
    const staleResult = await lookupMod.__testMapResolvePayloadForHarness({
        status: "not_found_or_stale",
    });
    assert.equal(staleResult.outcome, "stale");
    assert.equal(globalThis.AppUtils.storageGet("order_lookup_id"), "lookup-persist");
    assert.equal(globalThis.AppUtils.storageGet("browser_id"), "browser-should-remain");
    assert.equal(globalThis.AppUtils.storageGet("activeVendor"), "920001");
    assert.equal(globalThis.AppUtils.storageGet("token"), null);
    assert.equal(globalThis.AppUtils.storageGet("activeDineBookingId"), null);
    assert.equal(globalThis.AppUtils.storageGet("selected_dine_booking"), null);

    seedStaleIdentity();
    const foundResult = await lookupMod.__testMapResolvePayloadForHarness({
        status: "found",
        booking_id: 42,
        booking_no: "L-42",
        vendor_id: 920001,
        location_id: "LOC-1",
    });
    assert.equal(foundResult.outcome, "found");
    assert.equal(foundResult.booking.booking_id, 42);
    assert.equal(globalThis.AppUtils.storageGet("token"), "OLD-BOOKING");
    assert.equal(globalThis.AppUtils.storageGet("order_lookup_id"), "lookup-persist");

    console.log("bookingLookupService.harness: all assertions passed");
}

run().catch((err) => {
    console.error(err);
    process.exit(1);
});
