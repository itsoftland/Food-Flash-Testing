// orders/static/orders/js/services/notificationService.js
import { updateChatOnPush } from './chatService.js?v=20260820_1';

let notificationsEnabled = true;
let activeNotificationToken = null;
let snoozeTimers = {};
let orderStates = AppUtils.loadOrderStates();  // 💾 Load from storage
let notificationModal = null;
let clearTimers = {};  // Store timers to clear token after 1 hour

let statusMessageMapPromise = null;
async function getStatusMessageMap() {
    if (statusMessageMapPromise) return statusMessageMapPromise;
    const base = (typeof window !== "undefined" && typeof window.BASE === "string" && window.BASE) ? window.BASE : "/";
    const v =
        (typeof window !== "undefined" && typeof window.APP_VERSION === "string" && window.APP_VERSION.trim() !== "")
            ? `?v=${encodeURIComponent(window.APP_VERSION.trim())}`
            : "";
    statusMessageMapPromise = import(`${base}static/orders/js/config/statusMessages.js${v}`)
        .then((m) => m.STATUS_MESSAGE_MAP)
        .catch((err) => {
            console.warn("Failed to load status message templates", err);
            return {};
        });
    return statusMessageMapPromise;
}

function normalizeOrderTokenKey(token) {
    return String(token ?? "").trim();
}

/** Drop snoozed/unacknowledged state for other orders when starting a new token session. */
function purgeStaleOrderStatesExceptActive(activeToken) {
    const activeKey = normalizeOrderTokenKey(activeToken);
    if (!activeKey) return;

    let changed = false;
    for (const token of Object.keys(orderStates)) {
        if (normalizeOrderTokenKey(token) === activeKey) continue;
        if (snoozeTimers[token]) {
            clearTimeout(snoozeTimers[token]);
            delete snoozeTimers[token];
        }
        delete orderStates[token];
        changed = true;
    }
    if (changed) {
        AppUtils.saveOrderStates(orderStates);
    }
}

/**
 * Initializes the notification modal behavior including OK and Snooze handling.
 * @param {Bootstrap.Modal} modalInstance - Bootstrap modal instance
 * @param {{ activeToken?: string|null }} [options] - When set, only restore snoozes for this token and purge others.
 */
function initNotificationModal(modalInstance, options = {}) {
    const activeToken =
        options.activeToken != null && String(options.activeToken).trim() !== ""
            ? String(options.activeToken).trim()
            : null;

    if (activeToken) {
        purgeStaleOrderStatesExceptActive(activeToken);
    }

    notificationModal = modalInstance;

    // -----------------------------------------
    // 🔵 FIX: Remove button focus when modal closes
    // -----------------------------------------
    notificationModal._element.addEventListener('hidden.bs.modal', () => {
        const okBtn = document.getElementById('ok-notification');
        const snoozeBtn = document.getElementById('disable-notifications');

        if (okBtn) okBtn.blur();
        if (snoozeBtn) snoozeBtn.blur();
    });
    // -----------------------------------------

    // ✅ OK Button → acknowledge notification
    document.getElementById('ok-notification').addEventListener('click', async () => {
        if (activeNotificationToken && orderStates[activeNotificationToken]) {
            orderStates[activeNotificationToken].acknowledged = true;
            AppUtils.saveOrderStates(orderStates);
        }
        activeNotificationToken = null;
        notificationModal.hide();
        VibrationManager.stop();
    });

    // 🔕 Disable / Snooze Notifications Button
    document.getElementById('disable-notifications').addEventListener('click', () => {
        if (!activeNotificationToken) return;

        const token = activeNotificationToken;
        notificationModal.hide();

        if (orderStates[token] && !orderStates[token].acknowledged) {
            const userSnoozeDuration = 60000; // 🕒 Replace with dropdown / user input
            const now = Date.now();

            orderStates[token].snoozedAt = now;
            orderStates[token].snoozeDuration = userSnoozeDuration;
            AppUtils.saveOrderStates(orderStates);

            if (snoozeTimers[token]) clearTimeout(snoozeTimers[token]);

            snoozeTimers[token] = setTimeout(() => {
                if (!orderStates[token].acknowledged) {
                    showNotificationModal(orderStates[token].data);
                    AppUtils.notifyOrderReady(orderStates[token].data);
                }
            }, userSnoozeDuration);
        }

        activeNotificationToken = null;
    });

    // 🕓 Restore snoozed notifications on reload (only for the active order when known)
    for (const [token, state] of Object.entries(orderStates)) {
        if (
            activeToken &&
            normalizeOrderTokenKey(token) !== normalizeOrderTokenKey(activeToken)
        ) {
            continue;
        }
        if (!state.acknowledged && state.snoozedAt && state.snoozeDuration) {
            const now = Date.now();
            const elapsed = now - state.snoozedAt;
            const remaining = state.snoozeDuration - elapsed;

            if (remaining > 0) {
                snoozeTimers[token] = setTimeout(() => {
                    if (!orderStates[token].acknowledged) {
                        showNotificationModal(state.data);
                        AppUtils.notifyOrderReady(state.data);
                    }
                }, remaining);
            } else {
                // ⏰ Snooze expired while page reloaded
                showNotificationModal(state.data);
                AppUtils.notifyOrderReady(state.data);
            }
        }
    }
}


