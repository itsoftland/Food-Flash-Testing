// orders/static/orders/js/services/chatRestoreService.js
import { ChatHistoryService } from "./chatHistoryService.js";
import { appendMessage } from "./chatService.js";
import { WelcomeMessageService } from "./welcomeMessageService.js";

function isDineFlashBuffetRestoreSurface() {
  const base = window.BASE || "";
  if (base.includes("/dine_flash_buffet/")) return true;
  const path = (window.location?.pathname || "").toLowerCase();
  return path.includes("/dine_flash_buffet") || path.includes("/dineflashbuffet");
}

/** Dine Flash Buffet only — keep order token visible after history restore clears the chat. */
function buffetTokenAlreadyInChat(tokenStr) {
  const chatContainer = document.getElementById("chat-container");
  if (!chatContainer) return false;

  if (chatContainer.querySelector(`.message-row.user [data-token-no="${tokenStr}"]`)) {
    return true;
  }

  for (const bubble of chatContainer.querySelectorAll(".message-row.user .message-bubble.user")) {
    const content = bubble.querySelector(".message-content");
    if (!content) continue;
    const clone = content.cloneNode(true);
    clone.querySelectorAll(".reply-button, .message-timestamp").forEach((el) => el.remove());
    const plain = (clone.textContent || "").replace(/\s+/g, " ").trim();
    if (plain === tokenStr || plain.startsWith(`${tokenStr} `)) {
      return true;
    }
  }
  return false;
}

/** Prevents duplicate user-token bubbles when redirect + restore race (Dine Flash Buffet only). */
let buffetQrTokenBubbleShown = false;

function ensureBuffetQrTokenVisible(token) {
  if (!isDineFlashBuffetRestoreSurface() || token == null) return;
  const tokenStr = String(token).trim();
  if (!tokenStr) return;

  if (buffetQrTokenBubbleShown || buffetTokenAlreadyInChat(tokenStr)) {
    buffetQrTokenBubbleShown = true;
    return;
  }

  appendMessage(tokenStr, "user", "", "chat", tokenStr);
  buffetQrTokenBubbleShown = true;
}

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
          // Snapshot-based dedup: ONLY a full order-detail snapshot ("buffet_order_details")
          // marks a token as already-rendered. Incremental item updates, manager messages,
          // utility/status pushes and delivered notices are NOT snapshots and never gate a
          // manual lookup. A QR reload that restores a snapshot will skip re-rendering it.
          window.buffetOrderSnapshotTokens = new Set();

          // A token may have several saved snapshots (repeated manual lookups). Render only
          // the latest snapshot per token and drop the stale duplicates so the chat shows
          // a single, current order-details card after restore.
          const latestSnapshotIndexByToken = new Map();
          cachedMessages.forEach((msg, idx) => {
            if (msg.type === "buffet_order_details" && msg.token_no != null) {
              latestSnapshotIndexByToken.set(String(msg.token_no), idx);
            }
          });

          cachedMessages.forEach((msg, idx) => {
            if (msg.type === "buffet_order_details" && msg.token_no != null) {
              const tokenKey = String(msg.token_no);
              // Skip every snapshot for this token except the most recent one.
              if (latestSnapshotIndexByToken.get(tokenKey) !== idx) {
                return;
              }
              appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.token_no);
              window.buffetOrderSnapshotTokens.add(tokenKey);
              return;
            }
            appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.token_no);
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
        // First-time buffet redirect: VendorUIService restore can run after early
        // bootstrap and wipe the token message before history exists server-side.
        if (window.buffetQrTokenFromRedirect) {
          ensureBuffetQrTokenVisible(window.buffetQrTokenFromRedirect);
        }
        window.isRestoringHistory = false;
        restorePromise = null;
      }
    })();

    return restorePromise;
  }

  return { restore, ensureBuffetQrTokenVisible };
})();

