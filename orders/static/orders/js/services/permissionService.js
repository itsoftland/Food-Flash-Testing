// orders/static/orders/js/services/PermissionService.js
export const PermissionService = (() => {

    /** Options set via init(); only Dine Flash enables dineFlashFastPermissionUX. */
    let flowOptions = { dineFlashFastPermissionUX: false };

    const showModal = (forceShow = false) => {
        const modalElement = document.getElementById("permissionModal");

        if (modalElement && (forceShow || !localStorage.getItem("permissionStatus"))) {
            // console.log("🟢 [PermissionService] Showing permission modal (force:", forceShow, ")");
            const bsModal = new bootstrap.Modal(modalElement, {
                backdrop: 'static',
                keyboard: false
            });
            bsModal.show();
        } else {
            // console.log("⚪ [PermissionService] Modal not shown. Condition:", {
            // modalExists: !!modalElement,
            // hasPermissionStatus: !!localStorage.getItem("permissionStatus")
            // });
        }
    };


    const cleanupBackdrop = () => {
        // Remove any leftover modal backdrops (Bootstrap sometimes fails if async unlock happens fast)
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach(b => {
            b.classList.remove('show');
            b.remove();
        });
        document.body.classList.remove('modal-open');
        document.body.style.overflow = ''; // restore scroll
    };

    const requestPermissions = async () => {
        const current = Notification.permission;
        // console.log(`🔔 [PermissionService] Current permission: ${current}`);

        if (current === "granted") return true;

        if (current === "default") {
            const permission = await Notification.requestPermission();
            // console.log("🔔 [PermissionService] User response:", permission);
            return permission === "granted";
        }

        if (current === "denied") {
            showDeniedModal();
            return false;
        }
    };

    const showDeniedModal = () => {
        const helpModal = document.getElementById("notificationHelpModal");
        if (helpModal) {
            // console.log("🚫 [PermissionService] Showing denied modal");
            const bsHelpModal = new bootstrap.Modal(helpModal, {
                backdrop: 'static',
                keyboard: true
            });
            bsHelpModal.show();
        } else {
            AppUtils.showToast("You won’t receive real-time notifications unless enabled manually from browser settings");
        }
    };

    let deferredCallback = null;

    const setDeferredCallback = (callback) => {
        deferredCallback = callback;
        // console.log("🧩 [PermissionService] Deferred callback set.");
    };

    const finalizeAgreeGranted = async (granted, logDenyReason) => {
        if (granted) {
            if (
                typeof window !== "undefined" &&
                window.BASE?.includes("/dine_flash/") &&
                !window.BASE?.includes("/dine_flash_buffet/")
            ) {
                const dineFlashBootstrap =
                    window.DINE_FLASH_TRACKING_BOOTSTRAP &&
                    typeof window.DINE_FLASH_TRACKING_BOOTSTRAP === "object"
                        ? window.DINE_FLASH_TRACKING_BOOTSTRAP
                        : null;
                console.info("[dine_flash] notification permission granted", {
                    booking_id: dineFlashBootstrap?.booking_id ?? new URLSearchParams(window.location.search).get("booking_id"),
                    booking_no:
                        dineFlashBootstrap?.booking_no ??
                        new URLSearchParams(window.location.search).get("booking_no"),
                    browser_id: AppUtils.storageGet("browser_id") || null,
                    notification_permission: Notification.permission,
                    url: window.location?.href,
                });
            }
            AppUtils.showToast("Notifications enabled");
            if (typeof deferredCallback === "function") {
                await deferredCallback();
                deferredCallback = null;
            }
        } else if (logDenyReason) {
            console.warn("⚠️ [PermissionService] Permission request denied by user or browser.");
        }
    };

    let isAgreeInProgress = false;

    const resetGrantButtonVisualState = (btn) => {
        if (!btn) return;
        btn.blur();
        btn.disabled = false;
        btn.style.pointerEvents = "";
    };

    /** Notification API is absent in some browsers (e.g. iOS Safari non-PWA tab). */
    const isNotificationSupported = () =>
        typeof Notification !== "undefined" &&
        typeof Notification.requestPermission === "function";

    /** Hotfix scope: Dine Flash booking page only (excludes Buffet, Home, other flavours). */
    const isDineFlashBookingPage = () =>
        String(window.PROJECT_NAME || "").toLowerCase() === "dine_flash" &&
        String(window.location?.pathname || "").toLowerCase().includes("/table_booking/");

    const waitForPermissionWithTimeout = async (permissionPromise, timeoutMs = 2500) => {
        if (!permissionPromise) return null;
        const timeoutResult = "__permission_timeout__";
        const result = await Promise.race([
            permissionPromise,
            new Promise((resolve) => setTimeout(() => resolve(timeoutResult), timeoutMs)),
        ]);
        if (result === timeoutResult) {
            return null;
        }
        return result;
    };

    const handleAgree = async () => {
        if (isAgreeInProgress) return;
        isAgreeInProgress = true;
        // console.log("👍 [PermissionService] User agreed to enable notifications.");
        localStorage.setItem("permissionStatus", "granted");

        const fast = flowOptions.dineFlashFastPermissionUX === true;
        const permissionModalEl = document.getElementById("permissionModal");
        const bsModalInstance = bootstrap.Modal.getInstance(permissionModalEl);
        const grantBtn = document.getElementById("grant-permission");

        // Immediately clear pressed/active state before any async prompt appears.
        // This avoids the sticky "selected/loading" visual if user taps quickly.
        if (grantBtn) {
            grantBtn.blur();
            grantBtn.disabled = true;
            grantBtn.style.pointerEvents = "none";
        }

        try {
            if (!fast) {
                await AppUtils.unlockNotificationSound();
                bsModalInstance?.hide();
                cleanupBackdrop();
                const granted = await requestPermissions();
                await finalizeAgreeGranted(granted, true);
                return;
            }

            // Dine Flash booking page on a browser without the Notification API
            // (e.g. iOS Safari non-PWA tab) would otherwise throw a ReferenceError
            // here. Close the modal, still unlock sound, and skip notification work.
            if (isDineFlashBookingPage() && !isNotificationSupported()) {
                bsModalInstance?.hide();
                cleanupBackdrop();
                queueMicrotask(() => {
                    void AppUtils.unlockNotificationSound();
                });
                await finalizeAgreeGranted(false, false);
                return;
            }

            const currentPerm = Notification.permission;

            /** Native prompt must run with almost no preceding work so the gesture chain stays “hot”. */
            let permissionPromise = null;
            if (currentPerm === "default") {
                permissionPromise = Notification.requestPermission();
            }

            bsModalInstance?.hide();
            cleanupBackdrop();

            queueMicrotask(() => {
                void AppUtils.unlockNotificationSound();
            });

            let granted = false;
            if (currentPerm === "granted") {
                granted = true;
            } else if (currentPerm === "default" && permissionPromise) {
                const result = await waitForPermissionWithTimeout(permissionPromise, 2500);
                if (result === "granted") {
                    granted = true;
                } else if (result === "denied") {
                    showDeniedModal();
                } else {
                    // Some browsers may keep the permission promise unresolved for a long time.
                    // Don't keep the UI in a blocked state; proceed and rely on future checks.
                    granted = Notification.permission === "granted";
                }
            } else if (currentPerm === "denied") {
                showDeniedModal();
            }

            await finalizeAgreeGranted(
                granted,
                currentPerm === "default",
            );
        } finally {
            resetGrantButtonVisualState(grantBtn);
            isAgreeInProgress = false;
        }
    };

    const handleDeny = () => {
        // console.log("❌ [PermissionService] User denied permission.");
        localStorage.setItem("permissionStatus", "denied");
        const modal = bootstrap.Modal.getInstance(document.getElementById("permissionModal"));
        modal?.hide();
        cleanupBackdrop();
        showDeniedModal();
    };

    const bindEvents = (options = {}) => {
        flowOptions = {
            dineFlashFastPermissionUX: false,
            ...options,
        };
        // console.log("⚙️ [PermissionService] Binding button events...");
        document.getElementById("grant-permission")?.addEventListener("click", handleAgree);
        document.getElementById("deny-permission")?.addEventListener("click", handleDeny);
    };

    return {
        init: bindEvents,
        showModal,
        requestPermissions,
        setDeferredCallback
    };
})();
