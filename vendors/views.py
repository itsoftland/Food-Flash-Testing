# Standard library
import json
import logging

# Django
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils.timezone import now, localtime

# Third-party
from rest_framework import status, serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from firebase_admin import messaging

# Local app models
from .models import (
    Order,
    Vendor,
    Device,
    AndroidDevice,
    PushSubscription,
    AdminOutlet,
    AndroidAPK,
    UserProfile,
    VendorConfig
)

# Local app serializers
from .serializers import OrdersSerializer

# Cross-app serializers
from orders.serializers import VendorLogoSerializer

# Local utilities
from .utils import (
    send_push_notification,
    notify_web_push,
    build_tv_config_payload,
    build_vendor_config_payload,
    build_dine_flash_tv_booking_snapshot,
)
from .mqtt_client import get_mqtt_config_for_vendor

# Shared utilities / queries
from static.utils.functions.queries import get_order

# Orders / vendors services
from orders.utils import send_to_managers
from vendors.services.order_service import send_order_update
from vendors.services.get_or_create_azure_device import create_iot_credentials
from vendors.services.send_to_iot import get_azure_devices

# Logger
logger = logging.getLogger(__name__)

# Project name
project_name = getattr(settings, 'PROJECT_NAME', 'food_flash')


def _normalized_project_slug(value):
    return str(value or "").lower().replace("_", "").replace("-", "").replace(" ", "").strip()


def _is_dine_flash_buffet_server(name=None):
    """
    True when this process is the buffet customer stack.
    PROJECT_NAME is usually dine_flash_buffet; some envs use a display-style value
    (e.g. Buffet FLASH) so we match normalized slugs too.
    """
    raw = (name if name is not None else getattr(settings, "PROJECT_NAME", "")) or ""
    if raw.strip().lower() == "dine_flash_buffet":
        return True
    slug = _normalized_project_slug(raw)
    if slug == "dineflashbuffet" or slug.startswith("dineflashbuffet"):
        return True
    if slug == "buffetflash":
        return True
    return False


# API endpoints

@api_view(['GET'])
@permission_classes([AllowAny])
def get_current_time(request):
    """
    Returns the current time in the format: %Y-%m-%d %H:%M:%S

    :param request: The HTTP request object
    :return: A JSON response containing the current time
    :rtype: Response
    """
    
    current_ist = localtime(now())
    formatted_time = current_ist.strftime('%Y-%m-%d %H:%M:%S')
    return Response({'current_time': formatted_time})

@api_view(['GET'])
@permission_classes([AllowAny])
def list_order(request):
    """
    API endpoint to fetch all orders.

    :param request: The HTTP request object
    :return: A JSON response containing all orders
    :rtype: Response
    """
    orders = Order.objects.all()  
    serializer = OrdersSerializer(orders, many=True)
    return Response(serializer.data) 

