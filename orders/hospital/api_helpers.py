"""
Hospital Flash HTTP helpers shared by customer and manager create adapters.

Tracking URL and create-error mapping only. Order-creation business logic lives
in orders.hospital.order_create — do not add it here.

Must NOT be used by other product flavours.
"""
from urllib.parse import urlencode

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response

from orders.hospital.order_create import HospitalOrderCreateStatus

project_name = getattr(settings, "PROJECT_NAME", "").strip().lower()

# Roles permitted to create Hospital orders via the manager create API.
HOSPITAL_ORDER_CREATE_ROLES = frozenset({"admin_manager", "outlet_manager"})


def build_hospital_tracking_url(request, vendor, primary_order, batch_id):
    """
    Build a customer tracking URL for the shared home/ page.
    Mirrors Dine Flash booking_no + booking_id params and adds registration_batch_id
    for future multi-department queue tracking.
    """
    params = urlencode(
        {
            "location_id": vendor.location_id or "",
            "vendor_id": vendor.vendor_id,
            "booking_no": primary_order["token"],
            "booking_id": primary_order["order_id"],
            "registration_batch_id": str(batch_id),
        }
    )
    return request.build_absolute_uri(f"/{project_name}/home/?{params}")


def hospital_create_error_response(result):
    """Map HospitalOrderCreateResult error statuses to historical HTTP responses."""
    if result.status == HospitalOrderCreateStatus.SERIALIZER_INVALID:
        return Response(
            {"error": result.error_details},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if result.status == HospitalOrderCreateStatus.VENDOR_CONFIG_MISSING:
        return Response(
            {"error": result.error_message},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    if result.status == HospitalOrderCreateStatus.CREATE_FAILED:
        return Response(
            {"error": result.error_message},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return Response(
        {"error": result.error_message},
        status=status.HTTP_400_BAD_REQUEST,
    )
