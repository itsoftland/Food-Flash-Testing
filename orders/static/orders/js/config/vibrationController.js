// vibrationController.js

const VibrationManager = (function () {

    let vibrationInterval = null;
    let vibrationTimeout = null;

    
    // Load patterns dynamically
    import(`./vibrationPatterns.js`)
        .then(module => {
            VIBRATION_PATTERNS = module.VIBRATION_PATTERNS;
            // console.log("Vibration patterns loaded:", VIBRATION_PATTERNS);
        })
        .catch(err => console.error("Failed to load vibration patterns:", err));


    function isSupported() {
        return !!navigator.vibrate;
    }

    /**
     * Start vibrating
     * @param {string} patternKey - name of the vibration pattern
     * @param {number} durationSec - total vibration time in seconds (9999 = infinite)
     * @param {number} repeatEvery - interval between vibration loops in ms
     */
    function start(patternKey, durationSec = null, repeatEvery = 1000) {

        stop(); // Clear any previous running vibration

        if (!isSupported()) {
            AppUtils.showToast("Vibration not supported");
            console.warn("Vibration API not supported on this device.");
            return;
        }

        const config = VIBRATION_PATTERNS[patternKey];
        if (!config) {
            console.error("Invalid vibration pattern key:", patternKey);
            return;
        }

        const pattern = config.pattern;

        // Convert infinite marker
        if (durationSec === 9999) {
            durationSec = null; // signal infinite vibration
        }

        // First immediate vibration
        navigator.vibrate(pattern);

        // ---- INFINITE MODE ----
        if (durationSec === null) {
            vibrationInterval = setInterval(() => {
                navigator.vibrate(pattern);
            }, repeatEvery);
            return;
        }

        // ---- FIXED DURATION MODE ----
        vibrationInterval = setInterval(() => {
            navigator.vibrate(pattern);
        }, repeatEvery);

        // Auto-stop after duration
        vibrationTimeout = setTimeout(() => {
            stop();
        }, durationSec * 1000);
    }

    /** Stop all vibrations */
    function stop() {
        if (!isSupported()) return;

        // Clear interval
        if (vibrationInterval) {
            clearInterval(vibrationInterval);
            vibrationInterval = null;
        }

        // Clear auto-stop timeout
        if (vibrationTimeout) {
            clearTimeout(vibrationTimeout);
            vibrationTimeout = null;
        }

        // Stop immediately
        navigator.vibrate(0);
    }

    return { start, stop };

})();