@api_view(['POST'])
@permission_classes([AllowAny])
def save_subscription(request):
    """
    Saves a push subscription to the database.

    :param request: The HTTP request object
    :return: A JSON response containing a success message or an error message
    :rtype: Response

    The request body should contain the following fields:
    - `endpoint`: The endpoint URL of the push subscription
    - `keys`: A dictionary containing the public key and authentication secret of the push subscription
    - `browser_id`: The browser ID of the user
    - `token_number`: The token number of the order (optional)
    - `vendor_id`: The vendor ID of the vendor

    If the request is successful, the response will contain a success message. If the request fails, the response will contain an error message.
    """
    try:
        logger.info("📥 POST /save_subscription")
        logger.info(f"IP: {request.META.get('REMOTE_ADDR')}, UA: {request.META.get('HTTP_USER_AGENT')}")
        logger.debug(f"Payload received: {request.data}")

        data = request.data
        endpoint = data.get("endpoint")
        keys = data.get("keys", {})
        browser_id = data.get("browser_id")
        token_number = data.get("token_number")
        vendor_id = data.get("vendor_id")

        if not endpoint or not browser_id or not vendor_id:
            logger.warning("⚠️ Missing required subscription fields: endpoint=%s, browser_id=%s, vendor_id=%s",
                           endpoint, browser_id, vendor_id)
            return Response({"error": "Invalid subscription data"}, status=400)

        try:
            vendor = Vendor.objects.get(vendor_id=vendor_id)
            logger.info(f"✅ Vendor resolved: {vendor.name} (vendor_id={vendor.vendor_id})")
        except Vendor.DoesNotExist:
            logger.error(f"❌ Vendor not found for vendor_id={vendor_id}")
            return Response({"error": "Vendor not found."}, status=404)

        # 🚀 Backend-level Flavour Isolation:
        # Ensure the vendor belongs to the current backend project/flavour.
        # Normalized comparison handles 'food_flash' vs 'foodflashqc' etc.
        if vendor.admin_outlet.project_code:
            def normalize(s):
                return str(s or "").lower().replace("_", "").replace("-", "").strip()

            v_project_norm = normalize(vendor.admin_outlet.project_code)
            server_project_norm = normalize(project_name)

            # Check if one is a prefix of the other (e.g., 'foodflash' matches 'foodflashqc')
            is_match = (v_project_norm.startswith(server_project_norm) or 
                        server_project_norm.startswith(v_project_norm))

            # Dine Flash Buffet: outlets often keep food_flash (or foodflash*) project_code while
            # the customer PWA runs on dine_flash_buffet — same vendor/orders, stricter server slug.
            v_compact = v_project_norm.replace(" ", "")
            if not is_match and _is_dine_flash_buffet_server() and v_compact.startswith("foodflash"):
                is_match = True

            if not is_match:
                logger.warning("🚫 Cross-flavour subscription rejected | Vendor: %s, Server: %s",
                               vendor.admin_outlet.project_code, project_name)
                return Response({"error": "This vendor does not belong to the current project context."}, status=403)

        # 📥 Subscription Persistence:
        # The browser_id is now flavour-scoped on the web app, so treat it as the
        # primary identity to prevent cross-flavour endpoint relinking.
        subscription = PushSubscription.objects.filter(browser_id=browser_id).first()

        if not subscription:
            # Guard: endpoint may already exist for another browser identity.
            # Re-linking that row would merge flavours again, so reject instead.
            endpoint_subscription = PushSubscription.objects.filter(endpoint=endpoint).first()
            if endpoint_subscription and endpoint_subscription.browser_id != browser_id:
                logger.warning(
                    "🚫 Endpoint already linked to another browser_id | endpoint=%s old=%s new=%s",
                    endpoint,
                    endpoint_subscription.browser_id,
                    browser_id,
                )
                return Response(
                    {
                        "error": "Push endpoint is already registered for another browser session. "
                                 "Please refresh and resubscribe."
                    },
                    status=409
                )

        if not subscription:
            # Create new if still not found
            subscription = PushSubscription.objects.create(
                browser_id=browser_id,
                endpoint=endpoint,
                p256dh=keys.get("p256dh", ""),
                auth=keys.get("auth", ""),
            )
            logger.info(f"🆕 PushSubscription created | BrowserID={browser_id}")
        else:
            # Update existing (handles migration of browser_id)
            old_bid = subscription.browser_id
            subscription.browser_id = browser_id
            subscription.endpoint = endpoint
            subscription.p256dh = keys.get("p256dh", "")
            subscription.auth = keys.get("auth", "")
            subscription.save()
            logger.info(f"♻️ PushSubscription re-linked | OldID={old_bid}, NewID={browser_id}")

        # If token provided, try to link with order (optional)
        if token_number:
            # Prevent a single PushSubscription from accumulating links to multiple
            # orders/tokens over time (can cause cross-flavour leakage when projects
            # share the same browser in the past).
            subscription.tokens.clear()

            if project_name == "airline_flash":
                order = Order.objects.filter(sequence_code=token_number, vendor=vendor).order_by('-created_at').first()
                logger.info(f"🔍 Lookup via sequence_code for airline_flash: {token_number}")
            elif project_name == "dine_flash":
                order = Order.objects.filter(id=token_number, vendor=vendor).order_by('-created_at').first()
                logger.info(f"🔍 Lookup via booking_reference for dine flash: {token_number}")
            elif _is_dine_flash_buffet_server():
                # Link push subscription to the buffet order: token_no, primary key, or bill / table ref.
                raw = token_number
                order = None
                if raw not in (None, ""):
                    try:
                        n = int(raw)
                    except (TypeError, ValueError):
                        n = None
                    if n is not None:
                        order = (
                            Order.objects.filter(token_no=n, vendor=vendor)
                            .order_by("-created_at")
                            .first()
                        )
                        if not order:
                            order = (
                                Order.objects.filter(id=n, vendor=vendor)
                                .order_by("-created_at")
                                .first()
                            )
                    if not order:
                        order = (
                            Order.objects.filter(
                                table_booking_no=str(raw).strip(),
                                vendor=vendor,
                            )
                            .order_by("-created_at")
                            .first()
                        )
                logger.info(
                    "🔍 [dine_flash_buffet] save_subscription token_number=%r -> order_id=%s",
                    raw,
                    getattr(order, "id", None),
                )
            else:
                order = Order.objects.filter(token_no=token_number, vendor=vendor).order_by('-created_at').first()
                logger.info(f"🔍 Lookup via token_no for food flash: {token_number}")

            if order:
                subscription.tokens.add(order)
                logger.info(f"🔗 Linked subscription {subscription.id} with Order {order.id} (Token={token_number})")
            else:
                logger.warning(f"⚠️ No order found for token={token_number}, vendor_id={vendor_id}")

        return Response({"message": "Subscription saved successfully."}, status=200)

    except Exception as e:
        logger.exception("🔥 Unhandled exception in /save_subscription:")
        return Response({"error": str(e)}, status=500)



