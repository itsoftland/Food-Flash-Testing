import json
import logging
import threading
import time

from django.conf import settings
from django.db.models import Q
from firebase_admin import messaging
from vendors.fcm_log import log_fcm_send_success
from vendors.models import AndroidAPK

logger = logging.getLogger(__name__)


def _audit_fcm_success_async(**kwargs) -> None:
    try:
        from vendors.fcm_log import log_fcm_send_success

        log_fcm_send_success(**kwargs)
    except Exception:
        logger.exception("[FCM] Deferred audit log failed")


def _normalize_fcm_data_map(data: dict) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in (data or {}).items():
        if value is None:
            normalized[str(key)] = ""
        elif isinstance(value, bool):
            normalized[str(key)] = "true" if value else "false"
        else:
            normalized[str(key)] = str(value)
    return normalized


def send_fcm_multicast_raw_data(
    fcm_tokens,
    fcm_data: dict,
    *,
    android_high_priority=False,
    defer_success_audit=False,
    audit_label="",
):
    """Data-only FCM (no notification tray). Used as a wake-up for Dine Flash manager APK."""
    if not fcm_tokens:
        logger.warning("[FCM] No FCM tokens provided for raw data multicast.")
        return False, {"error": "No tokens to send"}

    try:
        payload = _normalize_fcm_data_map(fcm_data)
        multicast_kwargs = {
            "data": payload,
            "tokens": fcm_tokens,
        }
        if android_high_priority:
            multicast_kwargs["android"] = messaging.AndroidConfig(priority="high")
        message = messaging.MulticastMessage(**multicast_kwargs)
        response = messaging.send_each_for_multicast(message)

        failed_tokens = []
        failed_reasons = {}
        label = audit_label or payload.get("type") or "data"

        for idx, resp in enumerate(response.responses):
            if resp.success:
                if defer_success_audit:
                    token = fcm_tokens[idx]
                    threading.Thread(
                        target=_audit_fcm_success_async,
                        kwargs={
                            "source": "orders_fcm_multicast",
                            "label": label,
                            "token": token,
                            "payload": payload,
                        },
                        daemon=True,
                    ).start()
                else:
                    log_fcm_send_success(
                        source="orders_fcm_multicast",
                        label=label,
                        token=fcm_tokens[idx],
                        payload=payload,
                    )
                continue
            token = fcm_tokens[idx]
            error = str(resp.exception)
            failed_tokens.append(token)
            failed_reasons[token] = error
            logger.warning(f"[FCM] Raw data failed token: {token} | Reason: {error}")
            if "UNREGISTERED" in error or "INVALID_ARGUMENT" in error:
                AndroidAPK.objects.filter(token=token).delete()
                logger.info(f"[FCM] Removed invalid token from DB: {token}")

        if failed_tokens:
            return False, {"failed_tokens": failed_tokens, "reasons": failed_reasons}
        logger.info(f"[FCM] Raw data multicast successful: {response.success_count} messages sent.")
        return True, {"success_count": response.success_count}
    except Exception as e:
        logger.exception("[FCM] Error while sending raw data multicast FCM")
        return False, {"error": str(e)}


