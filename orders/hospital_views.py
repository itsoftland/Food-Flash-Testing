import logging
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Prefetch
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from manager.utils.utils import reset_counters_if_new_business_day
from vendors.models import Order, Utility, Vendor
from vendors.serializers import OrdersSerializer

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
    vendor = Vendor.objects.select_related("config").filter(vendor_id=vendor_id_int).first()
    if not vendor:
        return None, "Vendor not found."
    return vendor, None


def _vendor_page_context(vendor_id):
    utilities_enabled = False
    phone_number_enabled = False
    mr_number_enabled = False
    bill_number_enabled = False
    vendor_name = ""
    logo_url = ""

    if vendor_id:
        vendor, _err = _resolve_vendor(vendor_id)
        if vendor and hasattr(vendor, "config"):
            utilities_enabled = vendor.config.use_utilities
            phone_number_enabled = vendor.config.phone_number_enabled
            mr_number_enabled = vendor.config.mr_number_enabled
            bill_number_enabled = vendor.config.bill_number_enabled
            vendor_name = vendor.alias_name or vendor.name or ""
            if getattr(vendor, "logo", None) and hasattr(vendor.logo, "url"):
                logo_url = vendor.logo.url

    return {
        "vendor_id": vendor_id or "",
        "UTILITIES_ENABLED": utilities_enabled,
        "PHONE_NUMBER_ENABLED": phone_number_enabled,
        "MR_NUMBER_ENABLED": mr_number_enabled,
        "BILL_NUMBER_ENABLED": bill_number_enabled,
        "VENDOR_NAME": vendor_name,
        "VENDOR_LOGO_URL": logo_url,
    }


def _build_hospital_remarks(mr_number=None, bill_number=None, remarks=None):
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


def _allocate_booking_number(vendor, vendor_config, utility):
    """Reuse Dine Flash utility queue / token counter logic."""
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


def _next_token_no(vendor):
    max_token = Order.objects.filter(vendor=vendor).aggregate(m=Max("token_no")).get("m")
    return (max_token + 1) if max_token is not None else 1


def _build_hospital_tracking_url(request, vendor, primary_order, batch_id):
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


def hospital_patient_registration(request):
    """Hospital Flash — patient registration (step 1)."""
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid request method.")
    blocked = _hospital_flash_only()
    if blocked:
        return blocked

    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")
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
    if project_name != "hospital_flash":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    data = request.data or {}
    vendor_id = data.get("vendor_id")
    customer_name = (data.get("customer_name") or data.get("patient_name") or "").strip()
    phone_number = (data.get("phone_number") or "").strip() or None
    mr_number = (data.get("mr_number") or "").strip() or None
    bill_number = (data.get("bill_number") or "").strip() or None
    freeform_remarks = (data.get("remarks") or "").strip() or None
    remarks = _build_hospital_remarks(mr_number, bill_number, freeform_remarks)
    utility_ids = data.get("utility_ids") or []

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

    vendor_config = getattr(vendor, "config", None)
    if vendor_config is None:
        return Response({"error": "Vendor configuration missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if not vendor_config.use_utilities:
        return Response(
            {"error": "Departments are not enabled for this branch."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    unique_utility_ids = []
    seen = set()
    for raw_id in utility_ids:
        try:
            uid = int(raw_id)
        except (TypeError, ValueError):
            return Response({"error": f"Invalid utility_id: {raw_id!r}"}, status=status.HTTP_400_BAD_REQUEST)
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
        return Response(
            {"error": "One or more selected departments are invalid or inactive."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    utility_by_id = {u.id: u for u in utilities}
    ordered_selected_utilities = [utility_by_id[uid] for uid in unique_utility_ids]

    # Expand selected group departments into their included individual departments.
    # Selected individual departments are kept as-is. Final execution order follows
    # user selection order, while preventing duplicate token generation.
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

    if not expanded_departments:
        return Response(
            {"error": "Selected group department does not contain active individual departments."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    batch_id = uuid.uuid4()
    created_orders = []

    try:
        with transaction.atomic():
            for utility in expanded_departments:
                reset_counters_if_new_business_day(vendor, utility)
                vendor_config.refresh_from_db()
                utility.refresh_from_db()

                token_no = _next_token_no(vendor)
                booking_no = _allocate_booking_number(vendor, vendor_config, utility)

                order_payload = {
                    "vendor": vendor.id,
                    "token_no": token_no,
                    "table_booking_no": booking_no,
                    "counter_no": 1,
                    "updated_by": "customer",
                    "status": "waiting",
                    "customer_name": customer_name,
                    "phone_number": phone_number,
                    "remarks": remarks,
                    "utility": utility.id,
                }
                serializer = OrdersSerializer(data=order_payload)
                if not serializer.is_valid():
                    logger.warning(
                        "[hospital_patient_submit] Serializer validation failed | %s",
                        serializer.errors,
                    )
                    return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

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
        logger.exception("[hospital_patient_submit] Failed to create orders: %s", exc)
        return Response(
            {"error": "Unable to complete patient registration. Please try again."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.info(
        "[hospital_patient_submit] Created %s orders | vendor=%s batch=%s patient=%s",
        len(created_orders),
        vendor.vendor_id,
        batch_id,
        customer_name,
    )

    primary_order = created_orders[0]
    tracking_url = _build_hospital_tracking_url(request, vendor, primary_order, batch_id)

    return Response(
        {
            "message": "Patient registered successfully.",
            "registration_batch_id": str(batch_id),
            "patient_name": customer_name,
            "location_id": vendor.location_id,
            "vendor_id": vendor.vendor_id,
            "tracking_url": tracking_url,
            "departments": created_orders,
        },
        status=status.HTTP_201_CREATED,
    )