@api_view(["POST"])
@permission_classes([AllowAny])
def send_offers(request):
    """
    Send an offer to all active customers of a given vendor.

    Request Body:
    {
        "vendor_id": integer,
        "offer": string,
        "title": string
    }

    Response:
    {
        "message": string
    }

    Status Codes:
    - 400: Invalid request body or missing required fields.
    - 404: Invalid vendor ID.
    - 200: Offer sent successfully.

    :param request: Request object containing the request body.
    :return: Response object containing the response data and status code.
    """
    vendor_id = request.data.get("vendor_id")
    offer = request.data.get("offer")
    title = request.data.get("title")
    
    if not vendor_id:
        return Response({"message": "Vendor ID is required."}, status=400)

    try:
        vendor = Vendor.objects.get(vendor_id=vendor_id)
    except Vendor.DoesNotExist:
        return Response({"message": "Invalid vendor ID."}, status=404)

    # Serialize logo after vendor is confirmed
    vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
    logo_url = vendor_serializer.data.get('logo_url', '')

    payload = {
        "title": title,
        "body": offer,
        "name": vendor.name,
        "vendor_id": vendor.vendor_id,
        "location_id": vendor.location_id,
        "logo_url": logo_url,
        "type": "offers",
    }

    # Step 1: Get active orders
    active_orders = Order.objects.filter(vendor=vendor).exclude(status="ready")

    # Step 2: Get distinct subscriptions tied to active orders
    active_subscriptions = PushSubscription.objects.filter(tokens__in=active_orders).distinct()

    logger.info(f"Found {active_subscriptions.count()} subscriptions to notify for vendor {vendor.name}")

    sent_count = 0
    for sub in active_subscriptions:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth": sub.auth,
            },
        }
        success = send_push_notification(subscription_info, payload)
        if success:
            sent_count += 1

    return Response({"message": f"Offer sent to {sent_count} active customers."}, status=200)

@api_view(['POST'])
@permission_classes([AllowAny])
def register_device(request):
    """
    Registers a new device with the given serial_no and customer_id.

    Parameters:
    request (Request): Django's request object containing the serial_no and customer_id.

    Returns:
    Response: A response containing the status of the registration attempt and additional information if applicable.

    Status Codes:
    201 Created: Device is registered but not yet mapped to a vendor.
    200 OK: Device is already registered and mapped to a vendor or device is registered but not yet mapped to a vendor.
    400 Bad Request: Fields 'serial_no' and 'customer_id' are required.
    404 Not Found: Customer not found.
    409 Conflict: Serial number already registered with another customer.
    """
    serial_no = request.data.get('serial_no')
    customer_id = request.data.get('customer_id')

    request_ip = request.META.get('REMOTE_ADDR', 'Unknown')
    user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
    logger.info("Device registration attempt from IP: %s | User-Agent: %s", request_ip, user_agent)
    logger.debug("Incoming data — Serial No: %s, Customer ID: %s", serial_no, customer_id)

    if not serial_no or not customer_id:
        logger.warning("Missing fields: serial_no=%s, customer_id=%s", serial_no, customer_id)
        return Response({"error": "Fields 'serial_no' and 'customer_id' are required."}, status=400)

    try:
        # Step 1: Validate customer
        customer = AdminOutlet.objects.get(customer_id=customer_id)
        logger.info("Validated customer: %s", customer_id)

        try:
            # Step 2: Check if device exists with this serial_no
            existing_device = Device.objects.get(serial_no=serial_no)
            logger.info("Device with serial %s already exists", serial_no)

            if existing_device.admin_outlet == customer:
                if existing_device.vendor is not None:
                    logger.info("Device already mapped to vendor: %s", existing_device.vendor.vendor_id)
                    return Response({
                        "status": "Device is already registered and mapped to vendor.",
                        "mapped": True,
                        "vendor_id": existing_device.vendor.vendor_id,
                        "vendor_name": existing_device.vendor.name,
                    }, status=200)
                else:
                    logger.info("Device is registered but not mapped to any vendor.")
                    return Response({
                        "status": "Device is already registered but not yet mapped to a vendor.",
                        "mapped": False,
                        "vendor_id": None,
                        "vendor_name": None,
                    }, status=200)
            else:
                logger.warning("Device serial conflict: Already registered with another customer.")
                return Response({
                    "error": "Serial number already registered with another customer."
                }, status=409)

        except Device.DoesNotExist:
            # Step 4: New device, create it
            device = Device.objects.create(
                serial_no=serial_no,
                admin_outlet=customer,
                vendor=None
            )
            logger.info("New device registered: %s for customer: %s", serial_no, customer_id)
            return Response({
                "status": "Device is registered but not yet mapped to a vendor.",
                "mapped": False,
                "vendor_id": None,
                "vendor_name": None,
            }, status=201)

    except AdminOutlet.DoesNotExist:
        logger.error("Customer not found: %s", customer_id)
        return Response({"error": "Customer not found."}, status=404)

# @api_view(['POST'])
# @permission_classes([AllowAny])
# def register_android_device(request):
#     data = request.data
#     token = data.get('token')
#     customer_id = data.get('customer_id')
#     mac_address = data.get('mac_address')

#     logger.info("Android Device Registration")
#     logger.debug("Incoming data — token=%s, customer_id=%s, mac_address=%s", token, customer_id, mac_address)

