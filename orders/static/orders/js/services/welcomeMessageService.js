export const WelcomeMessageService = {
    show(outletName) {
        console.trace("WelcomeMessageService.show called with outletName:", outletName);
        const chatContainer = document.getElementById("chat-container");
        if (!chatContainer) return;

        // 🛡 Prevent duplicate welcome messages
        const existingWelcome = chatContainer.querySelector(".welcome-wrapper");
        if (existingWelcome) {
            console.log("[WelcomeMessageService] Welcome note already exists, skipping insert.");
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
            logoImg.src = localStorage.getItem("activeVendorLogo") || "/food_flash/static/images/default-logo.png";
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
            console.log("[WelcomeMessageService] Inserted welcome note at top");
        } else {
            chatContainer.appendChild(wrapper);
            console.log("[WelcomeMessageService] Appended welcome note to empty chat");
        }

        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
};

