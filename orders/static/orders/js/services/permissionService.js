export const PermissionService = (() => {

    const showModal = () => {
        const modalElement = document.getElementById("permissionModal");
        if (!localStorage.getItem("permissionStatus") && modalElement) {
            const bsModal = new bootstrap.Modal(modalElement, {
                backdrop: 'static',
                keyboard: false
            });
            bsModal.show();
        }
    };

    const requestPermissions = async () => {
        const current = Notification.permission;
        console.log("Current notification permission:", current);
        if (current === "granted") {
                return true;
            }

        if (current === "default") {
            const permission = await Notification.requestPermission();
            if (permission === "granted") {
                return true;
            } else {
                return false;
            }
        }
        if (current === "denied") {
            showDeniedModal();
            return false;
        }

        
    };

    const showDeniedModal = () => {
        const helpModal = document.getElementById("notificationHelpModal");
        if (helpModal) {
            const bsHelpModal = new bootstrap.Modal(helpModal, {
                backdrop: 'static',
                keyboard: true
            });
            bsHelpModal.show();
        } else {
            AppUtils.showToast("You won’t receive real-time notifications unless enabled manually from browser settings");
        }
    };
    let deferredCallback = null; // internal module-level variable

    const setDeferredCallback = (callback) => {
        deferredCallback = callback;
    };

    const handleAgree = async () => {
        localStorage.setItem("permissionStatus", "granted");
        await AppUtils.unlockNotificationSound();  // safe time to preload and unlock
        // Hide the modal after granting permission
        bootstrap.Modal.getInstance(document.getElementById("permissionModal"))?.hide();

        const granted = await requestPermissions();

        if (granted) {
            AppUtils.showToast("Notifications enabled");
            if (typeof deferredCallback === "function") {
                await deferredCallback();  // ✅ Run deferred logic
                deferredCallback = null;
            }
            
        }
    };


    // const handleAgree = () => {
    //     localStorage.setItem("permissionStatus", "granted");
    //     bootstrap.Modal.getInstance(document.getElementById("permissionModal"))?.hide();
    //     requestPermissions();
    //     playWelcomeMessage();
    // };

    const handleDeny = () => {
        localStorage.setItem("permissionStatus", "denied");
        bootstrap.Modal.getInstance(document.getElementById("permissionModal"))?.hide();
        showDeniedModal();
    };

    const bindEvents = () => {
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
