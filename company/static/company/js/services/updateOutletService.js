export const OutletUpdateService = (() => {
  const updateOutlet = async (formData,fetchWithAutoRefresh,API_ENDPOINTS) => {
    try {
      const response = await fetchWithAutoRefresh(API_ENDPOINTS.UPDATE_VENDOR, {
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
        auto_delete_hours,
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
        auto_delete_hours,
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
    if (auto_delete_hours !== undefined) formData.append('auto_delete_hours', auto_delete_hours);

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
