"""
Hospital order creation helpers.

Single source of truth for creating Hospital Flash patient Orders (one per
expanded department, shared registration_batch_id). Used by customer
hospital_patient_submit and the Outlet Manager hospital create API.

Must NOT be used by Food Flash, Dine Flash, Dine Flash Buffet, Airline Flash,
or other flavours. Contains no HTTP/auth/response code.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from django.db import transaction
from django.db.models import Max, Prefetch

from manager.utils.utils import reset_counters_if_new_business_day
from vendors.models import Order, Utility
from vendors.serializers import OrdersSerializer

logger = logging.getLogger(__name__)


class HospitalOrderCreateStatus(str, Enum):
    """Outcome codes consumed by Hospital create API views."""

    CREATED = "created"
    CUSTOMER_NAME_REQUIRED = "customer_name_required"
    UTILITY_IDS_REQUIRED = "utility_ids_required"
    INVALID_UTILITY_ID = "invalid_utility_id"
    VENDOR_CONFIG_MISSING = "vendor_config_missing"
    DEPARTMENTS_NOT_ENABLED = "departments_not_enabled"
    INVALID_DEPARTMENTS = "invalid_departments"
    EMPTY_GROUP_EXPANSION = "empty_group_expansion"
    SERIALIZER_INVALID = "serializer_invalid"
    CREATE_FAILED = "create_failed"


@dataclass(frozen=True)
class HospitalOrderCreateResult:
    """
    Create return contract.

    On CREATED: vendor, customer_name, registration_batch_id, and departments
    are set. departments entries match the historical hospital_patient_submit
    shape. On error statuses, error_message (and optionally error_details for
    serializer failures) carry the historical error payload text/body.
    """

    status: HospitalOrderCreateStatus
    error_message: Optional[str] = None
    error_details: Any = None
    vendor: Any = None
    customer_name: Optional[str] = None
    registration_batch_id: Optional[UUID] = None
    departments: list = field(default_factory=list)


def build_hospital_remarks(mr_number=None, bill_number=None, remarks=None):
    """Compose Order.remarks from optional MR, Bill, and freeform text."""
    lines = []
    if mr_number and str(mr_number).strip():
        lines.append(f"MR: {str(mr_number).strip()}")
    if bill_number and str(bill_number).strip():
        lines.append(f"Bill: {str(bill_number).strip()}")
    header = "\n".join(lines)
    extra = (remarks or "").strip()
    if extra:
        return f"{header}\n\n{extra}" if header else extra
    return header or None


def allocate_booking_number(vendor, vendor_config, utility):
    """Allocate display booking number (prefix counter or token fallback)."""
    if vendor_config.use_utilities and utility and utility.prefix:
        if utility.token_mode == Utility.TOKEN_MODE_CONTINUOUS:
            vendor_config.continuous_booking_counter += 1
            vendor_config.save(update_fields=["continuous_booking_counter"])
            booking_counter = vendor_config.continuous_booking_counter
        else:
            utility.utility_booking_counter += 1
            utility.save(update_fields=["utility_booking_counter"])
            booking_counter = utility.utility_booking_counter
        return f"{utility.prefix}-{booking_counter}"

    max_token = Order.objects.filter(vendor=vendor).aggregate(m=Max("token_no")).get("m")
    token_no = (max_token + 1) if max_token is not None else 1
    return str(token_no)


def next_token_no(vendor):
    max_token = Order.objects.filter(vendor=vendor).aggregate(m=Max("token_no")).get("m")
    return (max_token + 1) if max_token is not None else 1


def expand_hospital_departments(ordered_selected_utilities):
    """
    Expand selected utilities into individual departments for token creation.

    Group departments resolve to their included individual members. Individuals
    are kept as-is. Selection order is preserved; duplicates are skipped.
    """
    expanded_departments = []
    seen_department_ids = set()
    for selected_utility in ordered_selected_utilities:
        if selected_utility.department_type == Utility.DEPARTMENT_TYPE_GROUP:
            members = [
                member
                for member in selected_utility.group_departments.all()
                if member.department_type == Utility.DEPARTMENT_TYPE_INDIVIDUAL
            ]
            for member in members:
                if member.id in seen_department_ids:
                    continue
                seen_department_ids.add(member.id)
                expanded_departments.append(member)
            continue

        if selected_utility.id in seen_department_ids:
            continue
        seen_department_ids.add(selected_utility.id)
        expanded_departments.append(selected_utility)

    return expanded_departments


def create_hospital_orders(
    *,
    vendor,
    customer_name,
    utility_ids,
    phone_number=None,
    mr_number=None,
    bill_number=None,
    remarks=None,
    updated_by: str = "customer",
    user_profile=None,
    log_prefix: str = "[hospital]",
) -> HospitalOrderCreateResult:
    """
    Create Hospital Orders for each expanded department under one registration batch.

    Caller must supply a resolved Vendor instance (with config available).
    Does not perform HTTP parsing, auth, or response building.
    """
    customer_name = (customer_name or "").strip()
    phone_number = (phone_number or "").strip() or None
    mr_number = (mr_number or "").strip() or None
    bill_number = (bill_number or "").strip() or None
    freeform_remarks = (remarks or "").strip() or None

    if not customer_name:
        return HospitalOrderCreateResult(
            status=HospitalOrderCreateStatus.CUSTOMER_NAME_REQUIRED,
            error_message="customer_name is required.",
        )

    if not isinstance(utility_ids, list) or not utility_ids:
        return HospitalOrderCreateResult(
            status=HospitalOrderCreateStatus.UTILITY_IDS_REQUIRED,
            error_message="utility_ids must be a non-empty list of department IDs.",
        )

    vendor_config = getattr(vendor, "config", None)
    if vendor_config is None:
        return HospitalOrderCreateResult(
            status=HospitalOrderCreateStatus.VENDOR_CONFIG_MISSING,
            error_message="Vendor configuration missing.",
        )

    if not vendor_config.use_utilities:
        return HospitalOrderCreateResult(
            status=HospitalOrderCreateStatus.DEPARTMENTS_NOT_ENABLED,
            error_message="Departments are not enabled for this branch.",
        )

    unique_utility_ids = []
    seen = set()
    for raw_id in utility_ids:
        try:
            uid = int(raw_id)
        except (TypeError, ValueError):
            return HospitalOrderCreateResult(
                status=HospitalOrderCreateStatus.INVALID_UTILITY_ID,
                error_message=f"Invalid utility_id: {raw_id!r}",
            )
        if uid not in seen:
            seen.add(uid)
            unique_utility_ids.append(uid)

    utilities = list(
        Utility.objects.filter(
            id__in=unique_utility_ids,
            vendor=vendor,
            is_active=True,
        )
        .prefetch_related(
            Prefetch(
                "group_departments",
                queryset=Utility.objects.filter(
                    vendor=vendor,
                    is_active=True,
                ).order_by("display_order", "id"),
            )
        )
        .order_by("id")
    )
    if len(utilities) != len(unique_utility_ids):
        return HospitalOrderCreateResult(
            status=HospitalOrderCreateStatus.INVALID_DEPARTMENTS,
            error_message="One or more selected departments are invalid or inactive.",
        )

    utility_by_id = {u.id: u for u in utilities}
    ordered_selected_utilities = [utility_by_id[uid] for uid in unique_utility_ids]
    expanded_departments = expand_hospital_departments(ordered_selected_utilities)

    if not expanded_departments:
        return HospitalOrderCreateResult(
            status=HospitalOrderCreateStatus.EMPTY_GROUP_EXPANSION,
            error_message=(
                "Selected group department does not contain active individual departments."
            ),
        )

    composed_remarks = build_hospital_remarks(mr_number, bill_number, freeform_remarks)
    batch_id = uuid.uuid4()
    created_orders = []

    try:
        with transaction.atomic():
            for utility in expanded_departments:
                reset_counters_if_new_business_day(vendor, utility)
                vendor_config.refresh_from_db()
                utility.refresh_from_db()

                token_no = next_token_no(vendor)
                booking_no = allocate_booking_number(vendor, vendor_config, utility)

                order_payload = {
                    "vendor": vendor.id,
                    "token_no": token_no,
                    "table_booking_no": booking_no,
                    "counter_no": 1,
                    "updated_by": updated_by,
                    "status": "waiting",
                    "customer_name": customer_name,
                    "phone_number": phone_number,
                    "remarks": composed_remarks,
                    "utility": utility.id,
                }
                if user_profile is not None:
                    order_payload["manager_id"] = user_profile.id

                serializer = OrdersSerializer(data=order_payload)
                if not serializer.is_valid():
                    logger.warning(
                        "%s Serializer validation failed | %s",
                        log_prefix,
                        serializer.errors,
                    )
                    return HospitalOrderCreateResult(
                        status=HospitalOrderCreateStatus.SERIALIZER_INVALID,
                        error_message="Serializer validation failed.",
                        error_details=serializer.errors,
                    )

                order = serializer.save()
                Order.objects.filter(pk=order.pk).update(registration_batch_id=batch_id)
                order.registration_batch_id = batch_id
                created_orders.append(
                    {
                        "order_id": order.id,
                        "utility_id": utility.id,
                        "department_name": utility.display_name or utility.utility_name,
                        "display_code": utility.display_code or "",
                        "token": booking_no,
                        "token_no": token_no,
                        "registration_batch_id": str(batch_id),
                    }
                )
    except Exception as exc:
        logger.exception("%s Failed to create orders: %s", log_prefix, exc)
        return HospitalOrderCreateResult(
            status=HospitalOrderCreateStatus.CREATE_FAILED,
            error_message="Unable to complete patient registration. Please try again.",
        )

    logger.info(
        "%s Created %s orders | vendor=%s batch=%s patient=%s updated_by=%s",
        log_prefix,
        len(created_orders),
        getattr(vendor, "vendor_id", None),
        batch_id,
        customer_name,
        updated_by,
    )

    return HospitalOrderCreateResult(
        status=HospitalOrderCreateStatus.CREATED,
        vendor=vendor,
        customer_name=customer_name,
        registration_batch_id=batch_id,
        departments=created_orders,
    )
