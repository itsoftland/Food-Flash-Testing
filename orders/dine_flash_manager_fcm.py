"""
Dine Flash only: outlet-manager (AndroidAPK) FCM for customer chat and key booking events.

Other flavours keep using orders.utils.send_to_managers unchanged.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from firebase_admin import messaging

from vendors.fcm_log import log_fcm_send_success
from vendors.models import AndroidAPK, Vendor

logger = logging.getLogger(__name__)

_FCM_BATCH_SIZE = 500


def dine_flash_manager_fcm_enabled() -> bool:
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash"


def _manager_fcm_tokens(vendor: Vendor) -> list[str]:
    return list(
        AndroidAPK.objects.filter(user_profile__vendor=vendor)
        .values_list("token", flat=True)
    )


def send_dine_flash_manager_customer_message_fcm(
    vendor: Vendor,
    data: dict[str, Any],
    title: str,
    body: str,
) -> tuple[bool, dict[str, Any]]:
    """
    High-priority manager push when a customer sends a chat message.
    Uses data type ``user_reply`` so the manager app can refresh chat immediately.
    """
    if not dine_flash_manager_fcm_enabled():
        return False, {"error": "not_dine_flash"}

    tokens = _manager_fcm_tokens(vendor)
    if not tokens:
        logger.warning(
            "[dine_flash_manager_fcm] No manager tokens vendor_id=%s",
            getattr(vendor, "vendor_id", None),
        )
        return False, {"error": "No tokens"}

    payload = dict(data)
    payload.setdefault("type", "user_reply")

    fcm_data = {
        "type": "user_reply",
        "orders": json.dumps(payload),
        "project": "dine_flash",
    }
    if payload.get("booking_id") is not None:
        fcm_data["booking_id"] = str(payload["booking_id"])

    android_cfg = messaging.AndroidConfig(priority="high")
    notification = messaging.Notification(title=title, body=body)

    failed_tokens: list[str] = []
    success_count = 0

    for offset in range(0, len(tokens), _FCM_BATCH_SIZE):
        batch = tokens[offset : offset + _FCM_BATCH_SIZE]
        message = messaging.MulticastMessage(
            data=fcm_data,
            notification=notification,
            android=android_cfg,
            tokens=batch,
        )
        response = messaging.send_each_for_multicast(message)
        for idx, resp in enumerate(response.responses):
            if resp.success:
                success_count += 1
                log_fcm_send_success(
                    source="dine_flash_manager_fcm",
                    vendor_id=getattr(vendor, "vendor_id", None),
                    label="user_reply",
                    token=batch[idx],
                    payload=fcm_data,
                )
                continue
            token = batch[idx]
            error = str(resp.exception) if resp.exception else "unknown"
            failed_tokens.append(token)
            logger.warning(
                "[dine_flash_manager_fcm] Failed token=%s reason=%s",
                token,
                error,
            )
            if "UNREGISTERED" in error.upper() or "INVALID_ARGUMENT" in error.upper():
                AndroidAPK.objects.filter(token=token).delete()

    if failed_tokens and not success_count:
        return False, {"failed_tokens": failed_tokens}

    logger.info(
        "[dine_flash_manager_fcm] user_reply sent vendor_id=%s success=%s failed=%s",
        getattr(vendor, "vendor_id", None),
        success_count,
        len(failed_tokens),
    )
    return True, {"success_count": success_count, "failed_tokens": failed_tokens}
