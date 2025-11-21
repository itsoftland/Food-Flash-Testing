// vendorStore.js
import { get as idbGet, set as idbSet } from "https://cdnjs.cloudflare.com/ajax/libs/idb-keyval/6.2.1/index.min.js";

const VENDOR_KEY = "vendor_id";

// ---------------------------
// Cookie Helpers
// ---------------------------
function setCookie(name, value, days = 365) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; expires=${expires}; SameSite=Lax`;
}

function getCookie(name) {
  const cookieStr = `; ${document.cookie}`;
  const parts = cookieStr.split(`; ${name}=`);
  if (parts.length >= 2) return decodeURIComponent(parts.pop().split(";")[0]);
  return null;
}

// ---------------------------
// Universal GET
// ---------------------------
export async function getVendorId() {
  // 1. LocalStorage
  let id = localStorage.getItem(VENDOR_KEY);
  if (id) return parseInt(id);

  // 2. IndexedDB
  try {
    id = await idbGet(VENDOR_KEY);
    if (id) {
      localStorage.setItem(VENDOR_KEY, id);
      setCookie(VENDOR_KEY, id);
      return parseInt(id);
    }
  } catch (e) {
    console.warn("[VendorStore] IndexedDB read failed:", e);
  }

  // 3. Cookie fallback
  const cookieValue = getCookie(VENDOR_KEY);
  if (cookieValue) {
    const vendorId = parseInt(cookieValue);
    localStorage.setItem(VENDOR_KEY, vendorId);
    try { await idbSet(VENDOR_KEY, vendorId); } catch {}
    return vendorId;
  }

  return null;
}

// ---------------------------
// Universal SET
// ---------------------------
export async function setVendorId(id) {
  if (!id) return;

  localStorage.setItem(VENDOR_KEY, id);

  try {
    await idbSet(VENDOR_KEY, id);
  } catch (err) {
    console.warn("[VendorStore] IndexedDB write failed:", err);
  }

  setCookie(VENDOR_KEY, id);
}

// ---------------------------
// CLEAR
// ---------------------------
export async function clearVendorId() {
  localStorage.removeItem(VENDOR_KEY);
  try { await idbSet(VENDOR_KEY, null); } catch {}
  setCookie(VENDOR_KEY, "", -1);
}
