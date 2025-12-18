# Standard library
import json
import logging

# Django
from django.conf import settings
from django.db import transaction
from django.utils.timezone import now, localtime

# Third-party
from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes
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
    build_vendor_config_payload
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

        # Get or create subscription
        subscription, created = PushSubscription.objects.get_or_create(
            browser_id=browser_id,
            defaults={
                "endpoint": endpoint,
                "p256dh": keys.get("p256dh", ""),
                "auth": keys.get("auth", ""),
            },
        )

        if created:
            logger.info(f"🆕 PushSubscription created for browser_id={browser_id}")
        else:
            logger.info(f"♻️ PushSubscription found, updating browser_id={browser_id}")

        # Update subscription details if changed
        subscription.endpoint = endpoint
        subscription.p256dh = keys.get("p256dh", "")
        subscription.auth = keys.get("auth", "")
        subscription.save()
        logger.info(f"🔄 PushSubscription updated | ID={subscription.id}, BrowserID={subscription.browser_id}")

        # If token provided, try to link with order (optional)
        if token_number:
            if project_name == "airline_flash":
                order = Order.objects.filter(sequence_code=token_number, vendor=vendor).order_by('-created_at').first()
                logger.info(f"🔍 Lookup via sequence_code for airline_flash: {token_number}")
            elif project_name == "dine_flash":
                order = Order.objects.filter(id=token_number, vendor=vendor).order_by('-created_at').first()
                logger.info(f"🔍 Lookup via booking_reference for dine flash: {token_number}")
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

@api_view(['POST'])
@permission_classes([AllowAny])
def register_android_device(request):
    
    """
    Registers an Android device for a given customer.

    POST /api/register-android-device/
    Payload: { "token": <string>, "customer_id": <int>, "mac_address": <string> }
    Returns:
    - Mapped: True if the device is mapped to a vendor; False otherwise
    - Vendor ID: The ID of the vendor the device is mapped to
    - Vendor Name: The name of the vendor the device is mapped to
    - MQTT Config: The MQTT configuration for the device, if available
    - TV Config: The TV configuration for the device, if available

    """
    data = request.data
    token = data.get('token')
    customer_id = data.get('customer_id')
    mac_address = data.get('mac_address')

    logger.info("Android Device Registration")
    logger.debug("Incoming data — token=%s, customer_id=%s, mac_address=%s", token, customer_id, mac_address)

    # Validate required fields
    required_fields = ['customer_id', 'token', 'mac_address']
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        logger.warning("Missing required fields: %s", ", ".join(missing))
        return Response(
            {"error": "Fields 'token', 'customer_id', and 'mac_address' are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Fetch customer (AdminOutlet) – make sure customer_id is indexed in model
    try:
        customer = AdminOutlet.objects.get(customer_id=customer_id)
        logger.info("Customer found: customer_id=%s (AdminOutlet ID: %s)", customer_id, customer.id)
    except AdminOutlet.DoesNotExist:
        logger.error("Customer not found: customer_id=%s", customer_id)
        return Response({"error": "Customer not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        # Try to find existing device with related vendor/config and tv_config in one go
        device = AndroidDevice.objects.select_related('vendor__config', 'tv_config') \
            .filter(mac_address=mac_address, admin_outlet=customer).first()

        if device:
            # Only update token if changed
            if device.token != token:
                logger.info("Device found for mac_address=%s. Updating token.", mac_address)
                device.token = token
                device.save(update_fields=['token', 'updated_at'])
            else:
                logger.debug("Device found and token unchanged for mac_address=%s", mac_address)
            created = False
        else:
            # create inside atomic block
            with transaction.atomic():
                device = AndroidDevice.objects.create(
                    token=token,
                    mac_address=mac_address,
                    admin_outlet=customer
                )
            logger.info("New device created: mac_address=%s, token=%s", mac_address, token)
            # fetch again with related objects to have vendor/config/tv_config available
            device = AndroidDevice.objects.select_related('vendor__config', 'tv_config').get(pk=device.pk)
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

        # Build tv_config payload (use the reusable helper)
        try:
            tv_config_data = build_tv_config_payload(getattr(device, 'tv_config', None))
        except Exception as e:
            logger.error("Failed to build TV config payload: %s", str(e), exc_info=True)
            tv_config_data = None

        return Response({
            "status": "Device is mapped to vendor.",
            "mapped": mapped,
            "vendor_id": vendor_id,
            "vendor_name": vendor_name,
            "mqtt_config": mqtt_config,
            "tv_config": tv_config_data
        }, status=status.HTTP_200_OK)

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
    manager_id = request.data.get('manager_id')

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
        admin_outlet = AdminOutlet.objects.get(customer_id=customer_id)
        logger.info("[register_android_apk] Validated customer_id=%s", customer_id)

        user_profile = None
        # === Step 3: Validate Manager if Provided ===
        if manager_id:
            try:
                user_profile = UserProfile.objects.get(
                    id=manager_id,
                    role__in=['outlet_manager', 'admin_manager', 'order_manager'],
                    admin_outlet=admin_outlet
                )
                logger.info("[register_android_apk] Validated manager_id=%s for customer_id=%s", manager_id, customer_id)
            except UserProfile.DoesNotExist:
                logger.warning("[register_android_apk] Invalid manager_id=%s for customer_id=%s", manager_id, customer_id)
                return Response({"error": "Invalid manager ID for this customer."}, status=status.HTTP_400_BAD_REQUEST)

        # === Step 4: Check Device by MAC and Manager ===
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
            device.save()
        else:
            logger.info("[register_android_apk] Registering new device — MAC=%s", mac_address)
            device = AndroidAPK.objects.create(
                token=token,
                mac_address=mac_address,
                apk_version=apk_version,
                admin_outlet=admin_outlet,
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


def send_firebase_admin_multicast(fcm_tokens, data_payload):
    """
    Sends a true Firebase Admin SDK multicast data+notification message to multiple devices.
    """

    if not fcm_tokens:
        logger.warning("No FCM tokens provided for multicast.")
        return False, {"error": "No tokens to send"}

    try:
        message = messaging.MulticastMessage(
            data={
                "type": "ready_orders",
                "orders": data_payload  # Ensure this is a string, if JSON dump is needed
            },
            notification=messaging.Notification(
                title="Order Ready!",
                body="Order Status Send to Android TV"
            ),
            tokens=fcm_tokens,
        )
        response = messaging.send_each_for_multicast(message)

        failed_tokens = []
        for idx, resp in enumerate(response.responses):
            if not resp.success:
                failed_tokens.append(fcm_tokens[idx])

        if failed_tokens:
            logger.warning(f"Multicast partially failed: {len(failed_tokens)} failed tokens.")
            return False, {"failed_tokens": failed_tokens}

        logger.info(f"FCM multicast successful: {response.success_count} sent.")
        return True, {"success_count": response.success_count}

    except Exception as e:
        logger.exception("Multicast FCM error")
        return False, {"error": str(e)}
    
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
    android_devices = AndroidDevice.objects.filter(vendor=vendor)
    tokens = list(android_devices.values_list('token', flat=True))
    return send_firebase_admin_multicast(tokens, json.dumps(data))

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

