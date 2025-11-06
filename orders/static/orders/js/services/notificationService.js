// orders/static/orders/js/services/notificationService.js
import { updateChatOnPush } from './chatService.js';

let notificationsEnabled = true;
let activeNotificationToken = null;
let snoozeTimers = {};
let orderStates = AppUtils.loadOrderStates();  // 💾 Load from storage
let notificationModal = null;
let clearTimers = {};  // Store timers to clear token after 1 hour

function initNotificationModal(modalInstance) {
    notificationModal = modalInstance;

    document.getElementById('ok-notification').addEventListener('click',async () => {
        if (activeNotificationToken && orderStates[activeNotificationToken]) {
            orderStates[activeNotificationToken].acknowledged = true;
            AppUtils.saveOrderStates(orderStates);  // 💾 Save updated state
        }
        activeNotificationToken = null;
        notificationModal.hide();
    });

    document.getElementById('disable-notifications').addEventListener('click', () => {
        if (activeNotificationToken) {
            const token = activeNotificationToken;
            notificationModal.hide();
    
            if (orderStates[token] && !orderStates[token].acknowledged) {
                const userSnoozeDuration = 60000; // 🕒 Replace with actual user input (e.g., dropdown value)
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
        }
    });

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
               
                // Snooze already expired while page was reloading
                showNotificationModal(state.data);
                AppUtils.notifyOrderReady(state.data);
            }
        }
    }     
}

function showNotificationModal(pushData, source) {
    if (!notificationsEnabled || !pushData) return;

    const token = pushData.token_no;

    // If order state for token does not exist, initialize it
    if (!orderStates[token]) {
        orderStates[token] = {
            acknowledged: false,
            data: pushData,
            receivedAt: new Date().toISOString()
        };
    }

    const isPush = source !== 'usercheck';

    // If it's user-initiated and already acknowledged, skip
    if (!isPush && orderStates[token].acknowledged) {
        return;
    }

    // If it's a push, reset acknowledged to false so modal shows again
    if (isPush) {
        orderStates[token].acknowledged = false;
        orderStates[token].data = pushData;
        orderStates[token].receivedAt = new Date().toISOString();
    }

    // Show modal
    activeNotificationToken = token;
    AppUtils.saveOrderStates(orderStates);

    const modalHeader = document.querySelector('#notificationModal .modal-body h5');
    if (source === 'notification') {
        const outletName = pushData.name || "the outlet";
        const messages = [
            `🛎️ <strong>You’ve got a new update from ${outletName}</strong><br>View the chat for details.`
        ];
        const randomIndex = Math.floor(Math.random() * messages.length);
        modalHeader.innerHTML = messages[randomIndex];
    } else {
        if (pushData.status === 'cancelled') {
            modalHeader.innerHTML = `
                Unfortunately, your order <strong>${pushData.token_no}</strong> for <strong>${pushData.name}</strong> 
                has been cancelled. Please contact staff for assistance.`;
        } else if (pushData.status === 'ready') {
            modalHeader.innerHTML = `
                Your Order <strong>${pushData.token_no}</strong> for <strong>${pushData.name}</strong>
                is now <strong>${pushData.status}</strong> at <strong>Counter ${pushData.counter_no}</strong>.`;
        } else if (pushData.status === 'preparing') {
            modalHeader.innerHTML = `
                Your Order <strong>${pushData.token_no}</strong> for <strong>${pushData.name}</strong>
                is now <strong>${pushData.status}</strong>. Please wait while we finish it.`;
        } else if (pushData.status === 'delivered'){
            modalHeader.innerHTML = `
                Your Order <strong>${pushData.token_no}</strong> for <strong>${pushData.name}</strong>
                has been delivered. Thank you for choosing us!`;
        } else if (pushData.status === 'boarding'){
            modalHeader.innerHTML = `
                Boarding for <strong>Flight ${pushData.flight_no}</strong> has now started. 
                Please proceed to the boarding area with your belongings.`;
        } else if (pushData.status === 'final_call'){
            modalHeader.innerHTML = `
                This is the <strong>Final Call</strong> for <strong>Flight ${pushData.flight_no}</strong>. 
                Please proceed to the aircraft`;
        } else{
            modalHeader.innerHTML = `
                You have a new update. `;
        }
    }
    const snoozeBtn = document.getElementById('disable-notifications');
    snoozeBtn.disabled = false;
    notificationModal.show();

    AppUtils.playNotificationSound();

    const { vendor_id, logo_url, name } = pushData;
    updateChatOnPush(vendor_id, logo_url, name);

    // Set or reset the 1-hour auto-clear timer
    if (clearTimers[token]) clearTimeout(clearTimers[token]);
    clearTimers[token] = setTimeout(() => {
        delete orderStates[token];
        AppUtils.saveOrderStates(orderStates);
    }, 3600000); // 1 hour
}

// Export methods
export { initNotificationModal, showNotificationModal };


