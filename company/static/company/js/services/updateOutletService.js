import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';

export const OutletUpdateService = (() => {
  const updateOutlet = async (formData) => {
    try {
      const response = await fetchWithAutoRefresh('/company/api/update_vendor/', {
        method: 'PATCH',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.error || 'Outlet update failed');
      }

      return { success: true, data };
    } catch (error) {
      console.error('Outlet update error:', error);
      return { success: false, error: error.message || 'Something went wrong' };
    }
  };

  const buildFormData = ({
        vendor_id,
        name,
        alias_name,
        location,
        place_id,
        location_id,
        logoFile,
        menuFiles = [],
        deviceMapping = [],
        tvMapping = [],
    }) => {
    console.log({
        vendor_id,
        name,
        alias_name,
        location,
        place_id,
        location_id,
        logoFile,
        menuFiles,
        deviceMapping,
        tvMapping,
    });
    const formData = new FormData();

    formData.append('vendor_id', vendor_id);
    if (name) formData.append('name', name);
    if (alias_name) formData.append('alias_name', alias_name);
    if (location) formData.append('location', location);
    if (place_id) formData.append('place_id', place_id);
    if (location_id) formData.append('location_id', location_id);

    if (logoFile) formData.append('logo', logoFile);

    menuFiles.forEach(file => formData.append('menus', file));
    deviceMapping.forEach(serial => formData.append('device_mapping[]', serial));
    tvMapping.forEach(mac => formData.append('tv_mapping[]', mac));

    return formData;
  };

  return {
    updateOutlet,
    buildFormData,
  };
})();
