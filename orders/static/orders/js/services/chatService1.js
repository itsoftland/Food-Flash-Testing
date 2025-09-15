// static/js/services/chatService.js
import {ChatHistoryService}  from "./chatHistoryService.js";

export function updateChatOnPush(vendorId, logo_url, name) {
    document.querySelectorAll(".vendor-logo-wrapper").forEach(wrapper => {
        const logo = wrapper.querySelector("img");
        if (logo.dataset.vendorId == vendorId) {
            document.querySelectorAll(".vendor-logo-wrapper").forEach(w => w.classList.remove("active"));
            wrapper.classList.add("active");
            AppUtils.setSelectedOutletName(name);
            let ratingLink = localStorage.getItem("activeVendorRatingLink") || "https://default-rating-link.com";
            handleOutletSelection(vendorId, logo_url, ratingLink);
        }
    });
}

export async function handleOutletSelection(vendorId, vendor_logo, placeId) {
    localStorage.setItem("activeVendor", vendorId);
    localStorage.setItem("activeVendorLogo", vendor_logo);
    localStorage.setItem("activeVendorRatingLink", placeId);

    const chatContainer = document.getElementById("chat-container");
    window.isRestoringHistory = true;

    try {
        const browserId = AppUtils.getBrowserId();
        if (!browserId) {
            console.warn("No browser ID found. Cannot load chat history.");
            return;
        }

        const permissionStatus = localStorage.getItem("permissionStatus");
        if (permissionStatus !== "granted") {
            console.warn("Skipping chat history restore until notifications are allowed.");
            return;
        }

        const cachedMessages = await ChatHistoryService.load(vendorId, browserId) || [];
        console.log("Restored chat history:", cachedMessages);

        chatContainer.innerHTML = "";

        cachedMessages.forEach(msg => {
            appendMessage(
                msg.text,
                msg.sender,
                msg.timestamp,
                msg.type || null,
                msg.token_no,
                { persist: false }   // 🚫 don’t save again
            );
        });
    } catch (err) {
        console.error("Failed to restore chat history:", err);
    } finally {
        window.isRestoringHistory = false;
    }

    showWelcomeMessage(AppUtils.getSelectedOutletName() || "our outlet");
}



export function showWelcomeMessage(outletName) {
    const chatContainer = document.getElementById("chat-container");
    if (!chatContainer) return;

    const messages = [
        `Hi, Good Day! Welcome to ${outletName}.`,
        "Kindly enter the Bill Number and Send so that we can track your order."
    ];

    messages.forEach(msg => {
        const messageRow = document.createElement("div");
        messageRow.classList.add("message-row", "server");

        const logoImg = document.createElement("img");
        logoImg.src = localStorage.getItem("activeVendorLogo") || "/food_flash/static/images/default-logo.png";
        logoImg.alt = "Vendor Logo";
        logoImg.className = "server-logo";

        const messageBubble = document.createElement("div");
        messageBubble.classList.add("message-bubble", "server");
        messageBubble.textContent = msg;

        messageRow.appendChild(logoImg);
        messageRow.appendChild(messageBubble);
        chatContainer.appendChild(messageRow);
    });

    chatContainer.scrollTop = chatContainer.scrollHeight;
}
// ✅ Pure UI renderer
export function renderMessage({ text, sender, timestamp, type, token_no }) {
    const chatContainer = document.getElementById("chat-container");

    const messageRow = document.createElement("div");
    messageRow.classList.add("message-row", sender);

    const timeStamp = timestamp || new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        hour12: true
    });

    const messageBubble = document.createElement("div");
    messageBubble.classList.add("message-bubble", sender);

    messageBubble.innerHTML = `
        <div class="message-content">
            <button class="reply-button" title="Reply">
                <i class="fa-solid fa-reply"></i>
            </button>
            ${text}
            <span class="message-timestamp">${timeStamp}</span>
        </div>
    `;

    if (token_no) messageBubble.dataset.tokenNo = token_no;

    if (sender === "server") {
        const activeLogo = localStorage.getItem("activeVendorLogo") || "/food_flash/static/images/default-logo.png";
        const logoImg = document.createElement("img");
        logoImg.src = activeLogo;
        logoImg.alt = "Vendor Logo";
        logoImg.className = "server-logo";
        messageRow.appendChild(logoImg);
    }

    messageRow.appendChild(messageBubble);
    chatContainer.appendChild(messageRow);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    AppUtils.adjustChatResponsePadding();

    if (sender === 'server' && (type === 'foodstatus' || type === 'manager')) {
        attachReplyLogic(messageBubble);
    }

}

// ✅ Only history (no UI)
export async function saveMessageToHistory({ text, sender, type, token_no }) {
    const activeVendorId = localStorage.getItem("activeVendor");
    if (!activeVendorId) return;

    try {
        await ChatHistoryService.save({
            vendorId: activeVendorId,
            browser_id: AppUtils.getBrowserId(),
            sender,
            type: type || "chat",
            text,
            token_no
        });
    } catch (err) {
        console.error("Failed to save chat message:", err);
    }
}

// ✅ Decider (new entry point)
export function appendMessage(data, { persist = true } = {}) {
    // Ensure all required keys exist
    const normalized = {
        text: data.text ,
        sender: data.sender ,  
        type: data.type,
        token_no: data.token_no,
    };

    renderMessage(normalized);

    if (persist && !window.isRestoringHistory) {
        saveMessageToHistory(normalized);
    }
}


export function clearReplyMode() {
    const selectedMessage = document.querySelector('.message-bubble.server.selected');
    if (!selectedMessage) return;

    selectedMessage.classList.remove('selected');
    AppUtils.isReplyMode = false;

    const replyBtn = selectedMessage.querySelector('.reply-button');
    const icon = replyBtn?.querySelector('i');

    if (replyBtn && icon) {
        icon.classList.remove('fa-times');
        icon.classList.add('fa-reply');
        replyBtn.title = 'Reply';
        replyBtn.classList.remove('active');
    }
}

function attachReplyLogic(messageBubble) {
    const replyBtn = messageBubble.querySelector('.reply-button');
    if (!replyBtn) return;

    replyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const isSelected = messageBubble.classList.contains('selected');

        // Deselect all first
        document.querySelectorAll('.message-bubble.server')
                .forEach(el => el.classList.remove('selected'));

        if (!isSelected) {
            messageBubble.classList.add('selected');
            AppUtils.isReplyMode = true;

            const icon = replyBtn.querySelector('i');
            if (icon) {
                icon.classList.remove('fa-reply');
                icon.classList.add('fa-times');
                replyBtn.title = 'Cancel Reply';
                replyBtn.classList.add('active');
            }
        } else {
            messageBubble.classList.remove('selected');
            AppUtils.isReplyMode = false;

            const icon = replyBtn.querySelector('i');
            if (icon) {
                icon.classList.remove('fa-times');
                icon.classList.add('fa-reply');
                replyBtn.title = 'Reply';
                replyBtn.classList.remove('active');
            }
        }

        const inputBox = document.getElementById("chat-input");
        if (inputBox) inputBox.focus();

        const tokenNo = messageBubble.dataset.tokenNo;
        if (tokenNo) {
            console.log("Clicked Token No:", tokenNo);
        }
        console.log("Reply mode:", AppUtils.isReplyMode);
    });
}
