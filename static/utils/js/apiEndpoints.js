// static/utils/js/apiEndpoints.js
// ==========================================================
// 🌐 Global Project Info Initialization
// ==========================================================

// ✅ Safely read project info from the global scope with fallback values
const projectName = (
  typeof window.PROJECT_NAME === "string" && window.PROJECT_NAME.trim() !== ""
)
  ? window.PROJECT_NAME.trim()
  : "calleron"; // Default project name fallback

const projectDisplayName = (
  typeof window.PROJECT_DISPLAY_NAME === "string" && window.PROJECT_DISPLAY_NAME.trim() !== ""
)
  ? window.PROJECT_DISPLAY_NAME.trim()
  : "Caller On"; // Default display name fallback

const appVersion = (
  typeof window.APP_VERSION === "string" && window.APP_VERSION.trim() !== ""
)
  ? window.APP_VERSION.trim()
  : "1.0.0"; // Default app version fallback

// ==========================================================
// 🌍 Define and Expose Global Variables
// ==========================================================

// Construct the base path for the project (e.g., /airline_flash/)
window.BASE = `/${projectName}/`;

// Reassign and expose consistent global variables for reuse across modules
window.PROJECT_NAME = projectName;
window.PROJECT_DISPLAY_NAME = projectDisplayName;
window.APP_VERSION = appVersion;

// ==========================================================
// 🧩 Debug / Version Tracking (Optional)
// ==========================================================
// Uncomment these lines for debugging environment setup and version tracking
// console.log("🌍 Global BASE:", window.BASE);
// console.log(`🚀 Loaded Project: ${projectDisplayName}`);
// console.log(`🧩 App Version: ${projectDisplayName} ${appVersion}`);


