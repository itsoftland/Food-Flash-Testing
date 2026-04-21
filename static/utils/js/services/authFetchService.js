// static/utils/js/services/authFetchService.js

// Match orders/static/orders/js/utils.js AppUtils.getPrefixedKey so login + fetch use the same keys.
function authStorageKey(key) {
  const project = (window.PROJECT_NAME || 'default').toLowerCase().trim();
  return `${project}:${key}`;
}

function getStoredAuthValue(key) {
  const primary = localStorage.getItem(authStorageKey(key));
  if (primary && primary !== 'null' && primary !== 'undefined') return primary;
  const legacy = localStorage.getItem(key);
  if (legacy && legacy !== 'null' && legacy !== 'undefined') return legacy;
  return null;
}

export async function fetchWithAutoRefresh(url, options = {}) {
  if (!window.BASE) {
    console.error("❌ window.BASE is not defined. Make sure PROJECT_NAME is set in base.html");
    throw new Error("BASE not defined");
  } 

  const accessToken = getStoredAuthValue('access_token');
  const refreshToken = getStoredAuthValue('refresh_token');

  options.headers = options.headers || {};
  const hasAccessToken = !!accessToken && accessToken !== 'null' && accessToken !== 'undefined';
  if (hasAccessToken) {
    options.headers['Authorization'] = 'Bearer ' + accessToken;
  } else {
    delete options.headers['Authorization'];
  }
  options.credentials = options.credentials || 'same-origin';

  // Only set Content-Type if it's not FormData
  if (!(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
  }
  // Add CSRF token if available
  const csrfToken = AppUtils?.getCSRFToken?.();
  if (csrfToken) {
    options.headers['X-CSRFToken'] = csrfToken;
  }
  
  let response = await fetch(url, options);

  // If a stale/invalid JWT causes 401, retry once using session auth only.
  if (response.status === 401 && hasAccessToken) {
    const retryOptions = { ...options, headers: { ...(options.headers || {}) } };
    delete retryOptions.headers.Authorization;
    response = await fetch(url, retryOptions);
    if (response.ok) {
      return response;
    }
  }

  if (response.status === 401 && refreshToken) {
    // Attempt to refresh token dynamically
    const refreshUrl = `${window.BASE}api/token/refresh/`;
    const refreshResponse = await fetch(refreshUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: refreshToken }),
    });

    if (refreshResponse.ok) {
      const refreshData = await refreshResponse.json();
      localStorage.setItem(authStorageKey('access_token'), refreshData.access);

      // Retry original request with new token
      options.headers['Authorization'] = 'Bearer ' + refreshData.access;
      response = await fetch(url, options);
    } else {
      console.warn("⚠️ Token refresh failed. Redirecting to login.");
      window.location.href = `${window.BASE}login/`;
      return;
    }
  }

  return response;
}

