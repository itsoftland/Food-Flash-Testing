import logging

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.config.status_choices import STATUS_CHOICES_MAP
from orders.serializers import VendorLogoSerializer
from static.utils.functions.queries import update_patient_status_by_hospital_manager
from static.utils.functions.utils import get_vendor_business_day_range
from vendors.models import Order, Utility
from vendors.utils import notify_web_push

logger = logging.getLogger(__name__)
project_name = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()

HOSPITAL_STATUS_ACTIONS = frozenset({"called", "completed", "cancelled"})

HOSPITAL_STATUS_TRANSITIONS = {
    "registered": {"waiting"},
    "waiting": {"called", "completed", "cancelled"},
    "called": {"completed", "cancelled"},
}

HOSPITAL_TERMINAL_STATUSES = frozenset({"completed", "cancelled"})


def _hospital_flash_only_response():
    if project_name != "hospital_flash":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    return None


def _hospital_allowed_statuses():
    return {choice[0] for choice in STATUS_CHOICES_MAP.get("hospital_flash", [])}


def _validate_hospital_transition(current_status, new_status):
    current = (current_status or "").strip().lower()
    new = (new_status or "").strip().lower()
    if current in HOSPITAL_TERMINAL_STATUSES:
        return False, f"Cannot update a {current} order."
    allowed = HOSPITAL_STATUS_TRANSITIONS.get(current, set())
    if new not in allowed:
        return False, f"Transition from '{current}' to '{new}' is not allowed."
    return True, ""


def resolve_hospital_effective_departments(assigned_utilities):
    """
    Hospital Flash only: expand assigned utilities into individual departments.

    Group/package assignments resolve to their included individual departments.
    Individual assignments are kept as-is. Results are deduplicated.

    Example: Prime Package(Ortho, Xray) → [Ortho, Xray]
    Example: Prime Package + Lab → [Ortho, Xray, Lab]
    """
    if hasattr(assigned_utilities, "prefetch_related"):
        utilities = assigned_utilities.prefetch_related("group_departments")
    else:
        utilities = assigned_utilities

    effective = []
    seen_ids = set()
    for utility in utilities:
        if utility.department_type == Utility.DEPARTMENT_TYPE_GROUP:
            for member in utility.group_departments.all():
                if member.department_type != Utility.DEPARTMENT_TYPE_INDIVIDUAL:
                    continue
                if member.id in seen_ids:
                    continue
                seen_ids.add(member.id)
                effective.append(member)
            continue

        if utility.id in seen_ids:
            continue
        seen_ids.add(utility.id)
        effective.append(utility)

    return effective


def build_hospital_department_status_payload(request, order, new_status):
    """
    Single-department hospitalstatus payload for manager status updates.
    Never includes departments[] — batch cards remain registration snapshots only.
    """
    vendor = order.vendor
    vendor_serializer = VendorLogoSerializer(vendor, context={"request": request})
    logo_url = vendor_serializer.data.get("logo_url", "")
    utility_display = order.utility.display_name if order.utility else "-"
    batch_id = order.registration_batch_id

    return {
        "title": "Department Status Update",
        "body": f"{utility_display} ({order.table_booking_no}): {new_status}",
        "type": "hospitalstatus",
        "registration_batch_id": str(batch_id) if batch_id else None,
        "booking_id": order.id,
        "booking_no": order.table_booking_no,
        "utility_name": utility_display,
        "customer_name": order.customer_name,
        "status": new_status,
        "token_no": order.token_no,
        "counter_no": order.counter_no or 1,
        "name": vendor.name,
        "alias_name": vendor.alias_name,
        "vendor_id": vendor.vendor_id,
        "location_id": vendor.location_id,
        "logo_url": logo_url,
        "vibration_pattern": vendor.config.vibration_pattern,
        "vibration_duration": vendor.config.vibration_duration,
    }


