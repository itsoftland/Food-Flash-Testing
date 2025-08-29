// formFieldLabelService.js

// Field-to-label map
const fieldLabelMap = {
  place_id: "Google Review Link",
  logoInput: "Logo Image",
  menuFilesInput: "Menu Upload",
  device_mapping: "Device Mapping",
  tv_mapping: "TV Mapping",
  locationSelect: "Location",
  name: "Outlet Name",
  alias: "Alias Name",
  token_no: "Token Number",
  counter_no: "Counter Number",
  // Add more mappings as needed
};

// Main function
function getFriendlyFieldLabels(result) {
  if (!result || typeof result.message !== "string") return "";

  const message = result.message;
  const fieldsString = message.split(":")[1]?.trim() || "";

  const fields = fieldsString
    .split(",")
    .map(f => f.trim().replace(/\[\]$/, "")) // Remove trailing [] if present
    .map(f => fieldLabelMap[f] || f);        // Replace with label or keep original

  return `Please fill out the following fields: ${fields.join(", ")}`;
}

// Export the function
export default getFriendlyFieldLabels;
