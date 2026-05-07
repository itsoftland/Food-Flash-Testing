import logging
from django.conf import settings
from django.db import transaction, IntegrityError
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
    Order,
    Utility,
    BuffetOrderItem,
    AdminOutlet,
    UserProfile,
    AndroidAPK,
)
from manager.utils.utils import reset_counters_if_new_business_day

logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "").strip().lower()

@api_view(['POST'])
@permission_classes([AllowAny])
def buffet_submit_order(request):
    data = request.data or {}

    vendor_id = data.get("vendor_id")
    table_number = data.get("table_number")
    customer_name = data.get("customer_name")
    phone_number = data.get("phone_number")
    items_data = data.get("items", [])

    if not vendor_id or not items_data:
        return Response({"error": "vendor_id and items are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        vendor_id_int = int(vendor_id)
    except (ValueError, TypeError):
        return Response({"error": "Invalid vendor_id"}, status=status.HTTP_400_BAD_REQUEST)

    vendor = Vendor.objects.filter(vendor_id=vendor_id_int).first()
    if not vendor:
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        reset_counters_if_new_business_day(vendor, None)
        
        last_booking = Order.objects.filter(vendor=vendor).order_by("-token_no").first()
        token_no = (last_booking.token_no + 1) if last_booking else 1

        order = Order.objects.create(
            vendor=vendor,
            token_no=token_no,
            table_booking_no=table_number, # Store table number here
            counter_no=1,
            updated_by='customer',
            status='created',
            customer_name=customer_name,
            phone_number=phone_number,
        )

        created_items = []
        for item in items_data:
            utility_id = item.get("utility_id")
            utility = Utility.objects.filter(id=utility_id, vendor=vendor).first()
            if not utility:
                logger.warning(f"Utility {utility_id} not found for vendor {vendor_id_int}")
                continue
            
            customizations = item.get("customizations", [])
            item_remarks = item.get("remarks", "")
            is_grouped = item.get("is_grouped", False)
            quantity = int(item.get("quantity", 1))

            buffet_item = BuffetOrderItem.objects.create(
                order=order,
                utility=utility,
                status='created',
                customizations=customizations,
                remarks=item_remarks,
                is_grouped=is_grouped,
                quantity=quantity
            )
            created_items.append(buffet_item.id)
            
        if not created_items:
            # If no items were created (e.g. due to invalid utilities), rollback.
            transaction.set_rollback(True)
            return Response({"error": "No valid items found in order."}, status=status.HTTP_400_BAD_REQUEST)

    # Note: For DineFlash Buffet, we may need to trigger a web socket / mqtt message to the Kitchen View here.
    # The kitchen view will poll or rely on mqtt. We can add MQTT publishing later if required.

    return Response({
        "message": "Order placed successfully.",
        "order_id": order.id,
        "token_no": order.token_no,
        "table_number": table_number,
        "items_count": len(created_items)
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_table_booking(request):
    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")
    
    utilities_enabled = False
    phone_number_enabled = False

    if vendor_id:
        vendor = Vendor.objects.filter(vendor_id=vendor_id).first()
        if vendor and hasattr(vendor, "config"):
            utilities_enabled = vendor.config.use_utilities
            phone_number_enabled = vendor.config.phone_number_enabled

    context = {
        "vendor_id": vendor_id,
        "UTILITIES_ENABLED": utilities_enabled,
        "PHONE_NUMBER_ENABLED": phone_number_enabled,
    }

    return render(request, 'orders/buffet/table_booking.html', context)

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_utility_selection(request):
    return render(request, 'orders/buffet/utility_selection.html')

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_combined_options(request):
    return render(request, 'orders/buffet/combined_options.html')

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_order_confirmation(request):
    return render(request, 'orders/buffet/order_confirmation.html')


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

    admin_outlet = AdminOutlet.objects.filter(customer_id=customer_id).first()
    if not admin_outlet:
        return Response(
            {"error": "Invalid customer_id."},
            status=status.HTTP_404_NOT_FOUND,
        )

    utility_profile = (
        UserProfile.objects.select_related("vendor", "admin_outlet")
        .prefetch_related("assigned_utilities")
        .filter(
            user=user,
            role="utility_user",
            admin_outlet=admin_outlet,
        )
        .first()
    )
    if not utility_profile:
        return Response(
            {"error": "Utility user mapping not found for this customer."},
            status=status.HTTP_403_FORBIDDEN,
        )
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

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "message": "Utility login processed.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "device_approved": True,
            "utility_mapped": utility_mapped,
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
