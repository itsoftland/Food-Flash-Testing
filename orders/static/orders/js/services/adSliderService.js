export const AdSliderService = (() => {

    /**
     * Fetch ads from the backend based on vendor IDs
     * Sends vendor_ids as a query parameter (GET request)
     */
    const fetchAds = async (vendorIds) => {
        try {
            const response = await fetch(`/api/get_banners/?vendor_ids=${JSON.stringify(vendorIds)}`, {
                method: "GET",
            });

            // Throw error if response not ok
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

            // Return parsed JSON data (list of ad image URLs)
            return await response.json();
        } catch (error) {
            console.error("Error fetching ads:", error);
            return [];
        }
    };

    /**
     * Interleaves arrays of ads from multiple vendors
     * Example: [[a1, a2], [b1, b2]] => [a1, b1, a2, b2]
     */
    const interleaveAds = (vendorAdsArray) => {
        const result = [];
        let i = 0;
        let hasMore = true;

        // Loop until all arrays are exhausted
        while (hasMore) {
            hasMore = false;

            for (const ads of vendorAdsArray) {
                if (i < ads.length) {
                    result.push(ads[i]);
                    hasMore = true;
                }
            }

            i++;
        }

        return result;
    };

    /**
     * Render ad images into a slider container
     * Duplicates ads only if necessary to fill the visible area for smooth scroll
     */
    const renderAds = (ads, containerId = "ad-slider") => {
        const container = document.getElementById(containerId);
        if (!container) return;

        // Default fallback images
        const defaultAds = [
            "/media/ads/Default/Demo.jpg",
        ];

        // If no ads available, use default ones
        if (!ads || ads.length === 0) {
            ads = defaultAds;
        }

        // Clear existing content
        container.innerHTML = "";

        // Create a wrapper div for scrolling track
        const track = document.createElement("div");
        track.classList.add("ad-slider-track");

        // 1. Get visible width of the container
        const containerWidth = container.offsetWidth;

        // 2. Define fixed image width (match CSS or design)
        const imgWidth = 200;

        // 3. Calculate how many images are needed to fill the width
        const imagesNeeded = Math.ceil(containerWidth / imgWidth);

        // 4. Duplicate ads until there are enough to scroll smoothly
        let finalAds = [...ads];
        while (finalAds.length < imagesNeeded * 2) {
            finalAds = finalAds.concat(ads);
        }

        // 5. Create and append image elements to the track
        finalAds.forEach(adUrl => {
            const img = document.createElement("img");
            img.src = adUrl;
            img.alt = "Advertisement";
            img.classList.add("ad-slide");

            // iOS-specific rendering optimizations
            img.style.willChange = "transform";
            img.style.backfaceVisibility = "hidden";
            img.style.WebkitTransform = "translateZ(0)";

            // Set loading behavior and dimensions
            img.loading = "eager";
            img.width = imgWidth;
            img.height = 130;

            // Open full-screen modal on click
            img.addEventListener("click", () => {
                openAdModal(adUrl);
            });

            track.appendChild(img);
        });

        // Add the track to the container
        container.appendChild(track);

        // Start the infinite scrolling animation
        startScroll(track);
    };


    /**
     * Scrolls the ad track horizontally using CSS transform
     * Uses requestAnimationFrame for smooth animation
     */
    const startScroll = (track) => {
        let offset = 0;
        const speed = 0.5; // pixels per frame

        const scroll = () => {
            offset -= speed;

            // Reset scroll when half of the track has passed (loop simulation)
            const resetThreshold = track.scrollWidth / 2;
            if (Math.abs(offset) >= resetThreshold) {
                offset = 0;
            }

            // Apply the horizontal translation
            track.style.transform = `translateX(${offset}px)`;

            // Continue the animation loop
            requestAnimationFrame(scroll);
        };

        scroll();
    };

    /**
     * Opens a Bootstrap modal with the clicked ad image in larger view
     */
    const openAdModal = (src) => {
        const modalElement = document.getElementById("ad-modal");
        const modalImg = document.getElementById("ad-modal-img");

        if (modalElement && modalImg) {
            modalImg.src = src;

            // Bootstrap modal config: can't close by clicking outside or pressing Esc
            const bsModal = new bootstrap.Modal(modalElement, {
                backdrop: 'static',
                keyboard: false
            });

            bsModal.show();
        }
    };

    /**
     * Initializes the listener to reset modal image source when closed
     */
    const initModalListeners = () => {
        const modalElement = document.getElementById("ad-modal");
        if (!modalElement) return;

        modalElement.addEventListener("hidden.bs.modal", () => {
            const modalImg = document.getElementById("ad-modal-img");
            if (modalImg) modalImg.src = "";
        });
    };

    /**
     * Public initializer for this service
     * Should be called once on page load to set up modal cleanup
     */
    const init = () => {
        initModalListeners();
    };

    // Expose public methods
    return {
        init,
        fetchAds,
        interleaveAds,
        renderAds
    };
})();
