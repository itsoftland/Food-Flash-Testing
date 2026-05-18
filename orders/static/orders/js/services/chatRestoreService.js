// orders/static/orders/js/services/chatRestoreService.js
import { ChatHistoryService } from "./chatHistoryService.js";
import { appendMessage } from "./chatService.js";
import { WelcomeMessageService } from "./welcomeMessageService.js";

export const ChatRestoreService = (() => {
  let restorePromise = null;
  let lastRestoredVendorId = null;

  /**
   * Restore chat history for a given vendor
   * @param {string|number} vendorId
   * @returns {Promise<boolean>} true if any messages restored, false otherwise
   */
  async function restore(vendorId) {
    if (restorePromise) return restorePromise;

    // ⚡ Skip if restoring same vendor again
    if (lastRestoredVendorId === vendorId) {
      return Promise.resolve(true);
    }

    restorePromise = (async () => {
      try {
        window.isRestoringHistory = true;
        lastRestoredVendorId = vendorId;

        const browserId = AppUtils.getBrowserId();
        if (!browserId) {
          console.warn("ChatRestoreService: No browser ID, skipping restore.");
          return false;
        }

        const cachedMessages = await ChatHistoryService.load(vendorId, browserId) || [];
        const chatContainer = document.getElementById("chat-container");

        if (!chatContainer) {
          console.warn("ChatRestoreService: Chat container not found.");
          return false;
        }

        // Always clear when switching vendors
        chatContainer.innerHTML = "";
        
        // Restore messages
        if (window.BASE && window.BASE.includes('/airline_flash/')) {
          cachedMessages.forEach(msg => {
          // console.log(msg)
          appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.sequence_code,msg.passenger_name);
          });
        } else if (window.BASE && window.BASE.includes('/dine_flash_buffet/')) {
          // Track orders whose status cards were restored so a QR reload does not duplicate them.
          window.buffetRestoredOrderTokens = new Set();
          const buffetServerTypes = new Set([
            "buffet_utilities_status_summary",
            "buffet_ready_utilities_summary",
            "buffet_item_update",
            "buffet_item_preparing",
            "buffet_item_ready",
            "buffet_item_cancelled",
            "buffet_item_delivered",
            "buffet_utilities_status",
            "buffet_utilities_ready",
            "order_delivered",
            "buffet_manager",
            "manager",
          ]);
          cachedMessages.forEach(msg => {
            appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.token_no);
            if (
              msg.sender === "server" &&
              msg.token_no != null &&
              buffetServerTypes.has(msg.type)
            ) {
              window.buffetRestoredOrderTokens.add(String(msg.token_no));
            }
          });
        } else if (window.BASE && window.BASE.includes('/dine_flash/')) {
          cachedMessages.forEach(msg => {
          // console.log(msg)
          // console.log("Chat History booking_id",msg.booking_id)
          appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.booking_id);
          });
        } else {
          cachedMessages.forEach(msg => {
          appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.token_no);
          });
        }
      
        // 🟡 Always insert welcome note at the top
        WelcomeMessageService.show(AppUtils.getSelectedOutletName() || "our outlet", chatContainer, { prepend: true });

        return cachedMessages.length > 0;
      } catch (err) {
        console.error("ChatRestoreService.restore failed:", err);
        return false;
      } finally {
        window.isRestoringHistory = false;
        restorePromise = null;
      }
    })();

    return restorePromise;
  }

  return { restore };
})();