def send_fcm_multicast(
    fcm_tokens,
    data_payload,
    title=None,
    body=None,
    *,
    android_high_priority=False,
    defer_success_audit=False,
    include_notification=True,
    fcm_data_extra=None,
):
    """
    Sends a Firebase Admin SDK multicast message with both data and notification payloads.
    Logs and categorizes failures in detail.
    Allows custom title/body, falls back to defaults if not provided.
    """
    if not fcm_tokens:
        logger.warning("[FCM] No FCM tokens provided for multicast.")
        return False, {"error": "No tokens to send"}

    try:
        # Ensure payload is dict
        if isinstance(data_payload, str):
            data_payload = json.loads(data_payload)

        token_no = str(data_payload.get("token_no", ""))

        # Defaults
        default_title = "Order Tracking Started"
        default_body = f"A customer has entered their token number {token_no}. Track the order now."

        fcm_data = {
            "type": "ready_orders",
            "orders": json.dumps(data_payload),
        }
        if fcm_data_extra:
            fcm_data.update(_normalize_fcm_data_map(fcm_data_extra))
        multicast_kwargs = {
            "data": fcm_data,
            "tokens": fcm_tokens,
        }
        if include_notification:
            multicast_kwargs["notification"] = messaging.Notification(
                title=title or default_title,
                body=body or default_body,
            )
        if android_high_priority:
            multicast_kwargs["android"] = messaging.AndroidConfig(priority="high")
        message = messaging.MulticastMessage(**multicast_kwargs)

        response = messaging.send_each_for_multicast(message)

        failed_tokens = []
        failed_reasons = {}

        audit_label = title or default_title
        for idx, resp in enumerate(response.responses):
            if resp.success:
                if defer_success_audit:
                    token = fcm_tokens[idx]
                    threading.Thread(
                        target=_audit_fcm_success_async,
                        kwargs={
                            "source": "orders_fcm_multicast",
                            "label": audit_label,
                            "token": token,
                            "payload": fcm_data,
                        },
                        daemon=True,
                    ).start()
                else:
                    log_fcm_send_success(
                        source="orders_fcm_multicast",
                        label=audit_label,
                        token=fcm_tokens[idx],
                        payload=fcm_data,
                    )
                continue
            token = fcm_tokens[idx]
            error = str(resp.exception)

            failed_tokens.append(token)
            failed_reasons[token] = error

            logger.warning(f"[FCM] Failed token: {token} | Reason: {error}")

            # Clean up invalid tokens
            if "UNREGISTERED" in error or "INVALID_ARGUMENT" in error:
                AndroidAPK.objects.filter(token=token).delete()
                logger.info(f"[FCM] Removed invalid token from DB: {token}")

            # Retry hint
            if "UNAVAILABLE" in error:
                logger.warning(f"[FCM] Transient error for token {token}. Retry may succeed.")

        if failed_tokens:
            logger.warning(f"[FCM] Multicast partially failed. {len(failed_tokens)} failed tokens.")
            return False, {"failed_tokens": failed_tokens, "reasons": failed_reasons}

        logger.info(f"[FCM] Multicast successful: {response.success_count} messages sent.")
        return True, {"success_count": response.success_count}

    except Exception as e:
        logger.exception("[FCM] Error while sending multicast FCM")
        return False, {"error": str(e)}


_DINE_FLASH_MANAGER_ROLES = (
    "outlet_manager",
    "admin_manager",
    "order_manager",
    "manager",
)


def dine_flash_manager_fcm_payload(data: dict) -> dict:
    """
    Manager APK handles dine_manager-style payloads inside ready_orders, not user_reply.
    API response to the customer still uses user_reply; only the FCM copy is mapped.
    """
    payload = dict(data or {})
    if payload.get("type") != "user_reply":
        return payload
    reply = (payload.get("reply_status") or "").strip()
    payload["type"] = "dine_manager"
    payload["action"] = "message"
    payload["sender"] = "user"
    payload["status"] = reply or payload.get("status") or "message"
    payload["message"] = reply
    # Some APK builds ignore ready_orders when updated_by is customer.
    payload.pop("updated_by", None)
    return payload


def dine_flash_manager_fcm_data_extra(data: dict) -> dict[str, str]:
    """Top-level FCM data keys (outside ``orders`` JSON) for manager APK parsers."""
    mapped = dine_flash_manager_fcm_payload(data)
    return {
        "booking_id": mapped.get("booking_id"),
        "booking_no": mapped.get("booking_no"),
        "event": "customer_chat",
        "project": "dine_flash",
        "inner_type": mapped.get("type"),
    }


def send_dine_flash_manager_chat_wakeup(vendor, data: dict) -> tuple[bool, dict]:
    """
    Data-only booking_update wake-up (same pattern as TV FCM).
    Manager list/chat screens refresh from APIs after this trigger.
    """
    tokens = collect_manager_fcm_tokens(vendor)
    if not tokens:
        return False, {"error": "No tokens"}

    reply = (data.get("reply_status") or "").strip()
    flat = {
        "type": "booking_update",
        "booking_id": data.get("booking_id"),
        "booking_no": data.get("booking_no"),
        "project": "dine_flash",
        "event": "customer_chat",
        "status": reply or data.get("status") or "",
    }
    return send_fcm_multicast_raw_data(
        tokens,
        flat,
        android_high_priority=True,
        defer_success_audit=True,
        audit_label="Customer chat wake-up",
    )


