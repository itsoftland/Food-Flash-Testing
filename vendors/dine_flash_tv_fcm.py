"""
Dine Flash: FCM data messages to Android TV devices on booking status transitions.

Used only as a wake-up trigger; clients must refresh from APIs. Runs independently of
MQTT / vendor tv_communication_mode so TVs that register an FCM token still receive pushes.
"""
from __future__ import annotations

import logging
import threading
from typing import List, Sequence

from django.conf import settings
from django.db.models import Q
from firebase_admin import messaging

from vendors.models import AndroidDevice, Order, Vendor

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


def is_permanent_fcm_failure(error: str) -> bool:
    return "UNREGISTERED" in error or "INVALID_ARGUMENT" in error


def remove_stale_android_device_fcm_tokens(vendor: Vendor, tokens: Sequence[str]) -> None:
    """Drop invalid FCM registration tokens so we stop retrying dead endpoints."""
    unique_tokens = list(dict.fromkeys(t for t in tokens if t))
    if not unique_tokens:
        return

    for failed in unique_tokens:
        cleared = AndroidDevice.objects.filter(vendor=vendor).filter(
            Q(fcm_token=failed) | Q(token=failed)
        ).update(fcm_token=None, token="")
        if cleared:
            logger.info(
                "[dine_flash_fcm] Cleared invalid FCM token on %s device(s) vendor_id=%s",
                cleared,
                vendor.vendor_id,
            )


def _send_batches(vendor: Vendor, fcm_tokens: Sequence[str], data: dict[str, str]) -> None:
    stale_tokens: List[str] = []
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
            if is_permanent_fcm_failure(err):
                stale_tokens.append(batch[idx])

    remove_stale_android_device_fcm_tokens(vendor, stale_tokens)


def _send_dine_flash_tv_data_fcm_sync(vendor_id: int, data: dict[str, str], label: str) -> None:
    try:
        try:
            vendor = Vendor.objects.select_related("admin_outlet").get(pk=vendor_id)
        except Vendor.DoesNotExist:
            logger.warning("[dine_flash_fcm] Vendor id=%s not found; skip %s", vendor_id, label)
            return

        if not dine_flash_fcm_scope_applies(vendor):
            return

        fcm_tokens = collect_vendor_tv_fcm_tokens(vendor)
        if not fcm_tokens:
            logger.debug(
                "[dine_flash_fcm] No FCM tokens for vendor_id=%s; skip %s",
                vendor.vendor_id,
                label,
            )
            return

        _send_batches(vendor, fcm_tokens, data)
        logger.info(
            "[dine_flash_fcm] %s sent vendor_id=%s devices=%s",
            label,
            vendor.vendor_id,
            len(fcm_tokens),
        )
    except Exception:
        logger.exception("[dine_flash_fcm] Error during %s vendor_pk=%s", label, vendor_id)


def _normalize_status(raw_status: str | None) -> str:
    return (raw_status or "").strip().lower()


def should_notify_dine_flash_booking_status_transition(
    previous_status: str | None,
    new_status: str | None,
) -> bool:
    """
    Notify only when booking enters or leaves allocated.
    """
    prev = _normalize_status(previous_status)
    new = _normalize_status(new_status)
    return (prev != "allocated" and new == "allocated") or (
        prev == "allocated" and new != "allocated"
    )


def send_dine_flash_booking_status_fcm_sync(
    vendor_id: int,
    booking_id: int,
    current_status: str,
) -> None:
    """
    Sends data-only FCM to all TV devices mapped to the vendor. Logs failures; never raises.
    Includes booking_no / seat so TVs can update a row without a full HTTP refresh.
    """
    data: dict[str, str] = {
        "type": "booking_update",
        "status": _normalize_status(current_status),
        "booking_id": str(booking_id),
        "project": "dine_flash",
        "booking_no": "",
        "seat_no": "",
        "table_booking_no_display": "",
    }
    try:
        order = Order.objects.filter(pk=booking_id, vendor_id=vendor_id).only(
            "table_booking_no", "seat_no"
        ).first()
        if order:
            booking_no = (order.table_booking_no or "").strip() if order.table_booking_no else ""
            raw_seat = order.seat_no
            seat = (
                raw_seat.strip()
                if isinstance(raw_seat, str)
                else (str(raw_seat).strip() if raw_seat is not None else "")
            )
            data["booking_no"] = booking_no
            data["seat_no"] = seat
            if booking_no and seat:
                data["table_booking_no_display"] = f"{booking_no} [{seat}]"
            elif booking_no:
                data["table_booking_no_display"] = booking_no
            elif seat:
                data["table_booking_no_display"] = f"[{seat}]"
    except Exception:
        logger.exception(
            "[dine_flash_fcm] Could not enrich booking_update booking_id=%s vendor_pk=%s",
            booking_id,
            vendor_id,
        )

    _send_dine_flash_tv_data_fcm_sync(
        vendor_id=vendor_id,
        data=data,
        label=f"Booking status trigger booking_id={booking_id} status={data['status']}",
    )


def schedule_dine_flash_booking_status_fcm(
    vendor_id: int,
    booking_id: int,
    current_status: str,
) -> None:
    """Fire-and-forget background send so booking HTTP flow is never blocked."""

    def _run() -> None:
        try:
            send_dine_flash_booking_status_fcm_sync(vendor_id, booking_id, current_status)
        except Exception:
            logger.exception(
                "[dine_flash_fcm] Background task failed vendor_id=%s booking_id=%s status=%s",
                vendor_id,
                booking_id,
                current_status,
            )

    threading.Thread(
        target=_run,
        name=f"dine-flash-fcm-{booking_id}-{_normalize_status(current_status)}",
        daemon=True,
    ).start()


def send_dine_flash_configuration_updated_fcm_sync(vendor_id: int) -> None:
    data = {
        "type": "configuration_updated",
        "project": "dine_flash",
    }
    _send_dine_flash_tv_data_fcm_sync(
        vendor_id=vendor_id,
        data=data,
        label="Configuration update trigger",
    )


def schedule_dine_flash_configuration_updated_for_vendors(vendor_ids: Sequence[int]) -> None:
    """
    Fire-and-forget notification for one or many vendors.
    Dedupes vendor IDs to avoid unnecessary duplicate notifications for the same change.
    """
    deduped_vendor_ids = []
    seen = set()
    for raw in vendor_ids or []:
        try:
            vendor_id = int(raw)
        except (TypeError, ValueError):
            continue
        if vendor_id <= 0 or vendor_id in seen:
            continue
        seen.add(vendor_id)
        deduped_vendor_ids.append(vendor_id)

    if not deduped_vendor_ids:
        return

    def _run() -> None:
        for vendor_id in deduped_vendor_ids:
            try:
                send_dine_flash_configuration_updated_fcm_sync(vendor_id)
            except Exception:
                logger.exception(
                    "[dine_flash_fcm] Background configuration task failed vendor_id=%s",
                    vendor_id,
                )

    threading.Thread(
        target=_run,
        name=f"dine-flash-config-fcm-{'-'.join(str(v) for v in deduped_vendor_ids)}",
        daemon=True,
    ).start()


def send_dine_flash_booking_allocated_fcm_sync(vendor_id: int, booking_id: int) -> None:
    """Backward-compatible wrapper for old callers."""
    send_dine_flash_booking_status_fcm_sync(vendor_id, booking_id, "allocated")


def schedule_dine_flash_booking_allocated_fcm(vendor_id: int, booking_id: int) -> None:
    """Backward-compatible wrapper for old callers."""
    schedule_dine_flash_booking_status_fcm(vendor_id, booking_id, "allocated")
