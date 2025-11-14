// passengerInfoService.js
import { get as idbGet, set as idbSet } from "https://cdnjs.cloudflare.com/ajax/libs/idb-keyval/6.2.1/index.min.js";

const PASSENGER_INFO_KEY = "passenger_info";

// ───────────────────────────────────────────────
// 🔧 Cookie Utilities
// ───────────────────────────────────────────────
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

// ───────────────────────────────────────────────
// 🌐 Universal Get (with auto-rehydration)
// ───────────────────────────────────────────────
async function getAllPassengerInfo() {
  // 1️⃣ Try localStorage first
  let data = localStorage.getItem(PASSENGER_INFO_KEY);
  if (data) return JSON.parse(data);

  // 2️⃣ Try IndexedDB
  try {
    data = await idbGet(PASSENGER_INFO_KEY);
    if (data) {
      localStorage.setItem(PASSENGER_INFO_KEY, JSON.stringify(data));
      setCookie(PASSENGER_INFO_KEY, JSON.stringify(data));
      return data;
    }
  } catch (e) {
    console.warn("[PassengerStore] IndexedDB read failed:", e);
  }

  // 3️⃣ Try Cookie
  const cookieData = getCookie(PASSENGER_INFO_KEY);
  if (cookieData) {
    const parsed = JSON.parse(cookieData);
    localStorage.setItem(PASSENGER_INFO_KEY, JSON.stringify(parsed));
    try { await idbSet(PASSENGER_INFO_KEY, parsed); } catch {}
    return parsed;
  }

  return {};
}

// ───────────────────────────────────────────────
// 💾 Universal Set (auto-sync to all storages)
// ───────────────────────────────────────────────
async function setAllPassengerInfo(data) {
  if (!data || typeof data !== "object") return;
  localStorage.setItem(PASSENGER_INFO_KEY, JSON.stringify(data));
  try { await idbSet(PASSENGER_INFO_KEY, data); } catch (e) {
    console.warn("[PassengerStore] IndexedDB write failed:", e);
  }
  setCookie(PASSENGER_INFO_KEY, JSON.stringify(data));
}

// ───────────────────────────────────────────────
// ✈️ Save / Update Passenger
// ───────────────────────────────────────────────
export async function savePassengerInfo(sequenceCode, passengerName) {
  if (!sequenceCode || !passengerName) return;

  const data = await getAllPassengerInfo();
  data[sequenceCode] = passengerName;
  await setAllPassengerInfo(data);
}

// ───────────────────────────────────────────────
// 🔍 Retrieve Passenger
// ───────────────────────────────────────────────
export async function getPassengerName(sequenceCode) {
  const data = await getAllPassengerInfo();
  return data[sequenceCode] || null;
}

// ───────────────────────────────────────────────
// ❌ Remove Passenger
// ───────────────────────────────────────────────
export async function removePassengerInfo(sequenceCode) {
  const data = await getAllPassengerInfo();
  if (data[sequenceCode]) {
    delete data[sequenceCode];
    await setAllPassengerInfo(data);
  }
}

// ───────────────────────────────────────────────
// 🧹 Clear All Passenger Info
// ───────────────────────────────────────────────
export async function clearAllPassengerInfo() {
  localStorage.removeItem(PASSENGER_INFO_KEY);
  try { await idbSet(PASSENGER_INFO_KEY, {}); } catch {}
  setCookie(PASSENGER_INFO_KEY, "{}", -1);
}
