export const WelcomeMessageService = {
    show(outletName) {
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
};
