/**
 * ==========================================================
 * 📘 Vibration Tester Script — Styled & Selection Enabled
 * ==========================================================
 */

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const container = document.getElementById('patternList');
        if (!container) throw new Error('Container element "patternList" not found.');

        const { VIBRATION_PATTERNS } = await import(
            `${window.BASE || '/caller_on/'}static/orders/js/config/vibrationPatterns.js`
        );

        Object.keys(VIBRATION_PATTERNS).forEach(key => {
            const cfg = VIBRATION_PATTERNS[key];

            const item = document.createElement('div');
            item.className = 'pattern-item'; // custom CSS class
            item.textContent = cfg.name;

            // Click handler
            item.onclick = () => {
                // Stop any previous vibration
                VibrationManager.stop();

                // Start selected pattern
                VibrationManager.start(key, cfg.duration);

                // Remove 'selected' from all buttons
                document.querySelectorAll('.pattern-item').forEach(el => {
                    el.classList.remove('selected');
                });

                // Add 'selected' to the clicked item
                item.classList.add('selected');
            };

            container.appendChild(item);
        });

    } catch (err) {
        console.error('❌ Vibration Tester initialization failed:', err);
    }
});
