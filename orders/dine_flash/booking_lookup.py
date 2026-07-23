"""
Dine Flash order_lookup_id pointer helpers.

Opaque recovery key → current booking Order. Not browser_id. Not PushSubscription.
Latest Booking Wins: one mutable pointer per order_lookup_id (not history).

Used by book_table (upsert) and the dine_flash resolve_order_lookup API.
Must NOT be used by Food Flash, Dine Flash Buffet, Hospital Flash, or other flavours.
Does not mutate Order status, PushSubscription, or Chat.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from django.db import transaction

from vendors.models import DineFlashBookingLookup, Order

logger = logging.getLogger(__name__)

ORDER_LOOKUP_ID_MAX_LENGTH = 255


class DineFlashBookingLookupResolveStatus(str, Enum):
    """Outcome codes consumed by the dine_flash resolve_order_lookup API view."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class DineFlashBookingLookupResolveResult:
    """
    Resolver return contract.

    On FOUND, `data` matches the resolve_order_lookup success payload:
        {
            "booking_id": int,
            "booking_no": str,
            "vendor_id": int,
            "location_id": str,
        }
    """

    status: DineFlashBookingLookupResolveStatus
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
def upsert_dine_flash_booking_lookup(
    *, order_lookup_id: Any, order: Order
) -> Optional[DineFlashBookingLookup]:
    """
    Point order_lookup_id at booking order (Latest Booking Wins).

    If order_lookup_id is absent/invalid after normalize, no-op and return None.
    Reassigns an existing row for the same order_lookup_id to the new order.
    Clears any other lookup row already attached to this order (OneToOne invariant).
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return None

    if order is None or getattr(order, "pk", None) is None:
        logger.warning(
            "[dine_flash] upsert_booking_lookup skipped: order missing pk order_lookup_id=%s",
            normalized,
        )
        return None

    # OneToOne: this order must not remain linked under a different lookup id.
    DineFlashBookingLookup.objects.filter(order=order).exclude(
        order_lookup_id=normalized
    ).delete()

    mapping, created = DineFlashBookingLookup.objects.update_or_create(
        order_lookup_id=normalized,
        defaults={"order": order},
    )
    logger.info(
        "[dine_flash] booking_lookup %s order_lookup_id=%s order_id=%s booking_no=%s",
        "created" if created else "updated",
        normalized,
        order.pk,
        order.table_booking_no,
    )
    return mapping


def _build_resolve_success_payload(order: Order) -> dict[str, Any]:
    vendor = order.vendor
    return {
        "booking_id": order.id,
        "booking_no": order.table_booking_no or "",
        "vendor_id": vendor.vendor_id,
        "location_id": vendor.location_id,
    }


def resolve_dine_flash_booking_lookup(
    *,
    order_lookup_id: Any,
) -> DineFlashBookingLookupResolveResult:
    """
    Resolve order_lookup_id → booking_id, booking_no, vendor_id, location_id.

    Read-only. Does not mutate Order, PushSubscription, or Chat.
    """
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        return DineFlashBookingLookupResolveResult(
            status=DineFlashBookingLookupResolveStatus.INVALID_INPUT,
        )

    mapping = (
        DineFlashBookingLookup.objects.filter(order_lookup_id=normalized)
        .select_related("order", "order__vendor")
        .first()
    )
    if mapping is None or mapping.order_id is None:
        logger.info(
            "[dine_flash] resolve_order_lookup not_found order_lookup_id=%s",
            normalized,
        )
        return DineFlashBookingLookupResolveResult(
            status=DineFlashBookingLookupResolveStatus.NOT_FOUND,
        )

    return DineFlashBookingLookupResolveResult(
        status=DineFlashBookingLookupResolveStatus.FOUND,
        data=_build_resolve_success_payload(mapping.order),
    )


def resolve_dine_flash_booking_lookup_from_payload(
    payload: Mapping[str, Any],
) -> DineFlashBookingLookupResolveResult:
    """Convenience wrapper for JSON request bodies."""
    return resolve_dine_flash_booking_lookup(
        order_lookup_id=payload.get("order_lookup_id"),
    )
