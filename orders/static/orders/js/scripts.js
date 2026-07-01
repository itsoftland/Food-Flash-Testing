import { IosPwaInstallService } from './services/iosPwaInstallService.js';
import { AddOutletService } from "./services/addOutletService.js"; 
import { MenuModalService } from './services/menuModalService.js';
import { FeedbackService } from "./services/feedBackService.js";
import { PermissionService } from "./services/permissionService.js";
import { VendorUIService } from "./services/vendorUIService.js";
import { updateChatOnPush,appendMessage,clearReplyMode,saveChat } from "./services/chatService.js";
import { PushSubscriptionService } from "./services/pushSubscriptionService.js";
import { PushHealthMonitorService } from "./services/pushHealthMonitorService.js";
import { ChatRestoreService } from "./services/chatRestoreService.js";
import { ChatSyncService } from "./services/chatSyncService.js";
import { hydrateServerLogoElement } from "./services/welcomeMessageService.js";
import { ChatTemplateService } from "./services/chatTemplateService.js?v=20260605_1";
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
    const normalizeProjectName = (value) =>
        String(value || '').toLowerCase().replace(/[_-]/g, '').trim();

    const lockDineFlashHomeOnBack = () => {
        const path = (window.location?.pathname || "").toLowerCase();
        const isDineFlashHome = path.includes("/dine_flash/home/");
        const isDineFlashBuffetHome = path.includes("/dine_flash_buffet/home/");
        if (!isDineFlashHome && !isDineFlashBuffetHome) return;

        // Keep users on Dine Flash home when browser Back is pressed.
        // Build a small same-URL history buffer and refill it on popstate.
        const pushLockState = () => {
            window.history.pushState({ stayOnDineFlashHome: Date.now() }, "", window.location.href);
        };

        for (let i = 0; i < 12; i += 1) {
            pushLockState();
        }

        window.addEventListener("popstate", () => {
            pushLockState();
            pushLockState();
        });
    };

    lockDineFlashHomeOnBack();
    const isDineFlashHomePage = (window.location?.pathname || "").toLowerCase().includes("/dine_flash/home/");
    const isDineFlashBuffetHomePage = (window.location?.pathname || "").toLowerCase().includes("/dine_flash_buffet/home/");

    const inferProjectFromPath = () => {
        const path = (window.location?.pathname || '').toLowerCase();
        if (path.includes('/airline_flash') || path.includes('/airlineflash')) return 'airline_flash';
        if (path.includes('/dine_flash_buffet') || path.includes('/dineflashbuffet')) return 'dine_flash_buffet';
        if (path.includes('/dine_flash') || path.includes('/dineflash')) return 'dine_flash';
        if (path.includes('/food_flash') || path.includes('/foodflash')) return 'food_flash';
        const parts = path.split('/').filter(Boolean);
        return parts[0] || null;
    };

    const currentProject = () => window.PROJECT_NAME || inferProjectFromPath();
    const projectsMatch = (expected, incoming) => {
        const e = normalizeProjectName(expected);
        const i = normalizeProjectName(incoming);
        if (!e || !i) return false;
        return e === i || e.startsWith(i) || i.startsWith(e);
    };
    /** Buffet flavour only — `projectsMatch(x, "dine_flash")` is true for buffet because names share a prefix. */
    const isDineFlashBuffetProject = () =>
        normalizeProjectName(currentProject()) === "dineflashbuffet";

    // ⚠️ TEMP DIAGNOSTIC (iOS chat-card loss). Structured timeline logging only —
    // no business logic. Enabled for Dine Flash AND Dine Flash Buffet (excludes
    // Food Flash, Airline Flash, and other flavours, because `projectsMatch(x,
    // "dine_flash")` is true only for the dine_flash* family). Each log is prefixed
    // with the active project. Remove all `[diag]` logs once root cause is found.
    const dineFlashDiagEnabled = projectsMatch(currentProject(), "dine_flash");
    const diagProjectLabel = currentProject();
    const dineFlashDiag = (label, data) => {
        if (!dineFlashDiagEnabled) return;
        console.info(`[diag][${diagProjectLabel}] ${label}`, {
            ts: new Date().toISOString(),
            ...(data || {}),
        });
    };

    // ⚠️ TEMP DIAGNOSTIC (iOS push-delivery chain). Mirrors dineFlashDiag to the
    // console AND POSTs the breadcrumb to /api/dine_flash_client_diag/ so a push
    // can be traced end-to-end in the server logs without Safari Web Inspector.
    // Fire-and-forget, never throws, never blocks the UI. Remove with the other
    // `[diag]` logs once root cause is found.
    const dineFlashClientDiag = (step, fields) => {
        if (!dineFlashDiagEnabled) return;
        const data = fields || {};
        dineFlashDiag(step, data);
        try {
            const browserId =
                (typeof AppUtils !== "undefined" && AppUtils.getCurrentBrowserId?.()) || null;
            const url = `${AppUtils.getStartUrl()}api/dine_flash_client_diag/`;
            fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken":
                        (typeof AppUtils !== "undefined" && AppUtils.getCSRFToken?.()) || "",
                },
                credentials: "same-origin",
                keepalive: true,
                body: JSON.stringify({
                    step,
                    source: "page",
                    browser_id: browserId,
                    timestamp: Date.now(),
                    ...data,
                }),
            }).catch(() => {});
        } catch (e) {
            // Diagnostics must never break the page.
        }
    };
    console.info("REACHED LINE 92");
    dineFlashDiag("page init START", {
        url: window.location?.href,
        from_push: new URLSearchParams(window.location.search).get("from_push"),
        controller_present:
            typeof navigator !== "undefined" &&
            "serviceWorker" in navigator &&
            Boolean(navigator.serviceWorker.controller),
        browser_id_present: Boolean(
            (typeof AppUtils !== "undefined" && AppUtils.storageGet("browser_id")) || null
        ),
    });

    const ACTIVE_DINE_BOOKING_KEY = "activeDineBookingId";
    const normalizeBookingId = (value) => {
        if (value === null || value === undefined) return null;
        const trimmed = String(value).trim();
        return trimmed || null;
    };
    const setActiveDineBookingId = (bookingValue) => {
        if (!projectsMatch(currentProject(), "dine_flash")) return;
        if (isDineFlashBuffetProject()) return;
        const normalized = normalizeBookingId(bookingValue);
        if (!normalized) return;
        AppUtils.storageSet(ACTIVE_DINE_BOOKING_KEY, normalized);
    };
    const getActiveDineBookingId = () => {
        if (!projectsMatch(currentProject(), "dine_flash")) return null;
        if (isDineFlashBuffetProject()) return null;
        return normalizeBookingId(AppUtils.storageGet(ACTIVE_DINE_BOOKING_KEY));
    };

    // -------------------------------------------------------------------------
    // 🛡️ Helper: Re-establish connection on visibility change
    // -------------------------------------------------------------------------

    // console.log("✅ DOM ready — initialization...");

    let apiEndpoints;
    const base = window.BASE || '/caller_on/';
    const appVersion =
        (typeof window.APP_VERSION === "string" && window.APP_VERSION.trim() !== "")
            ? window.APP_VERSION.trim()
            : "";

    // ✅ Import notification service with cache-busting (ensures latest modal logic is used)
    const notificationModule = await import(
        `${base}static/orders/js/services/notificationService.js${appVersion ? `?v=${encodeURIComponent(appVersion)}` : ""}`
    );
    const { initNotificationModal, showNotificationModal } = notificationModule;

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
    const dineFlashBootstrap =
        window.DINE_FLASH_TRACKING_BOOTSTRAP &&
        typeof window.DINE_FLASH_TRACKING_BOOTSTRAP === "object"
            ? window.DINE_FLASH_TRACKING_BOOTSTRAP
            : null;
    let locationId = dineFlashBootstrap?.location_id ?? urlParams.get("location_id");
    const vendorFromQR = dineFlashBootstrap?.vendor_id ?? urlParams.get('vendor_id');
    const tokenFromQR = dineFlashBootstrap?.booking_no
        ?? urlParams.get('token_no')
        ?? urlParams.get('sequence_code')
        ?? urlParams.get('booking_no');
    const bookingIdfromQR = dineFlashBootstrap?.booking_id ?? urlParams.get('booking_id');
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
            // For Dine Flash / Dine Flash Buffet home, do not force-redirect on missing location.
            // Requirement: stay on .../home/ when navigating back (same-origin kiosk browsers).
            if (!isDineFlashHomePage && !isDineFlashBuffetHomePage) {
                // 3️⃣ Ask for it / show error / redirect
                AppUtils.showToast("No location ID found");
                // Optionally redirect to a location selection page
                window.location.href = base;
                throw new Error("Missing location ID");
            }
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
        setActiveDineBookingId(bookingIdfromQR);
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
    // Dine Flash Buffet: same fast permission UX as table_booking — keeps the native
    // notification prompt in the user-gesture chain (helps mobile / strict browsers).
    const isDineFlashBuffetSurface =
        (typeof window.PROJECT_NAME === "string" &&
            window.PROJECT_NAME.trim().toLowerCase() === "dine_flash_buffet") ||
        (window.location?.pathname || "").toLowerCase().includes("/dine_flash_buffet");
    const isDineFlashTableBookingSurface =
        (window.BASE && window.BASE.includes("/dine_flash/")) && !isDineFlashBuffetSurface;
    if (isDineFlashTableBookingSurface && tokenFromQR && bookingIdfromQR) {
        console.info("[dine_flash] page init booking available", {
            booking_id: bookingIdfromQR,
            booking_no: tokenFromQR,
            vendor_id: vendorFromQR,
            browser_id: AppUtils.storageGet("browser_id") || null,
            url: window.location?.href,
        });
    }
    // Set before VendorUIService.init so restore does not race with post-booking status fetch.
    if (isDineFlashTableBookingSurface && tokenFromQR && !isOpenedFromPush) {
        window.dineFlashBookingFromRedirect = true;
    }
    if (isDineFlashBuffetSurface) {
        PermissionService.init({ dineFlashFastPermissionUX: true });
    } else {
        PermissionService.init();
    }
    PermissionService.showModal();

    async function resumePushSubscriptionIfNeeded() {
        const activeVendor = await AppUtils.getActiveVendor();
        if (!activeVendor) {
            if (isDineFlashTableBookingSurface) {
                console.info("[dine_flash] resumePushSubscriptionIfNeeded early return", {
                    reason: "missing active vendor",
                });
            }
            return;
        }
        // Buffet post-order redirect links push in fetchOrderStatusOnce — avoid old saved token.
        if (tokenFromQR && isDineFlashBuffetSurface && !isOpenedFromPush) {
            return;
        }
        const token = tokenFromQR
            ? String(tokenFromQR).trim()
            : (await AppUtils.getToken());
        if (!token) {
            if (isDineFlashTableBookingSurface) {
                console.info("[dine_flash] resumePushSubscriptionIfNeeded early return", {
                    reason: "missing token",
                });
            }
            return;
        }
        try {
            if (isDineFlashTableBookingSurface) {
                console.info("[dine_flash] resumePushSubscriptionIfNeeded calling subscribe", {
                    token,
                    vendor_id: activeVendor,
                    notification_permission: Notification.permission,
                });
            }
            await PushSubscriptionService.subscribe(token, activeVendor);
        } catch (err) {
            console.error("❌ Subscription resume failed:", err);
        }
    }
    await resumePushSubscriptionIfNeeded();
    
    // Register Service Worker early so push subscription can bind sooner on cold starts.
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

    // Example usage: Get the last active vendor ID

    const vendorIdsString = AppUtils.storageGet("selectedVendors");
    if (vendorIdsString) {
        const vendorIdsArray = JSON.parse(vendorIdsString);
    
        const vendorIds = vendorIdsArray
            .map(id => parseInt(id))
            .filter(id => Number.isInteger(id) && !isNaN(id));
        await VendorUIService.init(vendorIds);
        ChatSyncService.init();
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
    const activeTokenForNotifications =
        tokenFromQR != null && String(tokenFromQR).trim() !== ""
            ? String(tokenFromQR).trim()
            : null;
    initNotificationModal(notificationModal, {
        activeToken: activeTokenForNotifications,
    });
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

        dineFlashDiag("SW message listener REGISTERED", {
            controller_present: Boolean(navigator.serviceWorker.controller),
        });
        navigator.serviceWorker.addEventListener('message', async (event) => {
            const diagPayload = event.data?.payload || {};
            dineFlashClientDiag("PAGE_MESSAGE_RECEIVED", {
                type: event.data?.type,
                message_id: diagPayload.message_id,
                booking_id: diagPayload.booking_id,
                token_no: diagPayload.token_no,
            });
            dineFlashDiag("SW message RECEIVED by page", {
                type: event.data?.type,
                has_payload: Boolean(event.data?.payload),
            });
            if (event.data && event.data.type === "OPEN_CHAT") {
                const payloadProject = event.data?.payload?.project;
                dineFlashDiag("OPEN_CHAT received", {
                    payload_project: payloadProject,
                    booking_id: event.data?.payload?.booking_id,
                    project_match: projectsMatch(currentProject(), payloadProject),
                });
                if (!projectsMatch(currentProject(), payloadProject)) {
                    dineFlashDiag("OPEN_CHAT REJECTED: project mismatch", {
                        expected: currentProject(),
                        incoming: payloadProject,
                    });
                    return;
                }
                // Call a function to display or refresh the chat view
                await showChatWindow(event.data.payload);   
            }
            if (event.data?.type === 'PUSH_RECEIVED') {
                PushHealthMonitorService.recordPushReceived();
            }
            if (event.data?.type === 'PUSH_STATUS_UPDATE') {
                const pushData = event.data.payload;
                // console.log("Payload Recieved:",pushData)
                dineFlashDiag("PUSH_STATUS_UPDATE received", {
                    type: pushData?.type,
                    project: pushData?.project,
                    booking_id: pushData?.booking_id,
                    token_no: pushData?.token_no,
                    vendor_id: pushData?.vendor_id,
                    status: pushData?.status,
                    message_id: pushData?.message_id,
                });
                // Ignore cross-flavour messages (fixes food_flash -> airline_flash leakage).
                const expectedProject = currentProject();

                const incomingProject =
                    pushData?.project != null ? String(pushData.project).toLowerCase().trim() : null;

                // If project identity doesn't match (or is missing), discard to avoid
                // cross-flavour card updates.
                if (!projectsMatch(expectedProject, incomingProject)) {
                    dineFlashClientDiag("FILTER_REJECTED", {
                        reason: "project_mismatch",
                        message_id: pushData?.message_id,
                        booking_id: pushData?.booking_id,
                        token_no: pushData?.token_no,
                        type: pushData?.type,
                    });
                    dineFlashDiag("PUSH_STATUS_UPDATE REJECTED: project mismatch", {
                        expected: expectedProject,
                        incoming: incomingProject,
                    });
                    return;
                }
                if (
                    isDineFlashBuffetSurface &&
                    window.buffetQrTokenFromRedirect &&
                    pushData?.token_no != null
                ) {
                    const expected = String(window.buffetQrTokenFromRedirect).trim();
                    const incoming = String(pushData.token_no).trim();
                    if (expected && incoming && expected !== incoming) {
                        dineFlashClientDiag("FILTER_REJECTED", {
                            reason: "token_mismatch",
                            message_id: pushData?.message_id,
                            booking_id: pushData?.booking_id,
                            token_no: pushData?.token_no,
                            type: pushData?.type,
                        });
                        dineFlashDiag("PUSH_STATUS_UPDATE REJECTED: buffet token mismatch (QR redirect window)", {
                            expected_token: expected,
                            incoming_token: incoming,
                        });
                        return;
                    }
                }
                // Table-booking Dine Flash only: buffet shares the "dine_flash" prefix in
                // `projectsMatch`, so exclude buffet or utility-ready pushes get dropped.
                if (
                    projectsMatch(expectedProject, "dine_flash") &&
                    normalizeProjectName(expectedProject) !== "dineflashbuffet"
                ) {
                    const incomingBookingId = normalizeBookingId(pushData?.booking_id);
                    const knownBookingIds = BookingMappingService.getAllBookingIds();
                    // Accept the push when its booking_id belongs to this browser's
                    // known Dine Flash bookings (BOOKING_ID_MAP membership) — NOT only
                    // the currently active booking. This lets every visible Dine Flash
                    // booking receive its own notifications. Active-booking selection is
                    // reserved for outbound actions and never suppresses inbound pushes.
                    if (
                        incomingBookingId &&
                        knownBookingIds.length > 0 &&
                        !knownBookingIds.includes(incomingBookingId)
                    ) {
                        dineFlashClientDiag("FILTER_REJECTED", {
                            reason: "booking_mismatch",
                            message_id: pushData?.message_id,
                            booking_id: pushData?.booking_id,
                            token_no: pushData?.token_no,
                            type: pushData?.type,
                        });
                        dineFlashDiag("PUSH_STATUS_UPDATE REJECTED: booking_id not in BOOKING_ID_MAP", {
                            incoming_booking_id: incomingBookingId,
                            known_booking_ids: knownBookingIds,
                        });
                        return;
                    }
                }

                // Extra safety: Airline UI expects `sequence_code`.
                if (expectedProject === "airline_flash") {
                    const seq = pushData?.sequence_code != null ? String(pushData.sequence_code).trim() : "";
                    if (!seq) return;
                }
                // ✅ Send ACK back to Service Worker confirming receipt
                if (navigator.serviceWorker.controller) {
                    navigator.serviceWorker.controller.postMessage({
                        type: "PUSH_STATUS_ACK",
                        token_no: pushData.token_no,
                    });
                }
                let selectedVendors = AppUtils.getStoredVendors() || [];
                // Check if the vendor is already in the list
                if (!selectedVendors.includes(pushData.vendor_id)) {
                    await AppUtils.appendVendorIfNotExists(pushData.vendor_id);
                    const vendorIds = AppUtils.getStoredVendors();
                    VendorUIService.init(vendorIds);
                }
                dineFlashClientDiag("FILTERS_PASSED", {
                    message_id: pushData?.message_id,
                    booking_id: pushData?.booking_id,
                    token_no: pushData?.token_no,
                    type: pushData?.type,
                });
                dineFlashDiag("PUSH_STATUS_UPDATE filters PASSED -> updating chat", {
                    booking_id: pushData?.booking_id,
                    type: pushData?.type || (window.BASE?.includes('/airline_flash/') ? 'flightstatus' : 'foodstatus'),
                });
                if (ChatSyncService.isAlreadyHandled(pushData)) {
                    return;
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
                try {
                switch (messageType) {
                    case 'offers':
                        AppUtils.playNotificationSound(pushData.vibration_pattern,pushData.vibration_duration);
                        appendMessage(messageHTML, 'server', null, 'offers', '', pushData.message_id);
                        break;

                    case 'manager':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'notification');
                        appendMessage(messageHTML, 'server', null, 'manager', pushData.token_no, pushData.message_id);
                        break;
                    case 'airline_manager':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'notification');
                        appendMessage(messageHTML, 'server', null, 'manager', pushData.sequence_code, pushData.message_id);
                        break;
                    case 'dine_manager':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'notification');
                        appendMessage(messageHTML, 'server', null, 'manager', pushData.booking_id, pushData.message_id);
                        break;
                    case 'buffet_manager':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'notification');
                        dineFlashDiag("PUSH buffet_manager APPENDING card", {
                            token_no: pushData.token_no,
                            message_id: pushData.message_id,
                            chat_children_before: document.getElementById('chat-container')?.childElementCount,
                            is_restoring_history: Boolean(window.isRestoringHistory),
                        });
                        appendMessage(messageHTML, 'server', null, 'buffet_manager', pushData.token_no, pushData.message_id);
                        dineFlashDiag("PUSH buffet_manager APPENDED card", {
                            token_no: pushData.token_no,
                            chat_children_after: document.getElementById('chat-container')?.childElementCount,
                        });
                        break;
                    case 'item_preparing':
                    case 'item_ready':
                    case 'item_cancelled':
                    case 'item_delivered':
                    case 'item_operation_closed':
                    case 'buffet_item_preparing':
                    case 'buffet_item_ready':
                    case 'buffet_item_cancelled':
                    case 'buffet_item_delivered':
                    case 'buffet_utilities_status':
                    case 'buffet_utilities_ready':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'push');
                        dineFlashDiag("PUSH buffet item/status APPENDING card", {
                            type: messageType,
                            token_no: pushData.token_no,
                            message_id: pushData.message_id,
                            chat_children_before: document.getElementById('chat-container')?.childElementCount,
                            is_restoring_history: Boolean(window.isRestoringHistory),
                        });
                        appendMessage(messageHTML, 'server', null, messageType, pushData.token_no, pushData.message_id);
                        dineFlashDiag("PUSH buffet item/status APPENDED card", {
                            type: messageType,
                            token_no: pushData.token_no,
                            chat_children_after: document.getElementById('chat-container')?.childElementCount,
                        });
                        break;
                    case 'order_delivered':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'push');
                        appendMessage(messageHTML, 'server', null, messageType, pushData.token_no, pushData.message_id);
                        break;
                    case 'foodstatus':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'push');
                        appendMessage(messageHTML, 'server', null, messageType, pushData.token_no, pushData.message_id);
                        break;
                    case 'flightstatus':
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'push');
                        appendMessage(messageHTML, 'server', null, messageType, pushData.sequence_code, pushData.message_id);
                        break;
                    case 'dinestatus':
                        if (
                            window.BASE?.includes('/dine_flash/') &&
                            !window.BASE?.includes('/dine_flash_buffet/')
                        ) {
                            console.info("[dine_flash] PUSH_STATUS_UPDATE dinestatus", {
                                booking_id: pushData.booking_id,
                                status: pushData.status,
                                utility_name: pushData.utility_name,
                            });
                        }
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'push');
                        dineFlashDiag("PUSH dinestatus APPENDING card", {
                            booking_id: pushData.booking_id,
                            message_id: pushData.message_id,
                            chat_children_before: document.getElementById('chat-container')?.childElementCount,
                            is_restoring_history: Boolean(window.isRestoringHistory),
                        });
                        appendMessage(messageHTML, 'server', null, messageType, pushData.booking_id, pushData.message_id);
                        dineFlashDiag("PUSH dinestatus APPENDED card", {
                            booking_id: pushData.booking_id,
                            chat_children_after: document.getElementById('chat-container')?.childElementCount,
                        });
                        break;
                    
                    case 'thankyou' :
                        AppUtils.notifyOrderReady(pushData);
                        await showNotificationModal(pushData, 'push');
                        appendMessage(messageHTML, 'server', null, messageType, pushData.booking_id, pushData.message_id);
                        break;

                    default:
                        console.warn("Unhandled push message type:", messageType);
                }
                dineFlashClientDiag("UI_APPENDED", {
                    message_id: pushData?.message_id,
                    booking_id: pushData?.booking_id,
                    token_no: pushData?.token_no,
                    type: messageType,
                });
                ChatSyncService.registerPushDelivered(pushData);
                } catch (uiErr) {
                    dineFlashClientDiag("UI_APPEND_FAILED", {
                        message_id: pushData?.message_id,
                        booking_id: pushData?.booking_id,
                        token_no: pushData?.token_no,
                        type: messageType,
                        error: (uiErr && (uiErr.message || String(uiErr))) || "unknown",
                    });
                    throw uiErr; // preserve original error propagation
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
            if (
                !isDineFlashBuffetSurface &&
                chatInput.value.length >= 4 &&
                event.key >= "0" &&
                event.key <= "9"
            ) {
                event.preventDefault();  // Only limit when NOT replying
            }

            if (event.key === "Enter") {
                event.preventDefault();
                sendButton.click();
            }
        } else if (isDineFlashBuffetSurface) {
            event.preventDefault();
            appendMessage("Please enter a valid token or bill number (digits only).", "server", null);
        } else if (base === "/food_flash/") {
            event.preventDefault();
            appendMessage("Please enter a valid 4-digit Order No.", "server", null);
        }
    });

    
    // Sanitize input on any indirect changes (e.g. autocomplete)
    chatInput.addEventListener("input", function(event) {
        if (AppUtils.isReplyMode || base === '/airline_flash/') return;

        if (isDineFlashBuffetSurface) {
            const cleanValue = chatInput.value.replace(/[^0-9]/g, "");
            if (chatInput.value !== cleanValue) {
                appendMessage("Only digits (0-9) are allowed for token or bill number.", "server", null);
            }
            chatInput.value = cleanValue;
            return;
        }

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
            }
            else if (base == '/dine_flash/'){
                chatInput.placeholder = "Enter your Booking No...";
            }
            else if (isDineFlashBuffetSurface) {
                chatInput.placeholder = "Enter your token or bill number...";
            }
            else{
                chatInput.placeholder = "Enter your Order No...";
            } 
        }
    });

    if (tokenFromQR && !isOpenedFromPush) {

        const vendorId = await AppUtils.getActiveVendor();

        // Dine Flash / Buffet: load booking + status immediately after redirect
        // (do not wait for permission modal, SW controller, or push subscription).
        let buffetUserTokenShown = false;
        let buffetStatusFetchPromise = null;
        let dineFlashUserBookingShown = false;
        let dineFlashStatusFetchPromise = null;
        if (isDineFlashTableBookingSurface) {
            dineFlashUserBookingShown = true;
            dineFlashStatusFetchPromise = (async () => {
                try {
                    await showChatWindow({});
                    appendMessage(tokenFromQR, "user", "", "chat", bookingIdfromQR);
                    try {
                        await saveChat(tokenFromQR, "user", "chat", bookingIdfromQR);
                    } catch (chatErr) {
                        console.warn("Dine Flash early chat save:", chatErr);
                    }
                    return await fetchOrderStatusOnce(tokenFromQR, null, bookingIdfromQR);
                } catch (err) {
                    console.warn("Dine Flash early chat bootstrap failed:", err);
                    dineFlashStatusFetchPromise = null;
                    dineFlashUserBookingShown = false;
                    return null;
                }
            })();
        }
        if (isDineFlashBuffetSurface) {
            window.buffetQrTokenFromRedirect = String(tokenFromQR);
            // Claim before async work so permission-modal handleToken cannot append again.
            buffetUserTokenShown = true;
            buffetStatusFetchPromise = (async () => {
                try {
                    await showChatWindow({});
                    ChatRestoreService.ensureBuffetQrTokenVisible(String(tokenFromQR));
                    return await fetchOrderStatusOnce(tokenFromQR);
                } catch (err) {
                    console.warn('Buffet early chat bootstrap failed:', err);
                    buffetStatusFetchPromise = null;
                    buffetUserTokenShown = false;
                    return null;
                }
            })();
        }

        // console.log("🔍 QR Scan Detected:", { tokenFromQR, vendorId, permissionStatus });

        // 🔧 Define core flow to handle token setup
        const handleToken = async () => {
            try {
                let displayToken = tokenFromQR;
                const skipBuffetChatDuplicate = isDineFlashBuffetSurface && buffetUserTokenShown;
                const skipDineFlashChatDuplicate = isDineFlashTableBookingSurface && dineFlashUserBookingShown;
                // Apply masking only for airline_flash
                if (!skipBuffetChatDuplicate && !skipDineFlashChatDuplicate) {
                    if (window.BASE && window.BASE.includes('/airline_flash/')) {
                        storedName = await getPassengerName(tokenFromQR);
                        // console.log("Passenger:", storedName);
                        // Append masked token in chat for Airline Flash
                        displayToken = maskSequenceCode(displayToken);
                        appendMessage(displayToken, 'user', "", 'chat',"",storedName);
                    } else if (isDineFlashBuffetSurface) {
                        ChatRestoreService.ensureBuffetQrTokenVisible(String(tokenFromQR));
                    } else {
                        appendMessage(displayToken, 'user', "", 'chat');
                    }
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
                    if (isDineFlashBuffetSurface) {
                        // dine_flash_buffet: guaranteed post-permission subscribe. handleToken runs from
                        // the permission-deferred callback, so permission is granted here (unlike the early
                        // buffetStatusFetchPromise). fetchOrderStatusOnce still links canonical token_no as fallback.
                        await PushSubscriptionService.subscribe(tokenFromQR, vendorId);
                    } else if (window.BASE && window.BASE.includes('/dine_flash/')) {
                        // bookingId = BookingMappingService.getBookingId(tokenFromQR.split("-")[1]);
                        console.info("[dine_flash] handleToken calling subscribe", {
                            booking_id: bookingIdfromQR,
                            booking_no: tokenFromQR,
                            vendor_id: vendorId,
                            notification_permission: Notification.permission,
                            url: window.location?.href,
                        });
                        await PushSubscriptionService.subscribe(bookingIdfromQR, vendorId);
                        // await PushSubscriptionService.subscribe(bookingId, vendorId);
                    } else {
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

                if (isDineFlashBuffetSurface && "serviceWorker" in navigator) {
                    // Non-blocking: chat/status already started; do not delay push setup.
                    void Promise.race([
                        new Promise((resolve) => {
                            if (navigator.serviceWorker.controller) {
                                resolve();
                                return;
                            }
                            navigator.serviceWorker.addEventListener("controllerchange", () => resolve(), {
                                once: true,
                            });
                        }),
                        new Promise((resolve) => setTimeout(resolve, 8000)),
                    ]).catch((swCtlErr) => {
                        console.warn("Buffet: waiting for service worker controller:", swCtlErr);
                    });
                }

                // ✅ Step 3: Save chat log
                try {
                    if (skipBuffetChatDuplicate || skipDineFlashChatDuplicate) {
                        // Saved during early chat bootstrap.
                    } else if (window.BASE && window.BASE.includes('/dine_flash/')) {
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

                const handleTokenPromise = handleToken().catch((err) => {
                    console.error("❌ Error in deferred handleToken flow:", err);
                    appendMessage(
                        "⚠️ Live alerts initialization is taking longer than expected. Status updates will still load.",
                        'server', null, 'error'
                    );
                    return null;
                });

                const fetchStatusTask = (async () => {
                    try {
                        let statusPromise = buffetStatusFetchPromise || dineFlashStatusFetchPromise;
                        if (!statusPromise) {
                            if (window.BASE && window.BASE.includes('/dine_flash/')) {
                                statusPromise = fetchOrderStatusOnce(tokenFromQR, null, bookingIdfromQR);
                            } else {
                                statusPromise = fetchOrderStatusOnce(tokenFromQR);
                            }
                        }
                        check_status = await statusPromise;

                        if (!check_status) {
                            console.warn("⚠️ Could not retrieve order status for token:", tokenFromQR);
                            appendMessage(
                                "⚠️ Couldn’t fetch the latest update right now. Please wait a few seconds or try again manually.",
                                'server', null, 'error'
                            );
                        }
                    } catch (fetchErr) {
                        console.error("❌ Order status fetch failed:", fetchErr);
                        appendMessage(
                            "⚠️ Couldn’t load current status. You’ll still get alerts once updates are available, or you can retry manually.",
                            'server', null, 'error'
                        );
                    }
                })();

                // Buffet + other flavours: push/SW setup in parallel with status fetch.
                await Promise.all([handleTokenPromise, fetchStatusTask]);

                // console.log("🎉 Permission flow and order fetch complete");

            } catch (err) {
                console.error("❌ Error during permission flow:", err);
                appendMessage(
                    "⚠️ A technical issue occurred while initializing. Please re-enter your details and try again.",
                    'server', null, 'error'
                );
            } finally {
                if (isDineFlashBuffetSurface) {
                    delete window.buffetQrTokenFromRedirect;
                }
                if (isDineFlashTableBookingSurface) {
                    delete window.dineFlashBookingFromRedirect;
                }
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
        // Dine Flash only: clear the input immediately after capture so the typed
        // value cannot be re-sent during the saveChat / fetchOrderStatusOnce awaits
        // (prevents the visible lag + accidental double-submit). `message` is already
        // captured above; no Dine Flash path re-reads chatInput.value after this point.
        if (window.BASE && window.BASE.includes('/dine_flash/')) {
            chatInput.value = '';
        }
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
            console.log(" 💬 Selected message has token number:",selectedMessage.dataset.tokenNo)
            const tokenNo = selectedMessage.dataset.tokenNo;
            if (isDineFlashBuffetSurface && !tokenNo) {
                appendMessage(
                    "Please tap Reply on an order status card to message the kitchen.",
                    "server",
                    null
                );
                chatInput.value = "";
                clearReplyMode();
                return;
            }
            if (tokenNo) {
                // This is a reply to a message with tokenNo
                await fetchOrderStatusOnce(tokenNo,message,tokenNo); // Attach token + reply inside this function
            } else {
                console.warn("Selected message has no token number.");
            }
            if (window.BASE && window.BASE.includes('/airline_flash/')) {
                storedName = await getPassengerName(tokenNo);
                appendMessage(message, 'user', "","chat",tokenNo,storedName);
            } else if (isDineFlashBuffetSurface) {
                appendMessage(message, 'user', "", "chat", tokenNo);
            } else {
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
                bookingNo = BookingMappingService.getBookingNo(message);
                bookingId = BookingMappingService.getBookingId(message);
                if (!bookingNo) {
                    appendMessage(message, 'user', null);
                    appendMessage(`Invalid Booking Number. Please check and try again.`, 'server', null);
                    chatInput.value = '';
                    return; // Stop further processing
                }
                console.log("Booking No for display:", bookingNo);
                // ❗ If multiple booking numbers → show selection UI instead
                if (Array.isArray(bookingNo)) {
                    appendChoiceOptions(bookingNo);
                    return;  // << STOP HERE
                }

                // Otherwise continue normally
                appendMessage(bookingNo, 'user', null, "chat", bookingId);
                setActiveDineBookingId(bookingId);
            }

            else if (isDineFlashBuffetSurface) {
                if (!/^[0-9]+$/.test(message)) {
                    appendMessage(
                        "Please enter a valid token or bill number (digits only), or tap Reply on a status card to message the kitchen.",
                        "server",
                        null
                    );
                    chatInput.value = "";
                    return;
                }
                appendMessage(message, "user", "", "chat", message);
                await saveChat(message, "user", "chat", message);
                try {
                    await fetchOrderStatusOnce(message, null, null, { manualEntry: true });
                } finally {
                    // Buffet manual lookup only: clear even when check-status returns 400.
                    chatInput.value = "";
                }
            } else {
                appendMessage(message, 'user', null);
            }
            if (window.BASE && window.BASE.includes('/dine_flash/')) {
                bookingId = BookingMappingService.getBookingId(message); 
                setActiveDineBookingId(bookingId);
                await saveChat(bookingNo, 'user', 'chat',bookingId);
                await fetchOrderStatusOnce(bookingNo, null, bookingId); // Pass booking_id so payload uses it (not booking_no)
            } else if (!isDineFlashBuffetSurface) {
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
        const logoImg = document.createElement("img");
        logoImg.alt = "Vendor Logo";
        logoImg.className = "server-logo";
        hydrateServerLogoElement(logoImg);
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

        bookingList.forEach(item => {

            const trimmed = BookingMappingService.getTrimmedKey(item.booking_no);

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
                setActiveDineBookingId(item.booking_id);
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

    /** Persist QR user token chat only after push subscription exists (avoids 500 on early save). */
    async function persistBuffetQrUserChatIfNeeded(linkToken) {
        const raw = window.buffetQrTokenFromRedirect;
        if (!raw || window.buffetQrUserChatPersisted) return;
        const userToken = String(raw).trim();
        const tokenKey =
            linkToken != null && String(linkToken).trim() !== ""
                ? String(linkToken).trim()
                : userToken;
        if (!userToken) return;
        try {
            await saveChat(userToken, "user", "chat", tokenKey);
            window.buffetQrUserChatPersisted = true;
        } catch (chatErr) {
            console.warn("Buffet user token chat save:", chatErr);
        }
    }

    // -------------------------------------------------------------------------
    // Dine Flash Buffet only — full order-detail snapshot tracking.
    //
    // A "snapshot" = the complete order-details card rendered from a backend lookup.
    // We track which tokens currently have a snapshot on screen so that:
    //   • QR reloads do not duplicate the restored snapshot,
    //   • repeated manual token entry replaces the snapshot instead of stacking copies.
    // Incremental status updates, manager messages and utility pushes are NOT snapshots
    // and never touch this store.
    // -------------------------------------------------------------------------
    function ensureBuffetSnapshotTokenStore() {
        if (!(window.buffetOrderSnapshotTokens instanceof Set)) {
            window.buffetOrderSnapshotTokens = new Set();
        }
        return window.buffetOrderSnapshotTokens;
    }

    function buffetSnapshotExists(tokenKey) {
        if (!tokenKey) return false;
        if (ensureBuffetSnapshotTokenStore().has(tokenKey)) return true;
        const chatContainer = document.getElementById("chat-container");
        return !!(
            chatContainer &&
            chatContainer.querySelector(
                `.message-row.server [data-buffet-snapshot-token="${tokenKey}"]`
            )
        );
    }

    function removeBuffetSnapshot(tokenKey) {
        if (!tokenKey) return;
        const chatContainer = document.getElementById("chat-container");
        if (chatContainer) {
            chatContainer
                .querySelectorAll(`[data-buffet-snapshot-token="${tokenKey}"]`)
                .forEach((node) => {
                    const row = node.closest(".message-row");
                    (row || node).remove();
                });
        }
        ensureBuffetSnapshotTokenStore().delete(tokenKey);
    }

    async function fetchOrderStatusOnce(token, replyText = null, bookingId = null, options = {}) {
        const activeVendor = await AppUtils.getActiveVendor();
        let payload = {};
        let type = '';
        // Decide flavour based on the actual URL path.
        // `window.BASE` is injected by templates and can drift across flavours.
        const path = (window.location && window.location.pathname) ? window.location.pathname : '';
        if (path.includes('/airline_flash/')) {
            payload = { sequence_code: token, vendor_id: activeVendor };
            type = 'flightstatus';
        }
        else if (path.includes('/dine_flash_buffet/')) {
            payload = { token_no: token, vendor_id: activeVendor };
            type = 'buffetstatus';
        }
        else if (path.includes('/dine_flash/')) {
            payload = { booking_id: bookingId || token, vendor_id: activeVendor };
            type = 'dinestatus';
            setActiveDineBookingId(bookingId || token);
        }
        else {
            payload = { token_no: token, vendor_id: activeVendor };
            type = 'foodstatus';
        }
        if (replyText) payload.reply_text = replyText;

        const buffetEarlyPushLink =
            type === "buffetstatus" &&
            ((typeof window.PROJECT_NAME === "string" &&
                window.PROJECT_NAME.trim().toLowerCase() === "dine_flash_buffet") ||
                (path && path.toLowerCase().includes("dine_flash_buffet")));

        let buffetPushLinked = false;

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
            if (type === 'dinestatus' && data?.logo_url) {
                AppUtils.storageSet("activeVendorLogo", String(data.logo_url));
            }

            if (buffetEarlyPushLink && data?.vendor_id != null) {
                const fromResponse = data?.token_no;
                const subscribeToken =
                    fromResponse != null && String(fromResponse).trim() !== ""
                        ? fromResponse
                        : token;
                const resolved =
                    subscribeToken != null && String(subscribeToken).trim() !== ""
                        ? subscribeToken
                        : token;
                if (resolved != null && String(resolved).trim() !== "") {
                    await PushSubscriptionService.subscribe(resolved, data.vendor_id);
                    PushHealthMonitorService.startMonitor(token, data.vendor_id);
                    await AppUtils.setToken(String(resolved));
                    buffetPushLinked = true;
                    await persistBuffetQrUserChatIfNeeded(resolved);
                }
            }
            if (!replyText) {
                if (type === "buffetstatus") {
                    const buffetTokenKey = String(
                        data.token_no != null && String(data.token_no).trim() !== ""
                            ? data.token_no
                            : token
                    ).trim();
                    const snapshotToken =
                        data.token_no != null ? data.token_no : token;
                    const manualEntry = options.manualEntry === true;

                    // Build the full order-detail snapshot as ONE message so it can be
                    // tracked, deduplicated and replaced as a single unit.
                    // `manual_lookup` selects the compact single-row summary renderer;
                    // the auto/QR order-created card keeps the original full renderer.
                    const snapshotPayload = { type: "buffet_order_details", ...data, manual_lookup: manualEntry };
                    const snapshotHtml = ChatTemplateService.build({
                        type: "buffet_order_details",
                        text: snapshotPayload,
                    });

                    const snapshotAlreadyShown = buffetSnapshotExists(buffetTokenKey);
                    dineFlashDiag("fetchOrderStatusOnce buffet snapshot decision", {
                        token: buffetTokenKey,
                        snapshot_already_shown: snapshotAlreadyShown,
                        manual_entry: manualEntry,
                        will_append: manualEntry || !snapshotAlreadyShown,
                        chat_children_before: document.getElementById('chat-container')?.childElementCount,
                        is_restoring_history: Boolean(window.isRestoringHistory),
                    });

                    // Manual valid token entry must ALWAYS show the latest details. If a
                    // snapshot already exists (restored or from an earlier lookup), replace
                    // it in place instead of stacking a duplicate card.
                    // QR / auto flows keep dedup: an already-present snapshot is left as-is.
                    if (manualEntry || !snapshotAlreadyShown) {
                        if (manualEntry) {
                            removeBuffetSnapshot(buffetTokenKey);
                        }
                        appendMessage(
                            snapshotHtml,
                            "server",
                            null,
                            "buffet_order_details",
                            snapshotToken
                        );
                        ensureBuffetSnapshotTokenStore().add(buffetTokenKey);
                        await saveChat(
                            snapshotPayload,
                            "server",
                            "buffet_order_details",
                            snapshotToken
                        );
                    }
                } else {
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
                        dineFlashDiag("fetchOrderStatusOnce APPENDING initial dinestatus card", {
                            booking_id: bookingId,
                            chat_children_before: document.getElementById('chat-container')?.childElementCount,
                            is_restoring_history: Boolean(window.isRestoringHistory),
                        });
                        appendMessage(messageHTML, 'server', null, type, bookingId);
                        await saveChat(data, 'server', type, bookingId);
                    } 
                    else {
                        appendMessage(messageHTML, 'server', null, type, data.token_no);
                        await saveChat(data, 'server', type, data.token_no);
                    }
                }
                await showNotificationModal(data, 'usercheck');
                AppUtils.notifyOrderReady(data);
            }
            if (window.BASE && window.BASE.includes('/dine_flash/')) {
                console.info("[dine_flash] fetchOrderStatusOnce calling subscribe", {
                    booking_id: bookingId,
                    vendor_id: data.vendor_id,
                    notification_permission: Notification.permission,
                });
                await PushSubscriptionService.subscribe(bookingId, data.vendor_id);
                PushHealthMonitorService.startMonitor(bookingId, data.vendor_id);
            }
            else if (!buffetEarlyPushLink || !buffetPushLinked) {
                // Dine Flash Buffet: customers often open the page without QR params, so
                // `tokenFromQR` is empty while `token` / `data.token_no` hold the order token.
                // Linking the push subscription must use that token or web push finds no rows.
                let subscribeToken = tokenFromQR;
                if (type === "buffetstatus") {
                    const fromResponse = data?.token_no;
                    subscribeToken =
                        fromResponse != null && String(fromResponse).trim() !== ""
                            ? fromResponse
                            : token;
                }
                const resolved =
                    subscribeToken != null && String(subscribeToken).trim() !== ""
                        ? subscribeToken
                        : token;
                await PushSubscriptionService.subscribe(resolved, data.vendor_id);
                PushHealthMonitorService.startMonitor(token, data.vendor_id);
                if (type === "buffetstatus" && resolved != null && String(resolved).trim() !== "") {
                    await AppUtils.setToken(String(resolved));
                    await persistBuffetQrUserChatIfNeeded(resolved);
                }
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
        await VendorUIService.ready();
        const vendorId = await AppUtils.getActiveVendor();
        const browser_id = AppUtils.getCurrentBrowserId();

        dineFlashDiag("showChatWindow", {
            vendor_id: vendorId,
            browser_id_present: Boolean(browser_id),
            will_restore: Boolean(browser_id),
            chat_children_current: chatContainer.childElementCount,
        });

        if (!browser_id) {
            console.warn("No browser ID, skipping restore wait.");
        }else {
            await ChatRestoreService.restore(vendorId);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    } 
});
