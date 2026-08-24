"""
Buffet order_lookup_id pointer helpers.

Opaque recovery key → current Order. Not browser_id. Not PushSubscription.
Latest Order Wins: one mutable pointer per order_lookup_id (not history).

Used by buffet_submit_order (upsert) and the buffet resolve_order_lookup API.
Must NOT be used by Food Flash, Dine Flash, Hospital Flash, or other flavours.
Does not mutate Order status, PushSubscription, or Chat.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from django.db import transaction

from static.utils.functions.utils import get_vendor_business_day_range
from vendors.models import BuffetOrderLookup, Order

logger = logging.getLogger(__name__)

ORDER_LOOKUP_ID_MAX_LENGTH = 255


class BuffetOrderLookupResolveStatus(str, Enum):
    """Outcome codes consumed by the resolve_order_lookup API view."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    NOT_FOUND_OR_STALE = "not_found_or_stale"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class BuffetOrderLookupResolveResult:
    """
    Resolver return contract.

    On FOUND, `data` matches the resolve_order_lookup success payload:
        {
            "token_no": int,
            "vendor_id": int,
            "location_id": str,
        }
    """

    status: BuffetOrderLookupResolveStatus
    data: Optional[dict[str, Any]] = None


def normalize_order_lookup_id(value: Any) -> Optional[str]:
    """
    Normalize an opaque order_lookup_id.

    Empty / whitespace-only → None (treat as absent).
    Present but longer than max → None (invalid; caller must not upsert).
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > ORDER_LOOKUP_ID_MAX_LENGTH:
        return None
    return text


@transaction.atomic
def upsert_buffet_order_lookup(*, order_lookup_id: Any, order: Order) -> Optional[BuffetOrderLookup]:
    """
    Point order_lookup_id at order (Latest Order Wins).

    If order_lookup_id is absent/invalid after normalize, no-op and return None.
    Reassigns an existing row for the same order_lookup_id to the new order.
    Clears any other lookup row already attached to this order (OneToOne invariant).
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return None

    if order is None or getattr(order, "pk", None) is None:
        logger.warning(
            "[buffet] upsert_order_lookup skipped: order missing pk order_lookup_id=%s",
            normalized,
        )
        return None

    # OneToOne: this order must not remain linked under a different lookup id.
    BuffetOrderLookup.objects.filter(order=order).exclude(
        order_lookup_id=normalized
    ).delete()

    mapping, created = BuffetOrderLookup.objects.update_or_create(
        order_lookup_id=normalized,
        defaults={"order": order},
    )
    logger.info(
        "[buffet] order_lookup %s order_lookup_id=%s order_id=%s token_no=%s",
        "created" if created else "updated",
        normalized,
        order.pk,
        order.token_no,
    )
    return mapping


def _build_resolve_success_payload(order: Order) -> dict[str, Any]:
    vendor = order.vendor
    return {
        "token_no": order.token_no,
        "vendor_id": vendor.vendor_id,
        "location_id": vendor.location_id,
    }


def _order_in_current_business_day(order: Order) -> bool:
    """
    Same business-day window as Buffet Active Order Selector
    (get_vendor_business_day_range). Prior-day orders remain in the DB but are
    not recoverable as the customer's current Latest Order.
    """
    vendor = getattr(order, "vendor", None)
    if vendor is None or order.created_at is None:
        return False
    start_dt, end_dt = get_vendor_business_day_range(vendor)
    return start_dt <= order.created_at <= end_dt


def resolve_buffet_order_lookup(
    *,
    order_lookup_id: Any,
) -> BuffetOrderLookupResolveResult:
    """
    Resolve order_lookup_id → token_no, vendor_id, location_id.

    Read-only. Does not mutate Order, PushSubscription, Chat, or BuffetOrderLookup.
    Orders outside the vendor's current business day are not recoverable.
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return BuffetOrderLookupResolveResult(
            status=BuffetOrderLookupResolveStatus.INVALID_INPUT,
        )

    mapping = (
        BuffetOrderLookup.objects.filter(order_lookup_id=normalized)
        .select_related("order", "order__vendor", "order__vendor__config")
        .first()
    )
    if mapping is None or mapping.order_id is None:
        logger.info(
            "[buffet] resolve_order_lookup not_found order_lookup_id=%s",
            normalized,
        )
        return BuffetOrderLookupResolveResult(
            status=BuffetOrderLookupResolveStatus.NOT_FOUND,
        )

    order = mapping.order
    if not _order_in_current_business_day(order):
        logger.info(
            "[buffet] resolve_order_lookup not_found_or_stale order_lookup_id=%s "
            "order_id=%s token_no=%s",
            normalized,
            order.pk,
            order.token_no,
        )
        return BuffetOrderLookupResolveResult(
            status=BuffetOrderLookupResolveStatus.NOT_FOUND_OR_STALE,
        )

    return BuffetOrderLookupResolveResult(
        status=BuffetOrderLookupResolveStatus.FOUND,
        data=_build_resolve_success_payload(order),
    )


def resolve_buffet_order_lookup_from_payload(
    payload: Mapping[str, Any],
) -> BuffetOrderLookupResolveResult:
    """Convenience wrapper for JSON request bodies."""
    return resolve_buffet_order_lookup(
        order_lookup_id=payload.get("order_lookup_id"),
    )
