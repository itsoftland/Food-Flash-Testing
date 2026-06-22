"""
Dine Flash PWA relaunch booking resolver.

Read-only helper used by the resolve_booking API endpoint. Locates today's
booking by vendor_id + booking_no (table_booking_no) within the vendor's
current business-day window. Optional client location_id is diagnostic only.

Must NOT be used by Food Flash, Dine Flash Buffet, or Airline Flash flows.
Does not mutate orders, send notifications, or mirror check_status() side effects.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from vendors.models import Order, Vendor

from static.utils.functions.utils import get_vendor_business_day_range

logger = logging.getLogger(__name__)


class DineFlashBookingResolveStatus(str, Enum):
    """Outcome codes consumed by the resolve_booking API view."""

    FOUND = "found"
    NOT_FOUND_OR_STALE = "not_found_or_stale"
    AMBIGUOUS = "ambiguous"
    VENDOR_NOT_FOUND = "vendor_not_found"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class DineFlashBookingResolveResult:
    """
    Resolver return contract.

    On FOUND, `data` matches the resolve_booking endpoint success payload:
        {
            "booking_id": int,
            "booking_no": str,
            "vendor_id": int,
            "location_id": str,
        }
  """

    status: DineFlashBookingResolveStatus
    data: Optional[dict[str, Any]] = None


def _normalize_booking_no(value: Any) -> Optional[str]:
    """booking_no is table_booking_no — alphanumeric (e.g. L-3, VIP-9)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_vendor_id(value: Any) -> Optional[int]:
    try:
        vendor_id = int(value)
    except (TypeError, ValueError):
        return None
    if vendor_id <= 0:
        return None
    return vendor_id


def _normalize_location_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_success_payload(order: Order) -> dict[str, Any]:
    vendor = order.vendor
    return {
        "booking_id": order.id,
        "booking_no": order.table_booking_no or "",
        "vendor_id": vendor.vendor_id,
        "location_id": vendor.location_id,
    }


def resolve_dine_flash_booking(
    *,
    vendor_id: Any,
    booking_no: Any,
    location_id: Any = None,
) -> DineFlashBookingResolveResult:
    """
    Resolve a Dine Flash booking for the vendor's current business day.

    Lookup identity: vendor_id + booking_no + business-day window on created_at.
    Optional location_id is accepted for diagnostic logging only and does not
    affect the lookup outcome. On FOUND, location_id in data is always the
    authoritative vendor.location_id.

    Args:
        vendor_id: External Vendor.vendor_id (e.g. 594597).
        booking_no: Customer token / table_booking_no (e.g. "L-3").
        location_id: Optional client hint (e.g. stale activeLocation); warn-only.

    Returns:
        DineFlashBookingResolveResult — never raises for expected lookup failures.
    """
    normalized_vendor_id = _normalize_vendor_id(vendor_id)
    normalized_booking_no = _normalize_booking_no(booking_no)
    normalized_location_id = _normalize_location_id(location_id)

    if normalized_vendor_id is None or normalized_booking_no is None:
        return DineFlashBookingResolveResult(
            status=DineFlashBookingResolveStatus.INVALID_INPUT,
        )

    try:
        vendor = Vendor.objects.get(vendor_id=normalized_vendor_id)
    except Vendor.DoesNotExist:
        logger.info(
            "[dine_flash] resolve_booking vendor_not_found vendor_id=%s booking_no=%s",
            normalized_vendor_id,
            normalized_booking_no,
        )
        return DineFlashBookingResolveResult(
            status=DineFlashBookingResolveStatus.VENDOR_NOT_FOUND,
        )

    if normalized_location_id is not None:
        vendor_location = (vendor.location_id or "").strip()
        if vendor_location != normalized_location_id:
            logger.warning(
                "[dine_flash] resolve_booking client_location_mismatch vendor_id=%s "
                "client_location=%s vendor_location=%s booking_no=%s",
                normalized_vendor_id,
                normalized_location_id,
                vendor_location,
                normalized_booking_no,
            )

    start_dt, end_dt = get_vendor_business_day_range(vendor)

    matches = list(
        Order.objects.filter(
            vendor=vendor,
            table_booking_no=normalized_booking_no,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )
        .select_related("vendor")
        .order_by("-created_at")[:2]
    )

    if not matches:
        logger.info(
            "[dine_flash] resolve_booking not_found_or_stale vendor_id=%s "
            "booking_no=%s business_day=%s..%s",
            normalized_vendor_id,
            normalized_booking_no,
            start_dt.isoformat(),
            end_dt.isoformat(),
        )
        return DineFlashBookingResolveResult(
            status=DineFlashBookingResolveStatus.NOT_FOUND_OR_STALE,
        )

    if len(matches) > 1:
        logger.warning(
            "[dine_flash] resolve_booking ambiguous vendor_id=%s booking_no=%s "
            "match_count=%s business_day=%s..%s",
            normalized_vendor_id,
            normalized_booking_no,
            len(matches),
            start_dt.isoformat(),
            end_dt.isoformat(),
        )
        return DineFlashBookingResolveResult(
            status=DineFlashBookingResolveStatus.AMBIGUOUS,
        )

    return DineFlashBookingResolveResult(
        status=DineFlashBookingResolveStatus.FOUND,
        data=_build_success_payload(matches[0]),
    )


def resolve_dine_flash_booking_from_payload(
    payload: Mapping[str, Any],
) -> DineFlashBookingResolveResult:
    """Convenience wrapper for JSON request bodies."""
    return resolve_dine_flash_booking(
        vendor_id=payload.get("vendor_id"),
        booking_no=payload.get("booking_no"),
        location_id=payload.get("location_id"),
    )
