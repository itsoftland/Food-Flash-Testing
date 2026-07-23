// static/utils/js/apiEndpoints.js
// ==========================================================
// 🌐 Global Project Info — lazy BASE (safe with dynamic import)
// ==========================================================
//
// Endpoints must resolve against the current window.PROJECT_NAME on each
// access. If BASE were frozen at module load, a module that evaluated before
// inline layout scripts could default to /calleron/ while the app lives under
// /dine_flash/, causing 404 HTML responses and JSON parse failures.

function syncWindowProjectGlobals() {
  const projectName =
    typeof window.PROJECT_NAME === "string" && window.PROJECT_NAME.trim() !== ""
      ? window.PROJECT_NAME.trim()
      : "calleron";

  const projectDisplayName =
    typeof window.PROJECT_DISPLAY_NAME === "string" &&
    window.PROJECT_DISPLAY_NAME.trim() !== ""
      ? window.PROJECT_DISPLAY_NAME.trim()
      : "Caller On";

  const appVersion =
    typeof window.APP_VERSION === "string" && window.APP_VERSION.trim() !== ""
      ? window.APP_VERSION.trim()
      : "1.0.0";

  window.BASE = `/${projectName}/`;
  window.PROJECT_NAME = projectName;
  window.PROJECT_DISPLAY_NAME = projectDisplayName;
  window.APP_VERSION = appVersion;
  return window.BASE;
}

function projectBase() {
  return syncWindowProjectGlobals();
}

// Paths are relative to project root (leading segment after /{project}/)
const RELATIVE_API_ENDPOINTS = {
  LOGIN: "api/login/",
  CONFIG: "company/api/configurations/",
  DASHBOARD_METRICS: "company/api/dashboard_metrics/",
  CREATE_VENDOR: "companyadmin/api/create_vendor/",
  COMPANY_OUTLET_CREATION_DATA: "company/api/get_outlet_creation_data/",
  GET_VENDORS: "company/api/get_vendors/",
  GET_VENDORS_DETAILS: "company/api/get_vendor_details/",
  UPDATE_VENDOR: "company/api/update_vendor/",
  GET_KEYPAD_DEVICES: "company/api/get_devices/",
  MAP_DEVICE: "company/api/map_device/",
  UNMAP_DEVICE: "company/api/unmap_device/",
  GET_ANDROID_TVS: "company/api/get_android_tvs/",
  MAP_ANDROID_TVS: "company/api/map_android_tvs/",
  UNMAP_ANDROID_TVS: "company/api/unmap_android_tvs/",
  UNMAP_AND_DELETE_ANDROID_TVS: "company/api/unmap_and_delete_android_tvs/",
  ORDER_COUNTS_SUMMARY: "company/api/order_counts_summary/",
  FILTERED_ORDERS: "company/api/filtered_orders/",
  ORDER_TIMELINE: "company/api/order_status_timeline/",
  BUFFET_ORDER_UTILITIES: "company/api/buffet_order_utilities/",
  GET_COMPANIES: "companyadmin/api/company_lists/",
  PRODUCT_REGISTRATION: "companyadmin/api/product-registration/",
  PRODUCT_AUTH_URL: "companyadmin/api/product-authentication/",
  LICENSE_CHECK: "company/api/license_check/",
  COMPANY_UPDATE_URL: "api/company-update/",
  UPDATE_COMPANY: "companyadmin/api/update_company/",
  UPDATE_COMPANY_ID: "companyadmin/api/update_company_id/",
  CREATE_USER: "company/api/create_user/",
  GET_USERS: "company/api/get_users/",
  GET_MANAGER_DEVICES: "company/api/get_manager_devices/",
  MAP_MANAGER_DEVICES: "company/api/map_manager_devices/",
  UNMAP_MANAGER_DEVICES: "company/api/unmap_manager_devices/",
  GET_UTILITY_USER_DEVICES: "company/api/get_utility_user_devices/",
  MAP_UTILITY_USER_DEVICES: "company/api/map_utility_user_devices/",
  UNMAP_UTILITY_USER_DEVICES: "company/api/unmap_utility_user_devices/",
  RELEASE_ANDROID_APK: "company/api/release_android_apk/",
  ASSIGN_USER: "company/api/map_user/",
  UNASSIGN_USER: "company/api/unmap_user/",
  BANNER_UPLOAD: "company/api/banner_upload/",
  BANNER_LIST: "company/api/banner_list/",
  BANNER_DELETE: "company/api/banner_delete/",
  CREATE_AD_PROFILE: "company/api/create_ad_profile/",
  ASSIGNED_PROFILES: "company/api/assigned_profiles/",
  ASSIGN_AD_PROFILE: "company/api/assign_ad_profile/",
  UNMAP_PROFILE: "company/api/unmap_profile/",
  DELETE_AD_PROFILE: "company/api/delete_ad_profile/",
  AVAILABLE_PROFILES: "company/api/available_profiles/",
  GET_AD_PROFILES: "company/api/get_ad_profiles/",
  CREATE_UTILITY: "company/api/create_utility/",
  GET_UTILITIES: "company/api/get_utilities/",
  UPDATE_UTILITY_STATUS: "company/api/update_utility_status/",
  UPDATE_UTILITY: "company/api/update_utility/",
  CREATE_TV_CONFIG: "company/api/tv_config_create/",
  GET_TV_CONFIG: "company/api/tv_config_list/",
  GET_TV_CONFIG_DETAIL: "company/api/tv_config_detail/{id}/",
  UPDATE_TV_CONFIG: "company/api/tv_config_update/{id}/",
  DELETE_TV_CONFIG: "company/api/tv_config_delete/{id}/",
  ASSIGN_TV_CONFIG: "company/api/tv_config_assign/",
  CLEAR_TV_CONFIG: "company/api/tv_config_clear/",
  TV_ADS_LIST: "company/api/tv_ads/list/",
  TV_ADS_UPLOAD: "company/api/tv_ads/upload/",
  TV_ADS_UPDATE: "company/api/tv_ads/{id}/update/",
  TV_ADS_DELETE: "company/api/tv_ads/{id}/delete/",
  REGISTER_COMPANY: "companyadmin/api/register-company/",
  UPDATE_ORDER: "vendors/api/update-order/",
  COMPANYADMIN_OUTLET_CREATION_DATA: "companyadmin/api/get_outlet_creation_data/",
  COMPANY_OUTLETS: "companyadmin/api/outlets/",
  CHECK_STATUS: "check-status/",
  FETCH_OUTLETS: "api/outlets/",
  GET_BANNERS: "api/get_banners/",
  GET_CHAT: "api/webchat-messages/",
  CREATE_CHAT: "api/webchat-messages-create/",
  READ_CHAT: "api/mark-messages-read/",
  FEEDBACK: "api/submit_feedback/",
  MENU: "api/menus/",
  SAVE_SUBSCRIPTION: "vendors/api/save-subscription/",
  VENDOR_LOGOS: "api/get_vendor_logos/",
  CREATE_PASSENGER: "api/public_create_passenger/",
  UTILITY_LIST: "api/utility_list/",
  HOSPITAL_PATIENT_SUBMIT: "api/hospital_patient_submit/",
  TABLE_BOOKING: "api/book_table/",
  DINE_FLASH_QR_EXCHANGE: "api/dine_flash_qr_exchange/",
  DINE_FLASH_RESOLVE_BOOKING: "api/dine_flash/resolve_booking/",
  DINE_FLASH_RESOLVE_ORDER_LOOKUP: "api/dine_flash/resolve_order_lookup/",
  BUFFET_RESOLVE_ORDER_LOOKUP: "api/buffet/resolve_order_lookup/",
  GENERATE_BUFFET_TABLE_QR: "company/api/generate_buffet_table_qr/",
  GENERATE_HOSPITAL_BRANCH_QR: "company/api/generate_hospital_branch_qr/",
  // ⚠️ TEMP DIAGNOSTIC (iOS push-delivery chain). Remove with the `[diag]` logs.
  DINE_FLASH_CLIENT_DIAG: "api/dine_flash_client_diag/",
};

