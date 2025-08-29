document.addEventListener("DOMContentLoaded", () => {
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
      const res = await fetch("/vendors/api/update-order/", {
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
