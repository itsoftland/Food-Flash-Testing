// Global utility object to store reusable helper functions
window.AppUtils = {

    // ─────────────────────────────────────
    // CSRF Token Utilities
    // ─────────────────────────────────────

    // Retrieves the CSRF token from a meta tag in the HTML document
    // Useful for making secure POST/PUT/DELETE requests in Django
    getCSRFToken: function () {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    },

    // ─────────────────────────────────────
    // Customer Info Helpers (Local Storage)
    // ─────────────────────────────────────

    // Stores the customer ID in localStorage under the key 'customer_id'
    // Useful for tracking/logging user activity across pages
    setCustomerId: function (id) {
        localStorage.setItem('customer_id', id);
    },

    // Retrieves the customer ID from localStorage, or returns null if not set
    // Can be used to fetch customer-specific data or personalize UI
    getCustomerId: function () {
        const customerId = localStorage.getItem('customer_id');
        return customerId ? customerId : null;
    },

    // Stores the customer name in localStorage under the key 'customer_name'
    // Useful for personalized greetings or identification
    setCustomerName: function (name) {
        localStorage.setItem('customer_name', name);
    },

    // Retrieves the customer name from localStorage, or returns a default
    // Helps in displaying meaningful customer labels
    getCustomerName: function () {
        const customerName = localStorage.getItem('customer_name');
        return customerName ? customerName : 'Unknown Customer';
    }

};
