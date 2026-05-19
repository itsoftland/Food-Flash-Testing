from firebase_admin import messaging
import json
import logging
from django.conf import settings
from vendors.dine_flash_tv_fcm import (
    collect_vendor_tv_fcm_tokens,
    is_permanent_fcm_failure,
    remove_stale_android_device_fcm_tokens,
)

logger = logging.getLogger(__name__)


def notify_android_tv(vendor, data):
    tokens = collect_vendor_tv_fcm_tokens(vendor)
    return send_firebase_admin_multicast(vendor, tokens, json.dumps(data))


def send_firebase_admin_multicast(vendor, fcm_tokens, data_payload):
    """
    Sends a Firebase Admin SDK multicast data+notification message to Android TV devices.
    Removes permanently invalid tokens from AndroidDevice and de-dupes the token list.
    """
    fcm_tokens = list(dict.fromkeys(t for t in (fcm_tokens or []) if t))
    if not fcm_tokens:
        logger.warning("No FCM tokens provided for multicast.")
        return False, {"error": "No tokens to send"}

    try:
        project_name = getattr(settings, "PROJECT_NAME", "food_flash").lower()
        message = messaging.MulticastMessage(
            data={
                "type": "ready_orders",
                "orders": data_payload,
                "project": project_name,
            },
            notification=messaging.Notification(
                title="Order Ready!",
                body="Order Status Send to Android TV",
            ),
            tokens=fcm_tokens,
        )
        response = messaging.send_each_for_multicast(message)

        transient_failed: list[str] = []
        stale_tokens: list[str] = []

        for idx, resp in enumerate(response.responses):
            if resp.success:
                continue
            token = fcm_tokens[idx]
            error = str(resp.exception) if resp.exception else "unknown"
            logger.warning("[android_tv_fcm] Failed token: %s | Reason: %s", token, error)
            if is_permanent_fcm_failure(error):
                stale_tokens.append(token)
            else:
                transient_failed.append(token)

        if stale_tokens:
            remove_stale_android_device_fcm_tokens(vendor, stale_tokens)

        transient_failed = list(dict.fromkeys(transient_failed))
        removed_tokens = list(dict.fromkeys(stale_tokens))

        if transient_failed:
            logger.warning(
                "Multicast partially failed: %s transient failed token(s).",
                len(transient_failed),
            )
            return False, {"failed_tokens": transient_failed}

        if removed_tokens:
            logger.info(
                "Multicast: removed %s invalid token(s) from DB for vendor_id=%s.",
                len(removed_tokens),
                vendor.vendor_id,
            )
            if response.success_count:
                return True, {
                    "success_count": response.success_count,
                    "removed_tokens": removed_tokens,
                }
            return False, {"removed_tokens": removed_tokens}

        logger.info("FCM multicast successful: %s sent.", response.success_count)
        return True, {"success_count": response.success_count}

    except Exception as e:
        logger.exception("Multicast FCM error")
        return False, {"error": str(e)}
