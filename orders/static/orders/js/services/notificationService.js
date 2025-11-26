// orders/static/orders/js/services/notificationService.js
import { updateChatOnPush } from './chatService.js';
import { STATUS_MESSAGE_MAP } from '../config/statusMessages.js';

let notificationsEnabled = true;
let activeNotificationToken = null;
let snoozeTimers = {};
let orderStates = AppUtils.loadOrderStates();  // 💾 Load from storage
let notificationModal = null;
let clearTimers = {};  // Store timers to clear token after 1 hour

/**
 * Initializes the notification modal behavior including OK and Snooze handling.
 * @param {Bootstrap.Modal} modalInstance - Bootstrap modal instance
 */
function initNotificationModal(modalInstance) {
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

    // 🕓 Restore snoozed notifications on reload
    for (const [token, state] of Object.entries(orderStates)) {
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
function showNotificationModal(pushData, source) {
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

    // 💬 Build modal message
    const modalHeader = document.querySelector('#notificationModal .modal-body h5');
    let messageFn = STATUS_MESSAGE_MAP[pushData.status];
    let messageHtml = messageFn ? messageFn(pushData) : "You have a new update.";

    // 🛎️ Override for push notification source
    if (source === 'notification') {
        const outletName = pushData.name || "the outlet";
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
    updateChatOnPush(vendor_id, logo_url, name);

    // 🧹 Auto-clear order state after 1 hour
    if (clearTimers[token]) clearTimeout(clearTimers[token]);
    clearTimers[token] = setTimeout(() => {
        delete orderStates[token];
        AppUtils.saveOrderStates(orderStates);
    }, 3600000); // 1 hour
}

export { initNotificationModal, showNotificationModal };
