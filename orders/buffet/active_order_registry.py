"""
Buffet Active Order Registry helpers.

Additive multi-order list keyed by opaque order_lookup_id.
Does NOT replace BuffetOrderLookup (Latest Order Wins), browser_id,
PushSubscription, cookies, or WebChatMessage.

Must NOT be used by Food Flash, Dine Flash, Hospital Flash, or other flavours.
Does not mutate Order status, PushSubscription, or Chat.

Phase 3 selector reads use list_selectable_buffet_active_orders /
serialize_buffet_active_order_for_selector only. Recovery must continue to use
BuffetOrderLookup via resolve_buffet_order_lookup.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from django.db import transaction
from django.db.models import Prefetch, QuerySet

from orders.buffet.order_lookup import normalize_order_lookup_id
from static.utils.functions.utils import get_vendor_business_day_range
from vendors.models import BuffetActiveOrder, BuffetOrderItem, BuffetOrderLookup, Order

logger = logging.getLogger(__name__)

# Item status that means the line is cancelled for selector "active" filtering.
_BUFFET_ITEM_CANCELLED = "cancelled"

# Item statuses that mean a line is finished (no longer customer-active).
# `ready` is intentionally excluded — customer may still be waiting for pickup.
_BUFFET_ITEM_FINISHED = frozenset({"cancelled", "delivered", "operation_closed"})

# Order-level status that means the booking is completed.
_BUFFET_ORDER_DELIVERED = "delivered"


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
def register_buffet_active_order(
    *,
    order_lookup_id: Any,
    order: Order,
) -> Optional[BuffetActiveOrder]:
    """
    Ensure `order` appears in the Active Order Registry under order_lookup_id.

    Idempotent for the same order. If the order is already registered under a
    different lookup id, reassigns it to the provided lookup id.
    Absent/invalid order_lookup_id → no-op (None).
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return None

    if order is None or getattr(order, "pk", None) is None:
        logger.warning(
            "[buffet] register_active_order skipped: order missing pk order_lookup_id=%s",
            normalized,
        )
        return None

    vendor_id = _vendor_business_id(order)
    if vendor_id is None:
        logger.warning(
            "[buffet] register_active_order skipped: vendor_id missing order_id=%s",
            order.pk,
        )
        return None

    token_no = order.token_no
    if token_no is None:
        logger.warning(
            "[buffet] register_active_order skipped: token_no missing order_id=%s",
            order.pk,
        )
        return None

    entry, created = BuffetActiveOrder.objects.update_or_create(
        order=order,
        defaults={
            "order_lookup_id": normalized,
            "token_no": int(token_no),
            "vendor_id": vendor_id,
        },
    )
    logger.info(
        "[buffet] active_order_registry %s order_lookup_id=%s order_id=%s token_no=%s vendor_id=%s",
        "created" if created else "updated",
        normalized,
        order.pk,
        entry.token_no,
        entry.vendor_id,
    )
    return entry


