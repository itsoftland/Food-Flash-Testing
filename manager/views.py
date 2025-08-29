import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orders.serializers import VendorLogoSerializer

from vendors.models import ChatMessage, Order
from vendors.serializers import OrdersSerializer
from vendors.services.order_service import send_order_update
from vendors.utils import notify_web_push
from vendors.order_utils import get_last_tokens 

from .serializers import ChatMessageSerializer
from .utils.utils import (get_manager_vendor, get_suggestion_messages,
                          get_order_counts)

from static.utils.functions.notifications import notify_android_tv
from static.utils.functions.queries import update_existing_order_by_manager

from static.utils.functions.utils import (
    get_vendor_business_day_range,
    get_vendor_current_date,
    get_vendor_current_time,
)

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order_by_manager(request):
    """
    API endpoint: Create an order manually by a manager.
    - Requires a valid `token_no` in the request body.
    - If an order already exists for today with the same token, it returns the existing order.
    - Otherwise, it creates a new order and returns its details.
    """

    logger.info("[create_order_by_manager] Request started | user=%s", request.user.username)

    token_no = request.data.get('token_no')
    logger.debug("[create_order_by_manager] Incoming token_no=%s", token_no)

    # === Step 1: Validate input ===
    if not token_no:
        logger.warning("[create_order_by_manager] Missing token_no | user=%s", request.user.username)
        return Response({'error': 'token_no is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token_no = int(token_no)
    except ValueError:
        logger.warning("[create_order_by_manager] Invalid token_no (non-integer) | value=%s | user=%s",
                       token_no, request.user.username)
        return Response({'error': 'All fields must be valid integers.'}, status=status.HTTP_400_BAD_REQUEST)

    # === Step 2: Resolve vendor for the manager ===
    vendor = get_manager_vendor(request.user)
    logger.info("[create_order_by_manager] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
                vendor.id, vendor.name, request.user.username)

    # Dynamically build tracking URL
    base_url = request.build_absolute_uri('/')
    tracking_url = f"{base_url}home/?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}&token_no={token_no}"
    logger.debug("[create_order_by_manager] Tracking URL generated | url=%s", tracking_url)

    # === Step 3: Check if order already exists for today ===
    try:
        start_dt, end_dt = get_vendor_business_day_range(vendor)
        if not start_dt or not end_dt:
            logger.error("[create_order_by_manager] Invalid business day range | vendor_id=%s", vendor.id)
            return Response({"error": "Invalid date range"}, status=400)

        order = Order.objects.filter(
            token_no=token_no, vendor=vendor, created_at__range=(start_dt, end_dt)
        ).first()

        if order:
            logger.info("[create_order_by_manager] Order already exists | order_id=%s | token_no=%s | vendor_id=%s",
                        order.id, token_no, vendor.id)
            return Response({
                'message': 'Order already exists for this token number.',
                'id': order.id,
                'token_no': order.token_no,
                'counter_no': order.counter_no,
                'updated_by': order.updated_by,
                'tracking_url': tracking_url,
                'status': order.status,
                'vendor': order.vendor.id,
                'name': order.vendor.name,
                'vendor_name': order.vendor.name,
                'manager_id': order.user_profile.id if order.user_profile else None,
                'manager_name': order.user_profile.name if order.user_profile else None,
                'device': order.device.id if order.device else None,
                'shown_on_tv': order.shown_on_tv,
                'notified_at': order.notified_at,
                'created_at': order.created_at,
                'updated_at': order.updated_at,
            }, status=status.HTTP_200_OK)
    except Order.DoesNotExist:
        logger.debug("[create_order_by_manager] No existing order found | token_no=%s | vendor_id=%s",
                     token_no, vendor.id)

    # === Step 4: Create new order ===
    try:
        new_order_data = {
            'name': vendor.name,
            'token_no': token_no,
            'vendor': vendor.id,
            'location_id': vendor.location_id,
            'counter_no': 1,
            'device': None,
            'updated_by': 'manager',
            'status': 'created',
            'type': 'foodstatus',
            'manager_id': request.user.profile_roles.first().id if request.user.profile_roles.exists() else None,
        }
        logger.debug("[create_order_by_manager] New order data prepared | data=%s", new_order_data)

        serializer = OrdersSerializer(data=new_order_data)
        if serializer.is_valid():
            serializer.save()
            data = serializer.data
            data['tracking_url'] = tracking_url
            data['message'] = 'Order created successfully by manager.'

            logger.info("[create_order_by_manager] New order created successfully | order_id=%s | token_no=%s | vendor_id=%s",
                        data.get('id'), token_no, vendor.id)
            return Response(data, status=status.HTTP_201_CREATED)
        else:
            logger.warning("[create_order_by_manager] Serializer validation failed | errors=%s", serializer.errors)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("[create_order_by_manager] Unexpected error occurred | token_no=%s | vendor_id=%s | error=%s",
                         token_no, vendor.id, str(e))
        return Response({'error': 'Internal server error'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_today_orders(request):
    """
    API endpoint: Retrieve all orders for today for the manager's vendor.
    - Returns order details only.
    """

    try:
        # === Step 1: Request start log ===
        logger.info(
            "[get_today_orders] Request started | user=%s | method=%s | path=%s",
            request.user.username, request.method, request.path
        )

        # === Step 2: Resolve vendor for the logged-in manager ===
        vendor = get_manager_vendor(request.user)
        logger.info(
            "[get_today_orders] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )

        # === Step 3: Get business day range (UTC) ===
        start_dt, end_dt = get_vendor_business_day_range(vendor)
        if not start_dt or not end_dt:
            logger.warning(
                "[get_today_orders] Invalid business day range | vendor_id=%s",
                vendor.id
            )
            return Response({"error": "Invalid date range"}, status=400)
        logger.debug(
            "[get_today_orders] Business day range | vendor_id=%s | start=%s | end=%s",
            vendor.id, start_dt, end_dt
        )

        # === Step 4: Fetch today's orders ===
        todays_orders = Order.objects.filter(
            vendor=vendor,
            created_at__range=(start_dt, end_dt)
        ).order_by('-updated_at')
        logger.info(
            "[get_today_orders] Fetched orders | vendor_id=%s | count=%s",
            vendor.id, todays_orders.count()
        )
        

        # === Step 5: Serialize orders ===
        data = OrdersSerializer(todays_orders, many=True, context={'request': request}).data
        logger.debug(
            "[get_today_orders] Serialized orders | vendor_id=%s | serialized_count=%s",
            vendor.id, len(data)
        )

        # === Step 6: Return response ===
        logger.info(
            "[get_today_orders] Returning response | user=%s | orders_count=%s",
            request.user.username, len(data)
        )
        
        # Compute counts (including unread based on new_notifications)
        status_counts = get_order_counts(todays_orders, data)
        # Merge counts into response
        response_data = {
            "message": "Today's orders retrieved successfully.",
            "count":len(data),
            **status_counts,   # Unpack counts as individual keys
            "detail": data
        }
        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        # === Step 7: Handle unexpected errors ===
        logger.exception(
            "[get_today_orders] Unexpected error | user=%s | error=%s",
            request.user.username, str(e)
        )
        return Response({"error": "Internal server error"}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_suggestions(request):
    """
    API endpoint to fetch manager suggestion messages for the current vendor.
    - Only accessible to authenticated users.
    - Retrieves vendor linked to the logged-in manager.
    - Collects suggestion messages for today and last 2 working days.
    """

    try:
        # === Step 1: Request start log ===
        logger.info(
            "[get_suggestion_messages] Request started | user=%s | method=%s | path=%s",
            request.user.username, request.method, request.path
        )

        # === Step 2: Resolve vendor from manager user ===
        vendor = get_manager_vendor(request.user)
        logger.info(
            "[get_suggestion_messages] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )

        # === Step 3: Fetch suggestions for vendor ===
        suggestions = get_suggestion_messages(vendor,limit=10)
        logger.info(
            "[get_suggestion_messages] Suggestions fetched | vendor_id=%s | count=%s",
            vendor.id, len(suggestions)
        )
        logger.debug(
            "[get_suggestion_messages] Suggestions detail | vendor_id=%s | suggestions=%s",
            vendor.id, suggestions
        )

        # === Step 4: Successful response ===
        response_data = {
            "message": "Suggestion messages retrieved successfully.",
            "suggestions": suggestions,
            "count": len(suggestions),
        }
        logger.info(
            "[get_suggestion_messages] Response ready | vendor_id=%s | count=%s",
            vendor.id, len(suggestions)
        )

        return Response(response_data, status=status.HTTP_200_OK)

    except NotFound as nf:
        # Specific case: Vendor not found
        logger.warning(
            "[get_suggestion_messages] Vendor not found | user=%s | error=%s",
            request.user.username, str(nf)
        )
        return Response({"error": str(nf)}, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(
            "[get_suggestion_messages] Unexpected error | user=%s | error=%s",
            request.user.username, str(e)
        )
        return Response({"error": "Internal server error"}, status=500)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def manager_order_update(request):
    """
    API endpoint: Allows a manager to update an order status or send a custom message.
    Actions supported:
        - "ready": Marks order ready, updates DB, notifies Android TV & web push.
        - "delivered": Marks order delivered, updates DB & sends web push.
        - "cancelled": Cancels order, updates DB & sends web push.
        - "message": Sends a custom manager message to customer via web push.
    """

    try:
        logger.info("📥 PATCH /manager_order_update called | user=%s", request.user.username)
        logger.debug("Request data: %s", request.data)

        data = request.data
        required_fields = ['token_no', 'status', 'action']
        missing = [f for f in required_fields if f not in data or data[f] in [None, ""]]

        # === Step 1: Validate required fields ===
        if missing:
            logger.warning("⛔ Missing fields: %s", ', '.join(missing))
            return Response(
                {"message": f"Missing fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # === Step 2: Validate token_no ===
        try:
            token_no = int(data['token_no'])
        except (TypeError, ValueError):
            logger.warning("❌ token_no must be a valid integer | value=%s", data['token_no'])
            return Response({"message": "token_no must be a valid integer."}, status=status.HTTP_400_BAD_REQUEST)

        status_to_update = data['status']
        action = request.data.get("action", "").lower()
        if action not in ["ready", "message", "delivered", "cancelled"]:
            return Response({"message": "Invalid action type."}, status=status.HTTP_400_BAD_REQUEST)
        action_type = action

        # === Step 3: Validate manager & vendor ===
        manager = getattr(request.user, 'profile_roles', None)
        if not manager or not manager.exists():
            logger.warning("⚠️ No manager profile found for user=%s", request.user.username)
            return Response({"message": "User is not a manager."}, status=status.HTTP_403_FORBIDDEN)
        manager = manager.first()
        if not manager.vendor:
            logger.warning("⚠️ Manager %s has no vendor", manager.name)
            return Response({"message": "Manager does not have an associated vendor."}, status=status.HTTP_403_FORBIDDEN)

        vendor = manager.vendor
        logger.info("🔧 Manager: %s | Vendor: %s (%s)", manager.name, vendor.name, vendor.vendor_id)

        # === Step 4: Get today's business day range ===
        start_dt, end_dt = get_vendor_business_day_range(vendor)
        if not start_dt or not end_dt:
            logger.warning("Invalid date range for vendor_id=%s", vendor.id)
            return Response({"error": "Invalid date range"}, status=400)

        order = Order.objects.filter(token_no=token_no, vendor=vendor, created_at__range=(start_dt, end_dt)).first()
        if not order:
            logger.warning("❌ No order found for token_no %s today.", token_no)
            return Response({"message": f"Order with token_no {token_no} not found."}, status=status.HTTP_404_NOT_FOUND)

        # === Step 5: Serialize vendor logo ===
        vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
        logo_url = vendor_serializer.data.get("logo_url", "")
        if not logo_url:
            logger.warning("⚠️ No logo URL for vendor %s", vendor.name)
            return Response({"message": "Vendor logo not found."}, status=status.HTTP_404_NOT_FOUND)

        # === Step 6: Prepare push payload ===
        payload = {
            "title": "Order Update by Manager",
            "body": f"Your order {token_no} status: {status_to_update.capitalize()}" if action_type == "ready"
                    else f"Your order {token_no} has an update from the manager." if action_type == "message"
                    else f"Your order {token_no} has been delivered." if action_type == "delivered"
                    else f"Your order {token_no} has been cancelled.",
            "token_no": token_no,
            "status": status_to_update.lower(),
            "counter_no": order.counter_no,
            "name": vendor.name,
            "vendor_id": vendor.vendor_id,
            "location_id": vendor.location_id,
            "logo_url": logo_url,
            "type": "foodstatus" if action_type in ["ready", "delivered", "cancelled"] else "manager",
            "message_id": None
        }

        android_tv_success, android_tv_info, push_errors = None, None, []

        # === Step 7: Handle different action types ===
        if action_type == "ready":
            # FCM push notifications if TV communication mode is not MQTT
            if vendor.config.tv_communication_mode != "MQTT":
                # 1. Notify Android TV
                android_tv_success, android_tv_info = notify_android_tv(vendor, data)
                logger.info("📺 Android TV notified | Success=%s | Info=%s", android_tv_success, android_tv_info)

            # 2. Update order in DB
            updated_order = update_existing_order_by_manager(token_no, vendor, None, action_type, manager)
            if not updated_order:
                logger.warning("❌ Failed to update order %s", token_no)
                return Response({"message": "Order update failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.info("✅ Order %s updated to %s", updated_order.token_no, status_to_update)

            # 3. Send MQTT update
            logger.info(f"📡 Sending MQTT update for vendor {vendor.vendor_id} with token {token_no}")
            if not hasattr(vendor, 'config') or not vendor.config.mqtt_mode:
                logger.warning(f"⚠️ Vendor {vendor.vendor_id} has no MQTT configuration.")
                return Response({"message": "Vendor has no MQTT configuration."}, status=status.HTTP_400_BAD_REQUEST)

            mqtt_success = send_order_update(vendor)
            if mqtt_success:
                logger.info(f"✅ MQTT update sent successfully for vendor {vendor.vendor_id}")
            else:
                logger.error(f"❌ Failed to send MQTT update for vendor {vendor.vendor_id}")
                return Response({"message": "Failed to send MQTT update."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # 4. Send Web Push (only if cooldown passed)
            cooldown = getattr(settings, "PUSH_COOLDOWN_SECONDS", 1)
            if not order.notified_at or (timezone.now() - order.notified_at) > timedelta(seconds=cooldown):
                logger.info("📤 Sending web push...")
                push_errors = notify_web_push(order, vendor, payload)
                order.notified_at = timezone.now()
                order.save(update_fields=["notified_at"])
                logger.info("🕒 Order %s marked as notified at %s", token_no, order.notified_at)
            else:
                logger.info("⏳ Cooldown active. Skipping web push for %s", token_no)

        elif action_type in ["delivered", "cancelled"]:
            logger.info("🔔 %s order %s by manager %s", action_type.capitalize(), token_no, manager.name)
            updated_order = update_existing_order_by_manager(token_no, vendor, None, action_type, manager)
            if updated_order:
                payload["title"] = f"Order {action_type.capitalize()}"
                push_errors = notify_web_push(order, vendor, payload)

        else:  # action_type == "message"
            MAX_MESSAGE_LENGTH = 200
            if status_to_update and len(status_to_update) > MAX_MESSAGE_LENGTH:
                return Response({"error": f"Message too long. Limit is {MAX_MESSAGE_LENGTH} characters."}, status=400)

            logger.info("ℹ️ Sending manager message via web push")
            chat_message = ChatMessage.objects.create(
                vendor=vendor,
                token_no=token_no,
                created_date=get_vendor_current_time(vendor).date(),
                sender='manager',
                is_send=True,
                message_text=status_to_update
            )
            payload["message_id"] = chat_message.id
            payload["status"] = status_to_update
            push_errors = notify_web_push(order, vendor, payload)
            if push_errors:
                logger.warning("❌ Failed web push for %s | Errors: %s", token_no, push_errors)
                chat_message.is_send = False
                chat_message.save(update_fields=["is_send"])
            else:
                logger.info("📤 Web push sent successfully for %s", token_no)

        # === Step 8: Return final response ===
        return Response({
            "success": True,
            "message": f"Order {'updated and ' if action_type == 'ready' else ''}notified successfully.",
            "token_no": token_no,
            "android_tv": android_tv_success,
            "android_tv_info": android_tv_info,
            "web_push": not push_errors,
            "web_push_info": push_errors,
            "mqtt":mqtt_success if action_type == "ready" else None
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("🔥 Unhandled exception in manager_order_update | user=%s", request.user.username)
        return Response({"success": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def chat_history(request):
    token_no = request.GET.get('token_no')
    if not token_no:
        return Response({"error": "token_no is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token_no = int(token_no)
    except ValueError:
        return Response({"error": "Invalid token_no."}, status=status.HTTP_400_BAD_REQUEST)

    vendor = get_manager_vendor(request.user)

    logger.info(f"[chat_history] Vendor resolved: id={vendor.id}, name={vendor.name}")

    today_date = get_vendor_current_date(vendor)

    # Mark only user messages as read
    ChatMessage.objects.filter(
        vendor=vendor,
        token_no=token_no,
        created_date=today_date,
        sender='user',
        is_read=False
    ).update(is_read=True)

    messages = ChatMessage.objects.filter(
        vendor=vendor,
        token_no=token_no,
        created_date=today_date
    ).order_by('created_at')

    serializer = ChatMessageSerializer(messages, many=True)
    return Response({"messages": serializer.data}, status=status.HTTP_200_OK)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def device_call(request):
    try:
        logger.info("📥 PATCH /device_call")
        logger.debug(f"Request Data: {request.data}")

        data = request.data
        required_fields = ['token_no','counter_no','status']
        missing = [f for f in required_fields if f not in data or data[f] in [None, ""]]

        if missing:
            logger.warning(f"⛔ Missing fields: {', '.join(missing)}")
            return Response({"message": f"Missing fields: {', '.join(missing)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate token_no as int
        try:
            token_no = int(data['token_no'])
        except (TypeError, ValueError):
            logger.warning("❌ token_no must be a valid integer.")
            return Response({"message": "token_no must be a valid integer."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate manager
        manager = getattr(request.user, 'profile_roles', None)
        if not manager or not manager.exists():
            logger.warning("⚠️ No manager profile found for the user.")
            return Response({"message": "User is not a manager."}, status=status.HTTP_403_FORBIDDEN)

        manager = manager.first()
        if not manager.vendor:
            logger.warning("⚠️ Manager does not have an associated vendor.")
            return Response({"message": "Manager does not have an associated vendor."}, status=status.HTTP_403_FORBIDDEN)

        vendor = manager.vendor
        logger.info(f"🔧 Manager: {manager.name}, Vendor: {vendor.name} ({vendor.vendor_id}), Token: {token_no}, Status: ready")

        # Get business day range in UTC
        start_dt, end_dt = get_vendor_business_day_range(vendor)

        if not start_dt or not end_dt:
            logger.warning(f"Invalid date range for vendor_id={vendor.id}")
            return Response({"error": "Invalid date range"}, status=400)
        status_to_update = data['status']
        # 2. Update in DB
        device = None  # Assuming device is not used in this context
        order = update_existing_order_by_manager(token_no, vendor, device, status_to_update, manager)
        if not order:
            logger.warning(f"❌ Failed to update order {token_no}")
            return Response({"message": "Order update failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info(f"✅ Order {order.token_no} updated to status: ready")
        # Serialize vendor logo
        vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
        logo_url = vendor_serializer.data.get("logo_url", "")
        if not logo_url:
            logger.warning(f"⚠️ No logo URL found for vendor {vendor.name}. Using default logo.")
            return Response({"message": "Vendor logo not found."}, status=status.HTTP_404_NOT_FOUND)

        # Prepare common push payload
        payload = {
            "title": "Order Update by Manager",
            "body": f"Your order {token_no} is ready for pickup at counter {data['counter_no']}.",
            "token_no": token_no,
            "status": "ready",
            "counter_no": order.counter_no,
            "name": vendor.name,
            "vendor_id": vendor.vendor_id,
            "location_id": vendor.location_id,
            "logo_url": logo_url,
            "type": "foodstatus",
            "message_id":None
        }

        android_tv_success = False
        android_tv_info = False
        push_errors = []

        # FCM push notifications if TV communication mode is not MQTT
        if vendor.config.tv_communication_mode != "MQTT":
            # Notify Android TV
            android_tv_success, android_tv_info = notify_android_tv(vendor, data)
            logger.info(f"📺 Android TV FCM sent | Success: {android_tv_success} | Info: {android_tv_info}")
            
       # MQTT Publish
        logger.info(f"Sending MQTT update for vendor {vendor.vendor_id} with token {token_no}")
        # Ensure the vendor has a config with mqtt_mode set
        if not hasattr(vendor, 'config') or not vendor.config.mqtt_mode:
            logger.warning(f"Vendor {vendor.vendor_id} has no MQTT configuration.")
            return Response({"message": "Vendor has no MQTT configuration."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Send order update via MQTT
        logger.info(f"Sending order update via MQTT for vendor {vendor.vendor_id},MQTT Server: {vendor.config.mqtt_server}")
        mqtt = send_order_update(vendor)
        if mqtt:
            logger.info(f"✅ MQTT update sent successfully for vendor {vendor.vendor_id}")
        else:
            logger.error(f"❌ Failed to send MQTT update for vendor {vendor.vendor_id}")
            return Response({"message": "Failed to send MQTT update."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Send Web Push (only if cooldown passed)
        cooldown = getattr(settings, "PUSH_COOLDOWN_SECONDS", 1)
        if not order.notified_at or (timezone.now() - order.notified_at) > timedelta(seconds=cooldown):
            logger.info(f"📤 Sending web push...")
            push_errors = notify_web_push(order, vendor, payload)
            order.notified_at = timezone.now()
            order.save(update_fields=["notified_at"])
            logger.info(f"🕒 Order {token_no} marked as notified at {order.notified_at}")
        else:
            logger.info(f"⏳ Cooldown active. Skipping web push for {token_no}.")


        # 📦 Final response
        return Response({
            "success": True,
            "message": "Order updated and notified successfully.",
            "token_no": token_no,
            "android_tv": android_tv_success,
            "android_tv_info": android_tv_info,
            "web_push": not push_errors,
            "web_push_info": push_errors,
            "mqtt": mqtt 
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(f"🔥 Unhandled exception in manager_order_update:{str(e)}")
        return Response({"success": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_tokens(request):
    """
    API endpoint to fetch the last N order tokens for the current vendor.
    - Only accessible to authenticated users.
    - Retrieves vendor linked to the logged-in manager.
    - Collects last N tokens where N is defined in vendor's config.
    """

    try:
        # === Step 1: Request start log ===
        logger.info(
            "[get_last_tokens] Request started | user=%s | method=%s | path=%s",
            request.user.username, request.method, request.path
        )

        # === Step 2: Resolve vendor from manager user ===
        vendor = get_manager_vendor(request.user)
        logger.info(
            "[get_last_tokens] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )

        if not hasattr(vendor, 'config') or not vendor.config.token_display_limit:
            logger.warning(
                "[get_last_tokens] Vendor has no token display limit configured | vendor_id=%s",
                vendor.id
            )
            return Response({"error": "Vendor has no token display limit configured."}, status=400)

        limit = vendor.config.token_display_limit

        # === Step 3: Fetch last N tokens for the vendor ===
        tokens = get_last_tokens(vendor, limit)
        logger.info(
            "[get_last_tokens] Tokens fetched | vendor_id=%s | tokens=%s",
            vendor.id, tokens
        )

        # === Step 4: Successful response ===
        response_data = {
            "message": "Last tokens retrieved successfully.",
            "tokens": tokens,
            "count": len(tokens),
        }
        logger.info(
            "[get_last_tokens] Response ready | vendor_id=%s | count=%s",
            vendor.id, len(tokens)
        )

        return Response(response_data, status=status.HTTP_200_OK)

    except NotFound as nf:
        # Specific case: Vendor not found
        logger.warning(
            "[get_last_tokens] Vendor not found | user=%s | error=%s",
            request.user.username, str(nf)
        )
        return Response({"error": str(nf)}, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(
            "[get_last_tokens] Unexpected error | user=%s | error=%s",
            request.user.username, str(e)   
        )
        return Response({"error": str(e)}, status=500)
            