// static/js/chatService.js
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

export function handleOutletSelection(vendorId, vendor_logo, placeId) {
    localStorage.setItem("activeVendor", vendorId);
    localStorage.setItem("activeVendorLogo", vendor_logo);
    localStorage.setItem("activeVendorRatingLink", placeId);

    const chatContainer = document.getElementById("chat-container");
    chatContainer.innerHTML = "";

    const outletName = AppUtils.getSelectedOutletName() || "our outlet";
    showWelcomeMessage(outletName);

    window.isRestoringHistory = true;
    const cachedMessages = ChatHistoryService.load(vendorId) || [];
    cachedMessages.forEach(msg => {
        appendMessage(msg.text, msg.sender, msg.timestamp, msg.type || null,msg.token_no);
    });
    window.isRestoringHistory = false;
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
        logoImg.src = localStorage.getItem("activeVendorLogo") || "/static/images/default-logo.png";
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

export function appendMessage(text, sender, timestamp = null,type,token_no) {
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
    if (token_no) {
        messageBubble.dataset.tokenNo = token_no;
    }

    if (sender === 'server') {
        const activeLogo = localStorage.getItem("activeVendorLogo") || '/static/images/default-logo.png';
        const logoImg = document.createElement('img');
        logoImg.src = activeLogo;
        logoImg.alt = 'Vendor Logo';
        logoImg.className = 'server-logo';
        messageRow.appendChild(logoImg);
    }

    messageRow.appendChild(messageBubble);
    console.log("Sender:", sender, "Type:", type);
    if (sender === 'server' && (type === 'foodstatus' || type === 'manager')) {
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
                if (tokenNo) {
                    console.log("Clicked Token No:", tokenNo);
                }
                console.log("Reply mode:", AppUtils.isReplyMode);
            });
        }
    } else {
        const replyBtn = messageBubble.querySelector('.reply-button');
        if (replyBtn) replyBtn.remove();
    }



    chatContainer.appendChild(messageRow);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    if (!window.isRestoringHistory) {
        const activeVendorId = localStorage.getItem("activeVendor");
        if (activeVendorId) {
            const existingMessages = ChatHistoryService.load(activeVendorId) || [];
            existingMessages.push({ text, sender, timestamp: timeStamp, type: type || null,token_no}); // ✅ FIXED
            ChatHistoryService.save(activeVendorId, existingMessages);
        }
    }

    AppUtils.adjustChatResponsePadding();
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
