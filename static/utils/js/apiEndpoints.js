// static/js/apiEndpoints.js

// Validate and derive project name safely
const projectName = (typeof window.PROJECT_NAME === "string" && window.PROJECT_NAME.trim() !== "")
  ? window.PROJECT_NAME.trim()
  : "calleron"; // fallback

// Declare a truly global base
window.BASE = `/${projectName}/`;  // ✅ globally accessible
console.log("Global BASE:", window.BASE);

// =======================
// ✅ API ENDPOINTS
// =======================
export const API_ENDPOINTS = {
  LOGIN :`${BASE}api/login/`,
  CONFIG : `${BASE}company/api/config/`,
  DASHBOARD_METRICS : `${BASE}company/api/dashboard_metrics/`,
  CREATE_VENDOR : `${BASE}companyadmin/api/create_vendor/`,
  GET_VENDORS : `${BASE}company/api/get_vendors/`,
  GET_VENDORS_DETAILS : `${BASE}company/api/get_vendor_details/`,
  UPDATE_VENDOR : `${BASE}company/api/update_vendor/`,
  GET_KEYPAD_DEVICES : `${BASE}company/api/get_devices/`,
  MAP_DEVICE : `${BASE}company/api/map_device/`,           
  UNMAP_DEVICE : `${BASE}company/api/unmap_device/`,     
  GET_ANDROID_TVS : `${BASE}company/api/get_android_tvs/`,  
  MAP_ANDROID_TVS : `${BASE}company/api/map_android_tvs/`,
  UNMAP_ANDROID_TVS : `${BASE}company/api/unmap_android_tvs/`,
  ORDER_COUNTS_SUMMARY : `${BASE}company/api/order_counts_summary/`,
  FILTERED_ORDERS : `${BASE}company/api/filtered_orders/`,
  ORDER_TIMELINE : `${BASE}company/api/order_status_timeline/`,
  GET_COMPANIES : `${BASE}companyadmin/api/company_lists/`,
  PRODUCT_REGISTRATION : `${BASE}companyadmin/api/product-registration/`,
  PRODUCT_AUTH_URL : `${BASE}companyadmin/api/product-authentication/`,
  LICENSE_CHECK : `${BASE}company/api/license_check/`,
  COMPANY_UPDATE_URL : `${BASE}api/company-update/`,
  UPDATE_COMPANY : `${BASE}companyadmin/api/update_company/`,
  CREATE_USER : `${BASE}company/api/create_user/`,
  GET_USERS : `${BASE}company/api/get_users/`,
  GET_MANAGER_DEVICES : `${BASE}company/api/get_manager_devices/`,
  MAP_MANAGER_DEVICES : `${BASE}company/api/map_manager_devices/`,
  UNMAP_MANAGER_DEVICES : `${BASE}company/api/unmap_manager_devices/`,
  ASSIGN_USER : `${BASE}company/api/map_user/`,
  UNASSIGN_USER : `${BASE}company/api/unmap_user/`,
  BANNER_UPLOAD : `${BASE}company/api/banner_upload/`,
  BANNER_LIST : `${BASE}company/api/banner_list/`,
  CREATE_AD_PROFILE : `${BASE}company/api/create_ad_profile/`,
  ASSIGNED_PROFILES : `${BASE}company/api/assigned_profiles/`,
  ASSIGN_AD_PROFILE : `${BASE}company/api/assign_ad_profile/`,
  UNMAP_PROFILE : `${BASE}company/api/unmap_profile/`,
  DELETE_AD_PROFILE : `${BASE}company/api/delete_ad_profile/`,
  AVAILABLE_PROFILES : `${BASE}company/api/available_profiles/`,
  GET_AD_PROFILES : `${BASE}company/api/get_ad_profiles/`,
  REGISTER_COMPANY : `${BASE}companyadmin/api/register-company/`,
  UPDATE_ORDER : `${BASE}vendors/api/update-order/`,
  OUTLET_CREATION_DATA : `${BASE}companyadmin/api/get_outlet_creation_data/`,
  COMPANY_OUTLETS : `${BASE}companyadmin/api/outlets/`,
  // Add more endpoints here
  CHECK_STATUS :`${BASE}check-status/`,
  FETCH_OUTLETS :`${BASE}api/outlets/`,
  GET_BANNERS :`${BASE}api/get_banners/`,
  GET_CHAT :`${BASE}api/webchat-messages/`,
  CREATE_CHAT : `${BASE}api/webchat-messages-create/`,
  READ_CHAT : `${BASE}api/mark-messages-read/`,
  FEEDBACK : `${BASE}api/submit_feedback/`,
  MENU : `${BASE}/api/menus/`,
  SAVE_SUBSCRIPTION : `${BASE}vendors/api/save-subscription/`,
  VENDOR_LOGOS : `${BASE}api/get_vendor_logos/`
};

// =======================
// ✅ WEB ENDPOINTS
// =======================
export const WEB_ENDPOINTS = {
  LOGIN :`${BASE}login/`,
  COMPANY_DASHBOARD : `${BASE}company/dashboard/`,
  ADMIN_DASHBOARD : `${BASE}companyadmin/dashboard/`,
  COMPANY_LIST : `${BASE}companyadmin/company_lists/`,
  OUTLET_DASHBOARD : `${BASE}outlet/dashboard/`,
  OUTLETS : `${BASE}company/outlets/`,
  COMPANY_OUTLETS : `${BASE}companyadmin/outlet_lists/`,
  UPDATE_OUTLET : `${BASE}company/update_outlet/`,
  DEVICE_LIST : `${BASE}company/device_list/`,
  ANDROID_TV_LIST : `${BASE}company/android_tv_list/`,
  ORDER_LIST : `${BASE}company/order_list/`,
  USER_LIST : `${BASE}company/user_list/`,
  PROFILE_LIST : `${BASE}company/profile_list/`,
  MAPPED_LIST : `${BASE}company/mapped_list/`,
  // Add more web endpoints here
};
