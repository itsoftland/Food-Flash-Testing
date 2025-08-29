// Import a utility function that automatically refreshes auth tokens if needed before fetching
import { fetchWithAutoRefresh } from '/static/utils/js/services/authFetchService.js';

// Wait for the DOM to fully load before running any script logic
document.addEventListener('DOMContentLoaded', async () => {

  // Reference to the HTML container where vendor cards will be inserted
  const vendorListContainer = document.getElementById('vendor-list');

  // ================================
  // 1. Fetch Vendor Data from API
  // ================================
  try {
    // Make an authenticated GET request to fetch vendor data
    const response = await fetchWithAutoRefresh('/company/api/get_vendors/', {
      method: 'GET'
    });

    // If the request fails (non-200 status), show an error
    if (!response.ok) {
      throw new Error("Failed to load vendors");
    }

    // Parse the JSON response
    const data = await response.json();
    const vendors = data.vendors || [];
    console.log(vendors); // Log for debugging purposes

    // ================================
    // 2. Handle Empty Vendor List
    // ================================
    if (vendors.length === 0) {
      // Show a warning alert if there are no vendors
      vendorListContainer.innerHTML = `
        <div class="col-12">
          <div class="alert alert-warning">No vendors have been added yet.</div>
        </div>`;
      return; // Exit early
    }

    // ============================================
    // 3. Render Each Vendor Card Dynamically
    // ============================================
    vendors.forEach(vendor => {
      // Create a Bootstrap grid column for each vendor
      const col = document.createElement('div');
      col.className = 'col-lg-3 col-md-4 col-sm-6 col-12 mb-4';

      // Set the inner HTML of the vendor card
      col.innerHTML = `
        <div class="vendor-tile">
          <div class="inner">
            <h4>${vendor.name}</h4>
            <p>Location: ${vendor.location || 'N/A'}</p>
          </div>
          <div class="icon">
            <i class="fas fa-store"></i>
          </div>
          <a data-vendor-id="${vendor.vendor_id}" class="small-box-footer">
            View Details <i class="fas fa-arrow-circle-right"></i>
          </a>
        </div>
      `;

      // Append the card to the container
      vendorListContainer.appendChild(col);
    });

  } catch (error) {
    // ====================================
    // 4. Handle Fetch Errors Gracefully
    // ====================================
    console.error('Error loading vendor data:', error);
    vendorListContainer.innerHTML = `
      <div class="col-12">
        <div class="alert alert-warning">Something went wrong while loading vendor data.</div>
      </div>`;
  }

  // ============================================
  // 5. Navigate to Outlet Update Page on Click
  // ============================================
  vendorListContainer.addEventListener('click', function (e) {
    // Use event delegation to capture clicks on any "View Details" links
    const link = e.target.closest('a[data-vendor-id]');
    if (link) {
      e.preventDefault(); // Prevent default link behavior
      const vendorId = link.dataset.vendorId;

      // Redirect to the outlet update page with the selected vendor ID
      window.location.href = `/company/update_outlet/?vendor_id=${vendorId}`;
    }
  });

});
