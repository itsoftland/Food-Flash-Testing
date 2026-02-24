# Vendor ID Creation and Navigation Issue Investigation

## Overview
The user is experiencing an issue where `vendor_id` is missing when navigating from the `table_booking` page to the `tracking` page during live hosting. This investigation identifies the source of `vendor_id` creation and potential reasons for its absence in production.

## 1. Who is responsible for creating `vendor_id`?
The **backend system** (specifically the `company` app) is responsible for generating the `vendor_id`.
- **Location**: [company/views.py](file:///home/silpc-010/Downloads/Food%20Flash%20Testing/company/views.py#L303-L308)
- **Logic**: When a new vendor/outlet is created via the `create_vendor` API, the system calls `generate_unique_vendor_id()`.
- **Implementation**: It generates a unique, random 6-digit integer (`100000` to `999999`) and ensures it doesn't already exist in the database.

```python
def generate_unique_vendor_id():
    while True:
        vendor_id = random.randint(100000, 999999)
        if not Vendor.objects.filter(vendor_id=vendor_id).exists():
            return vendor_id
```

## 2. Why is `vendor_id` missing during live hosting navigation?
Based on the code analysis, there are two primary reasons why `vendor_id` might be "missing" during navigation to the tracking page on a live hosting environment:

### A. URL "Cleaning" Logic
Both `table_booking.js` and `scripts.js` contain logic that **removes** the `vendor_id` parameter from the URL after it has been loaded into memory and storage.
- **In `table_booking.js`**:
  ```javascript
  // Clean URL: remove vendor_id param (keeps UX clean)
  const url = new URL(window.location.href);
  if (url.searchParams.has("vendor_id")) {
      url.searchParams.delete("vendor_id");
      history.replaceState({}, document.title, url.toString());
  }
  ```
- **In `scripts.js`**:
  ```javascript
  if (vendorFromQR) {
      await AppUtils.setCurrentVendors(vendorFromQR);
      const newUrl = window.location.origin + window.location.pathname;
      history.replaceState(null, "", newUrl);
  }
  ```
If the persistence mechanism (`localStorage`, `IndexedDB`, or `Cookies`) fails in the live environment (e.g., due to strict privacy settings or mismatched protocols), any subsequent page reload or navigation will lack the `vendor_id` because it was stripped from the URL.

### B. Absolute Base URL Misconfiguration
In `orders/views.py:book_table`, the `tracking_url` is constructed using `request.build_absolute_uri('/')`:
```python
base_url = request.build_absolute_uri('/')
tracking_url = f"{base_url}{project_name}/home/?vendor_id={vendor.vendor_id}..."
```
On live hosting (behind Nginx/Proxy), if the server is not configured with `USE_X_FORWARDED_HOST = True` and appropriate proxy headers, `request.build_absolute_uri('/')` might return `http://...` instead of `https://...`. 
- **Redirection Issue**: A redirect from `https` to `http` can cause the browser to treat the tracking page as a different origin or in-secure context, preventing it from accessing the `vendor_id` stored by the previous page.

## Recommendation
1. **Verify Proxy Settings**: Ensure the live environment correctly handles `X-Forwarded-Host` and `X-Forwarded-Proto` headers to ensure `build_absolute_uri` returns the correct `https` URL.
2. **Check Persistence**: Ensure `AppUtils.setCurrentVendors` is successfully writing to `localStorage` and `Cookies` in the live environment.
3. **QR Code Quality**: Ensure the QR code scanned by the customer actually includes the `vendor_id` in its query string.
