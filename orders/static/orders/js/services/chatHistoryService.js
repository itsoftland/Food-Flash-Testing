// orders/static/js/services/chatHistoryService.js
import { ChatTemplateService } from "./chatTemplateService.js";

const base = AppUtils.getStartUrl();
const apiModulePath = `${base}static/utils/js/apiEndpoints.js`;
let apiEndpoints;

try {
    const endpointsModule = await import(apiModulePath);
    apiEndpoints = endpointsModule.API_ENDPOINTS;
} catch (error) {
    console.error("Failed to import apiEndpoints:", error);
}

export const ChatHistoryService = (() => {
    /**
     * Fetch all messages for a vendor from the backend.
     * @param {number} vendorId 
     * @param {string} browserId
     * @returns {Promise<Array>}
     */
    const load = async (vendorId, browserId) => {
        try {
            const response = await fetch(
                `${apiEndpoints.GET_CHAT}?vendor_id=${vendorId}&browser_id=${browserId}`, 
                {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                }
            );
            if (!response.ok) throw new Error("Failed to fetch chat messages");

            const data = await response.json();
            // console.log("Chat History",data)

            if (!data || !Array.isArray(data.messages)) {
                console.warn("Unexpected response format:", data);
                return [];
            }

            return data.messages.map(msg => {
                // console.log("Raw message:", msg);
                let finalMsg = { ...msg };
                
                // If it's a system/manager message with JSON in message_text, parse it
                if ((msg.sender === 'system' || msg.sender === 'manager') && msg.message_text) {
                    try {
                        const parsed = JSON.parse(msg.message_text);
                        if (parsed && typeof parsed === 'object') {
                            finalMsg.type = parsed.type || msg.type;
                            finalMsg.text = parsed;
                        }
                    } catch (e) {
                        // console.error("Failed to parse message_text:", e);
                    }
                }

                const rendered = ChatTemplateService.build(finalMsg.type ? finalMsg : msg);
                // console.log("Rendered message:", rendered);

                return {
                    ...finalMsg, 
                    rendered, 
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
            let payload = {
                vendor: vendorId,
                browser_id,
                sender,
                type,
                text
            };

            // For Airline Flash → send `sequence_code`
            if (window.BASE === "/airline_flash/") {
                payload.sequence_code = token_no; // token_no actually holds sequence code in this context
            }
            else if (window.BASE === "/dine_flash/") {
                // For Dine Flash → send booking_no
                payload.booking_id = token_no;
            } 
            else {
                // For Food Flash → send numeric token_no
                payload.token_no = token_no;
            }

            const response = await fetch(apiEndpoints.CREATE_CHAT, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCSRFToken(),
                },
                body: JSON.stringify(payload),
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
            const response = await fetch(`${apiEndpoints.READ_CHAT}${vendorId}/`, {
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