def collect_manager_fcm_tokens(vendor) -> list[str]:
    """
    Resolve outlet-manager FCM registration tokens for a vendor.

    Dine Flash: devices were historically saved without ``user_profile`` even when
    ``manager_id`` was supplied at registration. Include those legacy rows via
    ``admin_outlet`` so pushes are not silently dropped.
    """
    is_dine_flash = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash"
    if not is_dine_flash:
        return [
            t
            for t in AndroidAPK.objects.filter(user_profile__vendor=vendor).values_list(
                "token", flat=True
            )
            if (t or "").strip()
        ]

    outlet_id = vendor.admin_outlet_id
    devices = (
        AndroidAPK.objects.filter(
            Q(user_profile__vendor=vendor)
            | Q(
                admin_outlet_id=outlet_id,
                user_profile__isnull=True,
            )
            | Q(
                admin_outlet_id=outlet_id,
                user_profile__role__in=_DINE_FLASH_MANAGER_ROLES,
            )
        )
        .order_by("-updated_at", "-id")
        .only("token", "mac_address", "id")
    )
    # Same physical handset re-registering leaves stale tokens; only use the newest per MAC.
    tokens: list[str] = []
    seen_mac: set[str] = set()
    for device in devices:
        mac_key = (device.mac_address or "").strip() or f"id:{device.id}"
        if mac_key in seen_mac:
            continue
        seen_mac.add(mac_key)
        token = (device.token or "").strip()
        if token:
            tokens.append(token)
    return tokens


def send_to_managers(vendor, data, title=None, body=None, *, defer_success_audit=False):
    """
    Sends a notification to all registered AndroidAPK devices for the given vendor.
    Supports optional custom title/body.
    """
    tokens = collect_manager_fcm_tokens(vendor)

    if not tokens:
        logger.warning(
            "[FCM] No manager tokens | vendor=%s | vendor_id=%s | outlet_id=%s",
            vendor.name,
            vendor.vendor_id,
            vendor.admin_outlet_id,
        )
        return False, {"error": "No tokens"}

    is_dine_flash = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash"
    is_customer_chat = is_dine_flash and (data or {}).get("type") == "user_reply"
    fcm_data = dine_flash_manager_fcm_payload(data) if is_dine_flash else data
    android_high_priority = is_customer_chat
    fcm_data_extra = dine_flash_manager_fcm_data_extra(data) if is_customer_chat else None
    if is_customer_chat:
        logger.info(
            "[FCM] Dine Flash customer chat push | vendor_id=%s | token_count=%s | fcm_type=%s",
            vendor.vendor_id,
            len(tokens),
            (fcm_data or {}).get("type"),
        )
    return send_fcm_multicast(
        tokens,
        fcm_data,
        title=title,
        body=body,
        android_high_priority=android_high_priority,
        defer_success_audit=defer_success_audit,
        fcm_data_extra=fcm_data_extra,
    )


def _fcm_failure_is_transient(info: dict) -> bool:
    reasons = (info or {}).get("reasons") or {}
    for err in reasons.values():
        upper = str(err).upper()
        if "UNAVAILABLE" in upper or "INTERNAL" in upper or "TIMEOUT" in upper:
            return True
    return False


def send_dine_flash_manager_chat_sync(vendor, data, title, body):
    """
    Dine Flash customer chat FCM.

    Manager handsets register via ``register_android_device`` (``AndroidDevice``) and
    refresh on ``booking_update`` — same path as allocate. ``AndroidAPK`` is only a
    fallback for legacy registrations.
    """
    if (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() != "dine_flash":
        return False, {"error": "not_dine_flash"}

    from vendors.dine_flash_tv_fcm import send_dine_flash_customer_chat_fcm_sync

    ok = False
    info: dict = {}
    for attempt in range(3):
        ok, info = send_dine_flash_customer_chat_fcm_sync(vendor, data)
        if ok:
            return ok, info
        if attempt < 2 and _fcm_failure_is_transient(info):
            time.sleep(0.2 * (attempt + 1))
            continue
        break

    apk_tokens = collect_manager_fcm_tokens(vendor)
    if apk_tokens:
        logger.info(
            "[FCM] Dine Flash customer chat falling back to AndroidAPK | vendor_id=%s | token_count=%s",
            vendor.vendor_id,
            len(apk_tokens),
        )
        for attempt in range(3):
            ok, info = send_to_managers(
                vendor,
                data,
                title=title,
                body=body,
                defer_success_audit=True,
            )
            if ok:
                return ok, info
            if attempt < 2 and _fcm_failure_is_transient(info):
                time.sleep(0.2 * (attempt + 1))
                continue
            break

    if not ok:
        logger.warning(
            "[FCM] Dine Flash customer chat push failed | vendor_id=%s | info=%s",
            vendor.vendor_id,
            info,
        )
    return ok, info
