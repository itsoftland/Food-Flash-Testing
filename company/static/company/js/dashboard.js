document.addEventListener('DOMContentLoaded', async () => {
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  const WEB_ENDPOINTS = apiModule.WEB_ENDPOINTS;

  const currentPath = window.location.pathname;

  // Show welcome only on dashboard
  if (currentPath.includes('/dashboard')) {
    setupOutletGreeting();
  }
  await getDashboardMetrics(fetchWithAutoRefresh,API_ENDPOINTS,WEB_ENDPOINTS);
});

function setupOutletGreeting() {
  const welcomeInfoContainer = document.getElementById('welcome-info');
  const outletName = localStorage.getItem('customer_name') || 'Admin';
  welcomeInfoContainer.innerHTML = `<span class="text-golden fw-bold">Welcome, ${outletName}</span>`;
}

async function getDashboardMetrics(fetchWithAutoRefresh, API_ENDPOINTS,WEB_ENDPOINTS) {
  const metricsContainer = document.getElementById("dashboard-metrics");

  try {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.DASHBOARD_METRICS, {
      method: 'GET',
    });
    const data = await response.json();

    const projectName = window.PROJECT_NAME || "food_flash";

    const iconMap = {
      keypad_devices: "mobile-retro",
      android_tvs: "tv",
      outlets: "store",
      airport: "plane-departure",
    };

    Object.entries(data).forEach(([key, value]) => {

      // Skip android_tvs and keypad_devices for airline_flash
      if (projectName === "airline_flash" && (key === "android_tvs" || key === "keypad_devices")) {
        return;
      }
      // Skip keypad_devices for dine_flash and dine_flash_buffet
      if ((projectName === "dine_flash" || projectName === "dine_flash_buffet") && key === "keypad_devices") {
        return;
      }

      const card = document.createElement("div");
      card.className = "col-6 col-md-3";

      // Rename according to flavour
      const displayKey =
        projectName === "airline_flash" && key === "outlets"
          ? "airport"
          : key;

      const className = `icon-circle ${displayKey.replaceAll('_', '-')}`;
      const formattedKey = displayKey
        .replace(/_/g, " ")
        .replace(/\b\w/g, c => c.toUpperCase());
      // console.log(displayKey)

      // Define target URLs per metric
      const pageLinks = {
        outlets: WEB_ENDPOINTS.OUTLETS,
        keypad_devices: WEB_ENDPOINTS.DEVICE_LIST,
        android_tvs: WEB_ENDPOINTS.ANDROID_TV_LIST,
        airport: WEB_ENDPOINTS.OUTLETS,
      };

      const targetUrl = pageLinks[displayKey] || "#";
      // Wrap the card in an anchor link
      card.innerHTML = `
        <a href="${targetUrl}" class="text-decoration-none">
          <div class="metric-card shadow-sm h-100 hover-scale">
            <div class="${className}">
              <i class="fas fa-${iconMap[displayKey] || 'chart-bar'}"></i>
            </div>
            <div class="metric-label">${formattedKey}</div>
            <div class="metric-value">${value}</div>
          </div>
        </a>
      `;

      metricsContainer.appendChild(card);
    });

  } catch (error) {
    console.error("Error fetching metrics:", error);
    metricsContainer.innerHTML = `<div class="col-12 text-danger">Failed to load metrics</div>`;
  }
}
