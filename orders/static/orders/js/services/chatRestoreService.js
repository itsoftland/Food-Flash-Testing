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
        } else{
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

