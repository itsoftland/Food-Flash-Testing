import { appendMessage } from './chatService.js';

export const FeedbackService = (() => {
    const steps = [
        { key: 'feedback_type', question: 'Select Feedback Type', options: ['Complaint', 'Suggestion', 'Compliment'] },
        { key: 'category', question: 'Is it about Dish or Service?', options: ['Dish', 'Service'] },
        { key: 'final', question: 'Leave your comment', input: true }
    ];

    let currentStep = 0;
    let formData = {};
    let cooldownActive = false;

    // Validate comment
    const validateInput = (comment) => {
        const trimmedComment = comment.trim();

        // Regex for allowed characters (letters, numbers, whitespace, and selected special characters)
        const allowedCharacters = /^[a-zA-Z0-9\s.,!?"/\u00A9-\u1FFF\u2000-\u3300]+$/;

        // Check if the comment contains only allowed characters
        if (!allowedCharacters.test(trimmedComment)) {
            // appendMessage("⚠️ Only letters, numbers, emojis, and basic punctuation (.,!?\"/) are allowed.", "server");
            return { valid: false, message: "⚠️ Only letters, numbers, emojis, and basic punctuation (.,!?\"/) are allowed." };
        }

        // Check if comment is not empty
        if (!trimmedComment) {
            return { valid: false, message: "⚠️ Please provide at least a comment or your name." };
        }

        // Check if comment is too short
        if (trimmedComment.length < 5) {
            return { valid: false, message: "⚠️ Comment is too short. Please elaborate." };
        }

        // Check for only special characters (e.g., `; ^ & % # @`)
        const onlySpecialChars = /^[^a-zA-Z0-9]+$/.test(trimmedComment);
        if (onlySpecialChars) {
            return { valid: false, message: "⚠️ Comment must include readable content." };
        }

        // If all checks pass, comment is valid
        return { valid: true };
    };

    const clearChatButtons = () => {
        const chatContainer = document.getElementById("chat-container");
        chatContainer.querySelectorAll("button").forEach(btn => btn.remove());
    };

    const renderStep = () => {
        clearChatButtons();
        const step = steps[currentStep];
        if (!step) return;
        appendMessage(step.question, "server");

        const chatContainer = document.getElementById("chat-container");

        if (step.options) {
            step.options.forEach(option => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-outline-primary m-1';
                btn.textContent = option;
                btn.onclick = () => {
                    if (formData[step.key] === option.toLowerCase()) return; // prevent re-click

                    appendMessage(option, "user");
                    formData[step.key] = option.toLowerCase();

                    // Remove next steps if user changes path
                    if (step.key === 'feedback_type') delete formData['category'];
                    if (step.key !== 'final') currentStep = steps.findIndex(s => s.key === step.key) + 1;

                    setTimeout(renderStep, 300);
                };
                chatContainer.appendChild(btn);
            });
        }

        if (step.input) {
            const nameInput = document.createElement('input');
            nameInput.className = 'form-control my-2';
            nameInput.placeholder = 'Your name (optional)';
            nameInput.id = 'feedback-name';

            const commentBox = document.createElement('textarea');
            commentBox.className = 'form-control my-2';
            commentBox.placeholder = 'Your comment...';
            commentBox.id = 'feedback-comment';

            const submitBtn = document.createElement('button');
            submitBtn.className = 'btn btn-outline-primary mt-2';
            submitBtn.textContent = 'Submit';

            submitBtn.onclick = () => {
                const name = nameInput.value;
                const comment = commentBox.value;

                const { valid, message } = validateInput(comment);
                if (!valid) {
                    appendMessage(message, "server");
                    return;
                }

                formData['name'] = name.trim();
                formData['comment'] = comment.trim();

                submitFeedback(submitBtn);
            };

            chatContainer.appendChild(nameInput);
            chatContainer.appendChild(commentBox);
            chatContainer.appendChild(submitBtn);
        }

        chatContainer.scrollTop = chatContainer.scrollHeight;
    };

    const submitFeedback = async (submitBtn) => {
        if (cooldownActive) {
            appendMessage("⏳ Please wait a moment before sending more feedback.", "server");
            return;
        }

        const vendorId = await AppUtils.getActiveVendor();
        submitBtn.disabled = true;

        try {
            const response = await fetch("/api/submit_feedback/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": AppUtils.getCSRFToken()
                },
                body: JSON.stringify({ vendor_id: vendorId, ...formData })
            });

            const data = await response.json();

            if (data.success) {
                appendMessage("✅ Thank you for your feedback!", "server");
                currentStep = 0;
                formData = {};
                cooldownActive = true;

                setTimeout(() => {
                    cooldownActive = false;
                }, 60000); // 1-minute cooldown
            } else {
                appendMessage(data.message || "❌ Failed to submit feedback. Try again.", "server");
            }

        } catch (error) {
            console.error("Error submitting feedback:", error);
            appendMessage("❌ An error occurred. Please try again later.", "server");
        }
    };

    const startFeedback = () => {
        currentStep = 0;
        formData = {};
        renderStep();
    };

    const bindEvents = () => {
        const buttons = document.querySelectorAll(".footer-button");

        buttons.forEach(button => {
            button.addEventListener("click", function () {
                buttons.forEach(btn => btn.classList.remove("active"));
                this.classList.add("active");

                if (this.classList.contains("feedback-btn")) {
                    startFeedback();
                }
            });
        });
    };

    return {
        init: bindEvents,
        startFeedback
    };
})();
