import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';
import { API_ENDPOINTS } from '/static/utils/js/apiEndpoints.js';

document.addEventListener('DOMContentLoaded', async () => {
  const currentPath = window.location.pathname;

  // Show welcome only on dashboard
  if (currentPath.includes('/dashboard') || currentPath.endsWith('/company/')) {
    setupOutletGreeting();
  }
  await getDashboardMetrics();
});

function setupOutletGreeting() {
  const welcomeInfoContainer = document.getElementById('welcome-info');
  const outletName = localStorage.getItem('customer_name') || 'Admin';
  welcomeInfoContainer.innerHTML = `<span class="text-golden fw-bold">Welcome, ${outletName}</span>`;
}
async function getDashboardMetrics() {
  const metricsContainer = document.getElementById("dashboard-metrics");

  try {
    const response = await fetchWithAutoRefresh(API_ENDPOINTS.DASHBOARD_METRICS, {
      method: 'GET',
    });

    const data = await response.json();

    const iconMap = {
      // mapped_keypad_devices: "mobile-retro",
      // unmapped_keypad_devices: "ban",
      // mapped_android_tvs: "tv",
      // unmapped_android_tvs: "ban",
      keypad_devices: "mobile-retro",
      // unmapped_keypad_devices: "ban",
      android_tvs: "tv",
      // unmapped_android_tvs: "ban",
      outlets: "store",
    };

    Object.entries(data).forEach(([key, value]) => {
      const card = document.createElement("div");
      card.className = "col-6 col-md-3";

      const className = `icon-circle ${key.replaceAll('_', '-')}`;
      const formattedKey = key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
      console.log(iconMap[key], key, value);

      card.innerHTML = `
        <div class="metric-card shadow-sm h-100">
          <div class="${className}">
            <i class="fas fa-${iconMap[key] || 'chart-bar'}"></i>
          </div>
          <div class="metric-label">${formattedKey}</div>
          <div class="metric-value">${value}</div>
        </div>
      `;


      metricsContainer.appendChild(card);
    });


  } catch (error) {
    console.error("Error fetching metrics:", error);
    metricsContainer.innerHTML = `<div class="col-12 text-danger">Failed to load metrics</div>`;
  }
}
