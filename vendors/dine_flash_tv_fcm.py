"""
Dine Flash: FCM data messages to Android TV devices on booking -> allocated transitions.

Used only as a wake-up trigger; clients must refresh from APIs. Runs independently of
MQTT / vendor tv_communication_mode so TVs that register an FCM token still receive pushes.
"""
from __future__ import annotations

import logging
import threading
from typing import List, Sequence

from django.conf import settings
from firebase_admin import messaging

from vendors.models import AndroidDevice, Vendor

logger = logging.getLogger(__name__)

_FCM_BATCH_SIZE = 500


def dine_flash_fcm_scope_applies(vendor: Vendor) -> bool:
    """True only for Dine Flash (not buffet or other flavours)."""
    outlet = getattr(vendor, "admin_outlet", None)
    outlet_code = (getattr(outlet, "project_code", None) or "").strip().lower()
    server = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    if server == "dine_flash_buffet" or outlet_code == "dine_flash_buffet":
        return False
    return outlet_code == "dine_flash" or server == "dine_flash"


def _device_fcm_registration_token(device: AndroidDevice) -> str:
    raw = (device.fcm_token or device.token or "").strip()
    return raw


def collect_vendor_tv_fcm_tokens(vendor: Vendor) -> List[str]:
    tokens: List[str] = []
    for device in AndroidDevice.objects.filter(vendor=vendor).only("token", "fcm_token"):
        t = _device_fcm_registration_token(device)
        if t:
            tokens.append(t)
    # De-dupe while keeping order
    return list(dict.fromkeys(tokens))


def _send_batches(fcm_tokens: Sequence[str], data: dict[str, str]) -> None:
    for i in range(0, len(fcm_tokens), _FCM_BATCH_SIZE):
        batch = list(fcm_tokens[i : i + _FCM_BATCH_SIZE])
        message = messaging.MulticastMessage(
            data=data,
            tokens=batch,
            android=messaging.AndroidConfig(priority="high"),
        )
        response = messaging.send_each_for_multicast(message)
        for idx, resp in enumerate(response.responses):
            if resp.success:
                continue
            err = str(resp.exception) if resp.exception else "unknown"
            logger.warning("[dine_flash_fcm] Send failed for token index %s: %s", idx, err)


def send_dine_flash_booking_allocated_fcm_sync(vendor_id: int, booking_id: int) -> None:
    """
    Sends data-only FCM to all TV devices mapped to the vendor. Logs failures; never raises.
    """
    try:
        try:
            vendor = Vendor.objects.select_related("admin_outlet").get(pk=vendor_id)
        except Vendor.DoesNotExist:
            logger.warning("[dine_flash_fcm] Vendor id=%s not found; skip FCM", vendor_id)
            return

        if not dine_flash_fcm_scope_applies(vendor):
            return

        fcm_tokens = collect_vendor_tv_fcm_tokens(vendor)
        if not fcm_tokens:
            logger.debug(
                "[dine_flash_fcm] No FCM tokens for vendor_id=%s; skip",
                vendor.vendor_id,
            )
            return

        data = {
            "type": "booking_update",
            "status": "allocated",
            "booking_id": str(booking_id),
            "project": "dine_flash",
        }

        _send_batches(fcm_tokens, data)
        logger.info(
            "[dine_flash_fcm] Allocated trigger sent vendor_id=%s booking_id=%s devices=%s",
            vendor.vendor_id,
            booking_id,
            len(fcm_tokens),
        )
    except Exception:
        logger.exception(
            "[dine_flash_fcm] Error vendor_pk=%s booking_id=%s",
            vendor_id,
            booking_id,
        )


def schedule_dine_flash_booking_allocated_fcm(vendor_id: int, booking_id: int) -> None:
    """Fire-and-forget background send so booking HTTP flow is never blocked."""

    def _run() -> None:
        try:
            send_dine_flash_booking_allocated_fcm_sync(vendor_id, booking_id)
        except Exception:
            logger.exception(
                "[dine_flash_fcm] Background task failed vendor_id=%s booking_id=%s",
                vendor_id,
                booking_id,
            )

    threading.Thread(
        target=_run,
        name=f"dine-flash-fcm-{booking_id}",
        daemon=True,
    ).start()
