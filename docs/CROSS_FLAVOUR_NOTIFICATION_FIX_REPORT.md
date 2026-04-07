# Cross-Flavour Notification Isolation Report

## Issue Summary

Food Flash and Airline Flash were leaking notifications across flavours when used on the same browser profile.

### Observed Problem
- A manager message sent from Food Flash was visible in Airline Flash web.
- This happened even when basic frontend filtering existed.

### Why It Happened
1. Browser identity and session state were partially shared in browser storage.
2. Push payload handling was not strict enough in all paths.
3. Backend subscription targeting could match by `token_no` + vendor (not strict enough when token numbers collide across flavours).

---

## Root Cause Details

### 1) Shared browser/session identity
Historically, storage keys were not fully flavour-scoped in every code path, so context (active vendor, selected vendors, chat context) could bleed between flavours.

### 2) Insufficient push gate checks
Service worker/page checks were present but needed stronger normalization and stricter routing to same-flavour clients only.

### 3) Backend matching by token number could collide
In `notify_web_push`, subscriptions were selected using token number and vendor:

```python
# BEFORE
PushSubscription.objects.filter(
    tokens__token_no=order.token_no,
    tokens__vendor=vendor
)
```

Since Food and Airline share the `Order` model and both use `token_no`, a matching `token_no` across flavours could include wrong subscriptions.

---

## Files Changed and Why

## `vendors/utils.py`

### What changed
- Subscription selection for web push now targets subscriptions linked to the **exact Order instance**.

### Why
- Prevent cross-flavour leakage due to token number collisions.

### Before
```python
subscriptions = list(
    PushSubscription.objects.filter(
        tokens__token_no=order.token_no,
        tokens__vendor=vendor
    ).distinct()
)
```

### After
```python
subscriptions = list(
    PushSubscription.objects.filter(tokens=order).distinct()
)
```

---

## `vendors/views.py` (`save_subscription`)

### What changed
- Persistence logic uses flavour-scoped `browser_id` as primary identity.
- Added guard to reject endpoint relinking to a different `browser_id` (HTTP 409).

### Why
- Avoid re-merging cross-flavour identities through shared endpoint updates.

### Before
```python
subscription = PushSubscription.objects.filter(endpoint=endpoint).first()
if not subscription:
    subscription = PushSubscription.objects.filter(browser_id=browser_id).first()
```

### After
```python
subscription = PushSubscription.objects.filter(browser_id=browser_id).first()
if not subscription:
    endpoint_subscription = PushSubscription.objects.filter(endpoint=endpoint).first()
    if endpoint_subscription and endpoint_subscription.browser_id != browser_id:
        return Response({"error": "...already registered..."}, status=409)
```

---

## `orders/templates/orders/service-worker.js`

### What changed
- Added strict project/flavour matching with normalized comparison.
- Added project inference from client URL.
- Broadcast (`PUSH_RECEIVED`, `PUSH_STATUS_UPDATE`) only to clients matching current flavour.
- Retained/dispatched guards for notification click restore flow.

### Why
- Prevent service worker from forwarding pushes to unrelated flavour tabs under same origin.

### Before
```javascript
if (EXPECTED_PROJECT && incomingProject !== EXPECTED_PROJECT) {
  return;
}
for (const client of allClients) {
  client.postMessage({ type: "PUSH_RECEIVED", payload });
}
```

### After
```javascript
if (EXPECTED_PROJECT && !projectsMatch(EXPECTED_PROJECT, incomingProject)) {
  return;
}
for (const client of allClients) {
  const clientProject = inferProjectFromUrl(client?.url);
  if (EXPECTED_PROJECT && !projectsMatch(EXPECTED_PROJECT, clientProject)) continue;
  client.postMessage({ type: "PUSH_RECEIVED", payload });
}
```

---

## `orders/static/orders/js/scripts.js`

### What changed
- Added normalized project matcher (`projectsMatch`) and path-based flavour inference.
- Applied strict filtering for `PUSH_STATUS_UPDATE`.
- Applied project validation for `OPEN_CHAT`.
- Replaced unscoped storage accesses with project-scoped access (`AppUtils.storageGet`, `AppUtils.getActiveVendor`, `AppUtils.getStoredVendors`) in key paths.

### Why
- Ensure UI never renders cross-flavour pushes and avoid leaking active context across flavours.

### Before
```javascript
if (expectedProject && incomingProject !== expectedProject) {
  return;
}
let selectedVendors = JSON.parse(localStorage.getItem('selectedVendors')) || [];
const vendorId = localStorage.getItem("activeVendor");
```

### After
```javascript
if (!projectsMatch(expectedProject, incomingProject)) {
  return;
}
let selectedVendors = AppUtils.getStoredVendors() || [];
const vendorId = await AppUtils.getActiveVendor();
```

---

## `orders/static/orders/js/services/chatService.js`

### What changed
- Replaced direct `localStorage` usage for active vendor metadata with project-scoped `AppUtils.storageGet/storageSet`.
- `saveChat` now resolves active vendor via scoped helper (`AppUtils.getActiveVendor()`).

### Why
- Prevent chat/session context from crossing flavours in same browser profile.

### Before
```javascript
localStorage.setItem("activeVendor", vendorId);
let ratingLink = localStorage.getItem("activeVendorRatingLink");
const activeVendorId = localStorage.getItem("activeVendor");
```

### After
```javascript
AppUtils.storageSet("activeVendor", vendorId);
let ratingLink = AppUtils.storageGet("activeVendorRatingLink");
const activeVendorId = await AppUtils.getActiveVendor();
```

---

## `orders/static/orders/js/services/menuModalService.js`

### What changed
- Replaced direct unscoped localStorage reads for `activeVendor` and `activeVendorRatingLink` with scoped helper APIs.

### Why
- Keep footer actions and menu/rating context flavour-isolated.

### Before
```javascript
const activeVendorId = localStorage.getItem("activeVendor");
let ratingLink = localStorage.getItem("activeVendorRatingLink");
```

### After
```javascript
const activeVendorId = AppUtils.storageGet("activeVendor");
let ratingLink = AppUtils.storageGet("activeVendorRatingLink");
```

---

## Data/Behavior Impact

1. **Isolation improved**
   - Food and Airline should no longer share push-driven UI updates when both are used in same browser profile.

2. **Stricter filtering**
   - Pushes missing valid project identity may be ignored by web clients.

3. **Endpoint conflict handling**
   - `save_subscription` can return 409 when endpoint is tied to another browser identity; client may need refresh/re-subscribe.

4. **Subscription targeting precision**
   - Pushes target only subscriptions linked to exact order relation.

---

## Possible Future Risks / Considerations

1. **Legacy payload paths**
   - Any future push code path that omits `project` may be filtered out by client guards.

2. **Operational support load**
   - Users with old service worker/cache state may need one-time unregister + hard reload.

3. **Token linking expectations**
   - If product later requires one browser to watch multiple unrelated orders simultaneously, current `tokens.clear()` behavior in subscription save flow may need redesign.

4. **Project naming variants**
   - New flavour names should be included in normalization/inference logic where needed.

5. **Local testing limitations**
   - Switching only `.env` project name is a partial test; true isolation should be verified with both flavours active concurrently under same browser profile.

---

## Recommended Test Checklist

1. Unregister service worker and clear cache/storage once.
2. Open Food and Airline in same browser profile.
3. Subscribe separately in both flavours.
4. Send manager message in Food.
5. Verify:
   - Food receives the update.
   - Airline does not render/update from that push.
6. Repeat inverse direction (Airline -> Food).