/**
 * Displays the notification modal with dynamic content based on order/flight status.
 * @param {Object} pushData - Data object containing notification payload.
 * @param {string} [source] - Source of the notification ('notification' or 'usercheck').
 */
async function showNotificationModal(pushData, source) {
    if (!notificationsEnabled || !pushData) return;

    const token = pushData.token_no;

    // Ensure token entry exists
    if (!orderStates[token]) {
        orderStates[token] = {
            acknowledged: false,
            data: pushData,
            receivedAt: new Date().toISOString()
        };
    }

    const isPush = source !== 'usercheck';

    // Skip if user manually checked already acknowledged token
    if (!isPush && orderStates[token].acknowledged) return;

    // Reset on push
    if (isPush) {
        orderStates[token].acknowledged = false;
        orderStates[token].data = pushData;
        orderStates[token].receivedAt = new Date().toISOString();
    }

    activeNotificationToken = token;
    AppUtils.saveOrderStates(orderStates);

    // 💬 Build modal message (prefer explicit push `type`, then status; merge buffet item fields)
    const modalHeader = document.querySelector('#notificationModal .modal-body h5');
    const modalPayload = { ...pushData };
    if (
      (modalPayload.item_name == null || modalPayload.item_name === "") &&
      Array.isArray(modalPayload.items)
    ) {
      const st = modalPayload.status;
      const match =
        modalPayload.items.find((it) => it && it.status === st) ||
        modalPayload.items.find((it) => it && it.status === "ready") ||
        modalPayload.items[0];
      if (match) {
        modalPayload.item_name = match.name || match.item_name || modalPayload.item_name;
      }
    }
    const noCounter =
      modalPayload.counter_no == null ||
      modalPayload.counter_no === "" ||
      String(modalPayload.counter_no) === "undefined";
    if (noCounter) {
      delete modalPayload.counter_no;
    }
    const STATUS_MESSAGE_MAP = await getStatusMessageMap();
    let messageFn =
      STATUS_MESSAGE_MAP[modalPayload.type] || STATUS_MESSAGE_MAP[modalPayload.status];
    let messageHtml = messageFn ? messageFn(modalPayload) : "You have a new update.";

    // Hospital Flash only: in-app modal text for patient department status updates.
    // Gated by type hospitalstatus + Hospital surface so other flavours cannot enter.
    const isHospitalFlashFlavour =
      (typeof window !== "undefined" &&
        typeof window.PROJECT_NAME === "string" &&
        window.PROJECT_NAME.trim().toLowerCase() === "hospital_flash") ||
      (typeof window !== "undefined" &&
        typeof window.BASE === "string" &&
        window.BASE.includes("/hospital_flash/")) ||
      (typeof window !== "undefined" &&
        typeof window.location?.pathname === "string" &&
        window.location.pathname.includes("/hospital_flash"));
    const hospitalTypeKey = String(modalPayload.type || "").toLowerCase();
    if (isHospitalFlashFlavour && hospitalTypeKey === "hospitalstatus") {
      const hospitalStatus = String(modalPayload.status || "").toLowerCase();
      const department =
        modalPayload.utility_name != null && String(modalPayload.utility_name).trim() !== ""
          ? String(modalPayload.utility_name).trim()
          : "your department";
      const bookingNo =
        modalPayload.booking_no != null && String(modalPayload.booking_no).trim() !== ""
          ? String(modalPayload.booking_no).trim()
          : (modalPayload.token_no != null && String(modalPayload.token_no).trim() !== ""
            ? String(modalPayload.token_no).trim()
            : "-");
      if (hospitalStatus === "called") {
        messageHtml = `Your token <strong>${bookingNo}</strong> has been called for <strong>${department}</strong>. Please proceed to the department.`;
      } else if (hospitalStatus === "completed") {
        messageHtml = `Your visit for <strong>${department}</strong> has been completed. Thank you.`;
      } else if (hospitalStatus === "cancelled") {
        messageHtml = `Your token <strong>${bookingNo}</strong> for <strong>${department}</strong> has been cancelled. Please contact the hospital staff for assistance.`;
      }
    } else if (isHospitalFlashFlavour && hospitalTypeKey === "hospital_pre_announcement") {
      // Hospital Flash only: shorter in-app modal. OS push, TTS, and chat are unchanged.
      const department =
        modalPayload.department_name != null && String(modalPayload.department_name).trim() !== ""
          ? String(modalPayload.department_name).trim()
          : (modalPayload.utility_name != null && String(modalPayload.utility_name).trim() !== ""
            ? String(modalPayload.utility_name).trim()
            : "your department");
      const bookingNo =
        modalPayload.booking_no != null && String(modalPayload.booking_no).trim() !== ""
          ? String(modalPayload.booking_no).trim()
          : (modalPayload.token_no != null && String(modalPayload.token_no).trim() !== ""
            ? String(modalPayload.token_no).trim()
            : "-");
      messageHtml = `Your turn for <strong>${department}</strong> is approaching. Token <strong>${bookingNo}</strong>.`;
    }

    // 🍽️ Buffet flavour: keep ready message aligned with other status templates.
    // Use BASE/path detection to avoid relying on PROJECT_NAME being set.
    const isBuffetFlavour =
      (typeof window !== "undefined" &&
        typeof window.BASE === "string" &&
        window.BASE.includes("/dine_flash_buffet/")) ||
      (typeof window !== "undefined" &&
        typeof window.location?.pathname === "string" &&
        window.location.pathname.includes("/dine_flash_buffet/"));
    if (isBuffetFlavour) {
      const statusKey = String(modalPayload.status || "").toLowerCase();
      const typeKey = String(modalPayload.type || "").toLowerCase();

      if (
        (typeKey === "buffet_utilities_status" || typeKey === "buffet_utilities_ready") &&
        (Array.isArray(modalPayload.utilities) || Array.isArray(modalPayload.ready_utilities))
      ) {
        const blocks =
          Array.isArray(modalPayload.utilities) && modalPayload.utilities.length
            ? modalPayload.utilities
            : (Array.isArray(modalPayload.ready_utilities) ? modalPayload.ready_utilities : []).map(
                (x) => ({
                  name: x.name,
                  lines: [{ status: "ready", quantity: 1 }],
                })
              );
        const lines = blocks.map((b) => {
          const name = (b && b.name) || "Station";
          const bits = (Array.isArray(b.lines) ? b.lines : []).map((ln) => {
            const st = ln.status || "?";
            const qty = ln.quantity != null ? Number(ln.quantity) : 1;
            const q = Number.isFinite(qty) && qty !== 1 ? ` ×${qty}` : "";
            return `${st}${q}`;
          });
          return `${name}: ${bits.join(", ") || "—"}`;
        });
        messageHtml = `
          Order <strong>${modalPayload.token_no}</strong> station update:<br>
          ${lines.join("<br>")}`;
      } else if (typeKey === "buffet_pre_announcement") {
        const itemLabel =
          (typeof modalPayload.item_name === "string" && modalPayload.item_name.trim() !== ""
            ? modalPayload.item_name.trim()
            : null) ||
          (typeof modalPayload.utility_name === "string" && modalPayload.utility_name.trim() !== ""
            ? modalPayload.utility_name.trim()
            : null) ||
          "your item";
        const token =
          modalPayload.token_no != null && String(modalPayload.token_no) !== ""
            ? modalPayload.token_no
            : "-";
        const eta =
          modalPayload.eta_minutes != null && Number(modalPayload.eta_minutes) > 0
            ? Number(modalPayload.eta_minutes)
            : null;
        messageHtml =
          eta != null
            ? `Your Order <strong>${token}</strong> for <strong>${itemLabel}</strong> is approaching its turn (approximately <strong>${eta}</strong> minute(s) away).`
            : `Your Order <strong>${token}</strong> for <strong>${itemLabel}</strong> is approaching its turn.`;
      } else {
        const isReadyLike =
          statusKey.includes("ready") ||
          typeKey.includes("ready");

        if (isReadyLike && modalPayload.token_no != null && String(modalPayload.token_no) !== "") {
          // Prefer item name first so buffet ready copy matches other status wording.
          const itemLabel =
            (typeof modalPayload.item_name === "string" && modalPayload.item_name.trim() !== ""
              ? modalPayload.item_name.trim()
              : null) ||
            (typeof modalPayload.name === "string" && modalPayload.name.trim() !== ""
              ? modalPayload.name.trim()
              : null) ||
            (typeof modalPayload.utility_name === "string" && modalPayload.utility_name.trim() !== ""
              ? modalPayload.utility_name.trim()
              : null) ||
            "your item";

          messageHtml = `
          Your Order <strong>${modalPayload.token_no}</strong> for <strong>${itemLabel}</strong> is now <strong>ready</strong>.<br>
          Please collect it.`;
        }
      }
    }

    // 🛎️ Override for push notification source
    if (source === 'notification') {
        const outletName = pushData.alias_name || pushData.name || "the outlet";
        messageHtml = `🛎️ <strong>You’ve got a new message from ${outletName}</strong><br>View the chat for details.`;
    }

    modalHeader.innerHTML = messageHtml;

    // Show modal
    const snoozeBtn = document.getElementById('disable-notifications');
    snoozeBtn.disabled = false;
    notificationModal.show();

    // 🔔 Sound + Chat Update
    AppUtils.playNotificationSound(pushData.vibration_pattern,pushData.vibration_duration);
    const { vendor_id, logo_url, name } = pushData;
    // Phase 8 (Dine Flash Buffet): skip Home vendor switch when push is for a
    // different active order under Multi-Order Mode. Other flavours unchanged.
    let applyPushHomeContext = true;
    if (isBuffetFlavour) {
        try {
            const base =
                typeof window !== "undefined" && typeof window.BASE === "string" && window.BASE
                    ? window.BASE
                    : "/";
            const v =
                typeof window !== "undefined" &&
                typeof window.APP_VERSION === "string" &&
                window.APP_VERSION.trim() !== ""
                    ? `?v=${encodeURIComponent(window.APP_VERSION.trim())}`
                    : "";
            const pushCompat = await import(
                `${base}static/orders/js/buffet/services/multiOrderPushCompatibilityService.js${v}`
            );
            if (typeof pushCompat.shouldApplyPushHomeContext === "function") {
                applyPushHomeContext = Boolean(pushCompat.shouldApplyPushHomeContext(pushData));
            }
        } catch (e) {
            console.warn("[buffet] notification home-context gate failed:", e);
        }
    }
    if (applyPushHomeContext) {
        updateChatOnPush(vendor_id, logo_url, name);
    }

    // 🧹 Auto-clear order state after 1 hour
    if (clearTimers[token]) clearTimeout(clearTimers[token]);
    clearTimers[token] = setTimeout(() => {
        delete orderStates[token];
        AppUtils.saveOrderStates(orderStates);
    }, 3600000); // 1 hour
}

export { initNotificationModal, showNotificationModal };
