import logging

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import render
from django.http import HttpResponseBadRequest
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from vendors.models import (
    Vendor,
    AdminOutlet,
    UserProfile,
    AndroidAPK,
)
from core.config.status_choices import STATUS_CHOICES_MAP
from orders.buffet_table_qr import is_valid_buffet_table_no, unsign_buffet_table_qr
from orders.buffet.active_order_registry import (
    latest_buffet_order_id_for_lookup,
    list_selectable_buffet_active_orders,
    serialize_buffet_active_order_for_selector,
)
from orders.buffet.order_create import (
    BUFFET_ITEM_REMARKS_MAX_LENGTH,
    BuffetOrderCreateStatus,
    create_buffet_order,
)
from orders.buffet.order_lookup import (
    BuffetOrderLookupResolveStatus,
    normalize_order_lookup_id,
    resolve_buffet_order_lookup,
)

logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "").strip().lower()


def _buffet_workflow_context(step):
    """Workflow footer context — Dine Flash Buffet customer flow only."""
    if project_name != "dine_flash_buffet":
        return {}
    return {
        "show_buffet_workflow_footer": True,
        "buffet_workflow_step": step,
    }

@api_view(['POST'])
@permission_classes([AllowAny])
def buffet_submit_order(request):
    logger.info(
        "[buffet_submit_order] Started | remote_addr=%s",
        request.META.get("REMOTE_ADDR"),
    )
    data = request.data or {}

    vendor_id = data.get("vendor_id")
    table_number = data.get("table_number")
    customer_name = data.get("customer_name")
    phone_number = data.get("phone_number")
    items_data = data.get("items", [])
    # Optional opaque recovery key (not browser_id). Absent/empty = no mapping write.
    raw_order_lookup_id = data.get("order_lookup_id")
    order_lookup_id = normalize_order_lookup_id(raw_order_lookup_id)
    if raw_order_lookup_id is not None and str(raw_order_lookup_id).strip() and order_lookup_id is None:
        logger.warning(
            "[buffet_submit_order] Invalid order_lookup_id | length=%s",
            len(str(raw_order_lookup_id).strip()),
        )
        return Response(
            {"error": "Invalid order_lookup_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # "+" / additional-order path: register Active Order only; do not move Latest Order Wins.
    # Default False preserves today's QR / single-order submit (lookup upsert unchanged).
    is_additional_order = data.get("is_additional_order") is True

    if not vendor_id or not items_data:
        logger.warning(
            "[buffet_submit_order] Missing required fields | vendor_id=%s | items_count=%s",
            vendor_id,
            len(items_data) if isinstance(items_data, list) else 0,
        )
        return Response({"error": "vendor_id and items are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        vendor_id_int = int(vendor_id)
    except (ValueError, TypeError):
        logger.warning("[buffet_submit_order] Invalid vendor_id | vendor_id=%s", vendor_id)
        return Response({"error": "Invalid vendor_id"}, status=status.HTTP_400_BAD_REQUEST)

    vendor = Vendor.objects.filter(vendor_id=vendor_id_int).first()
    if not vendor:
        logger.warning(
            "[buffet_submit_order] Vendor not found | vendor_id=%s",
            vendor_id_int,
        )
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    result = create_buffet_order(
        vendor=vendor,
        items_data=items_data,
        updated_by="customer",
        table_number=table_number,
        customer_name=customer_name,
        phone_number=phone_number,
        order_lookup_id=order_lookup_id,
        is_additional_order=is_additional_order,
        log_prefix="[buffet_submit_order]",
    )

    if result.status == BuffetOrderCreateStatus.REMARKS_TOO_LONG:
        return Response(
            {"error": result.error_message},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if result.status == BuffetOrderCreateStatus.NO_VALID_ITEMS:
        return Response(
            {"error": result.error_message},
            status=status.HTTP_400_BAD_REQUEST,
        )

    order = result.order
    created_items = result.created_item_ids or []

    # Note: For DineFlash Buffet, we may need to trigger a web socket / mqtt message to the Kitchen View here.
    # The kitchen view will poll or rely on mqtt. We can add MQTT publishing later if required.

    logger.info(
        "[buffet_submit_order] Order created | vendor_id=%s | order_id=%s | token_no=%s | "
        "table_number=%s | items_count=%s",
        vendor_id_int,
        order.id,
        order.token_no,
        table_number,
        len(created_items),
    )

    return Response({
        "message": "Order placed successfully.",
        "order_id": order.id,
        "token_no": order.token_no,
        "table_number": table_number,
        "items_count": len(created_items)
    }, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def resolve_order_lookup(request):
    """
    Dine Flash Buffet only: read-only order_lookup_id → token_no / vendor_id / location_id.
    Does not mutate Order status, PushSubscription, or Chat.
    """
    if project_name != "dine_flash_buffet":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    order_lookup_id = (request.data or {}).get("order_lookup_id")
    logger.info(
        "[buffet] resolve_order_lookup request | order_lookup_id_present=%s",
        bool(order_lookup_id),
    )

    try:
        result = resolve_buffet_order_lookup(order_lookup_id=order_lookup_id)

        if result.status == BuffetOrderLookupResolveStatus.FOUND:
            logger.info(
                "[buffet] resolve_order_lookup found | token_no=%s vendor_id=%s",
                result.data.get("token_no"),
                result.data.get("vendor_id"),
            )
            return Response(
                {"status": "found", **result.data},
                status=status.HTTP_200_OK,
            )

        if result.status == BuffetOrderLookupResolveStatus.INVALID_INPUT:
            return Response(
                {"status": BuffetOrderLookupResolveStatus.INVALID_INPUT.value},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if result.status == BuffetOrderLookupResolveStatus.NOT_FOUND:
            return Response(
                {"status": BuffetOrderLookupResolveStatus.NOT_FOUND.value},
                status=status.HTTP_404_NOT_FOUND,
            )

        if result.status == BuffetOrderLookupResolveStatus.NOT_FOUND_OR_STALE:
            return Response(
                {"status": BuffetOrderLookupResolveStatus.NOT_FOUND_OR_STALE.value},
                status=status.HTTP_404_NOT_FOUND,
            )

        logger.exception(
            "[buffet] resolve_order_lookup unhandled status | status=%s",
            result.status,
        )
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception:
        logger.exception("[buffet] resolve_order_lookup unexpected failure")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def list_active_orders(request):
    """
    Dine Flash Buffet only: Order Selector data API.

    Reads BuffetActiveOrder for order_lookup_id. Marks is_latest from
    BuffetOrderLookup (Latest Order Wins), never from the Registry.

    Does not mutate Order, PushSubscription, Chat, or recovery paths.
    """
    if project_name != "dine_flash_buffet":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    order_lookup_id = request.query_params.get("order_lookup_id")
    normalized = normalize_order_lookup_id(order_lookup_id)
    if normalized is None:
        logger.info(
            "[buffet] list_active_orders invalid_input | order_lookup_id_present=%s",
            order_lookup_id is not None and str(order_lookup_id).strip() != "",
        )
        return Response(
            {"status": "invalid_input"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    latest_order_id = latest_buffet_order_id_for_lookup(order_lookup_id=normalized)
    entries = list_selectable_buffet_active_orders(order_lookup_id=normalized)
    payload = [
        serialize_buffet_active_order_for_selector(
            entry,
            is_latest=(latest_order_id is not None and entry.order_id == latest_order_id),
        )
        for entry in entries
    ]
    logger.info(
        "[buffet] list_active_orders ok | order_lookup_id=%s count=%s latest_order_id=%s",
        normalized,
        len(payload),
        latest_order_id,
    )
    return Response(payload, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_table_booking(request):
    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")
    prefilled_table_no = None
    table_from_qr = False

    if project_name == "dine_flash_buffet":
        qr_token = request.GET.get("qr_token")
        if qr_token:
            payload = unsign_buffet_table_qr(qr_token)
            if payload and Vendor.objects.filter(vendor_id=payload["vendor_id"]).exists():
                vendor_id = payload["vendor_id"]
                prefilled_table_no = payload["table_no"]
                table_from_qr = True

        if not table_from_qr:
            legacy_table_no = request.GET.get("table_no")
            if legacy_table_no and is_valid_buffet_table_no(legacy_table_no):
                prefilled_table_no = str(int(str(legacy_table_no).strip()))
                table_from_qr = True

    utilities_enabled = False
    phone_number_enabled = False

    if vendor_id:
        vendor = Vendor.objects.filter(vendor_id=vendor_id).first()
        if vendor and hasattr(vendor, "config"):
            utilities_enabled = vendor.config.use_utilities
            phone_number_enabled = vendor.config.phone_number_enabled

    context = {
        "vendor_id": vendor_id or "",
        "prefilled_table_no": prefilled_table_no or "",
        "table_from_qr": table_from_qr,
        "UTILITIES_ENABLED": utilities_enabled,
        "PHONE_NUMBER_ENABLED": phone_number_enabled,
        **_buffet_workflow_context(1),
    }

    return render(request, 'orders/buffet/table_booking.html', context)

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_utility_selection(request):
    return render(
        request,
        'orders/buffet/utility_selection.html',
        _buffet_workflow_context(2),
    )

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_combined_options(request):
    return render(
        request,
        "orders/buffet/combined_options.html",
        {
            "buffet_remarks_max_length": BUFFET_ITEM_REMARKS_MAX_LENGTH,
            **_buffet_workflow_context(3),
        },
    )

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_order_confirmation(request):
    return render(
        request,
        'orders/buffet/order_confirmation.html',
        _buffet_workflow_context(4),
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def buffet_utility_login(request):
    """
    Buffet-only utility-user login with customer + device validation.
    """
    if project_name != "dine_flash_buffet":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    username = request.data.get("username")
    password = request.data.get("password")
    mac_address = request.data.get("mac_address")
    customer_id = request.data.get("customer_id")
    token = request.data.get("token")
    apk_version = request.data.get("apk_version")

    required = {
        "username": username,
        "password": password,
        "mac_address": mac_address,
        "customer_id": customer_id,
        "token": token,
        "apk_version": apk_version,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        return Response(
            {"error": f"Missing required fields: {', '.join(missing)}."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(username=username, password=password)
    if not user:
        return Response(
            {"error": "Invalid username or password."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    admin_outlets_qs = AdminOutlet.objects.filter(customer_id=customer_id).order_by("id")
    if not admin_outlets_qs.exists():
        return Response(
            {"error": "Invalid customer_id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    utility_profile = (
        UserProfile.objects.select_related("vendor", "admin_outlet")
        .prefetch_related("assigned_utilities")
        .filter(
            Q(
                user=user,
                role="utility_user",
                admin_outlet__in=admin_outlets_qs,
            )
            | Q(
                user=user,
                role="utility_user",
                vendor__admin_outlet__in=admin_outlets_qs,
            )
        )
        .first()
    )
    if not utility_profile:
        return Response(
            {"error": "Utility user mapping not found for this customer.", "device_approved": False},
            status=status.HTTP_403_FORBIDDEN,
        )
    admin_outlet = utility_profile.admin_outlet
    if utility_profile.vendor and utility_profile.vendor.admin_outlet_id in admin_outlets_qs.values_list("id", flat=True):
        admin_outlet = utility_profile.vendor.admin_outlet
    if utility_profile.vendor is None:
        return Response(
            {
                "error": "Utility user is not mapped to any vendor. Please contact admin.",
                "device_approved": False,
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    if utility_profile.vendor.admin_outlet_id != admin_outlet.id:
        return Response(
            {
                "error": "Utility user vendor does not belong to this customer. Please contact admin.",
                "device_approved": False,
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # Auto-register devices so admins can see/map them from dashboard.
    device = (
        AndroidAPK.objects.filter(mac_address=mac_address, admin_outlet=admin_outlet).first()
        or AndroidAPK.objects.filter(mac_address=mac_address).first()
    )
    if device and device.admin_outlet != admin_outlet:
        return Response(
            {
                "error": (
                    f"Device already registered with another customer "
                    f"{device.admin_outlet.customer_id}. Please contact admin."
                ),
                "device_approved": False,
            },
            status=status.HTTP_409_CONFLICT,
        )
    if device and device.user_profile and device.user_profile != utility_profile:
        return Response(
            {"error": "This device is mapped to another utility user.", "device_approved": False},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        if device:
            device.token = token
            device.apk_version = apk_version
            device.admin_outlet = admin_outlet
            device.save(update_fields=["token", "apk_version", "admin_outlet", "updated_at"])
        else:
            device = AndroidAPK.objects.create(
                token=token,
                apk_version=apk_version,
                mac_address=mac_address,
                admin_outlet=admin_outlet,
                user_profile=None,
            )
    except IntegrityError:
        logger.exception(
            "[buffet_utility_login] IntegrityError while auto-registering device | customer_id=%s, mac=%s",
            customer_id,
            mac_address,
        )
        return Response(
            {"error": "Device registration conflict. Please contact admin.", "device_approved": False},
            status=status.HTTP_409_CONFLICT,
        )

    # Login is allowed only when the registered device is mapped to this utility user.
    if device.user_profile != utility_profile:
        return Response(
            {"error": "Device not mapped with the utility user.", "device_approved": False},
            status=status.HTTP_403_FORBIDDEN,
        )

    mapped_utilities_qs = utility_profile.assigned_utilities.filter(
        vendor=utility_profile.vendor,
        is_active=True,
    ).order_by("id")
    utility_mapped = mapped_utilities_qs.exists()
    if not utility_mapped:
        return Response(
            {
                "error": "Utility user has no active utility mapping for this vendor.",
                "device_approved": False,
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    utilities = [
        {
            "id": util.id,
            "utility_name": util.utility_name,
            "display_name": util.display_name,
            "display_code": util.display_code,
            "token_mode": util.token_mode,
            "prefix": util.prefix,
        }
        for util in mapped_utilities_qs
    ]

    buffet_status_choices = STATUS_CHOICES_MAP.get("dine_flash_buffet", [])
    possible_statuses = [
        {"value": value, "label": label} for value, label in buffet_status_choices
    ]

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "message": "Utility login processed.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "device_approved": True,
            "utility_mapped": utility_mapped,
            "outlet_id": admin_outlet.id,
            "outlet_name": admin_outlet.customer_name or "",
            "possible_statuses": possible_statuses,
            "user": {
                "username": user.username,
                "role": "Utility User",
                "manager_id": utility_profile.id,
                "manager_name": utility_profile.name,
                "customer_id": admin_outlet.customer_id,
                "vendor_id": utility_profile.vendor.vendor_id if utility_profile.vendor else None,
            },
        },
        status=status.HTTP_200_OK,
    )