#     # Validate required fields
#     required_fields = ['customer_id', 'token', 'mac_address',]
#     missing = [f for f in required_fields if not data.get(f)]
#     if missing:
#         logger.warning(f"Missing required fields:{', '.join(missing)}",)
#         return Response(
#             {"error": "Fields 'token', 'customer_id', and 'mac_address' are required."},
#             status=status.HTTP_400_BAD_REQUEST
#         )
#     try:
#         customer = AdminOutlet.objects.get(customer_id=customer_id)
#         logger.info("Customer found: customer_id=%s (AdminOutlet ID: %s)", customer_id, customer.id)
#     except AdminOutlet.DoesNotExist:
#         logger.error("Customer not found: customer_id=%s", customer_id)
#         return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)

#     # Register or update device
#     try:
#         device, created = AndroidDevice.objects.get_or_create(
#             mac_address=mac_address,
#             admin_outlet=customer,
#             defaults={'token': token}
#         )
#         if not created:
#             logger.info("Device found for mac_address=%s. Updating token.", mac_address)
#             device.token = token
#             device.save()
#         else:
#             logger.info("New device created: mac_address=%s, token=%s", mac_address, token)
#     except Exception as e:
#         logger.error("Failed to register/update device: %s", str(e), exc_info=True)
#         return Response({"error": "Failed to register/update device."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#     # Check vendor mapping
#     if hasattr(device, 'vendor') and device.vendor:
#         if hasattr(device.vendor, 'config') :
#             if not device.vendor.config.tv_communication_mode:
#                 logger.warning(f"Vendor {device.vendor.vendor_id} has no communication configuration")
#                 return Response(
#                     {"error": "Vendor has no communication configuration."}, 
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
#             elif device.vendor.config.tv_communication_mode == "MQTT":
#                 mqtt_config = get_mqtt_config_for_vendor(device.vendor, device)
#                 logger.info(
#                     "Device mapped to vendor: %s (ID: %s) | MQTT Config: %s",
#                     device.vendor.name,
#                     device.vendor.vendor_id,
#                     json.dumps(mqtt_config)
#                 )
#                 logger.info(
#                         "Device mapped to vendor: %s (ID: %s) | Azure IoT Config: %s",
#                         device.vendor.name,
#                         device.vendor.vendor_id,
#                         json.dumps(mqtt_config)
#                     )
#             elif device.vendor.config.tv_communication_mode == "AZURE_IOT":
#                 if hasattr(device,'iot_credentials') and device.iot_credentials:
#                     mqtt_config = create_iot_credentials(device)
#                     logger.info(
#                         "Device mapped to vendor: %s (ID: %s) | Azure IoT Config: %s",
#                         device.vendor.name,
#                         device.vendor.vendor_id,
#                         mqtt_config
#                     )
#                 else:
#                     logger.warning(f"Vendor {device.vendor.vendor_id} has no Azure IoT credentials")
#                     logger.info("Generating new IoT credentials for device")
#                     mqtt_config = create_iot_credentials(device)
#                     logger.info(
#                         "Device mapped to vendor: %s (ID: %s) | Azure IoT Config: %s",
#                         device.vendor.name,
#                         device.vendor.vendor_id,
#                         json.dumps(mqtt_config)
#                     )
#             else:
#                 logger.warning("Vendor configuration is Firebase") 
#             # Fetch TV configuration assigned to this device
#             tv_config_data = build_tv_config_payload(device.tv_config)


#         else:
#             logger.warning("Vendor has no configuration") 
#             mqtt_config = None              
#         return Response({
#             "status": "Device is mapped to vendor.",
#             "mapped": True,
#             "vendor_id": device.vendor.vendor_id,
#             "vendor_name": device.vendor.name,
#             "mqtt_config": mqtt_config,
#             "tv_config_data":tv_config_data
#         }, status=status.HTTP_200_OK)
#     logger.info("Device registered but not mapped to any vendor.")
#     return Response({
#         "status": "Device is registered but not yet mapped to a vendor.",
#         "mapped": False,
#         "vendor_id": None,
#         "vendor_name": None,
#         "mqtt_config": None
#     }, status=status.HTTP_200_OK)


