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
import { ChatTemplateService } from "./services/chatTemplateService.js";
import { maskSequenceCode } from "./services/clipBoardService.js"
import { savePassengerInfo, getPassengerName } from './services/passengerInfoService.js';
import BookingMappingService from "./dineflash/services/bookingMappingService.js";


window.maskSequenceCode = maskSequenceCode

function onDOMReady(callback) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', callback);
    } else {
        callback();
    }
}
onDOMReady(async function () {
    // console.log("✅ DOM ready — initialization...");

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
    const tokenFromQR = urlParams.get('token_no') || urlParams.get('sequence_code') || urlParams.get('booking_no');
    const bookingIdfromQR = urlParams.get('booking_id');
    const passengerName = urlParams.get('passenger_name');
    const toggleBtn = document.getElementById("toggleArrowBtn");
    const pageWrapper = document.querySelector(".page-wrapper");
    const isOpenedFromPush = urlParams.get('from_push');

    // console.log("Sequence code:",tokenFromQR);
    // console.log("Passenger Name :",passengerName)
    let isAdVisible = true;
    let storedName = null;
    let bookingId = null;
    let bookingNo = null;
    let check_status = null;

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
    if (tokenFromQR && passengerName) {
        await savePassengerInfo(tokenFromQR, passengerName);
    }
    if (window.BASE && window.BASE.includes('/dine_flash/')) {
        // console.log("Initializing Booking Mapping Service for Dine Flash...");
        BookingMappingService.processBookingFromQR(tokenFromQR,bookingIdfromQR);
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
                console.log("Payload Recieved:",pushData)
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
                let type = window.BASE?.includes('/airline_flash/') ? 'flightstatus' : 'foodstatus';
                const messageType = pushData.type || type;
                console.log("Received push message:", messageType, pushData);

                const messageHTML = ChatTemplateService.build({
                    type: messageType,
                    text: pushData
                });

                // Handle different message types
                switch (messageType) {
                    case 'offers':
                        AppUtils.playNotificationSound(pushData.vibration_pattern,pushData.vibration_duration);
                        appendMessage(messageHTML, 'server', null, 'offers', '', pushData.message_id);
                        break;

                    case 'manager':
                        AppUtils.notifyOrderReady(pushData);
                        showNotificationModal(pushData, 'notification');
                        appendMessage(messageHTML, 'server', null, 'manager', pushData.token_no, pushData.message_id);
                        break;
                    case 'airline_manager':
                        AppUtils.notifyOrderReady(pushData);
                        showNotificationModal(pushData, 'notification');
                        appendMessage(messageHTML, 'server', null, 'manager', pushData.sequence_code, pushData.message_id);
                        break;

                    case 'foodstatus':
                        AppUtils.notifyOrderReady(pushData);
                        showNotificationModal(pushData, 'push');
                        appendMessage(messageHTML, 'server', null, messageType, pushData.token_no, pushData.message_id);
                        break;
                    case 'flightstatus':
                        AppUtils.notifyOrderReady(pushData);
                        showNotificationModal(pushData, 'push');
                        appendMessage(messageHTML, 'server', null, messageType, pushData.sequence_code, pushData.message_id);
                        break;

                    default:
                        console.warn("Unhandled push message type:", messageType);
                }
            }
        });
    }

    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.secure-copy-btn');
        if (!btn) return;

        const encoded = btn.getAttribute('data-code');
        if (!encoded) return;

        // Decode the real sequence code (kept hidden from UI)
        const realCode = atob(encoded);
        const inputBox = document.getElementById("chat-input");

        if (!inputBox) return;

        // Insert masked code visually
        inputBox.value = maskSequenceCode(realCode);

        // Store the actual sequence code internally (for use on send)
        inputBox.dataset.actualSequence = realCode;

        // Show confirmation toast
        if (window.AppUtils && typeof AppUtils.showToast === 'function') {
            AppUtils.showToast("Sequence code added securely!");
        } else {
            alert("Sequence code added securely!");
        }
    });

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
        } else if (base === "/food_flash/") {
            event.preventDefault();
            appendMessage("Please enter a valid 4-digit Order No.", "server", null);
        }
    });

    
    // Sanitize input on any indirect changes (e.g. autocomplete)
    chatInput.addEventListener("input", function(event) {
        if (AppUtils.isReplyMode || base === '/airline_flash/') return;  // ✅ Skip restrictions while replying

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
            // console.log(base)
            if (base == '/airline_flash/'){
                chatInput.placeholder = "Enter your Sequence Code..."; 
            }else if (base == '/dine_flash/'){
                chatInput.placeholder = "Enter your Booking No...";
            }
            else{
                chatInput.placeholder = "Enter your Order No...";
            } 
        }
    });

    if (tokenFromQR && !isOpenedFromPush) {

        const vendorId = localStorage.getItem("activeVendor");

        // console.log("🔍 QR Scan Detected:", { tokenFromQR, vendorId, permissionStatus });

        // 🔧 Define core flow to handle token setup
        const handleToken = async () => {
            try {
                let displayToken = tokenFromQR;
                // Apply masking only for airline_flash
                if (window.BASE && window.BASE.includes('/airline_flash/')) {
                    storedName = await getPassengerName(tokenFromQR);
                    // console.log("Passenger:", storedName);
                    // Append masked token in chat for Airline Flash
                    displayToken = maskSequenceCode(displayToken);
                    appendMessage(displayToken, 'user', "", 'chat',"",storedName);
                }else{
                    appendMessage(displayToken, 'user', "", 'chat');
                }

                // appendMessage(tokenFromQR, 'user', "", 'chat');
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
                    if (window.BASE && window.BASE.includes('/dine_flash/')) {
                        // bookingId = BookingMappingService.getBookingId(tokenFromQR.split("-")[1]);
                        await PushSubscriptionService.subscribe(bookingIdfromQR, vendorId);
                        // await PushSubscriptionService.subscribe(bookingId, vendorId);
                    }else{
                        await PushSubscriptionService.subscribe(tokenFromQR, vendorId);
                    }
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
                    if (window.BASE && window.BASE.includes('/dine_flash/')) {
                        await saveChat(tokenFromQR, 'user', 'chat', bookingIdfromQR);
                    }else{
                        await saveChat(tokenFromQR, 'user', 'chat', tokenFromQR);
                    }
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
                    if (window.BASE && window.BASE.includes('/dine_flash/')) {
                        check_status = await fetchOrderStatusOnce(tokenFromQR,null,bookingIdfromQR);
                    }else{
                        check_status = await fetchOrderStatusOnce(tokenFromQR);
                    }

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
        let message = chatInput.value.trim();
        if (message === '') return;
        const actualSequence = chatInput.dataset.actualSequence;

        if (window.BASE && window.BASE.includes('/airline_flash/') && actualSequence) {
            // Use the real unmasked value for backend logic
            message = actualSequence;

            // Clean up after sending
            delete chatInput.dataset.actualSequence;
        }


        const granted = await PermissionService.requestPermissions();
        if (!granted) {
            console.warn("⚠️ Notification permission not granted by user.");
            AppUtils.showToast("Notification not enabled. Proceeding without push alerts");
        }

        if (IosPwaInstallService.shouldRePrompt()) {
            IosPwaInstallService.showModal();
        }

        // Detect if it's a reply to a selected server message
        const selectedMessage = document.querySelector(".message-bubble.server.selected");

        if (selectedMessage) {
            // console.log(selectedMessage.dataset.tokenNo)
            const tokenNo = selectedMessage.dataset.tokenNo;
            if (tokenNo) {
                // This is a reply to a message with tokenNo
                await fetchOrderStatusOnce(tokenNo,message); // Attach token + reply inside this function
            } else {
                console.warn("Selected message has no token number.");
            }
            if (window.BASE && window.BASE.includes('/airline_flash/')) {
                storedName = await getPassengerName(tokenNo);
                appendMessage(message, 'user', "","chat",tokenNo,storedName);
            }else{
                appendMessage(message, 'user', null);
            }
            
            await saveChat(message, 'user', 'chat',tokenNo);
        } else {
            // No message selected → assume user typed token number directly
            if (window.BASE && window.BASE.includes('/airline_flash/')) {
                storedName = await getPassengerName(message);
                appendMessage(message, 'user', "","chat",message,storedName);
            } 
            else if (window.BASE && window.BASE.includes('/dine_flash/')) {
                let bookingNo = BookingMappingService.getBookingNo(message);
                // console.log("Booking No for display:", bookingNo);
                // ❗ If multiple booking numbers → STOP execution
                if (Array.isArray(bookingNo)) {
                    appendChoiceOptions(bookingNo);
                    return;  // << STOP HERE
                }

                // Otherwise continue normally
                appendMessage(bookingNo, 'user', null, "chat", bookingNo);
            }

            else {
                appendMessage(message, 'user', null);
            }
            if (window.BASE && window.BASE.includes('/dine_flash/')) {
                bookingId = BookingMappingService.getBookingId(message); 
                await saveChat(bookingNo, 'user', 'chat',bookingId);
                await fetchOrderStatusOnce(bookingNo); // Use bookingNo as tokenNo
            }else{
                await saveChat(message, 'user', 'chat',message);
                await fetchOrderStatusOnce(message); // Use message as tokenNo  
            }
             
        }

        // ✅ Clear input
        chatInput.value = '';
        clearReplyMode(); 
    });

    function appendChoiceOptions(bookingList) {
        const chatContainer = document.getElementById("chat-container");

        // Row wrapper exactly like appendMessage()
        const messageRow = document.createElement("div");
        messageRow.classList.add("message-row", "server");

        // Server logo
        const activeLogo = localStorage.getItem("activeVendorLogo");
        const logoImg = document.createElement("img");
        logoImg.src = activeLogo;
        logoImg.alt = "Vendor Logo";
        logoImg.className = "server-logo";
        messageRow.appendChild(logoImg);
        
        // Clear input
        chatInput.value = '';
        // Chat bubble
        const bubble = document.createElement("div");
        bubble.classList.add("message-bubble", "server", "choice-bubble");

        bubble.innerHTML = `
            <div class="message-content">
                <div class="choice-title">Multiple bookings found</div>
                <div class="choice-subtitle">Please select the correct booking</div>
                <div class="choice-options"></div>
            </div>
        `;

        const optionsContainer = bubble.querySelector(".choice-options");

        // bookingList.forEach(item => {

        //     const trimmed = item.booking_no.split("-")[1];

        //     const btn = document.createElement("button");
        //     btn.className = "choice-option-btn";

        //     btn.dataset.bookingId = item.booking_id;
        //     btn.dataset.trimmedNo = trimmed;

        //     btn.innerHTML = `
        //         <div class="opt-main">Booking No: <strong>${item.booking_no}</strong></div>
        //         <button class="choice-option-btn slide-reveal">
        //             Tap to View Status
        //         </button>
        //     `;

        //     // Handling the button selection
        //     btn.addEventListener("click", async () => {

        //         // Visually mark selected (premium effect)
        //         document.querySelectorAll(".choice-option-btn")
        //             .forEach(el => el.classList.remove("selected"));
        //         btn.classList.add("selected");
        //         bubble.classList.add("selected-choice");

        //         // Append user's selected booking as a chat message
        //         appendMessage(
        //             item.booking_no,            // text for display
        //             'user',
        //             null,
        //             "chat",
        //             item.booking_id
        //         );

        //         // Save the user's selection
        //         await saveChat(item.booking_no, 'user', 'chat', item.booking_id);

        //         // Trigger your main status fetch pipeline
        //         await fetchOrderStatusOnce(trimmed, null, item.booking_id);
        //         messageRow.innerHTML = ""; // Clear options after selection
        //         // chatInput.value = '';
        //     });

        //     optionsContainer.appendChild(btn);
        // });
        bookingList.forEach(item => {

            const trimmed = item.booking_no.split("-")[1];

            // Outer container (no more button-inside-button issue)
            const wrapper = document.createElement("div");
            wrapper.className = "choice-option-btn";  
            wrapper.dataset.bookingId = item.booking_id;
            wrapper.dataset.trimmedNo = trimmed;

            wrapper.innerHTML = `
                <div class="opt-main">Booking No: <strong>${item.booking_no}</strong></div>
                <button class="view-btn slide-reveal loop-sheen">
                    Tap to View Status
                </button>
            `;

            // Selecting only the actual click button
            const actionBtn = wrapper.querySelector(".view-btn");

            actionBtn.addEventListener("click", async () => {

                // Stop animation after click
                actionBtn.classList.remove("loop-sheen");
                actionBtn.classList.add("clicked");

                // Visual highlighting
                document.querySelectorAll(".view-btn").forEach(el => el.classList.remove("selected"));
                actionBtn.classList.add("selected");
                bubble.classList.add("selected-choice");

                // Add message to chat
                appendMessage(item.booking_no, 'user', null, "chat", item.booking_id);
                await saveChat(item.booking_no, 'user', 'chat', item.booking_id);

                // Trigger API call
                await fetchOrderStatusOnce(trimmed, null, item.booking_id);

                messageRow.innerHTML = "";
            });

            optionsContainer.appendChild(wrapper);
        });


        messageRow.appendChild(bubble);
        chatContainer.appendChild(messageRow);

        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    async function fetchOrderStatusOnce(token, replyText = null, bookingId = null) {
        const activeVendor = await AppUtils.getActiveVendor();
        let payload = {};
        let type = '';
        if (window.BASE && window.BASE.includes('/airline_flash/')) {
            payload = { sequence_code: token, vendor_id: activeVendor };
            type = 'flightstatus';
        }
        else if (window.BASE && window.BASE.includes('/dine_flash/')) {
            if (!bookingId) {
                bookingId = BookingMappingService.getBookingId(token.split("-")[1]);
                if (Array.isArray(bookingId)) {
                    // console.log("Multiple bookings found for token:", token, "→", bookingId);
                    console.warn("⚠️ Multiple bookings found for token:", token);
                    // Multiple bookings → show list to user
                    // showBookingSelectionUI(bookingData);
                    return; // stop here until user selects
                }
            }
            // console.log("Fetching booking ID for token:", token, "→", bookingId);
            payload = { booking_id: bookingId, vendor_id: activeVendor };
            type = 'dinestatus';
        } 
        else {
            payload = { token_no: token, vendor_id: activeVendor };
            type = 'foodstatus';
        }
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
            // console.log("Status response data:", data);

            if (!resp.ok) {
                const err = data.error || "Unknown server error";
                appendMessage(`❌ ${err}`, 'server', null);
                throw new Error(err);
            }
            if (!replyText) {
                const messageHTML = ChatTemplateService.build({
                    type: type,
                    text: data
                });
                // console.log("Built message HTML:", messageHTML);
                if (type === 'flightstatus') {
                    appendMessage(messageHTML, 'server', null, type, data.sequence_code);
                    await saveChat(data, 'server', type, data.sequence_code);
                }
                else if (type === 'dinestatus') {
                    appendMessage(messageHTML, 'server', null, type, bookingId);
                    await saveChat(data, 'server', type, bookingId);
                } 
                else {
                    appendMessage(messageHTML, 'server', null, type, data.token_no);
                    await saveChat(data, 'server', type, data.token_no);
                }
                showNotificationModal(data, 'usercheck');
                AppUtils.notifyOrderReady(data);
            }
            if (window.BASE && window.BASE.includes('/dine_flash/')) {
                await PushSubscriptionService.subscribe(bookingId, data.vendor_id);
                PushHealthMonitorService.startMonitor(bookingId, data.vendor_id);
            }
            else {
                await PushSubscriptionService.subscribe(tokenFromQR, data.vendor_id);
                PushHealthMonitorService.startMonitor(token, data.vendor_id);
            }
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
