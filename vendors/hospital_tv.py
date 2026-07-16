"""
Hospital Flash only: TV payload builder and transport dispatch for called patients.

Displays currently called patients using Order.table_booking_no (e.g. LAB-12).
Reuses existing MQTT and Firebase TV infrastructure without touching get_last_tokens().
"""

import logging

from django.conf import settings

from vendors.models import Order

logger = logging.getLogger(__name__)


def is_hospital_flash():
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "hospital_flash"


def get_hospital_called_booking_nos(vendor, *, start_dt, end_dt, limit=None):
    """
    Return table_booking_no strings for currently called patients in the business day.

    Results are ordered by most recently updated first and capped at token_display_limit.
    """
    if limit is None:
        config = getattr(vendor, "config", None)
        limit = getattr(config, "token_display_limit", None) or 8

    booking_nos = list(
        Order.objects.filter(
            vendor=vendor,
            status="called",
            created_at__range=(start_dt, end_dt),
        )
        .exclude(table_booking_no__isnull=True)
        .exclude(table_booking_no="")
        .order_by("-updated_at")
        .values_list("table_booking_no", flat=True)[:limit]
    )
    return booking_nos


def build_hospital_tv_payload(vendor, booking_nos):
    """Build the standard Hospital TV snapshot payload (string tokens, no padding)."""
    config = vendor.config
    tokens = list(booking_nos)
    return {
        "vendor_id": vendor.vendor_id,
        "mode": config.mqtt_mode,
        "total_count": len(tokens),
        "tokens": tokens,
    }


def refresh_hospital_tv(vendor, *, start_dt, end_dt):
    """
    Push the current called-patient snapshot to Hospital TVs.

    Dispatches via MQTT or Firebase based on vendor.config.tv_communication_mode.
    TV failures are logged and returned but never raised to callers.
    """
    if not is_hospital_flash():
        logger.debug("[refresh_hospital_tv] skipped: not hospital_flash deployment")
        return {"skipped": True, "reason": "not_hospital_flash"}

    try:
        config = vendor.config
    except Exception:
        logger.exception(
            "[refresh_hospital_tv] vendor config missing vendor_id=%s",
            getattr(vendor, "vendor_id", None),
        )
        return {"success": False, "error": "no_config"}

    limit = config.token_display_limit
    booking_nos = get_hospital_called_booking_nos(
        vendor, start_dt=start_dt, end_dt=end_dt, limit=limit
    )
    payload = build_hospital_tv_payload(vendor, booking_nos)
    mode = (config.tv_communication_mode or "").strip()

    if mode == "MQTT":
        try:
            from vendors.services.order_service import send_order_update

            success = send_order_update(vendor, payload)
            if not success:
                logger.warning(
                    "[refresh_hospital_tv] MQTT publish failed vendor_id=%s payload=%s",
                    vendor.vendor_id,
                    payload,
                )
            return {"success": bool(success), "transport": "MQTT", "payload": payload}
        except Exception:
            logger.exception(
                "[refresh_hospital_tv] MQTT error vendor_id=%s",
                vendor.vendor_id,
            )
            return {"success": False, "transport": "MQTT", "error": "mqtt_exception"}

    if mode == "Firebase":
        try:
            from static.utils.functions.notifications import notify_android_tv

            success, info = notify_android_tv(vendor, payload)
            if not success:
                logger.warning(
                    "[refresh_hospital_tv] Firebase notify failed vendor_id=%s info=%s",
                    vendor.vendor_id,
                    info,
                )
            return {
                "success": bool(success),
                "transport": "Firebase",
                "payload": payload,
                "info": info,
            }
        except Exception:
            logger.exception(
                "[refresh_hospital_tv] Firebase error vendor_id=%s",
                vendor.vendor_id,
            )
            return {"success": False, "transport": "Firebase", "error": "firebase_exception"}

    logger.info(
        "[refresh_hospital_tv] unsupported tv_communication_mode=%s vendor_id=%s",
        mode,
        vendor.vendor_id,
    )
    return {"skipped": True, "reason": f"unsupported_mode:{mode}"}
