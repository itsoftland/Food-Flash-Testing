"""
Buffet order creation helpers.

Single source of truth for creating Order + BuffetOrderItem rows for
Dine Flash Buffet. Used by customer buffet_submit_order and the manager
buffet create API.

Must NOT be used by Food Flash, Dine Flash, Hospital Flash, or other flavours
for their own create flows. Does not send notifications, mutate PushSubscription,
or Chat. Optional order_lookup_id / Active Order Registry hooks match the
existing customer submit behaviour.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from django.conf import settings
from django.db import transaction

from manager.utils.utils import reset_counters_if_new_business_day
from orders.buffet.active_order_registry import register_buffet_active_order
from orders.buffet.order_lookup import upsert_buffet_order_lookup
from vendors.models import BuffetOrderItem, Order, Utility

logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "").strip().lower()

# Aligns with dine_flash table_booking.js special_notes limit (200).
BUFFET_ITEM_REMARKS_MAX_LENGTH = 200


class BuffetOrderCreateStatus(str, Enum):
    """Outcome codes consumed by buffet create API views."""

    CREATED = "created"
    REMARKS_TOO_LONG = "remarks_too_long"
    NO_VALID_ITEMS = "no_valid_items"


@dataclass(frozen=True)
class BuffetOrderCreateResult:
    """
    Create return contract.

    On CREATED, `order` and `created_item_ids` are set.
    On error statuses, `error_message` matches the historical HTTP error text.
    """

    status: BuffetOrderCreateStatus
    order: Optional[Order] = None
    created_item_ids: Optional[list] = None
    error_message: Optional[str] = None


def buffet_item_remarks_text(raw):
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return str(raw)


def normalize_buffet_customizations(raw):
    if not raw:
        return []
    if not isinstance(raw, list):
        return []
    return sorted({str(x).strip() for x in raw if str(x).strip()})


def merge_identical_buffet_cart_lines(items_data):
    """
    Dine Flash Buffet: one BuffetOrderItem per distinct (utility, customizations, remarks).
    Identical individual lines (e.g. plain dosas with no options) become one row with summed quantity.
    """
    buckets = OrderedDict()
    for item in items_data or []:
        utility_id = item.get("utility_id")
        remarks = buffet_item_remarks_text(item.get("remarks")).strip()
        customizations = normalize_buffet_customizations(item.get("customizations"))
        try:
            qty = max(1, int(item.get("quantity", 1)))
        except (TypeError, ValueError):
            qty = 1
        key = (utility_id, tuple(customizations), remarks)
        if key not in buckets:
            buckets[key] = {
                "utility_id": utility_id,
                "remarks": remarks,
                "customizations": customizations,
                "quantity": 0,
                "is_grouped": bool(item.get("is_grouped", False)),
            }
        entry = buckets[key]
        entry["quantity"] += qty
        entry["is_grouped"] = entry["is_grouped"] or bool(item.get("is_grouped", False))

    merged = []
    for entry in buckets.values():
        if entry["quantity"] > 1:
            entry["is_grouped"] = True
        merged.append(entry)
    return merged


def create_buffet_order(
    *,
    vendor,
    items_data,
    updated_by: str = "customer",
    user_profile=None,
    table_number=None,
    customer_name=None,
    phone_number=None,
    order_lookup_id=None,
    is_additional_order: bool = False,
    log_prefix: str = "[buffet]",
) -> BuffetOrderCreateResult:
    """
    Create a Buffet Order and its BuffetOrderItem lines.

    Caller must supply a resolved Vendor instance. Does not perform HTTP
    validation (vendor_id parsing, auth). Preserves the historical create
    sequence: remarks check → optional merge → atomic token/order/items →
    optional lookup upsert → optional registry on_commit.
    """
    items_data = list(items_data or [])

    for item in items_data:
        remarks = buffet_item_remarks_text(item.get("remarks")).strip()
        if len(remarks) > BUFFET_ITEM_REMARKS_MAX_LENGTH:
            return BuffetOrderCreateResult(
                status=BuffetOrderCreateStatus.REMARKS_TOO_LONG,
                error_message=(
                    f"Special instructions cannot exceed {BUFFET_ITEM_REMARKS_MAX_LENGTH} "
                    "characters per item."
                ),
            )

    if project_name == "dine_flash_buffet":
        items_data = merge_identical_buffet_cart_lines(items_data)

    vendor_business_id = getattr(vendor, "vendor_id", None)

    with transaction.atomic():
        reset_counters_if_new_business_day(vendor, None)

        last_booking = Order.objects.filter(vendor=vendor).order_by("-token_no").first()
        token_no = (last_booking.token_no + 1) if last_booking else 1

        order_kwargs = {
            "vendor": vendor,
            "token_no": token_no,
            "table_booking_no": table_number,  # Store table number here
            "counter_no": 1,
            "updated_by": updated_by,
            "status": "created",
            "customer_name": customer_name,
            "phone_number": phone_number,
        }
        if user_profile is not None:
            order_kwargs["user_profile"] = user_profile

        order = Order.objects.create(**order_kwargs)

        created_items = []
        for item in items_data:
            utility_id = item.get("utility_id")
            utility = Utility.objects.filter(id=utility_id, vendor=vendor).first()
            if not utility:
                logger.warning(
                    "%s Utility not found | utility_id=%s | vendor_id=%s",
                    log_prefix,
                    utility_id,
                    vendor_business_id,
                )
                continue

            customizations = item.get("customizations", [])
            item_remarks = buffet_item_remarks_text(item.get("remarks")).strip()
            is_grouped = item.get("is_grouped", False)
            quantity = int(item.get("quantity", 1))

            buffet_item = BuffetOrderItem.objects.create(
                order=order,
                utility=utility,
                status="created",
                customizations=customizations,
                remarks=item_remarks,
                is_grouped=is_grouped,
                quantity=quantity,
            )
            created_items.append(buffet_item.id)

        if not created_items:
            # If no items were created (e.g. due to invalid utilities), rollback.
            transaction.set_rollback(True)
            logger.warning(
                "%s No valid items | vendor_id=%s | cart_lines=%s",
                log_prefix,
                vendor_business_id,
                len(items_data),
            )
            return BuffetOrderCreateResult(
                status=BuffetOrderCreateStatus.NO_VALID_ITEMS,
                error_message="No valid items found in order.",
            )

        # Latest Order Wins pointer — QR / primary path only (not "+" additional orders).
        if order_lookup_id and not is_additional_order:
            upsert_buffet_order_lookup(order_lookup_id=order_lookup_id, order=order)

        # Active Order Registry: additive, post-commit only. Never affects Order / lookup txn.
        if order_lookup_id:
            order_pk = order.pk
            registry_lookup_id = order_lookup_id

            def _register_buffet_active_order_after_commit():
                try:
                    order_obj = Order.objects.select_related("vendor").get(pk=order_pk)
                    register_buffet_active_order(
                        order_lookup_id=registry_lookup_id,
                        order=order_obj,
                    )
                except Exception:
                    logger.exception(
                        "%s active_order_registry failed | "
                        "order_lookup_id=%s order_id=%s is_additional_order=%s",
                        log_prefix,
                        registry_lookup_id,
                        order_pk,
                        is_additional_order,
                    )

            transaction.on_commit(_register_buffet_active_order_after_commit)

    return BuffetOrderCreateResult(
        status=BuffetOrderCreateStatus.CREATED,
        order=order,
        created_item_ids=created_items,
    )
