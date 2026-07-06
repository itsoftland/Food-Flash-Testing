// ============================================================
// 🌐 Project Asset Loader (Plain External Script)
// Dynamically loads correct logos, favicon, and apple-touch-icon
// based on window.PROJECT_NAME for multi-flavour Django projects.
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    const base = window.STATIC_BASE || '/static/';
    const projectName = (window.PROJECT_NAME || 'calleron').toLowerCase();

    // ==========================================================
    // 🎨 Define project-specific asset mappings
    // ==========================================================
    const assets = {
        food_flash: {
            fullLogo: `${base}company/images/foodflashlogo.webp`,
            miniLogo: `${base}company/images/ff_logo.webp`,
            favicon: `${base}orders/images/food-flash-logo.ico`,
            apple: `${base}company/images/ff_logo.webp`,
        },
        airline_flash: {
            fullLogo: `${base}company/images/airlineflashlogo.webp`,
            miniLogo: `${base}company/images/af_logo.webp`,
            favicon: `${base}orders/images/airline-flash-logo.ico`,
            apple: `${base}utils/Images/airlineflash-mini-logo.webp`,
        },
        service_flash: {
            fullLogo: `${base}company/images/serviceflashlogo.webp`,
            miniLogo: `${base}company/images/sf_logo.webp`,
            favicon: `${base}orders/images/service-flash-logo.ico`,
            apple: `${base}company/images/sf_logo.webp`,
        },
        dine_flash: {
            fullLogo: `${base}company/images/dineflashlogo.webp`,
            miniLogo: `${base}company/images/df_logo.webp`,
            favicon: `${base}orders/images/dine-flash-logo.ico`,
            apple: `${base}utils/Images/dineflash-mini-logo.webp`,
        },
        dine_flash_buffet: {
            fullLogo: `${base}company/images/dineflashlogo.webp`,
            miniLogo: `${base}company/images/df_logo.webp`,
            favicon: `${base}orders/images/dine-flash-logo.ico`,
            apple: `${base}utils/Images/dineflash-mini-logo.webp`,
        },
        hospital_flash: {
            fullLogo: `${base}company/images/calleronlogo.webp`,
            miniLogo: `${base}company/images/co_logo.webp`,
            favicon: `${base}orders/images/calleron-logo.ico`,
            apple: `${base}company/images/co_logo.webp`,
        },
        calleron: {
            fullLogo: `${base}company/images/calleronlogo.webp`,
            miniLogo: `${base}company/images/co_logo.webp`,
            favicon: `${base}orders/images/calleron-logo.ico`,
            apple: `${base}company/images/co_logo.webp`,
        },
    };

    // ✅ Select assets or fallback
    const selected = assets[projectName] || assets.calleron;

    // ==========================================================
    // 🖼️ Update main and mini logos
    // ==========================================================
    const mainLogo = document.getElementById('main-logo');
    const miniLogo = document.getElementById('mini-logo');
    if (mainLogo) mainLogo.src = selected.fullLogo;
    if (miniLogo) miniLogo.src = selected.miniLogo;

    // ==========================================================
    // 🔗 Utility to update or create <link> tags
    // ==========================================================
    function setLink(rel, href, type = null) {
        // console.log(href);
        let link = document.querySelector(`link[rel="${rel}"]`);
        if (!link) {
            link = document.createElement('link');
            link.rel = rel;
            if (type) link.type = type;
            document.head.appendChild(link);
        }
        link.href = href;
    }

    // ==========================================================
    // 🧩 Apply Favicon and Apple Touch Icon
    // ==========================================================
    setLink('icon', selected.favicon, 'image/x-icon');
    setLink('apple-touch-icon', selected.apple);
});
