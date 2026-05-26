import json
import logging

from django.conf import settings
from firebase_admin import messaging
from vendors.fcm_log import log_fcm_send_success
from vendors.models import AndroidAPK

logger = logging.getLogger(__name__)


def dine_flash_manager_fcm_payload(data: dict) -> dict:
    """
    Dine Flash only: remap customer chat for the manager APK FCM copy.

    Manager APK handles ``dine_manager`` inside ``ready_orders``, not ``user_reply``.
    The HTTP API response to the customer keeps ``user_reply``; only FCM is mapped.
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


def send_fcm_multicast(fcm_tokens, data_payload, title=None, body=None):
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
        message = messaging.MulticastMessage(
            data=fcm_data,
            notification=messaging.Notification(
                title=title or default_title,
                body=body or default_body,
            ),
            tokens=fcm_tokens,
        )

        response = messaging.send_each_for_multicast(message)

        failed_tokens = []
        failed_reasons = {}

        for idx, resp in enumerate(response.responses):
            if resp.success:
                log_fcm_send_success(
                    source="orders_fcm_multicast",
                    label=title or default_title,
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


def send_to_managers(vendor, data, title=None, body=None):
    """
    Sends a notification to all registered AndroidAPK devices for the given vendor.
    Supports optional custom title/body.
    """
    android_apk_devices = AndroidAPK.objects.filter(user_profile__vendor=vendor)
    tokens = list(android_apk_devices.values_list("token", flat=True))

    if not tokens:
        logger.warning(f"[FCM] No tokens found for vendor {vendor.name}")
        return False, {"error": "No tokens"}

    is_dine_flash = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash"
    fcm_payload = dine_flash_manager_fcm_payload(data) if is_dine_flash else data
    return send_fcm_multicast(tokens, fcm_payload, title=title, body=body)