const RELATIVE_WEB_ENDPOINTS = {
  LOGIN: "login/",
  COMPANY_DASHBOARD: "company/dashboard/",
  ADMIN_DASHBOARD: "companyadmin/dashboard/",
  COMPANY_LIST: "companyadmin/company_lists/",
  OUTLET_DASHBOARD: "outlet/dashboard/",
  OUTLETS: "company/outlets/",
  COMPANY_OUTLETS: "companyadmin/outlet_lists/",
  UPDATE_OUTLET: "company/update_outlet/",
  DEVICE_LIST: "company/device_list/",
  ANDROID_TV_LIST: "company/android_tvs/",
  ORDER_LIST: "company/order_list/",
  USER_LIST: "company/user_list/",
  PROFILE_LIST: "company/profile_list/",
  MAPPED_LIST: "company/mapped_list/",
};

function createEndpointProxy(relMap) {
  return new Proxy(
    {},
    {
      get(_target, prop) {
        if (prop === "then") return undefined;
        const rel = relMap[prop];
        if (rel === undefined) return undefined;
        const base = projectBase();
        return `${base}${rel}`;
      },
      has(_target, prop) {
        return Object.prototype.hasOwnProperty.call(relMap, prop);
      },
    }
  );
}

// =======================
// ✅ API ENDPOINTS
// =======================
export const API_ENDPOINTS = createEndpointProxy(RELATIVE_API_ENDPOINTS);

// =======================
// ✅ WEB ENDPOINTS
// =======================
export const WEB_ENDPOINTS = createEndpointProxy(RELATIVE_WEB_ENDPOINTS);

// Prime window.* once this module evaluates (matches previous side effects)
projectBase();