def _android_device_registration_queryset(*, skip_utilities_prefetch=False):
    """Prefetch TV relations for register_android_device (Dine Flash omits utilities)."""
    qs = AndroidDevice.objects.select_related("vendor__config", "tv_config")
    prefetch = ["tv_config__advertisements"]
    if not skip_utilities_prefetch:
        prefetch.append("tv_config__utilities")
    return qs.prefetch_related(*prefetch)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def register_android_device(request):
    
    """
    Registers an Android device for a given customer.

    POST /api/register-android-device/
    Payload: { "token": <string>, "customer_id": <int>, "mac_address": <string> [, "fcm_token": <string>] }

    For Dine Flash, `token` is the FCM registration token. When the same MAC re-registers
    with a new non-empty `token`, both `token` and `fcm_token` are updated. Optional
    `fcm_token` overrides the mirrored value when present in the body.
    Returns:
    - Mapped: True if the device is mapped to a vendor; False otherwise
    - Vendor ID: The ID of the vendor the device is mapped to
    - Vendor Name: The name of the vendor the device is mapped to
    - MQTT Config: The MQTT configuration for the device, if available
    - TV Config: The TV configuration for the device, if available

    """
    data = request.data
    raw_token = data.get("token")
    token = "" if raw_token is None else str(raw_token).strip()
    customer_id = data.get('customer_id')
    mac_address = data.get('mac_address')
    fcm_token_in_payload = "fcm_token" in data
    fcm_token_value = (data.get("fcm_token") or "").strip() or None if fcm_token_in_payload else None

    logger.info("Android Device Registration")
    logger.debug(
        "Incoming data — token=%s, customer_id=%s, mac_address=%s, fcm_token_present=%s",
        token,
        customer_id,
        mac_address,
        fcm_token_in_payload,
    )

    missing = []
    if not customer_id:
        missing.append("customer_id")
    if not mac_address:
        missing.append("mac_address")
    if missing:
        logger.warning("Missing required fields: %s", ", ".join(missing))
        return Response(
            {"error": f"Required field(s): {', '.join(missing)}."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Fetch customer (AdminOutlet) – make sure customer_id is indexed in model
    try:
        customer = AdminOutlet.objects.get(customer_id=customer_id)
        logger.info("Customer found: customer_id=%s (AdminOutlet ID: %s)", customer_id, customer.id)
    except AdminOutlet.DoesNotExist:
        logger.error("Customer not found: customer_id=%s", customer_id)
        return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)

    project_code = (getattr(customer, "project_code", "") or "").strip().lower()
    current_project = (project_name or "").strip().lower()
    is_dine_flash = project_code == "dine_flash" or current_project == "dine_flash"

    # Dine Flash may register before FCM token is available.
    if not is_dine_flash and not token:
        logger.warning("Missing required field: token")
        return Response(
            {"error": "Required field(s): token."},
            status=status.HTTP_400_BAD_REQUEST
        )

    device_qs = _android_device_registration_queryset(skip_utilities_prefetch=is_dine_flash)

    try:
        device = device_qs.filter(mac_address=mac_address, admin_outlet=customer).first()

        if device:
            update_fields = []
            # Do not overwrite when the client sends an empty value (e.g. first Dine Flash boot).
            if token and device.token != token:
                logger.info("Device found for mac_address=%s. Updating token.", mac_address)
                device.token = token
                update_fields.append("token")
            if fcm_token_in_payload:
                if device.fcm_token != fcm_token_value:
                    device.fcm_token = fcm_token_value
                    update_fields.append("fcm_token")
            elif token and device.fcm_token != token:
                # `token` is the FCM registration token when clients omit `fcm_token`.
                device.fcm_token = token
                update_fields.append("fcm_token")
            if update_fields:
                update_fields.append("updated_at")
                device.save(update_fields=update_fields)
            else:
                logger.debug("Device found and registration fields unchanged for mac_address=%s", mac_address)
            created = False
        else:
            # create inside atomic block
            create_kwargs = {
                "token": token,
                "mac_address": mac_address,
                "admin_outlet": customer,
            }
            if fcm_token_in_payload:
                create_kwargs["fcm_token"] = fcm_token_value
            elif token:
                create_kwargs["fcm_token"] = token
            with transaction.atomic():
                device = AndroidDevice.objects.create(**create_kwargs)
            logger.info("New device created: mac_address=%s, token=%s", mac_address, token)
            device = device_qs.get(pk=device.pk)
            created = True

    except Exception as e:
        logger.error("Failed to register/update device: %s", str(e), exc_info=True)
        return Response({"error": "Failed to register/update device."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Default response pieces
    mapped = False
    mqtt_config = None
    tv_config_data = None
    vendor_id = None
    vendor_name = None

    # If device is mapped to a vendor, prepare configs
    vendor = getattr(device, 'vendor', None)
    if vendor:
        mapped = True
        vendor_id = vendor.vendor_id
        vendor_name = vendor.name
        config = getattr(vendor, 'config', None)

        # If vendor config missing or has no communication mode, fail fast with user-friendly message
        if not config or not getattr(config, 'tv_communication_mode', None):
            logger.warning("Vendor %s has no communication configuration", vendor.vendor_id if vendor else "unknown")
            return Response({"error": "Vendor has no communication configuration."}, status=status.HTTP_400_BAD_REQUEST)

        # Communication mode branches
        mode = config.tv_communication_mode
        if mode == "MQTT":
            mqtt_config = get_mqtt_config_for_vendor(vendor, device)
            if logger.isEnabledFor(logging.INFO):
                logger.info("Device mapped to vendor: %s (ID: %s) | MQTT Config available", vendor.name, vendor.vendor_id)
        elif mode == "AZURE_IOT":
            # create or fetch IoT credentials only when needed
            if hasattr(device, 'iot_credentials') and device.iot_credentials:
                mqtt_config = create_iot_credentials(device)
            else:
                logger.info("Generating new IoT credentials for device: mac=%s", mac_address)
                mqtt_config = create_iot_credentials(device)
            if logger.isEnabledFor(logging.INFO):
                logger.info("Device mapped to vendor: %s (ID: %s) | Azure IoT Config available", vendor.name, vendor.vendor_id)
        else:
            # Firebase or other
            logger.warning("Vendor configuration is Firebase (or unsupported): %s", mode)
            mqtt_config = None

        is_dine_flash_buffet = (
            project_code == "dine_flash_buffet" or current_project == "dine_flash_buffet"
        )
        if is_dine_flash:
            vendor_name = vendor.alias_name or vendor.name
        device_tv_config = getattr(device, "tv_config", None)

        # Dine Flash variants: do not use defaults if TV config is missing.
        if (is_dine_flash or is_dine_flash_buffet) and not device_tv_config:
            logger.info(
                "Dine Flash TV config missing for project=%s, device mac=%s, vendor_id=%s",
                project_code,
                mac_address,
                vendor.vendor_id,
            )
            missing_config_response = {
                "status": "configuration not added",
                "message": "configuration not added",
                "mapped": mapped,
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "mqtt_config": mqtt_config,
                "tv_config": None,
            }
            if is_dine_flash:
                empty_counts = {"waiting": 0, "active_tables": 0, "ongoing_tables": 0}
                missing_config_response["dine_flash"] = {
                    "counts": empty_counts,
                    "displayed_counts": empty_counts.copy(),
                }
            return Response(missing_config_response, status=status.HTTP_200_OK)

        # Build tv_config payload (use the reusable helper)
        try:
            tv_config_data = build_tv_config_payload(
                device_tv_config,
                request=request,
                omit_utilities=is_dine_flash,
                include_dine_flash_fields=is_dine_flash,
                vendor_id=vendor_id if is_dine_flash else None,
            )
        except Exception as e:
            logger.error("Failed to build TV config payload: %s", str(e), exc_info=True)
            tv_config_data = None

        dine_flash_tv = None
        try:
            if is_dine_flash:
                dine_flash_tv = build_dine_flash_tv_booking_snapshot(
                    vendor, device_tv_config, request=request
                )
        except Exception as e:
            logger.error("Failed to build Dine Flash TV snapshot: %s", str(e), exc_info=True)
            # Keep Dine Flash API stable even when snapshot building fails.
            dine_flash_tv = {
                "counts": {"waiting": 0, "active_tables": 0, "ongoing_tables": 0},
                "displayed_counts": {"waiting": 0, "active_tables": 0, "ongoing_tables": 0},
            }

        response_body = {
            "status": "Device is mapped to vendor.",
            "mapped": mapped,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "mqtt_config": mqtt_config,
            "tv_config": tv_config_data,
        }
        if is_dine_flash:
            if isinstance(dine_flash_tv, dict):
                # Full snapshot (waiting / active_tables / …) so TV can render booking rows,
                # including table_booking_no_display and seat_no from build_dine_flash_tv_booking_snapshot.
                response_body["dine_flash"] = dict(dine_flash_tv)
            else:
                response_body["dine_flash"] = {
                    "counts": {"waiting": 0, "active_tables": 0, "ongoing_tables": 0},
                    "displayed_counts": {"waiting": 0, "active_tables": 0, "ongoing_tables": 0},
                }

        return Response(response_body, status=status.HTTP_200_OK)

    # Device created/updated but not mapped to any vendor
    logger.info("Device registered but not mapped to any vendor.")
    return Response({
        "status": "Device is registered but not yet mapped to a vendor.",
        "mapped": mapped,
        "vendor_id": None,
        "vendor_name": None,
        "mqtt_config": None,
        "tv_config": None
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def register_android_apk(request):
    """
    Registers or updates an Android APK device for a customer.
    - Validates customer and optional manager_id.
    - Updates or creates the AndroidAPK record.
    - Returns mapping status with manager if available.
    """
    token = request.data.get('token')
    customer_id = request.data.get('customer_id')
    mac_address = request.data.get('mac_address')
    apk_version = request.data.get('apk_version')
    is_dine_flash_buffet = (project_name or "").strip().lower() == "dine_flash_buffet"
    manager_id = request.data.get('manager_id')
    if is_dine_flash_buffet and not manager_id:
        manager_id = request.data.get('utility_manager_id')

    logger.debug(
        "[register_android_apk] Incoming data — token=%s, customer_id=%s, mac=%s, version=%s, manager_id=%s",
        token, customer_id, mac_address, apk_version, manager_id
    )

    # === Step 1: Validate Required Fields ===
    if not token or not customer_id or not mac_address or not apk_version or not manager_id:
        logger.warning(
            "[register_android_apk] Missing required fields — token=%s, customer_id=%s, mac=%s, apk_version=%s, manager_id=%s",
            token, customer_id, mac_address, apk_version, manager_id
        )
        return Response(
            {"error": "Fields 'token', 'customer_id', 'mac_address', 'apk_version' and 'manager_id' are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # === Step 2: Validate Customer ===
        admin_outlet = AdminOutlet.objects.filter(customer_id=customer_id).order_by("-id").first()
        if not admin_outlet:
            logger.error("[register_android_apk] Customer ID not found: %s", customer_id)
            return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)
        logger.info("[register_android_apk] Validated customer_id=%s", customer_id)

        user_profile = None
        # === Step 3: Validate Manager if Provided ===
        if manager_id:
            try:
                allowed_roles = ['outlet_manager', 'admin_manager', 'order_manager']
                if is_dine_flash_buffet:
                    allowed_roles.append('utility_user')
                user_profile = UserProfile.objects.get(
                    id=manager_id,
                    role__in=allowed_roles,
                    admin_outlet=admin_outlet
                )
                logger.info("[register_android_apk] Validated manager_id=%s for customer_id=%s", manager_id, customer_id)
            except UserProfile.DoesNotExist:
                logger.warning("[register_android_apk] Invalid manager_id=%s for customer_id=%s", manager_id, customer_id)
                return Response({"error": "Invalid manager ID for this customer."}, status=status.HTTP_400_BAD_REQUEST)

        # === Step 4: Check Device by MAC and token ===
        device = AndroidAPK.objects.filter(
            mac_address=mac_address,
            admin_outlet=admin_outlet,
            user_profile=user_profile if user_profile else None
        ).first() or AndroidAPK.objects.filter(
            mac_address=mac_address,
            admin_outlet=admin_outlet
        ).first() or AndroidAPK.objects.filter(
            mac_address=mac_address
        ).first()

        if device:
            logger.info(
                "[register_android_apk] Device already exists. Updating token and version — MAC=%s, manager=%s",
                mac_address, user_profile.name if user_profile else "None"
            )
            if device.admin_outlet != admin_outlet:
                logger.warning(
                    "[register_android_apk] MAC address conflict: Already registered with another Company - MAC=%s", mac_address
)
                return Response(
                    {
                        "status": "Device already registered with another customer %s."
                        "Please Contact Admin" % device.admin_outlet.customer_id,
                        "mapped": False,
                        "manager_id": None,
                        "manager_name": None,
                        "config": None
                    },
                    status=status.HTTP_200_OK
                )
            device.token = token
            device.apk_version = apk_version
            device.mac_address = mac_address
            device.admin_outlet = admin_outlet
            if is_dine_flash_buffet:
                device.user_profile = user_profile
            try:
                device.save()
            except IntegrityError:
                logger.exception(
                    "[register_android_apk] IntegrityError while updating device — token=%s, mac=%s",
                    token, mac_address
                )
                return Response(
                    {"error": "Device registration conflict. Please contact admin."},
                    status=status.HTTP_409_CONFLICT
                )
        else:
            logger.info("[register_android_apk] Registering new device — MAC=%s", mac_address)
            try:
                device = AndroidAPK.objects.create(
                    token=token,
                    mac_address=mac_address,
                    apk_version=apk_version,
                    admin_outlet=admin_outlet,
                    user_profile=user_profile if is_dine_flash_buffet else None
                )
            except IntegrityError:
                logger.exception(
                    "[register_android_apk] IntegrityError while creating device — token=%s, mac=%s",
                    token, mac_address
                )
                return Response(
                    {"error": "Device registration conflict. Please contact admin."},
                    status=status.HTTP_409_CONFLICT
                )

        # === Step 5: Return Mapping Status ===
        if device.user_profile:
            if device.user_profile != user_profile:
                return Response({
                    "status": "This Device is already using by another manager. Please contact admin.",
                    "mapped":False,
                    "manager_id": None,
                    "manager_name": None,
                    "config": None
                }, status=status.HTTP_200_OK)
            logger.info(
                "[register_android_apk] Device mapped to manager_id=%s (%s)",
                device.user_profile.id, device.user_profile.name
            )
            config_data = build_vendor_config_payload(device.user_profile.vendor)
            return Response({
                "status": "Device is mapped to a manager.",
                "mapped": True,
                "manager_id": device.user_profile.id,
                "manager_name": device.user_profile.name,
                "config": config_data,
            }, status=status.HTTP_200_OK)

        logger.info("[register_android_apk] Device registered but not mapped to any manager.")
        return Response({
            "status": "Device is registered but not yet mapped to a manager.",
            "mapped": False,
            "manager_id": None,
            "manager_name": None,
            "config": None
        }, status=status.HTTP_200_OK)

    except AdminOutlet.DoesNotExist:
        logger.error("[register_android_apk] Customer ID not found: %s", customer_id)
        return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        logger.exception("[register_android_apk] Unexpected error: %s", str(e))
        return Response({"error": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_vendor(vendor_id):
    return Vendor.objects.get(vendor_id=vendor_id)

def get_device(device_id, vendor_id):
    return Device.objects.get(serial_no=device_id, vendor_id=vendor_id)


def create_or_update_order(token_no, vendor, device, counter_no, status):
    order = get_order(token_no, vendor)
    if order:
        logger.info(f"Updating existing order {token_no}")
        order.status = status
        order.counter_no = counter_no
        order.device = device
        order.updated_by = "keypad_device"
        order.save()
    else:
        logger.info(f"Creating new order {token_no}")
        order_data = {
            'token_no': token_no,
            'vendor': vendor.id,
            'device': device.id,
            'counter_no': counter_no,
            'status': status,
        }
        serializer = OrdersSerializer(data=order_data)
        if not serializer.is_valid():
            logger.error(f"Order creation failed: {serializer.errors}")
            raise serializers.ValidationError(serializer.errors)
        order = serializer.save()
    return order

def notify_fcm(vendor, data):
    from static.utils.functions.notifications import send_firebase_admin_multicast
    from vendors.dine_flash_tv_fcm import collect_vendor_tv_fcm_tokens

    tokens = collect_vendor_tv_fcm_tokens(vendor)
    return send_firebase_admin_multicast(vendor, tokens, json.dumps(data))

PUSH_COOLDOWN_SECONDS = 2

@api_view(['PATCH'])
@permission_classes([AllowAny])
def update_order(request):
    try:
        # Validate request data
        data = request.data
        logger.info(
            f"[update_order] PATCH request from IP={request.META.get('REMOTE_ADDR')} "
            f"UA={request.META.get('HTTP_USER_AGENT')} "
            f"DATA={data}"
        )
        required_fields = ['vendor_id', 'token_no', 'device_id', 'counter_no', 'status']
        missing = [f for f in required_fields if not data.get(f)]
        if missing:
            logger.warning(f"[update_order] Missing fields: {', '.join(missing)}")
            return Response(
                {"message": f"Missing fields: {', '.join(missing)}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get vendor and device
        try:
            vendor = get_vendor(data['vendor_id'])
        except Vendor.DoesNotExist:
            logger.warning(f"[update_order] Vendor not found: vendor_id={data['vendor_id']}")
            return Response({"message": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            device = get_device(data['device_id'], vendor.id)
        except Device.DoesNotExist:
            logger.warning(
                f"[update_order] Device not found: device_id={data['device_id']} vendor_id={vendor.id}"
            )
            return Response({"message": "Device not found"}, status=status.HTTP_404_NOT_FOUND)

        status_to_update = data['status']
        token_no = data['token_no']
        counter_no = data['counter_no']

        logger.info(
            f"[update_order] Resolved: vendor={vendor.name} device={device.serial_no} "
            f"token_no={token_no} counter_no={counter_no} status={status_to_update}"
        )
        
        # FCM push notifications if TV communication mode is not MQTT
        if vendor.config.tv_communication_mode == "Firebase":
             # Prepare data payload
            try:
                fcm_result = notify_fcm(vendor, data)
                logger.info(f"[update_order] FCM sent successfully: {fcm_result}")
            except Exception as e:
                logger.exception("[update_order] FCM sending failed .Error:%s", str(e))
                fcm_result = {"error": str(e)}
        # Create or update order in DB
        order = create_or_update_order(token_no, vendor, device, counter_no, status_to_update)

        # Azure IoT Hub messages if TV communication mode is AZURE_IOT
        if vendor.config.tv_communication_mode == "AZURE_IOT":
            azure_iot = get_azure_devices(vendor)
            logger.info(f"[update_order] Azure IoT messages sent: {azure_iot}")

        # MQTT Publish if TV communication mode is MQTT
        if vendor.config.tv_communication_mode == "MQTT":      
            if not hasattr(vendor, 'config') or not vendor.config.mqtt_mode:
                logger.warning(f"[update_order] Vendor {vendor.vendor_id} has no MQTT configuration")
                return Response(
                    {"message": "Vendor has no MQTT configuration."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                mqtt = send_order_update(vendor)
                if mqtt:
                    logger.info(f"[update_order] ✅ MQTT update sent successfully for vendor {vendor.vendor_id}")
                else:
                    logger.error(f"[update_order] ❌ Failed to send MQTT update for vendor {vendor.vendor_id}")
                    return Response(
                        {"message": "Failed to send MQTT update."}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            except Exception as mqtt_err:
                logger.exception(f"[update_order] MQTT publish failed: {mqtt_err}")
                return Response(
                    {"message": "MQTT publish failed."}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        # Web push notifications if status is "ready"
        push_errors = []
        if status_to_update.lower() == "ready" and (
            not order.notified_at or (now() - order.notified_at).total_seconds() > PUSH_COOLDOWN_SECONDS
        ):
            vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
            payload = {
                "title": "Order Update",
                "body": f"Your order {token_no} is now ready.",
                "token_no": token_no,
                "status": status_to_update,
                "counter_no": counter_no,
                "name": vendor.name,
                'alias_name': vendor.alias_name,
                "vendor_id": vendor.vendor_id,
                "location_id": vendor.location_id,
                "logo_url": vendor_serializer.data.get("logo_url", ""),
                "type": "foodstatus",
                "vibration_pattern":vendor.config.vibration_pattern,
                "vibration_duration":vendor.config.vibration_duration
            }
            title="Keypad Device Alert"
            body=f"Order {token_no} is now ready to be served"
            # Notify managers via FCM
            send_to_managers(vendor, payload,title,body)
            
            try:
                push_errors = notify_web_push(order, vendor, payload)
            except Exception as push_err:
                logger.error(f"[update_order] Web push failed: {push_err}")
                push_errors = [str(push_err)]
            
            logger.info(f"[update_order] Web push notifications sent. Errors: {push_errors}")
            order.refresh_from_db()  # ✅ ensures latest status from DB
            order.notified_at = now()
            order.save(update_fields=['notified_at'])

        response_msg = {
            "message": "Order updated and notifications sent.",
            "token_no": token_no
        }
        logger.info(f"[update_order] Completed successfully for token {token_no}")
        return Response(response_msg, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"[update_order] Unexpected error: {e}")
        return Response({"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

