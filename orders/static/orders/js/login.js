import { dineFlashCustomerFetch } from "./dineflash/dineFlashFetch.js";

/**
 * ==========================================================
 * 📘 Dynamic Login Page Script
 * ==========================================================
 * File: /orders/static/orders/js/login.js
 * Description:
 * Handles environment-aware login configuration for multi-product systems
 * (e.g., food_flash, airline_flash, service_flash). Dynamically sets
 * background, logo, favicon, and imports required modules. Also manages
 * secure login, token handling, license verification, and role-based redirects.
 * ==========================================================
 */

document.addEventListener('DOMContentLoaded', async () => {
    /** @type {HTMLFormElement} - The login form element */
    const loginForm = document.getElementById('loginForm');

    // Declare dynamic service variables
    let callProductAuthAPI, ModalService, apiEndpoints, webEndpoints;

    try {
        /**
         * ----------------------------------------------------------
         * 🔧 Dynamic Project & Base Configuration
         * ----------------------------------------------------------
         */
        const base = window.BASE || '/caller_on/';
        const projectName = (window.PROJECT_NAME || 'caller_on').toLowerCase();

        /**
         * ----------------------------------------------------------
         * 🎨 Dynamic Background Setup
         * ----------------------------------------------------------
         * Sets background image, position, and color based on project.
         */
        const backgroundImages = {
            food_flash: `${base}static/utils/Images/foodflash-login-bg.webp`,
            airline_flash: `${base}static/utils/Images/airlineflash-login-bg.webp`,
            service_flash: `${base}static/utils/Images/serviceflash-login-bg.webp`,
            dine_flash: `${base}static/utils/Images/dineflash-login-bg.webp`,
            dine_flash_buffet: `${base}static/utils/Images/dineflash-login-bg.webp`
        };

        const body = document.querySelector("body.login-page");
        if (body) {
            const bgImage = backgroundImages[projectName];
            body.style.backgroundImage = `url("${bgImage}")`;
            body.style.backgroundRepeat = "no-repeat";
            body.style.backgroundPosition = "center center";
            body.style.backgroundAttachment = "fixed";
            body.style.backgroundSize = "cover";
            body.style.backgroundColor = "#f9f4ed";
        }

        /**
         * ----------------------------------------------------------
         * 🏷️ Dynamic Logo Configuration
         * ----------------------------------------------------------
         * Replaces the login logo dynamically based on the project name.
         */
        const loginLogoImg = document.querySelector('#login-logo-img');
        if (loginLogoImg) {
            const loginLogos = {
                food_flash: `${base}static/company/images/foodflashlogo.webp`,
                airline_flash: `${base}static/company/images/airlineflashlogo.webp`,
                service_flash: `${base}static/company/images/serviceflashlogo.webp`,
                dine_flash: `${base}static/company/images/dineflashlogo.webp`,
                dine_flash_buffet: `${base}static/company/images/dineflashlogo.webp`
            };
            loginLogoImg.src = loginLogos[projectName];
        }

        /**
         * ----------------------------------------------------------
         * 🧩 Favicon Configuration
         * ----------------------------------------------------------
         * Generates and appends the favicon dynamically based on project name.
         */
        const staticBase = `${window.location.origin}/${projectName ? projectName + '/' : ''}static/orders/images/`;

        const faviconMap = {
            'food_flash': 'food-flash-logo.ico',
            'airline_flash': 'airline-flash-logo.ico',
            'service_flash': 'service-flash-logo.ico',
            'dine_flash':'dine-flash-logo.ico',
            'dine_flash_buffet':'dine-flash-logo.ico'
        };

        const iconFile = faviconMap[projectName] || 'default-logo.ico';
        const faviconUrl = `${staticBase}${iconFile}`;

        const link = document.createElement('link');
        link.rel = 'icon';
        link.type = 'image/x-icon';
        link.href = faviconUrl;
        document.head.appendChild(link);

        /**
         * ----------------------------------------------------------
         * 📦 Dynamic Module Imports
         * ----------------------------------------------------------
         * Imports core utility modules only after DOM load
         * for better performance and modular separation.
         */
        const productAuthModule = await import(`${base}static/utils/js/services/productAuthService.js`);
        const modalServiceModule = await import(`${base}static/utils/js/services/modalService.js`);
        const endpointsModule = await import(`${base}static/utils/js/apiEndpoints.js`);

        callProductAuthAPI = productAuthModule.callProductAuthAPI;
        ModalService = modalServiceModule.ModalService;
        apiEndpoints = endpointsModule.API_ENDPOINTS;
        webEndpoints = endpointsModule.WEB_ENDPOINTS;

    } catch (importError) {
        console.error('❌ Failed to import required modules:', importError);
        return;
    }

    /**
     * ==========================================================
     * 🔐 LOGIN FORM HANDLER
     * ==========================================================
     * Handles secure authentication:
     * - Validates input
     * - Sends credentials to backend
     * - Stores tokens and user info
     * - Validates license for non-admin users
     * - Redirects by user role
     */
    loginForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        /** @type {string} */
        const username = document.getElementById('username').value.trim();
        /** @type {string} */
        const password = document.getElementById('password').value.trim();

        const payload = { username, password };

        try {
            // 🔸 Send login request to backend API
            const response = await dineFlashCustomerFetch(apiEndpoints.LOGIN, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': AppUtils.getCSRFToken() // Add CSRF token
                },
                body: JSON.stringify(payload)
            });

            // 🔸 Parse JSON response
            const data = await response.json();

            if (!response.ok) {
                alert(data.error || 'Login failed');
                return;
            }

            const role = data.user.role;

            // 🔸 Store tokens and user info
            AppUtils.storageSet('access_token', data.access);
            AppUtils.storageSet('refresh_token', data.refresh);
            AppUtils.setCustomerName(data.user.username);
            AppUtils.storageSet('role', role);

            /**
             * ---------------------------------------------
             * 🧾 License Verification for Non-Admin Users
             * ---------------------------------------------
             * Ensures valid license before accessing system.
             */
            if (role !== 'Super Admin') {
                const customerId = data?.user?.customer_id || '';
                AppUtils.setCustomerId(customerId);
                const { status } = await callProductAuthAPI(customerId);
                if (status === false) {
                    ModalService.showError(
                        "Your license has expired. Please click OK to return to login.",
                        () => { window.location.href = webEndpoints.LOGIN; }
                    );
                    return;
                }
            }

            /**
             * ---------------------------------------------
             * 🚦 Role-Based Redirection
             * ---------------------------------------------
             */
            if (role === 'Super Admin') {
                window.location.href = webEndpoints.ADMIN_DASHBOARD;
            } else if (role === 'Company') {
                window.location.href = webEndpoints.COMPANY_DASHBOARD;
            } else if (role === 'Outlet') {
                window.location.href = webEndpoints.DASHBOARD;
            } else {
                alert('Unknown user role');
            }

        } catch (err) {
            console.error('Login error:', err);
        }
    });
});
