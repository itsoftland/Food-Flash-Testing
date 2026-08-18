"""
Hospital Flash only: TV payload builder and transport dispatch for called patients.

Displays currently called patients using Order.table_booking_no (e.g. LAB-12).
Reuses existing MQTT and Firebase TV infrastructure without touching get_last_tokens().
"""

import logging
from collections import defaultdict
from datetime import timezone as dt_timezone

from django.conf import settings
from django.utils.timezone import is_aware, make_aware, get_current_timezone

from vendors.models import AndroidDevice, Order

logger = logging.getLogger(__name__)


def is_hospital_flash():
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "hospital_flash"


def _hospital_department_display_name(utility):
    """Match Hospital Flash TV configuration UI: display_name, else utility_name."""
    return utility.display_name or utility.utility_name


def build_hospital_tv_config_departments(tv_config):
    """
    Hospital Flash TV registration: departments selected on the TV configuration.

    Returns [] when no departments are selected. Group/package assignments expand to
    their individual member departments (same logic as order filtering).
    """
    if not tv_config:
        return []

    utilities = tv_config.utilities.filter(is_active=True)
    if not utilities.exists():
        return []

    from manager.hospital_views import resolve_hospital_effective_departments

    effective = resolve_hospital_effective_departments(utilities)
    return [
        {"id": dept.id, "name": _hospital_department_display_name(dept)}
        for dept in effective
    ]


def resolve_tv_config_utility_ids(tv_config):
    """
    Resolve TV configuration departments into individual utility IDs for order filtering.

    Empty or missing selection returns None (show all departments).
    """
    if not tv_config:
        return None

    utilities = tv_config.utilities.filter(is_active=True)
    if not utilities.exists():
        return None

    # Lazy import avoids circular dependency (manager.hospital_views imports refresh_hospital_tv).
    from manager.hospital_views import resolve_hospital_effective_departments

    effective = resolve_hospital_effective_departments(utilities)
    ids = {utility.id for utility in effective}
    return ids or set()


