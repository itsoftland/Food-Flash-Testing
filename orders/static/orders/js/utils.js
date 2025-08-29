import { get as idbGet, set as idbSet } from "https://cdnjs.cloudflare.com/ajax/libs/idb-keyval/6.2.1/index.min.js";
if (window.navigator.standalone) {
    console.log('Running in standalone mode');
}
// Global variable to store unlocked audio
let unlockedNotificationAudio = null;
window.AppUtils = {
    // ─────────────────────────────────────
    // CSRF Token
    // ─────────────────────────────────────
    getCSRFToken: function () {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    },
    // ─────────────────────────────────────
    // Global Chat Flags
    // ─────────────────────────────────────
    isReplyMode: false, // <- this is your global flag
    key: 'activeLocation',
    async get() {
        // 1️⃣ Try localStorage
        let locationId = localStorage.getItem(this.key);
        if (locationId) {
          console.log("[LocationStore] Loaded from localStorage:", locationId);
          return locationId;
        }
    
        // 2️⃣ Try IndexedDB
        try {
          locationId = await idbGet(this.key);
          if (locationId) {
            console.log("[LocationStore] Loaded from IndexedDB:", locationId);
            localStorage.setItem(this.key, locationId); // Rehydrate
            return locationId;
          }
        } catch (e) {
          console.warn("[LocationStore] IndexedDB read failed:", e);
        }
    
        // 3️⃣ Try Cookie (after slight delay for PWA cold boot)
        await new Promise(resolve => setTimeout(resolve, 200));
        locationId = this.getCookie(this.key);
        if (locationId) {
          console.log("[LocationStore] Loaded from Cookie:", locationId);
          localStorage.setItem(this.key, locationId); // Rehydrate
          try { await idbSet(this.key, locationId); } catch {}
          return locationId;
        }
    
        console.warn("[LocationStore] No activeLocation found in any storage.");
        return null;
      },
    async set(locationId) {
    if (!locationId) return;
    console.log("[LocationStore] Setting location:", locationId);

    // 1️⃣ Set in localStorage
    localStorage.setItem(this.key, locationId);

    // 2️⃣ Set in IndexedDB
    try {
        await idbSet(this.key, locationId);
    } catch (e) {
        console.warn("[LocationStore] IndexedDB write failed:", e);
    }

    // 3️⃣ Set in cookie
    this.setCookie(this.key, locationId);
    },

    setCookie(name, value, days = 365) {
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = `${name}=${encodeURIComponent(value)}; path=/; expires=${expires}; SameSite=Lax`;
    },

    getCookie(name) {
    const cookieStr = `; ${document.cookie}`;
    const parts = cookieStr.split(`; ${name}=`);
    if (parts.length >= 2) {
        return decodeURIComponent(parts.pop().split(';')[0]);
    }
    return null;
    },

    // ─────────────────────────────────────
    // Vendor Helpers
    // ─────────────────────────────────────
    getStoredVendors: function () {
        const storedVendors = localStorage.getItem('selectedVendors');
        return storedVendors ? JSON.parse(storedVendors) : [];
    },
    setSelectedOutletName: function (name) {
        localStorage.setItem('selectedOutletName', name);
    },

    getSelectedOutletName: function () {
        const outletName = localStorage.getItem('selectedOutletName');
        return outletName ? outletName : null;
    },
    setCurrentVendors: async function (vendorInput) {
        let newVendors = [];

        if (typeof vendorInput === 'string') {
            newVendors = vendorInput.split(',').map(v => parseInt(v.trim(), 10));
        } else if (Array.isArray(vendorInput)) {
            newVendors = vendorInput.map(v => parseInt(v, 10));
        }

        const updatedList = Array.from(new Set(newVendors));
        const lastVendor = updatedList[updatedList.length - 1];

        // Store in localStorage
        localStorage.setItem('selectedVendors', JSON.stringify(updatedList));
        if (lastVendor) {
            localStorage.setItem('activeVendor', lastVendor);
        }

        // Store in IndexedDB
        try {
            await idbSet('selectedVendors', updatedList);
            if (lastVendor) {
                await idbSet('activeVendor', lastVendor);
            }
        } catch (e) {
            console.warn("[VendorStore] Failed to write to IndexedDB:", e);
        }

        // Store in cookies
        this.setCookie('selectedVendors', JSON.stringify(updatedList));
        if (lastVendor) {
            this.setCookie('activeVendor', lastVendor);
        }

        console.log("[VendorStore] Vendors set successfully:", updatedList);
    },
    getActiveVendor: async function () {
        let vendorId = localStorage.getItem('activeVendor');
        if (vendorId) {
            console.log("[VendorStore] Loaded from localStorage:", vendorId);
            return parseInt(vendorId, 10);
        }

        try {
            vendorId = await idbGet('activeVendor');
            if (vendorId) {
                console.log("[VendorStore] Loaded from IndexedDB:", vendorId);
                localStorage.setItem('activeVendor', vendorId);
                return parseInt(vendorId, 10);
            }
        } catch (e) {
            console.warn("[VendorStore] IndexedDB read failed:", e);
        }

        await new Promise(resolve => setTimeout(resolve, 200));
        vendorId = this.getCookie('activeVendor');
        if (vendorId) {
            console.log("[VendorStore] Loaded from Cookie:", vendorId);
            localStorage.setItem('activeVendor', vendorId);
            try { await idbSet('activeVendor', vendorId); } catch {}
            return parseInt(vendorId, 10);
        }

        console.warn("[VendorStore] No activeVendor found.");
        return null;
    },

    appendVendorIfNotExists: async function (vendorId) {
        let selectedVendors = JSON.parse(localStorage.getItem('selectedVendors')) || [];
        selectedVendors.push(vendorId);

        const updatedList = Array.from(new Set(selectedVendors));
        localStorage.setItem('selectedVendors', JSON.stringify(updatedList));
        localStorage.setItem('activeVendor', updatedList[updatedList.length - 1]);

        try {
            await idbSet('selectedVendors', updatedList);
            await idbSet('activeVendor', updatedList[updatedList.length - 1]);
        } catch (e) {
            console.warn("[VendorStore] IndexedDB write failed:", e);
        }

        this.setCookie('selectedVendors', JSON.stringify(updatedList));
        this.setCookie('activeVendor', updatedList[updatedList.length - 1]);
    },
    // ─────────────────────────────────────
    // Token Management
    // ─────────────────────────────────────
    getToken: async function () {
        let token = localStorage.getItem('token');
        if (token) {
            console.log("[TokenStore] Loaded from localStorage:", token);
            return token;
        }

        try {
            token = await idbGet('token');
            if (token) {
                console.log("[TokenStore] Loaded from IndexedDB:", token);
                localStorage.setItem('token', token);
                return token;
            }
        } catch (e) {
            console.warn("[TokenStore] IndexedDB read failed:", e);
        }

        await new Promise(resolve => setTimeout(resolve, 200));
        token = this.getCookie('token');
        if (token) {
            console.log("[TokenStore] Loaded from Cookie:", token);
            localStorage.setItem('token', token);
            try { await idbSet('token', token); } catch {}
            return token;
        }

        console.warn("[TokenStore] No token found.");
        return null;
    },

    setToken: async function (token) {
        if (!token) return;
        console.log("[TokenStore] Setting token:", token);

        localStorage.setItem('token', token);
        try { await idbSet('token', token); } catch (e) {
            console.warn("[TokenStore] IndexedDB write failed:", e);
        }
        this.setCookie('token', token);
    },
    // ─────────────────────────────────────
    // Notification Sound
    // ─────────────────────────────────────
    // ============================================
    // Unlock Notification Sound + Preferred Voice (iOS + Android)
    // ============================================
    unlockNotificationSound: async function () {
        console.log("[Unlock] Unlocking notification sound and TTS...");

        // 🔊 Unlock notification sound
        unlockedNotificationAudio = new Audio('/static/orders/audio/0112.mp3');
        unlockedNotificationAudio.volume = 1.0;
        unlockedNotificationAudio.muted = false;
        unlockedNotificationAudio.playsInline = true;

        unlockedNotificationAudio.play().then(() => {
            unlockedNotificationAudio.pause();
            unlockedNotificationAudio.currentTime = 0;
            console.log('🔓 Notification sound unlocked.');
        }).catch(err => {
            console.warn('🔇 Sound unlock failed:', err);
        });

        // 🗣 Unlock speech synthesis
        try {
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
            const isAndroid = /Android/i.test(navigator.userAgent);

            const iosPreferredNames = ["Samantha", "Karen", "Moira"];
            const androidPreferredNames = ["Assamese India", "Google US English", "English (United States)"];

            let voices = window.speechSynthesis.getVoices();

            // ✅ Wait for voices to load only on Android if none yet
            if (isAndroid && voices.length === 0) {
                console.log("[TTS] Waiting for voices to load on Android...");
                voices = await new Promise(resolve => {
                    window.speechSynthesis.onvoiceschanged = () => {
                        const loadedVoices = window.speechSynthesis.getVoices();
                        if (loadedVoices.length) {
                            console.log(`[TTS] Voices loaded: ${loadedVoices.length}`);
                            resolve(loadedVoices);
                        }
                    };
                });
            }

            // 1️⃣ Try platform preferred names first
            let preferredVoice = voices.find(v =>
                v.lang.startsWith("en") &&
                (isIOS
                    ? iosPreferredNames.includes(v.name)
                    : androidPreferredNames.includes(v.name))
            );

            // 2️⃣ If no match, try any English female voice
            if (!preferredVoice) {
                preferredVoice = voices.find(v =>
                    v.lang.startsWith("en") &&
                    (/female/i.test(v.name) ||
                    /(Karen|Samantha|Moira)/i.test(v.name) ||
                    /Google.*English.*Female/i.test(v.name))
                );
            }

            // 3️⃣ If no match, try any English voice
            if (!preferredVoice) {
                preferredVoice = voices.find(v => v.lang.startsWith("en"));
            }

            // 4️⃣ If still no match, fallback to first available
            if (!preferredVoice) {
                preferredVoice = voices[0];
            }

            console.log(`[TTS] Unlocking with preferred voice: ${preferredVoice?.name || "default"}`);

            // Unlock utterance (silent but valid speech)
            const unlockUtterance = new SpeechSynthesisUtterance("Voice ready");
            unlockUtterance.voice = preferredVoice;
            unlockUtterance.volume = 0; // Silent but still counts
            window.speechSynthesis.speak(unlockUtterance);

            console.log("🔓 Speech synthesis unlocked and preferred voice preloaded.");
        } catch (e) {
            console.warn("🔇 Speech synthesis unlock failed:", e);
        }
    },


    // Use this in your existing method
    playNotificationSound : function (volume = 1.0) {
        if (unlockedNotificationAudio) {
            unlockedNotificationAudio.volume = Math.max(0, Math.min(volume, 1));
            unlockedNotificationAudio.currentTime = 0;
            unlockedNotificationAudio.play().catch(err =>
                console.error('Error playing notification sound:', err)
            );
        } else {
            console.warn('🔕 Notification sound is not unlocked yet.');
        }

        // Vibration if supported
        if (navigator.vibrate) {
            console.log('🔔 Vibration triggered.');
            navigator.vibrate([500, 200, 500, 200, 500, 200, 500]);
        }
    },
    playWelcomeMessage :function(){
        const welcome = new SpeechSynthesisUtterance('Hi, Welcome. Please enter your token number to track your order.');
        speechSynthesis.speak(welcome);
    },
    // ─────────────────────────────────────
    // Viewport Utility
    // ─────────────────────────────────────
    adjustChatResponsePadding: function () {
        const chatResponse = document.querySelector('.chat-response');
        const chatFooter = document.querySelector('.chat-footer');
        const premiumFooter = document.querySelector('.premium-footer');
    
        if (!chatResponse) return;
    
        const chatFooterHeight = chatFooter?.offsetHeight || 0;
        const premiumFooterHeight = premiumFooter?.offsetHeight || 0;
    
        const viewportHeight = window.visualViewport?.height || window.innerHeight;
        const keyboardOffset = window.innerHeight - viewportHeight;
    
        const totalBottomOffset = chatFooterHeight + premiumFooterHeight + keyboardOffset;
    
        chatResponse.style.paddingBottom = `${totalBottomOffset}px`; // Add safe spacing
    
        // Optional: Dynamically limit height if needed
        const topOffset = 120; // Same as your padding-top
        const calculatedHeight = viewportHeight - chatFooterHeight - premiumFooterHeight - 20;
        chatResponse.style.maxHeight = `${calculatedHeight}px`;
    },
    initPaddingAdjustmentListeners: function () {
        const self = this;
        const adjust = () => self.adjustChatResponsePadding();
    
        window.addEventListener('load', adjust);
        window.addEventListener('resize', adjust);
        window.visualViewport?.addEventListener('resize', adjust);
        window.addEventListener('focusin', adjust);
        window.addEventListener('focusout', adjust);
    },

    showToast: function(message) {
        const toast = document.getElementById('customToast');
        toast.textContent = message;
        toast.classList.add('show');
        setTimeout(() => {
          toast.classList.remove('show');
        }, 3000); // 3 seconds
    },
    // ─────────────────────────────────────
    // Notification State (Persistent)
    // ─────────────────────────────────────
    notificationStorageKey: "notification_order_states",

    saveOrderStates: function (orderStates) {
        try {
            localStorage.setItem(this.notificationStorageKey, JSON.stringify(orderStates));
        } catch (e) {
            console.error("Failed to save orderStates to storage", e);
        }
    },

    loadOrderStates: function () {
        try {
            const stored = localStorage.getItem(this.notificationStorageKey);
            return stored ? JSON.parse(stored) : {};
        } catch (e) {
            console.error("Failed to load orderStates from storage", e);
            return {};
        }
    },
    // ============================================
    // Unlock Notification Sound + Preferred Voice (iOS + Android)
    // ============================================
    notifyOrderReady: function(pushData) {
        try {
            console.log(`[TTS] Speaking order ready message: Order ${pushData.token_no} - Counter ${pushData.counter_no}`);
            const synth = window.speechSynthesis;
            let message;
            if (pushData.status === 'ready') {
                message = `Your order number ${pushData.token_no} is ready at counter ${pushData.counter_no}. Please collect it.`;
            } else if (pushData.status === 'cancelled') {
                message = `Unfortunately, your order number ${pushData.token_no} has been cancelled.`;
            } else if (pushData.status === 'delivered') {
                message = `Your order number ${pushData.token_no} has been delivered. Thank you for choosing us.`;
            } else if (pushData.status === 'preparing') {
                message = `Your order number ${pushData.token_no} is currently being prepared. Please wait while we finish it.`;
            }
            else {
                message = `Your order number ${pushData.token_no} has a new update. Please check the app for details.`;
            }

            console.log(`[TTS] Message to speak: ${message}`);
            const utterance = new SpeechSynthesisUtterance(message);

            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
            const iosPreferredNames = ["Samantha", "Karen", "Moira"];
            const androidPreferredNames = ["Google US English", "English (United States)"];

            const voices = synth.getVoices();
            console.log(`[TTS] Voices available: ${voices.length}`);

            const preferredVoice = voices.find(v =>
                v.lang.startsWith("en") &&
                (isIOS
                    ? iosPreferredNames.includes(v.name)
                    : androidPreferredNames.includes(v.name))
            ) || voices[0]; // fallback

            if (preferredVoice) {
                utterance.voice = preferredVoice;
                console.log(`[TTS] Using preferred voice: ${preferredVoice.name}`);
            } else {
                console.log("[TTS] Using default system voice.");
            }

            utterance.pitch = 1;
            utterance.rate = 1;
            utterance.volume = 1;

            synth.cancel();
            synth.speak(utterance);

        } catch (e) {
            console.error("[TTS] Failed to notify order readiness:", e);
        }
    },
    // ─────────────────────────────────────,

    /**
         * Convert a base64 VAPID public key to a Uint8Array
         * for use with the PushManager.subscribe() method.
         */
    urlBase64ToUint8Array: function (base64String) {
        const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    },

    /**
     * Get or generate a unique browser identifier.
     * Stores and retrieves it from localStorage.
     */
    getBrowserId: function () {
        let browserId = localStorage.getItem('browser_id');
        if (!browserId) {
            browserId = crypto.randomUUID();
            localStorage.setItem('browser_id', browserId);
        }
        return browserId;
    },
    // ─────────────────────────────────────
    // Device Detection
    // ─────────────────────────────────────
    getDeviceName: function () {
        const ua = navigator.userAgent;
        let deviceName = '';

        const isMobile = {
            Android: () => /Android/i.test(ua),
            iOS: () => /iPhone|iPad|iPod/i.test(ua),
            Windows: () => /IEMobile/i.test(ua),
            Zebra: () => /TC70|TC55/i.test(ua),
            Datalogic: () => /DL-AXIS/i.test(ua),
            Bluebird: () => /EF500/i.test(ua),
            Honeywell: () => /CT50/i.test(ua),
            BlackBerry: () => /BlackBerry/i.test(ua),
            any: function () {
                return (
                    this.Android() || this.iOS() || this.Windows() ||
                    this.Zebra() || this.Datalogic() || this.Bluebird() ||
                    this.Honeywell() || this.BlackBerry()
                );
            }
        };

        if (isMobile.Zebra()) deviceName = 'Zebra';
        else if (isMobile.Datalogic()) deviceName = 'Datalogic';
        else if (isMobile.Bluebird()) deviceName = 'Bluebird';
        else if (isMobile.Honeywell()) deviceName = 'Honeywell';
        else if (isMobile.BlackBerry()) deviceName = 'BlackBerry';
        else if (isMobile.iOS()) deviceName = 'iOS';
        else if (isMobile.Android()) {
            const match = ua.match(/\((?:Linux; )?Android [^;]+; ([^)]+)\)/);
            if (match && match[1]) {
                deviceName = match[1].trim(); // Example: "Redmi Note 10", "SM-G991B"
            } else {
                deviceName = 'Android';
            }
        } else if (isMobile.Windows()) {
            deviceName = 'Windows';
        }

        console.log('Device Name:', deviceName);
        return deviceName;
    },
    getNotificationHelpPath: function () {
        const model = this.getDeviceName();

        if (/Samsung|SM-/i.test(model)) {
            return "Settings > Apps > Your App > Notifications";
        } else if (/Redmi|Mi|Xiaomi/i.test(model)) {
            return "Settings > Notifications > Manage Notifications > Your App";
        } else if (/Vivo/i.test(model)) {
            return "Settings > Notifications and status bar > Notification management";
        } else if (/Realme/i.test(model)) {
            return "Settings > App Management > Your App > Notifications";
        } else if (/Oppo/i.test(model)) {
            return "Settings > App Management > Your App > Notification management";
        } else if (/iPhone|iPad/i.test(model)) {
            return "Settings > Notifications > Your App";
        }

        return "Please check device Settings > Apps > Your App > Notifications";
    },

    warnBackgroundRestrictions: function () {
        const model = this.getDeviceName();

        if (/Redmi|Mi|Xiaomi/i.test(model)) {
            this.showToast("Set 'Battery Saver' to 'No restrictions' for this app under Battery & Performance.");
        } else if (/Vivo|Oppo|Realme/i.test(model)) {
            this.showToast("Enable 'Auto Start' and allow background activity for this app in system settings.");
        }
    },

    openBrowserNotificationSettings: function () {
        this.showToast("To enable notifications, go to your browser > Site Settings > Notifications.");
    },


};

