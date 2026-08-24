// orders/static/orders/js/services/chatRestoreService.js
import { ChatHistoryService } from "./chatHistoryService.js?v=20260821_2";
import { ChatSyncService } from "./chatSyncService.js?v=20260824_1";
import { appendMessage } from "./chatService.js?v=20260821_2";
import { WelcomeMessageService } from "./welcomeMessageService.js";
import { HOSPITAL_MANAGER_PUSH_TYPE } from "../hospital/hospitalCommon.js";

// ⚠️ TEMP DIAGNOSTIC (iOS chat-card loss). Dine Flash AND Dine Flash Buffet only;
// logs when chat history restore runs/clears the container so a clear-after-append
// race is visible on the timeline. Remove with the other `[diag]` logs.
function dineFlashRestoreDiag(label, data) {
  const base = window.BASE || "";
  const isDineFlashBuffet = base.includes("/dine_flash_buffet/");
  const isDineFlash = base.includes("/dine_flash/");
  if (!isDineFlash && !isDineFlashBuffet) return;
  const projectLabel = isDineFlashBuffet ? "dine_flash_buffet" : "dine_flash";
  console.info(`[diag][${projectLabel}] ${label}`, {
    ts: new Date().toISOString(),
    ...(data || {}),
  });
}

function isDineFlashBuffetRestoreSurface() {
  const base = window.BASE || "";
  if (base.includes("/dine_flash_buffet/")) return true;
  const path = (window.location?.pathname || "").toLowerCase();
  return path.includes("/dine_flash_buffet") || path.includes("/dineflashbuffet");
}

function isHospitalFlashRestoreSurface() {
  const base = String(window.BASE || "");
  const project = String(window.PROJECT_NAME || "").toLowerCase();
  const path = String(window.location?.pathname || "").toLowerCase();
  return (
    project === "hospital_flash" ||
    base.includes("/hospital_flash/") ||
    path.includes("/hospital_flash")
  );
}

/**
 * Customer presentation only — recreate dataset.utilityName on restored
 * Hospital replyable bubbles so subsequent replies keep Scenario 4 labels.
 * Does not affect routing / booking_id identity.
 */
function resolveHospitalRestoredPresentationLabel(msg) {
  const type = String(msg?.type || "").toLowerCase();
  const text =
    typeof msg?.text === "object" && msg.text !== null ? msg.text : {};

  if (type === HOSPITAL_MANAGER_PUSH_TYPE || type === "hospital_manager") {
    const name = String(text.utility_name || "").trim();
    return name || null;
  }

  if (type === "hospitalstatus") {
    const departments = Array.isArray(text.departments) ? text.departments : [];
    if (departments.length > 1) {
      return "All departments";
    }
    if (departments.length === 1) {
      const name = String(departments[0]?.utility_name || "").trim();
      return name || null;
    }
    const name = String(text.utility_name || "").trim();
    return name || null;
  }

  return null;
}

function tagLatestHospitalRestoredPresentation(msg) {
  const label = resolveHospitalRestoredPresentationLabel(msg);
  if (!label) return;
  const chatContainer = document.getElementById("chat-container");
  const bubbles = chatContainer?.querySelectorAll(
    ".message-row.server .message-bubble.server"
  );
  const bubble = bubbles?.[bubbles.length - 1];
  if (!bubble) return;
  bubble.dataset.utilityName = label;
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

    ChatSyncService.resetForVendor(vendorId);

    restorePromise = (async () => {
      try {
        window.isRestoringHistory = true;
        lastRestoredVendorId = vendorId;

        const browserId = AppUtils.getBrowserId();
        dineFlashRestoreDiag("restore START", {
          vendor_id: vendorId,
          browser_id_present: Boolean(browserId),
        });
        if (!browserId) {
          console.warn("ChatRestoreService: No browser ID, skipping restore.");
          return false;
        }

        // Phase 9: Buffet Multi-Order may coalesce this load with Selected rebuild.
        let cachedMessages;
        if (isDineFlashBuffetRestoreSurface()) {
          try {
            const convMod = await import(
              "../buffet/services/selectedOrderConversationService.js?v=20260824_1"
            );
            if (typeof convMod.loadChatHistoryFresh === "function") {
              cachedMessages = (await convMod.loadChatHistoryFresh(vendorId, browserId)) || [];
            }
          } catch (e) {
            // fall through to direct load
          }
        }
        if (!cachedMessages) {
          cachedMessages = (await ChatHistoryService.load(vendorId, browserId)) || [];
        }
        ChatSyncService.seedFromMessages(cachedMessages, vendorId);
        const chatContainer = document.getElementById("chat-container");

        if (!chatContainer) {
          console.warn("ChatRestoreService: Chat container not found.");
          return false;
        }

        dineFlashRestoreDiag("restore CLEARING chat container", {
          vendor_id: vendorId,
          chat_children_before_clear: chatContainer.childElementCount,
          restored_message_count: cachedMessages.length,
        });
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

          // Phase 9: when Multi-Order Mode is on, paint only Selected Order's
          // conversation (tokenless vendor-level messages still shown).
          let selectedTokenFilter = null;
          try {
            const convMod = await import(
              "../buffet/services/selectedOrderConversationService.js?v=20260824_1"
            );
            if (
              typeof convMod.shouldIsolateConversation === "function" &&
              convMod.shouldIsolateConversation()
            ) {
              const { getSelectedOrder } = await import(
                "../buffet/services/selectedOrderService.js"
              );
              const selected = getSelectedOrder();
              if (selected && selected.token_number) {
                selectedTokenFilter = String(selected.token_number).trim();
              }
            }
          } catch (e) {
            selectedTokenFilter = null;
          }

          const messageMatchesSelected = (msg) => {
            if (!selectedTokenFilter) return true;
            const msgToken =
              msg.token_no === null || msg.token_no === undefined
                ? ""
                : String(msg.token_no).trim();
            if (!msgToken) return true;
            return msgToken === selectedTokenFilter;
          };

          // A token may have several saved snapshots (repeated manual lookups). Render only
          // the latest snapshot per token and drop the stale duplicates so the chat shows
          // a single, current order-details card after restore.
          const latestSnapshotIndexByToken = new Map();
          cachedMessages.forEach((msg, idx) => {
            if (msg.type === "buffet_order_details" && msg.token_no != null) {
              if (!messageMatchesSelected(msg)) return;
              latestSnapshotIndexByToken.set(String(msg.token_no), idx);
            }
          });

          cachedMessages.forEach((msg, idx) => {
            if (!messageMatchesSelected(msg)) return;

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
        } else if (isHospitalFlashRestoreSurface()) {
          cachedMessages.forEach((msg) => {
            appendMessage(
              msg.rendered,
              msg.sender,
              msg.timestamp,
              msg.type,
              msg.token_no
            );
            if (msg.sender === "server") {
              tagLatestHospitalRestoredPresentation(msg);
            }
          });
        } else {
          cachedMessages.forEach(msg => {
          appendMessage(msg.rendered, msg.sender, msg.timestamp, msg.type, msg.token_no);
          });
        }
      
        // 🟡 Always insert welcome note at the top
        WelcomeMessageService.show(AppUtils.getSelectedOutletName() || "our outlet", chatContainer, { prepend: true });

        dineFlashRestoreDiag("restore FINISH", {
          vendor_id: vendorId,
          restored_message_count: cachedMessages.length,
          chat_children_after: chatContainer.childElementCount,
        });
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

