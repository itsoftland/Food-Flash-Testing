import { IosPwaInstallService } from './services/iosPwaInstallService.js';
import { AddOutletService } from "./services/addOutletService.js"; 
import { MenuModalService } from './services/menuModalService.js';
import { FeedbackService } from "./services/feedBackService.js";
import { PermissionService } from "./services/permissionService.js";
import { initNotificationModal, showNotificationModal } from './services/notificationService.js';
import { VendorUIService } from "./services/vendorUIService.js";
import { updateChatOnPush,appendMessage,clearReplyMode } from "./services/chatService.js";
import { PushSubscriptionService } from "./services/pushSubscriptionService.js";
import { PushHealthMonitorService } from "./services/pushHealthMonitorService.js";



document.addEventListener('DOMContentLoaded', async function() {
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
    console.log("isOpenedFromPush",isOpenedFromPush);
    console.log("parameters in url",tokenFromQR,locationId,vendorFromQR);

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
            window.location.href = "/";
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
        console.log("Token from QR:", tokenFromQR);
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
        console.log(vendorIdsString, "vendoridsstring");
        const vendorIdsArray = JSON.parse(vendorIdsString);
    
        const vendorIds = vendorIdsArray
            .map(id => parseInt(id))
            .filter(id => Number.isInteger(id) && !isNaN(id));
        VendorUIService.init(vendorIds);
    }

    const isAndroid = /Android/i.test(navigator.userAgent);
    console.log("Android device:", isAndroid);    
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
        navigator.serviceWorker.register("/service-worker.js", { scope: '/' })
        .then((registration) => {
            console.log("Service Worker Registered:", registration);
              if (registration.active) {
                registration.active.postMessage({
                type: "SET_BASE_URL",
                baseUrl: window.location.origin,
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
        console.log("No active service worker controller. Reloading...");
        // You can uncomment this if you want an automatic reload:
        // window.location.reload();
    }

    console.log("Notification API supported:", "Notification" in window);

    if (navigator.serviceWorker) {
        // Update the service worker with the current page URL on load.
        // Listen for messages from the service worker
        navigator.serviceWorker.addEventListener("message", (event) => {
            if (event.data && event.data.type === "OPEN_CHAT") {
            console.log("Received OPEN_CHAT message:", event.data.payload);
            // Call a function to display or refresh the chat view
            showChatWindow(event.data.payload);   
            }
        });
        
        // Optionally, update the service worker with the current page URL if needed
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
            if (event.data?.type === 'PUSH_RECEIVED') {
                PushHealthMonitorService.recordPushReceived();
            }
            if (event.data?.type === 'PUSH_STATUS_UPDATE') {
                const pushData = event.data.payload;
                console.log('Received push update via postMessage:', pushData);
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
                    <div class="response-title">${pushData.name || "Unknown"}</div>
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
                        <div class="response-title">${pushData.name}</div>
                        <div class="response-title">🔥 ${pushData.title}</div>
                        <div style="color: #333; font-size: 15px;">
                            ${pushData.body || "Delicious deals await. Come grab your favorite combo now!"}
                        </div>
                    
                `;
                const managerMessageHTML = `
                    <div class="response-title">📩 ${pushData.name || "Outlet"}</div>
                    <div class="manager-message-body">
                        <div class="manager-badge">Manager Notification</div>
                        <div class="custom-manager-message">
                            ${pushData.status || "Hello! Here's an update regarding your order."}
                        </div>
                    </div>
                `;
                console.log("Push Data Type:", pushData.type);
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
        console.log("Key:", event.key, "Value:", chatInput.value, "isReplyMode:", AppUtils.isReplyMode);
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


     // fallback handler

    // Show chat window if token is present
    if (tokenFromQR && !isOpenedFromPush) {
        console.log("Token from QR:", tokenFromQR);
        const permissionStatus = localStorage.getItem("permissionStatus")

        if (permissionStatus === "granted") {
            // ✅ Permission already granted — proceed immediately
            appendMessage(tokenFromQR, 'user', null);
            AppUtils.getNotificationHelpPath();
            try {
                    const check_status = await fetchOrderStatusOnce(tokenFromQR);
                    console.log("Order status:", check_status);
                } catch (err) {
                    chatInput.value = tokenFromQR;
                    console.error("Failed to fetch status:", err);
                }
        } else {
        // ⚠️ Permission not granted yet — defer logic
            PermissionService.setDeferredCallback(async () => {
                appendMessage(tokenFromQR, 'user', null);
                AppUtils.getNotificationHelpPath();

                try {
                    const check_status = await fetchOrderStatusOnce(tokenFromQR);
                    console.log("Order status:", check_status);
                } catch (err) {
                    chatInput.value = tokenFromQR;
                    console.error("Failed to fetch status:", err);
                }
            });
        }
    } else {
        // No token, just show chat window
        showChatWindow({});
        AppUtils.playWelcomeMessage();
    }

    // Send button logic
    sendButton.addEventListener('click', async function () {
        console.log("button clicked")
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
        } else {
            // No message selected → assume user typed token number directly
            await fetchOrderStatusOnce(message); // Use message as tokenNo
            appendMessage(message, 'user', null);
        }

        // ✅ Clear input
        chatInput.value = '';
        clearReplyMode(); 
    });



    // Single check to confirm the order status
    async function fetchOrderStatusOnce(token, replyText = null) {
        const activeVendor = await AppUtils.getActiveVendor();
        console.log("Active Vendor ID in order update:", activeVendor);
        const payload = {
            token_no: token,
            vendor_id: activeVendor,
        };

        if (replyText) {
            payload.reply_text = replyText;
        }

        console.log("Payload to send:", payload);
        fetch('/check-status/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': AppUtils.getCSRFToken(),  // Optional if using CSRF protection in Django
            },
            body: JSON.stringify(payload),
        })
        // handle your response here
        .then(async (response) => {
            const responseData = await response.json();

            if (!response.ok) {
                const errorMessage = responseData.error || "An unknown error occurred.";
                appendMessage(`❌ ${errorMessage}`, 'server', null);
                throw new Error(`Server responded with error: ${errorMessage}`);
            }
            const data = responseData;
            console.log(data);
            const statusClassMap = {
                    preparing: 'preparing-color',
                    ready: 'ready-color',
                    delivered: 'delivered-color',
                    cancelled: 'cancelled-color'
                };

            const statusKey = data?.status || 'unknown';
            const statusClass = statusClassMap[statusKey] || 'unknown-color';
            console.log("Status Class:", statusClass);
            const messageHTML = `
                    <div class="response-title">${data.name || "Unknown"}</div>
                    <div class="status">
                        Status: 
                        <span class="${statusClass}">
                            ${data.status || "Unknown"}
                        </span>
                    </div>
                    <div class="info-badges">
                        <div class="badge">Counter No: ${data.counter_no || ""}</div>
                        <div class="badge">Token No: ${data.token_no || ""}</div>
                    </div>
                `;
            if (!replyText){

                appendMessage(messageHTML, 'server', null, 'foodstatus',data.token_no);
                // If status is ready, notify user
                // if (data.status === "ready") {
                showNotificationModal(data,'usercheck');
                AppUtils.notifyOrderReady(data);
                // }
            }

            // Subscribe for push notifications
            PushSubscriptionService.subscribe(token, data.vendor);
            // Perform health monitoring
            PushHealthMonitorService.startMonitor(token, data.vendor);
        })
        .catch(error => {
            console.error("Error fetching order status:", error);
            if (!error.handled) {
                console.log("⚠️ Something went wrong. Please try again.", 'server', null);
            }
        });
    }
    
    function showChatWindow(data) {
        const chatContainer = document.querySelector('.chat-container');
        const chatInput = document.getElementById('chat-input'); 

        if (!chatContainer || !chatInput) return;

        // Temporarily hide and show chat
        chatContainer.style.display = "none";
        setTimeout(() => {
            chatContainer.style.display = "block";
        }, 100);

        // Auto-scroll
        setTimeout(() => {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }, 50);

        chatContainer.scrollIntoView({ behavior: "smooth" });
        const statusClassMap = {
                    preparing: 'preparing-color',
                    ready: 'ready-color',
                    delivered: 'delivered-color',
                    cancelled: 'cancelled-color'
                };

        const statusKey = data?.status || 'unknown';
        const statusClass = statusClassMap[statusKey] || 'unknown-color';

        // ✅ Reuse the logic to render the push message
        if (data) {
            const messageHTML = `
                    <div class="response-title">${data.name || "Unknown"}</div>
                    <div class="status">
                        Status: 
                        <span class="${statusClass}">
                            ${data.status || "Unknown"}
                        </span>
                    </div>
                    <div class="info-badges">
                        <div class="badge">Counter No: ${data.counter_no || ""}</div>
                        <div class="badge">Token No: ${data.token_no || ""}</div>
                    </div>
                `;

            const offerMessageHTML = `
                <div class="response-title">${data.name}</div>
                <div class="response-title">🔥 ${data.title}</div>
                <div style="color: #333; font-size: 15px;">
                    ${data.body || "Delicious deals await. Come grab your favorite combo now!"}
                </div>
            `;

            const managerMessageHTML = `
                <div class="response-title">📩 ${data.name || "Outlet"}</div>
                <div class="manager-message-body">
                    <div class="manager-badge">Manager Notification</div>
                    <div class="custom-manager-message">
                        ${data.status || "Hello! Here's an update regarding your order."}
                    </div>
                </div>
            `;

            if (data.type === "offers") {
                appendMessage(offerMessageHTML, 'server', null, 'offers', '', data.message_id);
                AppUtils.playNotificationSound();
            } else if (data.type === "manager") {
                appendMessage(managerMessageHTML, 'server', null, 'manager', data.token_no, data.message_id);
                showNotificationModal(data, 'notification');
            } else if (data.type === "foodstatus") {
                appendMessage(messageHTML, 'server', null, 'foodstatus', data.token_no, data.message_id);
                showNotificationModal(data, 'push');
                AppUtils.notifyOrderReady(data);
            }
        }

        console.log("✅ Chat window is now open or refreshed.", data);
    }

    // function showChatWindow(data) {
    //     const chatContainer = document.querySelector('.chat-container');
    //     const chatInput = document.getElementById('chat-input'); 
    
    //     if (!chatContainer || !chatInput) return;
    
    //     // Temporarily hide and show chat
    //     chatContainer.style.display = "none";
    //     setTimeout(() => {
    //         chatContainer.style.display = "block";
    //     }, 100);
    
    //     // Auto-scroll
    //     setTimeout(() => {
    //         chatContainer.scrollTop = chatContainer.scrollHeight;
    //     }, 50);
    
    //     // Set token if available
    //     if (data && data.token_no) {
    //         chatInput.value = data.token_no;
    //         chatInput.value = '';  
    //     }
    
    //     chatContainer.scrollIntoView({ behavior: "smooth" });
    
    //     console.log("Chat window is now open or refreshed.", data);
    // }    
});