// =======================
// ✅ API ENDPOINTS
// =======================
export const API_ENDPOINTS = {
  LOGIN: `${BASE}api/login/`,
  CONFIG: `${BASE}company/api/configurations/`,
  DASHBOARD_METRICS: `${BASE}company/api/dashboard_metrics/`,
  CREATE_VENDOR: `${BASE}companyadmin/api/create_vendor/`,
  COMPANY_OUTLET_CREATION_DATA: `${BASE}company/api/get_outlet_creation_data/`,
  GET_VENDORS: `${BASE}company/api/get_vendors/`,
  GET_VENDORS_DETAILS: `${BASE}company/api/get_vendor_details/`,
  UPDATE_VENDOR: `${BASE}company/api/update_vendor/`,
  GET_KEYPAD_DEVICES: `${BASE}company/api/get_devices/`,
  MAP_DEVICE: `${BASE}company/api/map_device/`,
  UNMAP_DEVICE: `${BASE}company/api/unmap_device/`,
  GET_ANDROID_TVS: `${BASE}company/api/get_android_tvs/`,
  MAP_ANDROID_TVS: `${BASE}company/api/map_android_tvs/`,
  UNMAP_ANDROID_TVS: `${BASE}company/api/unmap_android_tvs/`,
  ORDER_COUNTS_SUMMARY: `${BASE}company/api/order_counts_summary/`,
  FILTERED_ORDERS: `${BASE}company/api/filtered_orders/`,
  ORDER_TIMELINE: `${BASE}company/api/order_status_timeline/`,
  GET_COMPANIES: `${BASE}companyadmin/api/company_lists/`,
  PRODUCT_REGISTRATION: `${BASE}companyadmin/api/product-registration/`,
  PRODUCT_AUTH_URL: `${BASE}companyadmin/api/product-authentication/`,
  LICENSE_CHECK: `${BASE}company/api/license_check/`,
  COMPANY_UPDATE_URL: `${BASE}api/company-update/`,
  UPDATE_COMPANY: `${BASE}companyadmin/api/update_company/`,
  UPDATE_COMPANY_ID: `${BASE}companyadmin/api/update_company_id/`,
  CREATE_USER: `${BASE}company/api/create_user/`,
  GET_USERS: `${BASE}company/api/get_users/`,
  GET_MANAGER_DEVICES: `${BASE}company/api/get_manager_devices/`,
  MAP_MANAGER_DEVICES: `${BASE}company/api/map_manager_devices/`,
  UNMAP_MANAGER_DEVICES: `${BASE}company/api/unmap_manager_devices/`,
  ASSIGN_USER: `${BASE}company/api/map_user/`,
  UNASSIGN_USER: `${BASE}company/api/unmap_user/`,
  BANNER_UPLOAD: `${BASE}company/api/banner_upload/`,
  BANNER_LIST: `${BASE}company/api/banner_list/`,
  BANNER_DELETE: `${BASE}company/api/banner_delete/`,
  CREATE_AD_PROFILE: `${BASE}company/api/create_ad_profile/`,
  ASSIGNED_PROFILES: `${BASE}company/api/assigned_profiles/`,
  ASSIGN_AD_PROFILE: `${BASE}company/api/assign_ad_profile/`,
  UNMAP_PROFILE: `${BASE}company/api/unmap_profile/`,
  DELETE_AD_PROFILE: `${BASE}company/api/delete_ad_profile/`,
  AVAILABLE_PROFILES: `${BASE}company/api/available_profiles/`,
  GET_AD_PROFILES: `${BASE}company/api/get_ad_profiles/`,
  CREATE_UTILITY: `${BASE}company/api/create_utility/`,
  GET_UTILITIES: `${BASE}company/api/get_utilities/`,
  UPDATE_UTILITY_STATUS: `${BASE}company/api/update_utility_status/`,
  UPDATE_UTILITY: `${BASE}company/api/update_utility/`,
  CREATE_TV_CONFIG: `${BASE}company/api/tv_config_create/`,
  GET_TV_CONFIG: `${BASE}company/api/tv_config_list/`,
  GET_TV_CONFIG_DETAIL: `${BASE}company/api/tv_config_detail/{id}/`,
  UPDATE_TV_CONFIG: `${BASE}company/api/tv_config_update/{id}/`,
  DELETE_TV_CONFIG: `${BASE}company/api/tv_config_delete/{id}/`,
  ASSIGN_TV_CONFIG: `${BASE}company/api/tv_config_assign/`,
  REGISTER_COMPANY: `${BASE}companyadmin/api/register-company/`,
  UPDATE_ORDER: `${BASE}vendors/api/update-order/`,
  COMPANYADMIN_OUTLET_CREATION_DATA: `${BASE}companyadmin/api/get_outlet_creation_data/`,
  COMPANY_OUTLETS: `${BASE}companyadmin/api/outlets/`,
  // Add more endpoints here
  CHECK_STATUS: `${BASE}check-status/`,
  FETCH_OUTLETS: `${BASE}api/outlets/`,
  GET_BANNERS: `${BASE}api/get_banners/`,
  GET_CHAT: `${BASE}api/webchat-messages/`,
  CREATE_CHAT: `${BASE}api/webchat-messages-create/`,
  READ_CHAT: `${BASE}api/mark-messages-read/`,
  FEEDBACK: `${BASE}api/submit_feedback/`,
  MENU: `${BASE}api/menus/`,
  SAVE_SUBSCRIPTION: `${BASE}vendors/api/save-subscription/`,
  VENDOR_LOGOS: `${BASE}api/get_vendor_logos/`,
  //Airline Flash Specific
  CREATE_PASSENGER: `${BASE}api/public_create_passenger/`,
  //DINE FLASH SPECIFIC
  UTILITY_LIST: `${BASE}api/utility_list`,
  TABLE_BOOKING: `${BASE}api/book_table/`,
};

// =======================
// ✅ WEB ENDPOINTS
// =======================
export const WEB_ENDPOINTS = {
  LOGIN: `${BASE}login/`,
  COMPANY_DASHBOARD: `${BASE}company/dashboard/`,
  ADMIN_DASHBOARD: `${BASE}companyadmin/dashboard/`,
  COMPANY_LIST: `${BASE}companyadmin/company_lists/`,
  OUTLET_DASHBOARD: `${BASE}outlet/dashboard/`,
  OUTLETS: `${BASE}company/outlets/`,
  COMPANY_OUTLETS: `${BASE}companyadmin/outlet_lists/`,
  UPDATE_OUTLET: `${BASE}company/update_outlet/`,
  DEVICE_LIST: `${BASE}company/device_list/`,
  ANDROID_TV_LIST: `${BASE}company/android_tv_list/`,
  ORDER_LIST: `${BASE}company/order_list/`,
  USER_LIST: `${BASE}company/user_list/`,
  PROFILE_LIST: `${BASE}company/profile_list/`,
  MAPPED_LIST: `${BASE}company/mapped_list/`,
  // Add more web endpoints here
};
