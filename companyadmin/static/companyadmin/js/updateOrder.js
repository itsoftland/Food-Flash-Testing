// companyadmin/static/companyadmin/js/updateOrder.js

document.addEventListener("DOMContentLoaded", async () => {
  // Validate BASE exists
  if (!window.BASE) throw new Error('window.BASE is not defined');

  // ✅ Dynamically set background image for .image-section
  const imageSection = document.querySelector(".image-section");
  if (imageSection) {
    imageSection.style.backgroundImage = `url("${window.BASE}static/utils/Images/foodflashKeypad.webp")`;
    imageSection.style.backgroundRepeat = "no-repeat";
    imageSection.style.backgroundPosition = "center";
    imageSection.style.backgroundSize = "contain";
    imageSection.style.minHeight = "300px";
  }

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;
  
  const form = document.getElementById("update-order-form");
  const statusBox = document.getElementById("update-status");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const token_no = document.getElementById("token_no").value.trim();
    const counter_no = document.getElementById("counter_no").value.trim();
    const vendor_id = document.getElementById("vendor_id").value;
    const device_id = document.getElementById("device_id").value;

    const payload = {
      vendor_id,
      device_id,
      token_no,
      counter_no,
      status: "ready",
    };

    try {
      const res = await fetchWithAutoRefresh(API_ENDPOINTS.UPDATE_ORDER, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (res.ok) {
        statusBox.textContent = data.message;
        statusBox.style.display = "block";
        statusBox.classList.remove("text-danger");
        statusBox.classList.add("text-success");
        form.reset();
      } else {
        statusBox.textContent = data.message || "Failed to update order.";
        statusBox.style.display = "block";
        statusBox.classList.remove("text-success");
        statusBox.classList.add("text-danger");
      }
    } catch (err) {
      statusBox.textContent = "Something went wrong!";
      statusBox.style.display = "block";
      statusBox.classList.remove("text-success");
      statusBox.classList.add("text-danger");
      console.error("Error:", err);
    }
  });
});
