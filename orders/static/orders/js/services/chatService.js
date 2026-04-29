// static/js/chatService.js
import {ChatHistoryService}  from "./chatHistoryService.js";

export function updateChatOnPush(vendorId, logo_url, name) {
    document.querySelectorAll(".vendor-logo-wrapper").forEach(wrapper => {
        const logo = wrapper.querySelector("img");
        if (logo.dataset.vendorId == vendorId) {
            document.querySelectorAll(".vendor-logo-wrapper").forEach(w => w.classList.remove("active"));
            wrapper.classList.add("active");
            AppUtils.setSelectedOutletName(name);
            let ratingLink = AppUtils.storageGet("activeVendorRatingLink") || "https://default-rating-link.com";
            handleOutletSelection(vendorId, logo_url, ratingLink);
        }
    });
}

export async function handleOutletSelection(vendorId, vendor_logo, placeId) {
    AppUtils.storageSet("activeVendor", vendorId);
    AppUtils.storageSet("activeVendorLogo", vendor_logo);
    AppUtils.storageSet("activeVendorRatingLink", placeId);
}

export function appendMessage(text, sender, timestamp = null,type,token_no,passenger_name = null) {
    console.log("Booking ID from message:", token_no);
    const chatContainer = document.getElementById("chat-container");

    const messageRow = document.createElement('div');
    messageRow.classList.add('message-row', sender);

    const timeStamp = timestamp || new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
    });

    const messageBubble = document.createElement('div');
    messageBubble.classList.add('message-bubble', sender);
    
    if (sender === 'server'){

        messageBubble.innerHTML = `
            <div class="message-content">
                <button class="reply-button" title="Reply">
                    <i class="fa-solid fa-reply"></i>
                </button>
                ${text}
                <span class="message-timestamp">
                    ${timeStamp} 
                </span>
            </div>
            `;
    } else if (window.BASE == '/airline_flash/'){
        messageBubble.innerHTML = `
            <div class="message-content">
                <button class="reply-button" title="Reply">
                    <i class="fa-solid fa-reply"></i>
                </button>
                ${text}
                <span class="passenger-name-label">👤 ${passenger_name}</span>
                <span class="dot">•</span>
                <span class="message-timestamp">
                    ${timeStamp} 
                </span>
            </div>
            `;
    } else {
        messageBubble.innerHTML = `
            <div class="message-content">
                <button class="reply-button" title="Reply">
                    <i class="fa-solid fa-reply"></i>
                </button>
                ${text}
                <span class="message-timestamp timestamp-padded">
                    ${timeStamp} 
                </span>
            </div>
            `;
    }

    if (token_no) {
        messageBubble.dataset.tokenNo = token_no;
    }

    messageRow.appendChild(messageBubble);
    if (sender === 'server' && (type === 'foodstatus' || type === 'manager')|| (type === 'flightstatus') || (type === 'airline_manager') || (type === 'dinestatus') || (type === 'dine_manager')) {
        const replyBtn = messageBubble.querySelector('.reply-button');
        if (replyBtn) {
            replyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const isSelected = messageBubble.classList.contains('selected');

                // Deselect all first
                document.querySelectorAll('.message-bubble.server').forEach(el => el.classList.remove('selected'));

                // Toggle selection and reply mode
                if (!isSelected) {
                    messageBubble.classList.add('selected');
                    AppUtils.isReplyMode = true;

                    // Change icon to close
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

                    // Change icon back to reply
                    const icon = replyBtn.querySelector('i');
                    if (icon) {
                        icon.classList.remove('fa-times');
                        icon.classList.add('fa-reply');
                        replyBtn.title = 'Reply';
                        replyBtn.classList.remove('active');
                    }
                }

                // Focus input
                const inputBox = document.getElementById("chat-input");
                if (inputBox) inputBox.focus();

                // Optional: Store token number globally if needed
                const tokenNo = messageBubble.dataset.tokenNo;
            });
        }
    } 
    else if (type === 'thankyou') {
        const replyBtn = messageBubble.querySelector('.reply-button');
        if (replyBtn) replyBtn.remove();
        messageBubble.classList.add("thankyou-message");
    }
    else {
        const replyBtn = messageBubble.querySelector('.reply-button');
        if (replyBtn) replyBtn.remove();
    }
    chatContainer.appendChild(messageRow);

    // Final logo hydration fallback for server cards:
    // if the card logo is empty/broken, reuse the outlet logo already visible in header.
    if (sender === 'server') {
        const resolveFallbackLogo = () =>
            (document.querySelector(".vendor-logo-wrapper.active img")?.src) ||
            (document.querySelector(".vendor-logo-wrapper img")?.src) ||
            (AppUtils.storageGet("activeVendorLogo")) ||
            (localStorage.getItem("activeVendorLogo")) ||
            "";

        const hydrateLogo = (img) => {
            if (!img) return;
            const fallbackLogo = resolveFallbackLogo();
            if (!fallbackLogo) return;
            if (!img.getAttribute("src") || img.naturalWidth === 0) {
                img.src = fallbackLogo;
            }
        };

        messageRow.querySelectorAll("img.server-logo").forEach((img) => {
            if (!img) return;

            // Resolve fallback at error time (not at append time), because outlet logos
            // may load after this message is first rendered.
            img.onerror = () => hydrateLogo(img);

            // Immediate attempt.
            hydrateLogo(img);

            // Delayed second attempt for races where outlet logos render slightly later.
            setTimeout(() => hydrateLogo(img), 600);
        });
    }

    chatContainer.scrollTop = chatContainer.scrollHeight;
    AppUtils.adjustChatResponsePadding();
}
export async function saveChat(text, sender, type, token_no) {
    // console.log("Saving chat message:", {text, sender, type, token_no});
    const activeVendorId = await AppUtils.getActiveVendor();
    if (!activeVendorId) return;

    let normalizedText;

    if (type === "chat") {
        // User typed message → wrap inside JSON
        normalizedText = { content: text };
    } else if (typeof text === "string") {
        // Server/system accidentally sends string → wrap it
        normalizedText = { message: text };
    } else {
        // Already JSON (status / offers / manager payload)
        normalizedText = text;
    }

    try {
        await ChatHistoryService.save({
            vendorId: activeVendorId,
            browser_id: AppUtils.getBrowserId(),
            sender,
            type,
            text: normalizedText,
            token_no
        });
    } catch (err) {
        console.error("Failed to save chat message:", err);
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
