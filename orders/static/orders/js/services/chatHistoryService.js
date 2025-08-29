// static/js/chatHistoryService.js

export const ChatHistoryService = (() => {
    const MAX_AGE_MINUTES = 120;

    const getKey = (vendorId) => `chat_history_${vendorId}`;

    const save = (vendorId, messages) => {
        const key = getKey(vendorId);
        const data = {
            savedAt: Date.now(),
            messages: messages.map(msg => ({
                text: msg.text,
                sender: msg.sender,
                timestamp: msg.timestamp || Date.now(),
                type:msg.type || null,
                token_no:msg.token_no

            }))
        };
        localStorage.setItem(key, JSON.stringify(data));
    };

    const load = (vendorId) => {
        const key = getKey(vendorId);
        const rawData = localStorage.getItem(key);

        if (!rawData) return [];

        try {
            const data = JSON.parse(rawData);
            const ageInMinutes = (Date.now() - data.savedAt) / 60000;

            if (ageInMinutes > MAX_AGE_MINUTES) {
                localStorage.removeItem(key);
                showSessionExpiredMessage();
                return [];
            }

            return Array.isArray(data.messages) ? data.messages : [];
        } catch (err) {
            console.error("Failed to parse chat history:", err);
            localStorage.removeItem(key);
            return [];
        }
    };

    const clearExpired = () => {
        const keysToRemove = [];

        Object.keys(localStorage).forEach(key => {
            if (key.startsWith("chat_history_")) {
                try {
                    const data = JSON.parse(localStorage.getItem(key));
                    const ageInMinutes = (Date.now() - data.savedAt) / 60000;

                    if (ageInMinutes > MAX_AGE_MINUTES) {
                        keysToRemove.push(key);
                    }
                } catch {
                    keysToRemove.push(key);
                }
            }
        });

        keysToRemove.forEach(key => {
            localStorage.removeItem(key);
        });

        if (keysToRemove.length > 0) {
            showSessionExpiredMessage();
        }
    };

    const showSessionExpiredMessage = () => {
        const chatContainer = document.getElementById("chat-container");
        if (!chatContainer) return;

        const message = `Hi! It looks like your previous <strong>session expired</strong>. Please select an outlet again.`;

        const messageRow = document.createElement("div");
        messageRow.classList.add("message-row", "server");

        const logoImg = document.createElement("img");
        logoImg.src = localStorage.getItem("activeVendorLogo") || "/static/images/default-logo.png";
        logoImg.alt = "Vendor Logo";
        logoImg.className = "server-logo";

        const messageBubble = document.createElement("div");
        messageBubble.classList.add("message-bubble", "server");
        messageBubble.innerHTML = message;

        messageRow.appendChild(logoImg);
        messageRow.appendChild(messageBubble);
        chatContainer.appendChild(messageRow);

        chatContainer.scrollTop = chatContainer.scrollHeight;
    };

    const registerAutoCleanup = () => {
        const clear = () => clearExpired();
        document.addEventListener("DOMContentLoaded", clear);
        window.addEventListener("focus", clear);
    };

    registerAutoCleanup();

    return {
        save,
        load,
        clearExpired
    };
})();
