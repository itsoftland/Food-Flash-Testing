import { AdSliderService } from "./adSliderService.js";
import { AddOutletService } from "./addOutletService.js";
import { handleOutletSelection } from "./chatService.js";
import { WelcomeMessageService } from "./welcomeMessageService.js";

export const VendorUIService = {
    async init(vendorIds) {
        if (!vendorIds.length) return;

        try {
            await this.loadAndRenderAds(vendorIds);
            await this.loadVendorLogos(vendorIds);
        } catch (error) {
            console.error("VendorUIService initialization failed:", error);
        }
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
            const response = await fetch("/api/get_vendor_logos/", {
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
                AppUtils.setSelectedOutletName(vendor.name);
                localStorage.setItem("activeVendorLogo", vendor.logo_url);
                WelcomeMessageService.show(AppUtils.getSelectedOutletName() || "our outlet");

                handleOutletSelection(vendor.vendor_id, vendor.logo_url, vendor.place_id);

                setTimeout(() => {
                    wrapper.scrollIntoView({
                        behavior: "smooth",
                        inline: "center",
                        block: "nearest",
                    });
                }, 100);
            }

            logo.addEventListener("click", () => {
                document.querySelectorAll(".vendor-logo-wrapper").forEach(el => el.classList.remove("active"));
                wrapper.classList.add("active");
                AppUtils.setSelectedOutletName(vendor.name);
                handleOutletSelection(vendor.vendor_id, vendor.logo_url, vendor.place_id);
            });

            wrapper.appendChild(logo);
            logoContainer.appendChild(wrapper);
        });

        this.appendAddOutletButton(logoContainer);
        AddOutletService.init();
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
