/**
 * -------------------------------------------------------------
 * WelcomeMessageService
 * -------------------------------------------------------------
 * Dynamically displays the welcome messages for customers
 * based on the active project flavour (Food Flash / Airline Flash).
 *
 * Source: window.PROJECT_NAME (set by Django in base.html)
 *
 * Flavour behaviour:
 * - Food Flash: Bill Number based order tracking
 * - Airline Flash: Flight Travel updates
 *
 * -------------------------------------------------------------
 */

export const WelcomeMessageService = {
    show(outletName) {
        const chatContainer = document.getElementById("chat-container");
        if (!chatContainer) return;

        // 🛡 Prevent duplicate welcome messages
        const existingWelcome = chatContainer.querySelector(".welcome-wrapper");
        if (existingWelcome) return;

        // -------------------------------------------------------------
        // 1️⃣ Define flavour-based messages
        // -------------------------------------------------------------
        const WELCOME_MESSAGES = {
            default: [
                "Hi, Good Day! Welcome to {outletName}.",
                "Kindly enter the Bill Number and Send so that we can track your order."
            ],
            food_flash: [
                "Hi, Good Day! Welcome to {outletName}.",
                "Kindly enter the Bill Number and Send so that we can track your order."
            ],
            airline_flash: [
                "Hi, Good Day! Welcome to {outletName}.",
                "Enter your Flight Number to stay updated on your boarding schedule and gate announcements."
            ]
        };

        // -------------------------------------------------------------
        // 2️⃣ Select message set based on PROJECT_NAME
        // -------------------------------------------------------------
        const projectKey = (window.PROJECT_NAME || "default").toLowerCase();
        const selectedMessages = WELCOME_MESSAGES[projectKey] || WELCOME_MESSAGES.default;

        // Replace {outletName} placeholder dynamically
        const messages = selectedMessages.map(msg =>
            msg.replace("{outletName}", outletName)
        );

        // -------------------------------------------------------------
        // 3️⃣ Build welcome message elements
        // -------------------------------------------------------------
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

        // -------------------------------------------------------------
        // 4️⃣ Append to chat container
        // -------------------------------------------------------------
        if (chatContainer.children.length > 0) {
            chatContainer.insertBefore(wrapper, chatContainer.firstChild);
        } else {
            chatContainer.appendChild(wrapper);
        }

        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
};
