export const MenuModalService = (() => {
    const menuContent = document.getElementById("menuContent");

    const renderMenu = (fileList) => {
        if (!fileList || fileList.length === 0) {
                menuContent.innerHTML = `
                    <div class="text-center">
                        <p class="text-warning">No menu available. Showing default menu.</p>
                        <img src="/static/orders/files/menu.jpg" alt="Default Menu" class="img-fluid rounded shadow" style="max-height: 500px;">
                    </div>
                `;
                return;
            }

        const imageFiles = fileList.filter(f => /\.(jpg|jpeg|png|webp)$/i.test(f));
        const pdfFiles = fileList.filter(f => /\.pdf$/i.test(f));

        menuContent.innerHTML = ""; // Clear previous content

        if (pdfFiles.length > 0 && imageFiles.length === 0) {
            menuContent.innerHTML = `
                <iframe src="${pdfFiles[0]}" width="100%" height="500px" frameborder="0"></iframe>
            `;
            return;
        }

        if (imageFiles.length === 1 && pdfFiles.length === 0) {
            menuContent.innerHTML = `
                <img src="${imageFiles[0]}" alt="Menu" class="img-fluid" onerror="this.src='/static/orders/files/menu.jpg'">
            `;
            return;
        }

        if (imageFiles.length > 1) {
            const carouselId = "menuCarousel";
            menuContent.innerHTML = `
                <div class="menu-carousel-wrapper text-center">
                    <div id="${carouselId}" class="carousel slide" data-bs-ride="carousel">
                        <div class="carousel-inner">
                            ${imageFiles.map((file, index) => `
                                <div class="carousel-item ${index === 0 ? "active" : ""}">
                                    <img src="${file}" class="d-block w-100" alt="Menu Page ${index + 1}">
                                </div>
                            `).join("")}
                        </div>

                        <!-- Prev / Next Controls -->
                        <button class="carousel-control-prev" type="button" data-bs-target="#${carouselId}" data-bs-slide="prev">
                            <span class="carousel-control-prev-icon bg-dark rounded-circle" aria-hidden="true"></span>
                            <span class="visually-hidden">Previous</span>
                        </button>
                        <button class="carousel-control-next" type="button" data-bs-target="#${carouselId}" data-bs-slide="next">
                            <span class="carousel-control-next-icon bg-dark rounded-circle" aria-hidden="true"></span>
                            <span class="visually-hidden">Next</span>
                        </button>
                    </div>

                    <!-- Indicators placed outside the image -->
                    <ol class="carousel-indicators custom-indicators mt-3">
                        ${imageFiles.map((_, index) => `
                            <li data-bs-target="#${carouselId}" data-bs-slide-to="${index}" class="${index === 0 ? "active" : ""}"></li>
                        `).join("")}
                    </ol>
                </div>
            `;
            return;
        }

        // Mixed or unsupported
        menuContent.innerHTML = `
                    <div class="text-center">
                        <p class="text-warning">No menu available. Showing default menu.</p>
                        <img src="/static/orders/files/menu.jpg" alt="Default Menu" class="img-fluid rounded shadow" style="max-height: 500px;">
                    </div>
                `;
                return;
    };

    let modalInstance = null;

    const openModalWithFiles = (filePaths) => {
        renderMenu(filePaths);

        if (!modalInstance) {
            modalInstance = new bootstrap.Modal(document.getElementById("menuImageModal"), {
                backdrop: 'static',
                keyboard: false
            });
        }
        modalInstance.show();
    };

    const bindEvents = () => {
        const buttons = document.querySelectorAll(".footer-button"); 
        const menuModal = document.getElementById("menuImageModal");
    
        // 🧹 Cleanup any leftover backdrops if modal is closed
        menuModal.addEventListener("hidden.bs.modal", () => {
            const backdrops = document.querySelectorAll('.modal-backdrop');
            backdrops.forEach(b => b.remove());
            document.body.classList.remove('modal-open');
        });

        buttons.forEach(button => {
            button.addEventListener('click', function () {
                buttons.forEach(btn => btn.classList.remove('active'));
                this.classList.add('active');
                console.log(this.classList.contains('menu-button'))

                // Check if clicked button is for opening the menu modal
                if (this.classList.contains('menu-btn')) {
                    const activeVendorId = localStorage.getItem("activeVendor");

                    if (!activeVendorId) {
                        AppUtils.showToast("No active vendor selected");
                        return;
                    }

                    fetch(`/api/menus/`, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "X-CSRFToken": AppUtils.getCSRFToken(),
                        },
                        body: JSON.stringify({ vendor_ids: [parseInt(activeVendorId)] })
                    })
                        .then(res => {
                            if (!res.ok) throw new Error("Menu not found");
                            return res.json();
                        })
                        .then(data => {
                            if (!Array.isArray(data) || data.length === 0) {
                                throw new Error("No menu data");
                            }
                            const vendorMenu = data[0];
                            const menuFiles = vendorMenu.menus || [];
                            openModalWithFiles(menuFiles);
                        })
                        .catch(err => {
                            console.error("Menu fetch failed:", err);
                            menuContent.innerHTML = `<p class="text-danger">Failed to load menu.</p>`;

                            if (!modalInstance) {
                                modalInstance = new bootstrap.Modal(menuModal, {
                                    backdrop: 'static',
                                    keyboard: false
                                });
                            }

                            modalInstance.show();
                        });
                }
                else if (this.classList.contains('rating-btn')) {
                    console.log('Rating button clicked');
                    let ratingLink = localStorage.getItem("activeVendorRatingLink") || "https://default-rating-link.com";
                    // Construct the Google Review URL
                    const googleReviewUrl = `https://search.google.com/local/writereview?placeid=${ratingLink}`;

                    // Open the review page in a new browser tab
                    window.open(googleReviewUrl, "_blank");
                } 
            });
        });
        // 🔹 Detect clicks outside to remove active state
        document.addEventListener('click', (event) => {
            // Check if click is outside footer buttons and outside modals
            if (!event.target.closest('.footer-button') && !event.target.closest('.modal')) {
                buttons.forEach(btn => btn.classList.remove('active'));
            }
        });
    };

    return {
        init: bindEvents,
        openModalWithFiles
    };
})();
