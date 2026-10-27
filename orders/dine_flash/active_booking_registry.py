"""
Dine Flash Active Booking Registry helpers.

Additive multi-booking list keyed by opaque order_lookup_id.
Does NOT replace DineFlashBookingLookup (Latest Booking Wins).

Must NOT be used by Buffet, Food Flash, Hospital Flash, or other flavours.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import transaction
from django.db.models import QuerySet

from orders.dine_flash.booking_lookup import normalize_order_lookup_id
from static.utils.functions.utils import get_vendor_business_day_range
from vendors.models import DineFlashActiveBooking, DineFlashBookingLookup, Order

logger = logging.getLogger(__name__)

_DINE_FLASH_REGISTRY_ACTIVE = frozenset(
    {"created", "waiting", "allocated", "occupied"}
)
_DINE_FLASH_REGISTRY_INACTIVE = frozenset(
    {"booking_cancelled", "operation_closed"}
)


def _vendor_business_id(order: Order) -> Optional[int]:
    vendor = getattr(order, "vendor", None)
    if vendor is None:
        return None
    vendor_id = getattr(vendor, "vendor_id", None)
    if vendor_id is None:
        return None
    try:
        return int(vendor_id)
    except (TypeError, ValueError):
        return None


@transaction.atomic
def register_dine_flash_active_booking(
    *,
    order_lookup_id: Any,
    order: Order,
) -> Optional[DineFlashActiveBooking]:
    """
    Ensure `order` appears in the Active Booking Registry under order_lookup_id.
    Idempotent for the same order. Absent/invalid order_lookup_id → no-op.
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return None

    if order is None or getattr(order, "pk", None) is None:
        logger.warning(
            "[dine_flash] register_active_booking skipped: order missing pk order_lookup_id=%s",
            normalized,
        )
        return None

    vendor_id = _vendor_business_id(order)
    if vendor_id is None:
        logger.warning(
            "[dine_flash] register_active_booking skipped: vendor_id missing order_id=%s",
            order.pk,
        )
        return None

    booking_no = (getattr(order, "table_booking_no", None) or "").strip()
    if not booking_no:
        logger.warning(
            "[dine_flash] register_active_booking skipped: table_booking_no missing order_id=%s",
            order.pk,
        )
        return None

    token_no = order.token_no

    entry, created = DineFlashActiveBooking.objects.update_or_create(
        order=order,
        defaults={
            "order_lookup_id": normalized,
            "table_booking_no": booking_no,
            "vendor_id": vendor_id,
            "token_no": int(token_no) if token_no is not None else None,
        },
    )
    logger.info(
        "[dine_flash] active_booking_registry %s order_lookup_id=%s order_id=%s "
        "booking_no=%s vendor_id=%s",
        "created" if created else "updated",
        normalized,
        order.pk,
        entry.table_booking_no,
        entry.vendor_id,
    )
    return entry


def list_dine_flash_active_bookings(*, order_lookup_id: Any) -> QuerySet:
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return DineFlashActiveBooking.objects.none()

    return (
        DineFlashActiveBooking.objects.filter(order_lookup_id=normalized)
        .select_related("order", "order__vendor")
        .order_by("-created_at", "-id")
    )


@transaction.atomic
def remove_dine_flash_active_booking(*, order: Order) -> bool:
    if order is None or getattr(order, "pk", None) is None:
        return False
    deleted, _ = DineFlashActiveBooking.objects.filter(order=order).delete()
    if deleted:
        logger.info(
            "[dine_flash] active_booking_registry removed order_id=%s booking_no=%s",
            order.pk,
            getattr(order, "table_booking_no", None),
        )
    return bool(deleted)


def is_dine_flash_booking_registry_active(order: Optional[Order]) -> bool:
    if order is None or getattr(order, "pk", None) is None:
        return False
    status = (getattr(order, "status", None) or "").strip().lower()
    if status in _DINE_FLASH_REGISTRY_INACTIVE:
        return False
    if status in _DINE_FLASH_REGISTRY_ACTIVE:
        return True
    logger.warning(
        "[dine_flash] active_booking_registry unknown status excluded order_id=%s status=%s",
        order.pk,
        status,
    )
    return False


def sync_dine_flash_active_booking_lifecycle(*, order: Order) -> bool:
    if is_dine_flash_booking_registry_active(order):
        return False
    return remove_dine_flash_active_booking(order=order)


def _booking_in_current_business_day(order: Order, *, range_cache: dict) -> bool:
    vendor = getattr(order, "vendor", None)
    if vendor is None or order.created_at is None:
        return False
    cache_key = vendor.pk
    if cache_key not in range_cache:
        range_cache[cache_key] = get_vendor_business_day_range(vendor)
    start_dt, end_dt = range_cache[cache_key]
    return start_dt <= order.created_at <= end_dt


def is_selectable_dine_flash_active_booking(
    entry: DineFlashActiveBooking, *, range_cache: Optional[dict] = None
) -> bool:
    if entry is None or entry.order_id is None:
        return False
    order = getattr(entry, "order", None)
    if order is None:
        return False
    if not is_dine_flash_booking_registry_active(order):
        return False
    cache = range_cache if range_cache is not None else {}
    if not _booking_in_current_business_day(order, range_cache=cache):
        return False
    return True


def latest_dine_flash_booking_id_for_lookup(*, order_lookup_id: Any) -> Optional[int]:
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return None
    return (
        DineFlashBookingLookup.objects.filter(order_lookup_id=normalized)
        .values_list("order_id", flat=True)
        .first()
    )


def list_selectable_dine_flash_active_bookings(
    *, order_lookup_id: Any
) -> list[DineFlashActiveBooking]:
    qs = list_dine_flash_active_bookings(order_lookup_id=order_lookup_id)
    range_cache: dict = {}
    return [
        entry
        for entry in qs
        if is_selectable_dine_flash_active_booking(entry, range_cache=range_cache)
    ]


def serialize_dine_flash_active_booking_for_selector(
    entry: DineFlashActiveBooking,
    *,
    is_latest: bool,
) -> dict:
    return {
        "order_lookup_id": entry.order_lookup_id,
        "vendor_id": entry.vendor_id,
        "booking_id": entry.order_id,
        "booking_no": entry.table_booking_no,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "is_latest": bool(is_latest),
    }
