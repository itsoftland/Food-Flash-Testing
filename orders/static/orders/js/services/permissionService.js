// orders/static/orders/js/services/PermissionService.js
export const PermissionService = (() => {

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

    const handleAgree = async () => {
        // console.log("👍 [PermissionService] User agreed to enable notifications.");
        localStorage.setItem("permissionStatus", "granted");

        await AppUtils.unlockNotificationSound();
        // console.log("🔊 [PermissionService] Notification sound unlocked.");

        const modal = bootstrap.Modal.getInstance(document.getElementById("permissionModal"));
        modal?.hide();

        // Force cleanup in case Bootstrap doesn't remove backdrop
        cleanupBackdrop();

        const granted = await requestPermissions();

        if (granted) {
            AppUtils.showToast("Notifications enabled");
            // console.log("✅ [PermissionService] Permission granted, executing deferred callback...");
            if (typeof deferredCallback === "function") {
                await deferredCallback();
                deferredCallback = null;
            }
        } else {
            console.warn("⚠️ [PermissionService] Permission request denied by user or browser.");
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

    const bindEvents = () => {
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
