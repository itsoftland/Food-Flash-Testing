import { AdSliderService } from "./adSliderService.js";
import { AddOutletService } from "./addOutletService.js";
import { ChatRestoreService } from "./chatRestoreService.js?v=20260821_2";
import { handleOutletSelection } from "./chatService.js?v=20260821_2";
import { WelcomeMessageService } from "./welcomeMessageService.js";

const base = AppUtils.getStartUrl();
const apiModulePath = `${base}static/utils/js/apiEndpoints.js`;
let apiEndpoints;

try {
    const endpointsModule = await import(apiModulePath);
    apiEndpoints = endpointsModule.API_ENDPOINTS;
} catch (error) {
    console.error("Failed to import apiEndpoints:", error);
}

let vendorUiReadyPromise = Promise.resolve();

// ⚠️ TEMP DIAGNOSTIC (iOS chat-card loss). Dine Flash AND Dine Flash Buffet only;
// logs whether the vendor bar triggers an EARLY restore (which can clear cards
// before bootstrap). Remove with the other `[diag]` logs.
function dineFlashVendorDiag(label, data) {
    const base = window.BASE || "";
    const isDineFlashBuffet = base.includes("/dine_flash_buffet/");
    const isDineFlash = base.includes("/dine_flash/");
    if (!isDineFlash && !isDineFlashBuffet) return;
    const projectLabel = isDineFlashBuffet ? "dine_flash_buffet" : "dine_flash";
    console.info(`[diag][${projectLabel}] ${label}`, {
        ts: new Date().toISOString(),
        ...(data || {}),
    });
}

export const VendorUIService = {
    ready() {
        return vendorUiReadyPromise;
    },

    async init(vendorIds) {
        if (!vendorIds.length) {
            vendorUiReadyPromise = Promise.resolve();
            return;
        }

        vendorUiReadyPromise = (async () => {
            try {
                await this.loadAndRenderAds(vendorIds);
                await this.loadVendorLogos(vendorIds);
            } catch (error) {
                console.error("VendorUIService initialization failed:", error);
            }
        })();

        return vendorUiReadyPromise;
    },

    async loadAndRenderAds(vendorIds) {
        try {
            const adsData = await AdSliderService.fetchAds(vendorIds);
            const vendorAdsArray = adsData.map(vendor => vendor.ads);
            const interleavedAds = AdSliderService.interleaveAds(vendorAdsArray);
            AdSliderService.renderAds(interleavedAds);
            AdSliderService.init();
        } catch (err) {
            console.error("Failed to load ads:", err);
        }
    },

    async loadVendorLogos(vendorIds) {
        try {
            const response = await fetch(apiEndpoints.VENDOR_LOGOS, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": AppUtils.getCSRFToken(),
                },
                credentials: "same-origin",
                body: JSON.stringify({ vendor_ids: vendorIds }),
            });

            const data = await response.json();
            this.renderVendorLogos(data);
        } catch (error) {
            console.error("Error fetching vendor logos:", error);
        }
    },
    async renderVendorLogos(vendors) {
        const logoContainer = document.getElementById("vendor-logo-bar");
        const activeVendorId = await AppUtils.getActiveVendor();
        if (!logoContainer) return;

        logoContainer.innerHTML = "";
        let restorePromise = null;
        let browser_id = AppUtils.getCurrentBrowserId();

        vendors.forEach(vendor => {
            const wrapper = document.createElement("div");
            wrapper.classList.add("vendor-logo-wrapper");

            const logo = document.createElement("img");
            logo.src = vendor.logo_url;
            logo.alt = vendor.name;
            logo.classList.add("vendor-logo");
            logo.dataset.vendorId = vendor.vendor_id;

            if (vendor.vendor_id === activeVendorId) {
                wrapper.classList.add("active");
                const outletLabel =
                    (vendor.alias_name || vendor.name || "").trim() || "our outlet";
                AppUtils.setSelectedOutletName(outletLabel);
                AppUtils.storageSet("activeVendorLogo", vendor.logo_url);
                handleOutletSelection(vendor.vendor_id, vendor.logo_url, vendor.place_id);
                const skipRestoreForBuffetQrRedirect =
                    String(window.PROJECT_NAME || "").trim().toLowerCase() === "dine_flash_buffet" &&
                    window.buffetQrTokenFromRedirect;
                const skipRestoreForDineFlashBookingRedirect = Boolean(window.dineFlashBookingFromRedirect);
                dineFlashVendorDiag("VendorUIService restore decision", {
                    vendor_id: vendor.vendor_id,
                    browser_id_present: Boolean(browser_id),
                    skip_buffet_qr_redirect: Boolean(skipRestoreForBuffetQrRedirect),
                    skip_dine_flash_booking_redirect: skipRestoreForDineFlashBookingRedirect,
                    will_restore:
                        Boolean(browser_id) &&
                        !skipRestoreForBuffetQrRedirect &&
                        !skipRestoreForDineFlashBookingRedirect,
                });
                if (browser_id && !skipRestoreForBuffetQrRedirect && !skipRestoreForDineFlashBookingRedirect) {
                    ChatRestoreService.restore(vendor.vendor_id);
                } else if (!browser_id) {
                    console.warn("No browser ID, skipping restore.");
                }
                WelcomeMessageService.show(outletLabel);
                setTimeout(() => {
                    wrapper.scrollIntoView({
                        behavior: "smooth",
                        inline: "center",
                        block: "nearest",
                    });
                }, 100);
            }

            logo.addEventListener("click", async() => {
                document.querySelectorAll(".vendor-logo-wrapper").forEach(el => el.classList.remove("active"));
                wrapper.classList.add("active");
                const outletLabel =
                    (vendor.alias_name || vendor.name || "").trim() || "our outlet";
                AppUtils.setSelectedOutletName(outletLabel);
                handleOutletSelection(vendor.vendor_id, vendor.logo_url, vendor.place_id);
                restorePromise = await ChatRestoreService.restore(vendor.vendor_id);
            });

            wrapper.appendChild(logo);
            logoContainer.appendChild(wrapper);
        });

        this.appendAddOutletButton(logoContainer);
        AddOutletService.init();

        const activeOutlet =
            (typeof AppUtils.getSelectedOutletName === "function" && AppUtils.getSelectedOutletName()) ||
            "our outlet";
        WelcomeMessageService.refresh(activeOutlet);

        // ✅ Only now wait for restore
        if (restorePromise) {
            browser_id = AppUtils.getCurrentBrowserId();
            if (!browser_id) {
                console.warn("No browser ID, skipping restore wait.");
                return;
            }
            restorePromise;
        }
    },

    appendAddOutletButton(container) {
        const spacer = document.createElement("div");
        spacer.style.flex = "1";

        const addBtnWrapper = document.createElement("div");
        addBtnWrapper.className = "add-btn-wrapper flex-shrink-0 ms-2";
        addBtnWrapper.innerHTML = `<button id="add-outlet-btn" class="btn add-outlet-btn">+</button>`;

        container.appendChild(spacer);
        container.appendChild(addBtnWrapper);
    }
};
