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

const DEFAULT_OUTLET_NAME = "our outlet";

function normalizeOutletName(outletName) {
    if (outletName == null) return DEFAULT_OUTLET_NAME;
    const trimmed = String(outletName).trim();
    if (!trimmed || trimmed.toLowerCase() === "undefined") return DEFAULT_OUTLET_NAME;
    return trimmed;
}

function resolveFallbackLogo() {
    return (
        document.querySelector(".vendor-logo-wrapper.active img")?.src ||
        document.querySelector(".vendor-logo-wrapper img")?.src ||
        (typeof AppUtils !== "undefined" && AppUtils.storageGet("activeVendorLogo")) ||
        localStorage.getItem("activeVendorLogo") ||
        ""
    );
}

function hydrateWelcomeLogo(img) {
    if (!img) return;
    const fallbackLogo = resolveFallbackLogo();
    if (!fallbackLogo) return;
    const currentSrc = img.getAttribute("src") || "";
    if (!currentSrc || img.naturalWidth === 0) {
        img.src = fallbackLogo;
    }
}

/** Shared with chat rows that use server-logo before vendor bar is ready. */
export function hydrateServerLogoElement(logoImg) {
    attachWelcomeLogoHydration(logoImg);
}

function attachWelcomeLogoHydration(logoImg) {
    if (!logoImg) return;
    const initial =
        (typeof AppUtils !== "undefined" && AppUtils.storageGet("activeVendorLogo")) ||
        localStorage.getItem("activeVendorLogo") ||
        resolveFallbackLogo() ||
        "";
    if (initial) logoImg.src = initial;

    logoImg.onerror = () => hydrateWelcomeLogo(logoImg);
    hydrateWelcomeLogo(logoImg);
    setTimeout(() => hydrateWelcomeLogo(logoImg), 600);
}

function buildWelcomeMessages(outletName) {
    const WELCOME_MESSAGES = {
        default: [
            "Hi {customerName}, Good Day! Welcome to {outletName}.",
            "Kindly enter the Bill Number and Send so that we can track your order."
        ],
        food_flash: [
            "Hi {customerName}, Good Day! Welcome to {outletName}.",
            "Kindly enter the Bill Number and Send so that we can track your order."
        ],
        airline_flash: [
            "Hi {customerName}, Good Day! Welcome to {outletName}.",
            "Enter your Sequence Code to stay updated on your boarding schedule and gate announcements."
        ],
        dine_flash: [
            "Hi {customerName}, Welcome to {outletName}!",
            "Kindly enter your booking number to check your table allocation status."
        ],
        dine_flash_buffet: [
            "Hi {customerName}, Good Day! Welcome to {outletName}.",
            "Kindly enter your token or bill number and send so we can track your order."
        ]
    };

    const projectKey = (window.PROJECT_NAME || "default").toLowerCase();
    const selectedMessages = WELCOME_MESSAGES[projectKey] || WELCOME_MESSAGES.default;
    const safeOutlet = normalizeOutletName(outletName);

    let customerName = "";
    if (typeof AppUtils !== "undefined" && typeof AppUtils.getCustomerName === "function") {
        customerName = AppUtils.getCustomerName() || "";
    }
    if (projectKey === "dine_flash_buffet") {
        customerName = "";
    }

    return selectedMessages.map((msg) => {
        let processedMsg = msg.replace("{outletName}", safeOutlet);
        if (customerName) {
            processedMsg = processedMsg.replace("{customerName}", customerName);
        } else {
            processedMsg = processedMsg.replace("{customerName}, ", "");
            processedMsg = processedMsg.replace("Hi {customerName}", "Hi");
        }
        return processedMsg;
    });
}

export const WelcomeMessageService = {
    show(outletName) {
        const chatContainer = document.getElementById("chat-container");
        if (!chatContainer) return;

        const existingWelcome = chatContainer.querySelector(".welcome-wrapper");
        if (existingWelcome) {
            this.refresh(outletName);
            return;
        }

        const messages = buildWelcomeMessages(outletName);
        const wrapper = document.createElement("div");
        wrapper.classList.add("welcome-wrapper");

        messages.forEach((msg) => {
            const messageRow = document.createElement("div");
            messageRow.classList.add("message-row", "server");

            const logoImg = document.createElement("img");
            logoImg.alt = "Vendor Logo";
            logoImg.className = "server-logo";
            attachWelcomeLogoHydration(logoImg);

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
    },

    /** Update logos/text on an existing welcome block after vendor logos load. */
    refresh(outletName) {
        const chatContainer = document.getElementById("chat-container");
        if (!chatContainer) return;

        const wrapper = chatContainer.querySelector(".welcome-wrapper");
        if (!wrapper) return;

        const messages = buildWelcomeMessages(
            outletName != null
                ? outletName
                : (typeof AppUtils !== "undefined" && AppUtils.getSelectedOutletName
                    ? AppUtils.getSelectedOutletName()
                    : null)
        );

        const rows = wrapper.querySelectorAll(".message-row.server");
        rows.forEach((row, index) => {
            const bubble = row.querySelector(".message-bubble.server");
            if (bubble && messages[index] != null) {
                bubble.textContent = messages[index];
            }
            const logoImg = row.querySelector("img.server-logo");
            if (logoImg) attachWelcomeLogoHydration(logoImg);
        });
    }
};
