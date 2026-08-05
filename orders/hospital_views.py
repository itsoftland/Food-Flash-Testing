import logging

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from orders.hospital.api_helpers import (
    build_hospital_tracking_url,
    hospital_create_error_response,
)
from orders.hospital.order_create import (
    HospitalOrderCreateStatus,
    create_hospital_orders,
)
from orders.hospital_qr import unsign_hospital_branch_qr
from vendors.models import Vendor

logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "").strip().lower()


def _hospital_flash_only():
    if project_name != "hospital_flash":
        return HttpResponseNotFound()
    return None


def _resolve_vendor(vendor_id):
    if not vendor_id:
        return None, "vendor_id is required."
    try:
        vendor_id_int = int(vendor_id)
    except (TypeError, ValueError):
        return None, "Invalid vendor_id."
    vendor = Vendor.objects.select_related("config", "admin_outlet").filter(
        vendor_id=vendor_id_int
    ).first()
    if not vendor:
        return None, "Vendor not found."
    return vendor, None


def _vendor_page_context(vendor_id):
    utilities_enabled = False
    phone_number_enabled = False
    mr_number_enabled = False
    bill_number_enabled = False
    vendor_name = ""
    hospital_name = ""
    logo_url = ""

    if vendor_id:
        vendor, _err = _resolve_vendor(vendor_id)
        if vendor and hasattr(vendor, "config"):
            utilities_enabled = vendor.config.use_utilities
            phone_number_enabled = vendor.config.phone_number_enabled
            mr_number_enabled = vendor.config.mr_number_enabled
            bill_number_enabled = vendor.config.bill_number_enabled
            vendor_name = vendor.alias_name or vendor.name or ""
            if getattr(vendor, "admin_outlet", None):
                hospital_name = vendor.admin_outlet.customer_name or ""
            if getattr(vendor, "logo", None) and hasattr(vendor.logo, "url"):
                logo_url = vendor.logo.url

    return {
        "vendor_id": vendor_id or "",
        "UTILITIES_ENABLED": utilities_enabled,
        "PHONE_NUMBER_ENABLED": phone_number_enabled,
        "MR_NUMBER_ENABLED": mr_number_enabled,
        "BILL_NUMBER_ENABLED": bill_number_enabled,
        "VENDOR_NAME": vendor_name,
        "HOSPITAL_NAME": hospital_name,
        "VENDOR_LOGO_URL": logo_url,
    }


def hospital_patient_registration(request):
    """Hospital Flash — patient registration (step 1)."""
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid request method.")
    blocked = _hospital_flash_only()
    if blocked:
        return blocked

    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")

    # Prefer signed branch QR token when present (same pattern as Buffet table QR).
    qr_token = request.GET.get("qr_token")
    if qr_token:
        payload = unsign_hospital_branch_qr(qr_token)
        if payload and Vendor.objects.filter(vendor_id=payload["vendor_id"]).exists():
            vendor_id = payload["vendor_id"]

    context = _vendor_page_context(vendor_id)
    return render(request, "orders/hospital/patient_registration.html", context)


def hospital_department_selection(request):
    """Hospital Flash — department multi-select (step 2)."""
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid request method.")
    blocked = _hospital_flash_only()
    if blocked:
        return blocked

    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")
    context = _vendor_page_context(vendor_id)
    return render(request, "orders/hospital/department_selection.html", context)


def hospital_registration_confirmation(request):
    """Hospital Flash — registration confirmation with per-department tokens."""
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid request method.")
    blocked = _hospital_flash_only()
    if blocked:
        return blocked

    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")
    context = _vendor_page_context(vendor_id)
    return render(request, "orders/hospital/registration_confirmation.html", context)


@api_view(["POST"])
@permission_classes([AllowAny])
def hospital_patient_submit(request):
    """
    Hospital Flash — public patient registration / order create.

    Thin HTTP adapter over create_hospital_orders. Request/response contract
    is unchanged from the historical monolithic implementation.
    """
    if project_name != "hospital_flash":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    data = request.data or {}
    vendor_id = data.get("vendor_id")
    customer_name = (data.get("customer_name") or data.get("patient_name") or "").strip()
    phone_number = (data.get("phone_number") or "").strip() or None
    mr_number = (data.get("mr_number") or "").strip() or None
    bill_number = (data.get("bill_number") or "").strip() or None
    freeform_remarks = (data.get("remarks") or "").strip() or None
    utility_ids = data.get("utility_ids") or []

    # Preserve historical validation order: name / utility_ids before vendor_id errors.
    if not customer_name:
        return Response({"error": "customer_name is required."}, status=status.HTTP_400_BAD_REQUEST)

    if not isinstance(utility_ids, list) or not utility_ids:
        return Response(
            {"error": "utility_ids must be a non-empty list of department IDs."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    vendor, err = _resolve_vendor(vendor_id)
    if err:
        code = status.HTTP_404_NOT_FOUND if "not found" in err.lower() else status.HTTP_400_BAD_REQUEST
        return Response({"error": err}, status=code)

    result = create_hospital_orders(
        vendor=vendor,
        customer_name=customer_name,
        utility_ids=utility_ids,
        phone_number=phone_number,
        mr_number=mr_number,
        bill_number=bill_number,
        remarks=freeform_remarks,
        updated_by="customer",
        user_profile=None,
        log_prefix="[hospital_patient_submit]",
    )

    if result.status != HospitalOrderCreateStatus.CREATED:
        return hospital_create_error_response(result)

    primary_order = result.departments[0]
    tracking_url = build_hospital_tracking_url(
        request, result.vendor, primary_order, result.registration_batch_id
    )

    return Response(
        {
            "message": "Patient registered successfully.",
            "registration_batch_id": str(result.registration_batch_id),
            "patient_name": result.customer_name,
            "location_id": result.vendor.location_id,
            "vendor_id": result.vendor.vendor_id,
            "tracking_url": tracking_url,
            "departments": result.departments,
        },
        status=status.HTTP_201_CREATED,
    )