def get_hospital_called_booking_nos(
    vendor, *, start_dt, end_dt, limit=None, utility_ids=None
):
    """
    Return table_booking_no strings for currently called patients in the business day.

    Results are ordered by most recently updated first and capped at token_display_limit.
    When utility_ids is None, all departments are included. When utility_ids is an empty set,
    no patients match.
    """
    if limit is None:
        config = getattr(vendor, "config", None)
        limit = getattr(config, "token_display_limit", None) or 8

    qs = Order.objects.filter(
        vendor=vendor,
        status="called",
        created_at__range=(start_dt, end_dt),
    )
    if utility_ids is not None:
        qs = qs.filter(utility_id__in=utility_ids)

    booking_nos = list(
        qs.exclude(table_booking_no__isnull=True)
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


def _format_hospital_registration_called_at(dt):
    """UTC ISO-8601 with Z suffix for the Hospital Flash registration snapshot only."""
    if dt is None:
        return None
    if is_aware(dt):
        utc_dt = dt.astimezone(dt_timezone.utc)
    else:
        utc_dt = make_aware(dt, get_current_timezone()).astimezone(dt_timezone.utc)
    iso = utc_dt.replace(microsecond=0).isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    return iso


def _hospital_registration_called_tokens(
    vendor, *, start_dt, end_dt, limit=None, utility_ids=None
):
    """
    Registration-only called-patient rows.

    Uses the same vendor / status / business-day / department / ordering / limit
    rules as get_hospital_called_booking_nos, but returns token objects instead of
    strings. Not used by MQTT or Firebase refresh.
    """
    if limit is None:
        config = getattr(vendor, "config", None)
        limit = getattr(config, "token_display_limit", None) or 8

    qs = Order.objects.filter(
        vendor=vendor,
        status="called",
        created_at__range=(start_dt, end_dt),
    )
    if utility_ids is not None:
        qs = qs.filter(utility_id__in=utility_ids)

    rows = list(
        qs.exclude(table_booking_no__isnull=True)
        .exclude(table_booking_no="")
        .order_by("-updated_at")
        .values("table_booking_no", "utility_id", "updated_at")[:limit]
    )
    return [
        {
            "token": row["table_booking_no"],
            "utility_id": row["utility_id"],
            "called_at": _format_hospital_registration_called_at(row["updated_at"]),
        }
        for row in rows
    ]


def build_hospital_tv_registration_snapshot(vendor, tv_config=None):
    """
    Bootstrap snapshot for Hospital TV registration responses.

    When tv_config is provided, filters called patients to the configuration's departments.
    Returns tokens (token, utility_id, called_at) and total_count for the
    hospital_flash registration key only. Live TV MQTT/Firebase payloads are unchanged.
    """
    if not is_hospital_flash():
        return None

    from static.utils.functions.utils import get_vendor_business_day_range

    try:
        config = vendor.config
    except Exception:
        logger.exception(
            "[build_hospital_tv_registration_snapshot] vendor config missing vendor_id=%s",
            getattr(vendor, "vendor_id", None),
        )
        return {"tokens": [], "total_count": 0}

    start_dt, end_dt = get_vendor_business_day_range(vendor)
    utility_ids = resolve_tv_config_utility_ids(tv_config)
    tokens = _hospital_registration_called_tokens(
        vendor,
        start_dt=start_dt,
        end_dt=end_dt,
        limit=config.token_display_limit,
        utility_ids=utility_ids,
    )
    return {
        "tokens": tokens,
        "total_count": len(tokens),
    }


def _group_hospital_tv_devices(vendor):
    devices = list(
        AndroidDevice.objects.filter(vendor=vendor)
        .select_related("tv_config")
        .prefetch_related(
            "tv_config__utilities",
            "tv_config__utilities__group_departments",
        )
    )
    groups = defaultdict(list)
    for device in devices:
        groups[device.tv_config_id].append(device)
    return groups


def _dispatch_hospital_tv_firebase(vendor, devices, payload):
    from static.utils.functions.notifications import notify_android_tv
    from vendors.dine_flash_tv_fcm import collect_fcm_tokens_for_devices

    tokens = collect_fcm_tokens_for_devices(devices)
    if not tokens:
        return {"success": False, "error": "no_tokens", "device_count": len(devices)}

    success, info = notify_android_tv(vendor, payload, fcm_tokens=tokens)
    return {
        "success": bool(success),
        "info": info,
        "token_count": len(tokens),
    }


def _dispatch_hospital_tv_mqtt(vendor, devices, payload, mqtt_mode):
    from vendors.mqtt_client import publish_mqtt

    if mqtt_mode == "Individual":
        if not devices:
            return {"success": False, "transport": "MQTT", "mode": "Individual", "error": "no_devices"}
        results = [publish_mqtt(vendor, payload, device=device) for device in devices]
        return {
            "success": all(results),
            "transport": "MQTT",
            "mode": "Individual",
            "device_count": len(devices),
        }

    success = publish_mqtt(vendor, payload)
    return {"success": bool(success), "transport": "MQTT", "mode": "All"}


def _refresh_hospital_tv_vendor_wide(vendor, *, start_dt, end_dt, limit, mode, mqtt_mode):
    """Legacy vendor-wide refresh when no Android TVs are registered."""
    booking_nos = get_hospital_called_booking_nos(
        vendor, start_dt=start_dt, end_dt=end_dt, limit=limit
    )
    payload = build_hospital_tv_payload(vendor, booking_nos)

    if mode == "MQTT":
        result = _dispatch_hospital_tv_mqtt(vendor, [], payload, mqtt_mode)
        result["payload"] = payload
        return result

    if mode == "Firebase":
        from static.utils.functions.notifications import notify_android_tv

        success, info = notify_android_tv(vendor, payload)
        return {
            "success": bool(success),
            "transport": "Firebase",
            "payload": payload,
            "info": info,
        }

    return {"skipped": True, "reason": f"unsupported_mode:{mode}"}


def refresh_hospital_tv(vendor, *, start_dt, end_dt):
    """
    Push the current called-patient snapshot to Hospital TVs.

    Groups Android TVs by assigned TV configuration, builds a department-filtered
    payload per group, and dispatches via MQTT or Firebase based on vendor config.
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
    mode = (config.tv_communication_mode or "").strip()
    mqtt_mode = config.mqtt_mode or "All"

    if mode not in {"MQTT", "Firebase"}:
        logger.info(
            "[refresh_hospital_tv] unsupported tv_communication_mode=%s vendor_id=%s",
            mode,
            vendor.vendor_id,
        )
        return {"skipped": True, "reason": f"unsupported_mode:{mode}"}

    device_groups = _group_hospital_tv_devices(vendor)
    if not device_groups:
        try:
            return _refresh_hospital_tv_vendor_wide(
                vendor,
                start_dt=start_dt,
                end_dt=end_dt,
                limit=limit,
                mode=mode,
                mqtt_mode=mqtt_mode,
            )
        except Exception:
            logger.exception(
                "[refresh_hospital_tv] vendor-wide dispatch error vendor_id=%s",
                vendor.vendor_id,
            )
            return {"success": False, "transport": mode, "error": f"{mode.lower()}_exception"}

    group_results = []
    mqtt_all_payloads_sent = {}

    for tv_config_id, devices in device_groups.items():
        tv_config = devices[0].tv_config if devices else None
        utility_ids = resolve_tv_config_utility_ids(tv_config)
        booking_nos = get_hospital_called_booking_nos(
            vendor,
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
            utility_ids=utility_ids,
        )
        payload = build_hospital_tv_payload(vendor, booking_nos)
        payload_key = tuple(payload["tokens"])

        try:
            if mode == "Firebase":
                result = _dispatch_hospital_tv_firebase(vendor, devices, payload)
            elif mqtt_mode == "Individual":
                result = _dispatch_hospital_tv_mqtt(vendor, devices, payload, "Individual")
            else:
                if payload_key in mqtt_all_payloads_sent:
                    result = dict(mqtt_all_payloads_sent[payload_key])
                else:
                    result = _dispatch_hospital_tv_mqtt(vendor, devices, payload, "All")
                    mqtt_all_payloads_sent[payload_key] = dict(result)
            result["payload"] = payload
            result["tv_config_id"] = tv_config_id
            result["device_count"] = len(devices)
            group_results.append(result)
        except Exception:
            logger.exception(
                "[refresh_hospital_tv] group dispatch error vendor_id=%s tv_config_id=%s",
                vendor.vendor_id,
                tv_config_id,
            )
            group_results.append(
                {
                    "success": False,
                    "transport": mode,
                    "tv_config_id": tv_config_id,
                    "payload": payload,
                    "error": f"{mode.lower()}_exception",
                }
            )

    overall_success = all(result.get("success") for result in group_results)
    first_payload = group_results[0]["payload"] if group_results else None
    return {
        "success": overall_success,
        "transport": mode,
        "groups": group_results,
        "payload": first_payload,
    }
