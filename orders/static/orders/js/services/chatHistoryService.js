// static/js/chatHistoryService.js
import { ChatTemplateService } from "./chatTemplateService.js";

export const ChatHistoryService = (() => {
    /**
     * Fetch all messages for a vendor from the backend.
     * @param {number} vendorId 
     * @param {string} browserId
     * @returns {Promise<Array>}
     */
    const load = async (vendorId, browserId) => {
        console.trace("ChatHistoryService.load invoked");
        try {
            const response = await fetch(
                `/food_flash/api/webchat-messages/?vendor_id=${vendorId}&browser_id=${browserId}`, 
                {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                }
            );
            if (!response.ok) throw new Error("Failed to fetch chat messages");

            const data = await response.json();
            console.log("ChatHistoryService load data:", data);

            if (!data || !Array.isArray(data.messages)) {
                console.warn("Unexpected response format:", data);
                return [];
            }

            console.log("ChatHistoryService loaded messages:", data.messages.length);

            return data.messages.map(msg => {
                const rendered = ChatTemplateService.build(msg);

                return {
                    ...msg, // keep raw info (sender, type, token_no, etc.)
                    rendered, // ✅ HTML (or plain text for user messages)
                    timestamp: msg.timestamp
                        ? new Date(msg.timestamp).toLocaleTimeString([], { 
                            hour: '2-digit', 
                            minute: '2-digit', 
                            hour12: true 
                          })
                        : ""
                };
            });
        } catch (err) {
            console.error("ChatHistoryService load error:", err);
            return [];
        }
    };

    /**
     * Save a single message to the backend.
     */
    const save = async ({ vendorId, browser_id, sender, type, text, token_no }) => {
        try {
            const response = await fetch('/food_flash/api/webchat-messages-create/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken(),
                },
                body: JSON.stringify({
                    vendor: vendorId,
                    browser_id,
                    sender,
                    type,
                    text,
                    token_no
                })
            });

            if (!response.ok) throw new Error("Failed to save chat message");

            return await response.json();
        } catch (err) {
            console.error("ChatHistoryService save error:", err);
            return null;
        }
    };

    const markAsRead = async (vendorId) => {
        try {
            const response = await fetch(`/food_flash/api/mark-messages-read/${vendorId}/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCSRFToken() }
            });

            if (!response.ok) {
                console.warn(`Failed to mark messages as read for vendor ${vendorId}`);
            }
        } catch (err) {
            console.error("Failed to mark messages as read:", err);
        }
    };

    const getCSRFToken = () => {
        return document.cookie
            .split(';')
            .find(c => c.trim().startsWith('csrftoken='))?.split('=')[1] || '';
    };

    return {
        load,
        save,
        markAsRead
    };
})();