def _authorize_hospital_department_user(user_profile, order):
    """Hospital department users fail closed when unassigned; managers stay unrestricted."""
    if user_profile.role != "utility_user":
        return True
    assigned_utilities = user_profile.assigned_utilities.all()
    if not assigned_utilities.exists():
        return False
    effective_departments = resolve_hospital_effective_departments(assigned_utilities)
    if not effective_departments:
        return False
    return order.utility_id in {dept.id for dept in effective_departments}


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def manager_patient_update(request):
    """
    Hospital Flash: update a single department order status and notify the patient.

    Body: { "booking_id": <int>, "action": "called"|"completed"|"cancelled", "utility_id": <int>? }
    """
    blocked = _hospital_flash_only_response()
    if blocked:
        return blocked

    data = request.data
    booking_id_raw = data.get("booking_id")
    action = (data.get("action") or data.get("status") or "").strip().lower()

    if booking_id_raw in (None, ""):
        return Response({"message": "booking_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not action:
        return Response({"message": "action is required."}, status=status.HTTP_400_BAD_REQUEST)
    if action not in HOSPITAL_STATUS_ACTIONS:
        return Response(
            {"message": "Invalid action.", "allowed": sorted(HOSPITAL_STATUS_ACTIONS)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if action not in _hospital_allowed_statuses():
        return Response({"message": "Invalid hospital status."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        booking_id = int(booking_id_raw)
    except (TypeError, ValueError):
        return Response({"message": "booking_id must be a valid integer."}, status=status.HTTP_400_BAD_REQUEST)

    manager_qs = getattr(request.user, "profile_roles", None)
    if not manager_qs or not manager_qs.exists():
        return Response({"message": "User is not a manager."}, status=status.HTTP_403_FORBIDDEN)
    manager = manager_qs.first()
    if not manager.vendor:
        return Response({"message": "Manager does not have an associated vendor."}, status=status.HTTP_403_FORBIDDEN)

    vendor = manager.vendor
    start_dt, end_dt = get_vendor_business_day_range(vendor)
    if not start_dt or not end_dt:
        return Response({"error": "Invalid date range"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            booking = (
                Order.objects.select_for_update()
                .select_related("utility", "vendor", "vendor__config")
                .filter(id=booking_id, vendor=vendor, created_at__range=(start_dt, end_dt))
                .first()
            )
            if not booking:
                return Response(
                    {"message": f"Booking with booking_id {booking_id} not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not _authorize_hospital_department_user(manager, booking):
                return Response(
                    {"message": "You are not authorized to update this department order."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            utility_id = data.get("utility_id")
            if utility_id not in (None, ""):
                try:
                    utility_id_int = int(utility_id)
                except (TypeError, ValueError):
                    return Response(
                        {"message": "utility_id must be a valid integer."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if booking.utility_id != utility_id_int:
                    return Response(
                        {"message": "utility_id does not match this booking."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            previous_status = (booking.status or "").strip().lower()
            if previous_status == action:
                payload = build_hospital_department_status_payload(request, booking, action)
                return Response(
                    {
                        "success": True,
                        "message": "Status unchanged.",
                        "booking_id": booking.id,
                        "status": action,
                        "payload": payload,
                    },
                    status=status.HTTP_200_OK,
                )

            valid, error_message = _validate_hospital_transition(previous_status, action)
            if not valid:
                return Response({"message": error_message}, status=status.HTTP_400_BAD_REQUEST)

            updated_booking = update_patient_status_by_hospital_manager(booking, action, manager)
            payload = build_hospital_department_status_payload(request, updated_booking, action)
            notify_web_push(updated_booking, vendor, payload)

            logger.info(
                "[manager_patient_update] booking_id=%s utility=%s %s -> %s manager=%s",
                booking_id,
                updated_booking.utility.display_name if updated_booking.utility else "-",
                previous_status,
                action,
                manager.name,
            )

            return Response(
                {
                    "success": True,
                    "message": "Patient status updated successfully.",
                    "booking_id": updated_booking.id,
                    "booking_no": updated_booking.table_booking_no,
                    "status": action,
                    "previous_status": previous_status,
                    "utility_name": payload.get("utility_name"),
                    "registration_batch_id": payload.get("registration_batch_id"),
                    "payload": payload,
                },
                status=status.HTTP_200_OK,
            )
    except Exception:
        logger.exception("[manager_patient_update] Unexpected error booking_id=%s", booking_id)
        return Response(
            {"success": False, "message": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