def list_buffet_active_orders(*, order_lookup_id: Any) -> QuerySet:
    """
    Active registry rows for order_lookup_id (newest first).

    Business-day filtering is intentionally not applied here (Phase 10).
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return BuffetActiveOrder.objects.none()

    return (
        BuffetActiveOrder.objects.filter(order_lookup_id=normalized)
        .select_related("order", "order__vendor")
        .order_by("-created_at", "-id")
    )


def count_buffet_active_orders(*, order_lookup_id: Any) -> int:
    return list_buffet_active_orders(order_lookup_id=order_lookup_id).count()


@transaction.atomic
def remove_buffet_active_order(*, order: Order) -> bool:
    """
    Remove the registry entry for `order` if present.
    Returns True when a row was deleted.
    """
    if order is None or getattr(order, "pk", None) is None:
        return False

    deleted, _ = BuffetActiveOrder.objects.filter(order=order).delete()
    if deleted:
        logger.info(
            "[buffet] active_order_registry removed order_id=%s token_no=%s",
            order.pk,
            getattr(order, "token_no", None),
        )
    return bool(deleted)


def serialize_buffet_active_order(entry: BuffetActiveOrder) -> dict:
    """Stable dict shape for later list APIs (Phase 3+)."""
    return {
        "token_no": entry.token_no,
        "vendor_id": entry.vendor_id,
        "booking_id": entry.booking_id,
        "order_lookup_id": entry.order_lookup_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "order_status": entry.order.status if entry.order_id else None,
    }


def _buffet_order_items(order: Order) -> list:
    return list(order.buffet_items.all())


def _buffet_order_is_fully_cancelled(order: Order) -> bool:
    """
    True when the order has no BuffetOrderItem lines, or every line is cancelled.

    Buffet has no reliable order-level cancel; item-level cancel is the source of truth.
    """
    items = _buffet_order_items(order)
    if not items:
        return True
    return all(item.status == _BUFFET_ITEM_CANCELLED for item in items)


def _buffet_order_is_fully_finished(order: Order) -> bool:
    """
    True when every line is in a finished state (delivered / cancelled /
    operation_closed). Mixed ready+delivered stays active.
    """
    items = _buffet_order_items(order)
    if not items:
        return True
    return all(item.status in _BUFFET_ITEM_FINISHED for item in items)


def is_buffet_order_registry_active(order: Optional[Order]) -> bool:
    """
    Whether `order` should remain in the Active Order Registry.

    Inactive when:
    - order is missing
    - Order.status is delivered (booking completed)
    - fully cancelled (all lines cancelled / no lines)
    - fully finished (all lines delivered / cancelled / operation_closed)

    Does not consult BuffetOrderLookup. Not a recovery check.
    """
    if order is None or getattr(order, "pk", None) is None:
        return False
    if getattr(order, "status", None) == _BUFFET_ORDER_DELIVERED:
        return False
    if _buffet_order_is_fully_cancelled(order):
        return False
    if _buffet_order_is_fully_finished(order):
        return False
    return True


def sync_buffet_active_order_lifecycle(*, order: Order) -> bool:
    """
    Remove the registry row when the order is no longer active.

    Returns True when a row was deleted. No-op when still active or absent.
    Safe to call from manager status transitions (Buffet only).
    """
    if is_buffet_order_registry_active(order):
        return False
    return remove_buffet_active_order(order=order)


def _buffet_order_in_current_business_day(order: Order, *, range_cache: dict) -> bool:
    vendor = getattr(order, "vendor", None)
    if vendor is None or order.created_at is None:
        return False
    cache_key = vendor.pk
    if cache_key not in range_cache:
        range_cache[cache_key] = get_vendor_business_day_range(vendor)
    start_dt, end_dt = range_cache[cache_key]
    return start_dt <= order.created_at <= end_dt


def is_selectable_buffet_active_order(entry: BuffetActiveOrder, *, range_cache: Optional[dict] = None) -> bool:
    """
    Whether a registry row should appear in the Order Selector API.

    Excludes orphaned rows, inactive (cancelled / completed / finished) orders,
    and orders outside the vendor's current business day.
    Uses the same active definition as sync_buffet_active_order_lifecycle.
    """
    if entry is None or entry.order_id is None:
        return False
    order = getattr(entry, "order", None)
    if order is None:
        return False
    if not is_buffet_order_registry_active(order):
        return False
    cache = range_cache if range_cache is not None else {}
    if not _buffet_order_in_current_business_day(order, range_cache=cache):
        return False
    return True


def latest_buffet_order_id_for_lookup(*, order_lookup_id: Any) -> Optional[int]:
    """
    Latest Order Wins pointer from BuffetOrderLookup (not the Registry).

    Absent/invalid lookup id or missing mapping → None.
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return None
    return (
        BuffetOrderLookup.objects.filter(order_lookup_id=normalized)
        .values_list("order_id", flat=True)
        .first()
    )


def list_selectable_buffet_active_orders(*, order_lookup_id: Any) -> list[BuffetActiveOrder]:
    """
    Registry rows eligible for the Order Selector API (newest first).

    Read-only filter. Lifecycle removals happen on status transitions via
    sync_buffet_active_order_lifecycle; this remains a safety net for stale rows.
    """
    qs = list_buffet_active_orders(order_lookup_id=order_lookup_id).prefetch_related(
        Prefetch(
            "order__buffet_items",
            queryset=BuffetOrderItem.objects.only("id", "order_id", "status"),
        )
    )
    range_cache: dict = {}
    return [
        entry
        for entry in qs
        if is_selectable_buffet_active_order(entry, range_cache=range_cache)
    ]


def serialize_buffet_active_order_for_selector(
    entry: BuffetActiveOrder,
    *,
    is_latest: bool,
) -> dict:
    """
    Lean Order Selector payload. Builds on serialize_buffet_active_order fields
    without exposing booking_id / order_status.
    """
    base = serialize_buffet_active_order(entry)
    return {
        "order_lookup_id": base["order_lookup_id"],
        "vendor_id": base["vendor_id"],
        "token_number": base["token_no"],
        "created_at": base["created_at"],
        "is_latest": bool(is_latest),
    }
