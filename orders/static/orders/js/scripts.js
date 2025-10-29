import { IosPwaInstallService } from './services/iosPwaInstallService.js';
import { AddOutletService } from "./services/addOutletService.js"; 
import { MenuModalService } from './services/menuModalService.js';
import { FeedbackService } from "./services/feedBackService.js";
import { PermissionService } from "./services/permissionService.js";
import { initNotificationModal, showNotificationModal } from './services/notificationService.js';
import { VendorUIService } from "./services/vendorUIService.js";
import { updateChatOnPush,appendMessage,clearReplyMode,saveChat } from "./services/chatService.js";
import { PushSubscriptionService } from "./services/pushSubscriptionService.js";
import { PushHealthMonitorService } from "./services/pushHealthMonitorService.js";
import { ChatRestoreService } from "./services/chatRestoreService.js";
function onDOMReady(callback) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback);
    } else {
        callback();
    }
}
onDOMReady(async function () {
    console.log("✅ DOM ready — initialization...");

    let apiEndpoints;
    const base = window.BASE || '/caller_on/';

    // ✅ Import endpoints dynamically
    const endpointsModule = await import(`${base}static/utils/js/apiEndpoints.js`);
    apiEndpoints = endpointsModule.API_ENDPOINTS;

    // ✅ Your entire existing logic continues here ↓↓↓
    IosPwaInstallService.init();
    AppUtils.initPaddingAdjustmentListeners();
    const notificationModal = new bootstrap.Modal(document.getElementById('notificationModal'), {
        backdrop: 'static',
        keyboard: false      
    });    
    const chatInput = document.getElementById('chat-input');
    const sendButton = document.getElementById('send-button');
    const urlParams = new URLSearchParams(window.location.search);
    let locationId = urlParams.get("location_id");
    const vendorFromQR = urlParams.get('vendor_id');
    const tokenFromQR = urlParams.get('token_no');
    const toggleBtn = document.getElementById("toggleArrowBtn");
    const pageWrapper = document.querySelector(".page-wrapper");
    const isOpenedFromPush = urlParams.get('from_push');

    let isAdVisible = true;

    // 1️⃣ Check URL param first
    if (locationId) {
        AppUtils.set(locationId); // Store it
    } else {
        // 2️⃣ Fallback to localStorage
        locationId = AppUtils.get();

        if (!locationId )  {
            // 3️⃣ Ask for it / show error / redirect
            AppUtils.showToast("No location ID found");
            // Optionally redirect to a location selection page
            window.location.href = base;
            throw new Error("Missing location ID");
        }
    }

    if (vendorFromQR) {
        await AppUtils.setCurrentVendors(vendorFromQR);
        // Optional: Clean the URL
        const newUrl = window.location.origin + window.location.pathname;
        history.replaceState(null, "", newUrl);
    } else {
        AddOutletService.init();
    }
    if (tokenFromQR) {
        await AppUtils.setToken(tokenFromQR);
    }
    // Initialize the ad slider visibility 
    toggleBtn.addEventListener("click", function () {
        const sliderWrapper = document.getElementById('ad-slider-wrapper');

        if (isAdVisible) {
            sliderWrapper.classList.add("slide-up");
            pageWrapper.style.top = "119px"; 
            pageWrapper.style.borderTop = "1px solid #fdbf50";
            toggleBtn.classList.add("rotated");
        } else {
            sliderWrapper.classList.remove("slide-up");
            pageWrapper.style.top = "270px";
            pageWrapper.style.borderTop = "none";
            toggleBtn.classList.remove("rotated");
        }
        isAdVisible = !isAdVisible;
    });

    MenuModalService.init();
    FeedbackService.init();
    PermissionService.init();
    PermissionService.showModal();
    
    // Example usage: Get the last active vendor ID

    const vendorIdsString = localStorage.getItem("selectedVendors");
    if (vendorIdsString) {
        const vendorIdsArray = JSON.parse(vendorIdsString);
    
        const vendorIds = vendorIdsArray
            .map(id => parseInt(id))
            .filter(id => Number.isInteger(id) && !isNaN(id));
        VendorUIService.init(vendorIds);
    }

    const isAndroid = /Android/i.test(navigator.userAgent);
    // Adjust viewport for mobile devices
    function setDynamicVH() {
        let vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    }
    window.addEventListener('resize', setDynamicVH);
    setDynamicVH();
    
    // 1) Try the official Brave check
    let braveDetected = false;
    if (navigator.brave && typeof navigator.brave.isBrave === 'function') {
        braveDetected = await navigator.brave.isBrave();
    }

    // 2) If that fails, try user agent or UA-CH fallback
    if (!braveDetected) {
        if (navigator.userAgent.includes("Brave")) {
            braveDetected = true;
        } else if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
            const data = await navigator.userAgentData.getHighEntropyValues(["brands"]);
            if (data.brands.some(b => b.brand.includes("Brave"))) {
                braveDetected = true;
            }
        }
    }

    // 3) If Brave is detected, show instructions
    if (braveDetected) {
        AppUtils.showToast("It looks like you're using Brave. Please ensure:\n\n1. Brave Settings > Privacy and Security > Site and Shields Settings > Notifications > 'Sites can ask to send notifications' is ON.\n2. Enable 'Use Google Services for Push Messaging' if shown.\n\nOtherwise, push notifications may fail");
    }
    initNotificationModal(notificationModal);
    // 1. Register the Service Worker at the root scope
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register(`${base}service-worker.js`, { scope: base })
        .then((registration) => {
              if (registration.active) {
                registration.active.postMessage({
                type: "SET_BASE_URL",
                baseUrl: window.location.origin + base,
                });

                registration.active.postMessage({
                type: "UPDATE_LAST_PAGE",
                url: window.location.href,
                });
            }     
        })
        .catch((error) => {
            console.error("Service Worker Registration Failed:", error);
        });
    }

    // 2. If there's no controller, optionally reload once to let the SW take control
    if (!navigator.serviceWorker.controller) {
        console.warn("Service worker not controlling page. Deferring message until SW ready.");
    }

    if (navigator.serviceWorker) {
        // update the service worker with the current page URL if needed
        navigator.serviceWorker.ready.then((registration) => {
            if (registration.active) {
            registration.active.postMessage({
                type: "UPDATE_LAST_PAGE",
                url: window.location.href,
            });
            }
        });

        // Optionally, you can listen for navigation events (if using a SPA or similar)
        window.addEventListener("popstate", () => {
            navigator.serviceWorker.ready.then((registration) => {
            if (registration.active) {
                registration.active.postMessage({
                type: "UPDATE_LAST_PAGE",
                url: window.location.href,
                });
            }
            });
        });

        navigator.serviceWorker.addEventListener('message', async (event) => {
            if (event.data && event.data.type === "OPEN_CHAT") {
                // Call a function to display or refresh the chat view
                await showChatWindow(event.data.payload);   
            }
            if (event.data?.type === 'PUSH_RECEIVED') {
                PushHealthMonitorService.recordPushReceived();
            }
            if (event.data?.type === 'PUSH_STATUS_UPDATE') {
                const pushData = event.data.payload;
                // ✅ Send ACK back to Service Worker confirming receipt
                if (navigator.serviceWorker.controller) {
                    navigator.serviceWorker.controller.postMessage({
                        type: "PUSH_STATUS_ACK",
                        token_no: pushData.token_no,
                    });
                }
                let selectedVendors = JSON.parse(localStorage.getItem('selectedVendors')) || [];
                // Check if the vendor is already in the list
                if (!selectedVendors.includes(pushData.vendor_id)) {
                    await AppUtils.appendVendorIfNotExists(pushData.vendor_id);
                    const vendorIds = AppUtils.getStoredVendors();
                    VendorUIService.init(vendorIds);
                }
                updateChatOnPush(pushData.vendor_id,pushData.logo_url,pushData.name);
                // Customize the chat message as needed. Here we assume pushData contains token_number and status.
                
                const statusClassMap = {
                    preparing: 'preparing-color',
                    ready: 'ready-color',
                    delivered: 'delivered-color',
                    cancelled: 'cancelled-color'
                };

                const statusKey = pushData?.status || 'unknown';
                const statusClass = statusClassMap[statusKey] || 'unknown-color';

                const messageHTML = `
                    <div class="response-title">${pushData.alias_name || "Unknown"}</div>
                    <div class="status">
                        Status: 
                        <span class="${statusClass}">
                            ${pushData.status || "Unknown"}
                        </span>
                    </div>
                    <div class="info-badges">
                        <div class="badge">Counter No: ${pushData.counter_no || ""}</div>
                        <div class="badge">Token No: ${pushData.token_no || ""}</div>
                    </div>
                `;

                const offerMessageHTML = `
                        <div class="response-title">${pushData.alias_name}</div>
                        <div class="response-title">🔥 ${pushData.title}</div>
                        <div style="color: #333; font-size: 15px;">
                            ${pushData.body || "Delicious deals await. Come grab your favorite combo now!"}
                        </div>
                    
                `;
                const managerMessageHTML = `
                    <div class="response-title">📩 ${pushData.alias_name || "Outlet"}</div>
                    <div class="manager-message-body">
                        <div class="manager-badge">Manager Notification</div>
                        <div class="custom-manager-message">
                            ${pushData.status || "Hello! Here's an update regarding your order."}
                        </div>
                    </div>
                `;
                if (pushData.type =="offers"){
                    AppUtils.playNotificationSound();
                    appendMessage(offerMessageHTML, 'server',null,'offers','',pushData.message_id); 

                }else if (pushData.type === "manager") {
                    AppUtils.notifyOrderReady(pushData);
                    showNotificationModal(pushData, 'notification');
                    appendMessage(managerMessageHTML, 'server',null, 'manager',pushData.token_no,pushData.message_id); 
                } else {
                if (pushData.type === "foodstatus") {
                    AppUtils.notifyOrderReady(pushData); 
                    showNotificationModal(pushData,'push');
                    appendMessage(messageHTML, 'server',null,'foodstatus',pushData.token_no,pushData.message_id);
                    }
                }
            }
        });
    }

    chatInput.addEventListener("keydown", function(event) {
        if (AppUtils.isReplyMode) {
            if (event.key === "Enter") {
                event.preventDefault();
                sendButton.click();
            }
            return;  // Allow all text if replying
        }

        const allowedKeys = ["Backspace", "Delete", "ArrowLeft", "ArrowRight", "Tab", "Enter"];

        if (
            (event.key >= "0" && event.key <= "9") ||
            allowedKeys.includes(event.key)
        ) {
            if (chatInput.value.length >= 4 && event.key >= "0" && event.key <= "9") {
                event.preventDefault();  // Only limit when NOT replying
            }

            if (event.key === "Enter") {
                event.preventDefault();
                sendButton.click();
            }
        } else {
            event.preventDefault();
            appendMessage("Please enter a valid 4-digit Order No.", "server", null);
        }
    });

    
    // Sanitize input on any indirect changes (e.g. autocomplete)
    chatInput.addEventListener("input", function(event) {
        if (AppUtils.isReplyMode) return;  // ✅ Skip restrictions while replying

        let cleanValue = chatInput.value.replace(/[^0-9]/g, "").substring(0, 4);
        if (chatInput.value !== cleanValue) {
            appendMessage("Only digits (0-9) are allowed.", "server", null);
        }
        chatInput.value = cleanValue;
    });


    chatInput.addEventListener("focus", function () {
        const selectedMessage = document.querySelector(".message-bubble.server.selected");

        if (selectedMessage) {
            chatInput.type = "text";
            chatInput.placeholder = "Type your message..."; 
        } else {
            chatInput.type = "tel";
            chatInput.placeholder = "Enter your Order No..."; 
        }
    });

    if (tokenFromQR && !isOpenedFromPush) {

        const vendorId = localStorage.getItem("activeVendor");

        // console.log("🔍 QR Scan Detected:", { tokenFromQR, vendorId, permissionStatus });

        // 🔧 Define core flow to handle token setup
        const handleToken = async () => {
            try {
                appendMessage(tokenFromQR, 'user', "", 'chat');
                // console.log("💬 Token appended to chat:", tokenFromQR);

                // ✅ Step 1: Ensure Service Worker is ready
                try {
                    if (!navigator.serviceWorker.controller) {
                        // console.log("⏳ Waiting for Service Worker to become active...");
                        await navigator.serviceWorker.ready;
                    }
                    console.log("🟢 Service Worker ready");
                } catch (swErr) {
                    console.error("❌ Service Worker initialization failed:", swErr);
                    appendMessage(
                        "⚠️ Unable to start background service. You may still continue, but live updates might not appear automatically. Please try again manually if needed.",
                        'server', null, 'error'
                    );
                }

                // ✅ Step 2: Subscribe for push notifications
                try {
                    await PushSubscriptionService.subscribe(tokenFromQR, vendorId);
                    // console.log("✅ Push subscription successful");
                } catch (subErr) {
                    console.error("❌ Push subscription failed:", subErr);
                    appendMessage(
                        "⚠️ Couldn’t enable live notifications right now. You can still view updates manually if required.",
                        'server', null, 'error'
                    );
                }

                // ✅ Step 3: Save chat log
                try {
                    await saveChat(tokenFromQR, 'user', 'chat', tokenFromQR);
                    // console.log("💾 Chat saved successfully");
                } catch (chatErr) {
                    console.error("❌ Chat saving failed:", chatErr);
                    appendMessage(
                        "⚠️ Temporary data couldn’t be saved. You can continue using the app, or re-enter details if needed.",
                        'server', null, 'error'
                    );
                }

            } catch (err) {
                chatInput.value = tokenFromQR;
                // console.error("❌ Unexpected error in handleToken:", err);
                appendMessage(
                    "⚠️ Something went wrong while processing your request. Please try entering the details manually once more.",
                    'server', null, 'error'
                );
            }
        };

        // ✅ Always show permission modal regardless of prior state
        // console.log("📢 Showing permission modal...")
        PermissionService.showModal(true);

        // ✅ Defer main flow until modal OK button is clicked
        PermissionService.setDeferredCallback(async () => {
            // console.log("🧩 Permission modal confirmed (OK clicked)");

            try {
                AppUtils.getNotificationHelpPath();
                // console.log("📂 Notification help path loaded");

                await handleToken();

                // ✅ Step 4: Fetch order status
                try {
                    // console.log("📡 Fetching order status...");
                    const check_status = await fetchOrderStatusOnce(tokenFromQR);

                    if (!check_status) {
                        console.warn("⚠️ Could not retrieve order status for token:", tokenFromQR);
                        appendMessage(
                            "⚠️ Couldn’t fetch the latest update right now. Please wait a few seconds or try again manually.",
                            'server', null, 'error'
                        );
                    }
                    // } else {
                    //     console.log("✅ Order status retrieved successfully:", check_status);
                    // }

                } catch (fetchErr) {
                    console.error("❌ Order status fetch failed:", fetchErr);
                    appendMessage(
                        "⚠️ Couldn’t load current status. You’ll still get alerts once updates are available, or you can retry manually.",
                        'server', null, 'error'
                    );
                }

                // console.log("🎉 Permission flow and order fetch complete");

            } catch (err) {
                console.error("❌ Error during permission flow:", err);
                appendMessage(
                    "⚠️ A technical issue occurred while initializing. Please re-enter your details and try again.",
                    'server', null, 'error'
                );
            }
        });

    } else {
        // console.log("💬 No QR detected or opened from push notification. Loading chat window...");
        await showChatWindow({});
        AppUtils.playWelcomeMessage();
    }


    // Send button logic
    sendButton.addEventListener('click', async function () {
        const message = chatInput.value.trim();
        if (message === '') return;

        const granted = await PermissionService.requestPermissions();
        if (!granted) {
            AppUtils.showToast("Notification not enabled. Proceeding without push alerts");
        }

        if (IosPwaInstallService.shouldRePrompt()) {
            IosPwaInstallService.showModal();
        }

        // Detect if it's a reply to a selected server message
        const selectedMessage = document.querySelector(".message-bubble.server.selected");

        if (selectedMessage) {
            const tokenNo = selectedMessage.dataset.tokenNo;
            if (tokenNo) {
                // This is a reply to a message with tokenNo
                await fetchOrderStatusOnce(tokenNo,message); // Attach token + reply inside this function
            } else {
                console.warn("Selected message has no token number.");
            }

            appendMessage(message, 'user', null);
            await saveChat(message, 'user', 'chat',tokenNo);
        } else {
            // No message selected → assume user typed token number directly
            appendMessage(message, 'user', null);
            await saveChat(message, 'user', 'chat',message);
            await fetchOrderStatusOnce(message); // Use message as tokenNo   
        }

        // ✅ Clear input
        chatInput.value = '';
        clearReplyMode(); 
    });
    
    async function fetchOrderStatusOnce(token, replyText = null) {
        const activeVendor = await AppUtils.getActiveVendor();
        const payload = { token_no: token, vendor_id: activeVendor };
        if (replyText) payload.reply_text = replyText;

        try {
            const resp = await fetch(apiEndpoints.CHECK_STATUS, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': AppUtils.getCSRFToken(),
                },
                body: JSON.stringify(payload),
            });

            const data = await resp.json();

            if (!resp.ok) {
                const err = data.error || "Unknown server error";
                appendMessage(`❌ ${err}`, 'server', null);
                throw new Error(err);
            }
            if (!replyText) {
                // build messageHTML exactly as before
                const statusClassMap = {
                    preparing: 'preparing-color',
                    ready: 'ready-color',
                    delivered: 'delivered-color',
                    cancelled: 'cancelled-color'
                };
                const statusKey = data?.status || 'unknown';
                const statusClass = statusClassMap[statusKey] || 'unknown-color';
                const messageHTML = `
                    <div class="response-title">${data.alias_name || "Unknown"}</div>
                    <div class="status">Status:
                        <span class="${statusClass}">${data.status || "Unknown"}</span>
                    </div>
                    <div class="info-badges">
                        <div class="badge">Counter No: ${data.counter_no || ""}</div>
                        <div class="badge">Token No: ${data.token_no || ""}</div>
                    </div>`;

                appendMessage(messageHTML, 'server', null, 'foodstatus', data.token_no);
                await saveChat(data, 'server', 'foodstatus', data.token_no);
                showNotificationModal(data, 'usercheck');
                AppUtils.notifyOrderReady(data);
            }

            await PushSubscriptionService.subscribe(token, data.vendor_id);
            PushHealthMonitorService.startMonitor(token, data.vendor_id);

            return data;  // << important: return the fetched data
        } catch (err) {
            console.error("Error fetching order status:", err);
            throw err;
        }
    }

    async function showChatWindow(data) {
        const chatContainer = document.getElementById('chat-container');
        const chatInput = document.getElementById('chat-input'); 

        if (!chatContainer || !chatInput) return;
        const vendorId=localStorage.getItem("activeVendor");
        const browser_id = AppUtils.getCurrentBrowserId();

        if (!browser_id) {
            console.warn("No browser ID, skipping restore wait.");
        }else {
            await ChatRestoreService.restore(vendorId);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    } 
});
