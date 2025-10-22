export const WelcomeMessageService = {
    show(outletName) {
        const chatContainer = document.getElementById("chat-container");
        if (!chatContainer) return;

        // 🛡 Prevent duplicate welcome messages
        const existingWelcome = chatContainer.querySelector(".welcome-wrapper");
        if (existingWelcome) {
            return;
        }

        const messages = [
            `Hi, Good Day! Welcome to ${outletName}.`,
            "Kindly enter the Bill Number and Send so that we can track your order."
        ];

        // wrapper to identify later
        const wrapper = document.createElement("div");
        wrapper.classList.add("welcome-wrapper");

        messages.forEach(msg => {
            const messageRow = document.createElement("div");
            messageRow.classList.add("message-row", "server");

            const logoImg = document.createElement("img");
            logoImg.src = localStorage.getItem("activeVendorLogo");
            logoImg.alt = "Vendor Logo";
            logoImg.className = "server-logo";

            const messageBubble = document.createElement("div");
            messageBubble.classList.add("message-bubble", "server");
            messageBubble.textContent = msg;

            messageRow.appendChild(logoImg);
            messageRow.appendChild(messageBubble);
            wrapper.appendChild(messageRow);
        });

        if (chatContainer.children.length > 0) {
            chatContainer.insertBefore(wrapper, chatContainer.firstChild);
        } else {
            chatContainer.appendChild(wrapper);
        }

        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
};

