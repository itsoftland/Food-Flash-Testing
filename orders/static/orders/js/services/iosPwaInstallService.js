export const IosPwaInstallService = (() => {
    let modalInstance = null;

    const isIosSafari = () => {
        const ua = window.navigator.userAgent.toLowerCase();
        const isIos = /iphone|ipad|ipod/.test(ua);
        const isSafari = /^((?!chrome|android).)*safari/i.test(window.navigator.userAgent);
        return isIos && isSafari;
    };

    const isInStandaloneMode = () => {
        return ('standalone' in window.navigator) && window.navigator.standalone;
    };

    const hasAgreed = () => localStorage.getItem("iosA2HS") === "true";
    const hasDenied = () => localStorage.getItem("iosA2HS") === "false";

    const shouldShowPrompt = () => {
        return !(hasAgreed() || hasDenied());
    };
    const shouldRePrompt = () => {
        return hasAgreed() && !isInStandaloneMode();
    };

    const showModal = () => {
        const modalEl = document.getElementById("iosInstallModal");
        if (modalEl && !modalInstance) {
            modalInstance = new bootstrap.Modal(modalEl, {
                backdrop: 'static',
                keyboard: false
            });
        }
        modalInstance?.show();
    };

    const dismiss = () => {
        modalInstance?.hide();
    };

    const init = () => {
        const standalone = isInStandaloneMode();
        const prompt = shouldShowPrompt();

        if (isIosSafari() && !standalone && prompt) {
            showModal();
        }
    };

    return {
        init,
        showModal,
        dismiss,
        hasAgreed,
        hasDenied,
        isInStandaloneMode,
        shouldRePrompt
    };
})();
