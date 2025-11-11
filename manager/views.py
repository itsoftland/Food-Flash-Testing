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
from orders.utils import send_to_managers

from vendors.models import ChatMessage, Order
from vendors.serializers import OrdersSerializer
from vendors.services.order_service import send_order_update
from vendors.utils import notify_web_push
from vendors.order_utils import get_last_tokens 
from vendors.services.send_to_iot import get_azure_devices

from .serializers import ChatMessageSerializer
from .utils.utils import (get_manager_vendor, get_suggestion_messages,
                          get_order_counts, generate_sequence_code,
                          get_passenger_counts,notify_related_passengers,
                          create_bulk_chat_messages)

from static.utils.functions.notifications import notify_android_tv
from static.utils.functions.queries import (update_existing_order_by_manager,
                                             update_existing_status_by_airlinemanager)


from static.utils.functions.utils import (
    get_vendor_business_day_range,
    get_vendor_current_date,
    get_vendor_current_time,
)

logger = logging.getLogger(__name__)

project_name = getattr(settings, "PROJECT_NAME", "food_flash").lower()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_order_by_manager(request):
    """
    Create an order manually by a manager.
    - Food Flash → Requires `token_no` manually.
    - Airline Flash → Auto-generates `token_no` and sequence_code based on flight details.
    """
    logger.info("[create_order_by_manager] Started | user=%s | project=%s", request.user.username, project_name)

    # --- Step 1: Resolve vendor ---
    vendor = get_manager_vendor(request.user)
    logger.info("[create_order_by_manager] Vendor resolved | id=%s | name=%s", vendor.id, vendor.name)

    # --- Step 2: Field validation based on project ---
    token_no = request.data.get("token_no")

    if project_name == "airline_flash":
        required_fields = ["flight_no", "pnr_no", "seat_no","zone", "passenger_name"]
        missing = [f for f in required_fields if not request.data.get(f)]
        if missing:
            logger.warning("[create_order_by_manager] Missing required airline fields | %s", missing)
            return Response(
                {"error": f"Missing required fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract airline fields
        flight_no = request.data.get("flight_no")
        pnr_no = request.data.get("pnr_no")
        seat_no = request.data.get("seat_no")
        zone = request.data.get("zone")
        passenger_name = request.data.get("passenger_name")

        # Build sequence code
        sequence_code = generate_sequence_code(flight_no, pnr_no, seat_no, zone, passenger_name)
        # Auto-generate next token number for this vendor
        last_order = Order.objects.filter(vendor=vendor).order_by("-token_no").first()
        token_no = (last_order.token_no + 1) if last_order else 1

        logger.info(
            "[create_order_by_manager] AirlineFlash token auto-generated | vendor_id=%s | new_token=%s | sequence=%s",
            vendor.id, token_no, sequence_code
        )

    else:
        # Food Flash behaviour (unchanged)
        if not token_no:
            logger.warning("[create_order_by_manager] Missing token_no for Food Flash | user=%s", request.user.username)
            return Response({'error': 'token_no is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_no = int(token_no)
        except ValueError:
            return Response({'error': 'Invalid token number.'}, status=status.HTTP_400_BAD_REQUEST)

    # --- Step 3: Build tracking URL ---
    base_url = request.build_absolute_uri('/')

    # --- Step 4: Check for existing order today ---
    if project_name == "airline_flash":
        order = Order.objects.filter(
            flight_no=flight_no,seat_no=seat_no,pnr_no=pnr_no,passenger_name=passenger_name, vendor=vendor
        ).first()
        tracking_url = f"{base_url}{project_name}/home/?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}&sequence_code={sequence_code}&passenger_name={passenger_name}"
    else:
        start_dt, end_dt = get_vendor_business_day_range(vendor)
        order = Order.objects.filter(
            token_no=token_no, vendor=vendor, created_at__range=(start_dt, end_dt)
        ).first()
        tracking_url = f"{base_url}{project_name}/home/?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}&token_no={token_no}"
    if order:
        logger.info("[create_order_by_manager] Existing order found | token=%s", token_no)
        order_data = {
            'id': order.id,
            'token_no': order.token_no,
            'counter_no': order.counter_no,
            'updated_by': order.updated_by,
            'tracking_url': tracking_url,
            'status': order.status,
            'vendor': order.vendor.id,
            'vendor_name': order.vendor.name,
            'manager_id': order.user_profile.id if order.user_profile else None,
            'manager_name': order.user_profile.name if order.user_profile else None,
            'device': order.device.id if order.device else None,
            'shown_on_tv': order.shown_on_tv,
            'notified_at': order.notified_at,
            'created_at': order.created_at,
            'updated_at': order.updated_at,
            'type': 'flightstatus' if project_name == 'airline_flash' else 'foodstatus',
            'message': 'Order already exists for this token number.',
        }
        if project_name == "airline_flash":
            order_data.update({
                "flight_no": order.flight_no,
                "pnr_no": order.pnr_no,
                "seat_no": order.seat_no,
                "zone":order.zone,
                "passenger_name": order.passenger_name,
                "sequence_code": order.sequence_code,
            })
        return Response(order_data, status=status.HTTP_200_OK)

    # --- Step 5: Prepare new order data ---
    new_order_data = {
        'vendor': vendor.id,
        'token_no': token_no,
        'counter_no': 1,
        'updated_by': 'manager',
        'status':'created' if project_name == 'food_flash' else 'waiting',
        'type': 'flightstatus' if project_name == 'airline_flash' else 'foodstatus',
        'name': vendor.name,
        'location_id': vendor.location_id,
        'device': None,
        'manager_id': request.user.profile_roles.first().id if request.user.profile_roles.exists() else None,
    }

    if project_name == "airline_flash":
        new_order_data.update({
            "flight_no": flight_no,
            "pnr_no": pnr_no,
            "seat_no": seat_no,
            "zone":zone,
            "passenger_name": passenger_name,
            "sequence_code": sequence_code,
        })

    logger.debug("[create_order_by_manager] Prepared new order data | %s", new_order_data)

    # --- Step 6: Serialize and save ---
    serializer = OrdersSerializer(data=new_order_data)
    if serializer.is_valid():
        serializer.save()
        data = serializer.data
        data["tracking_url"] = tracking_url
        data["message"] = "Order created successfully by manager."
        logger.info("[create_order_by_manager] Order created successfully | token=%s | project=%s", token_no, project_name)
        return Response(data, status=status.HTTP_201_CREATED)
    else:
        logger.warning("[create_order_by_manager] Serializer validation failed | %s", serializer.errors)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

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
# === Airline Flash Api ===
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_passengers_list(request):
    """
    Retrieve passengers list grouped as flight_no → zone → passengers,
    including zone-wise unread notification counts.
    """
    try:
        logger.info(
            "[get_passengers_list] Request started | user=%s | method=%s | path=%s",
            request.user.username, request.method, request.path
        )

        vendor = get_manager_vendor(request.user)
        logger.info(
            "[get_passengers_list] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )

        passengers_qs = Order.objects.filter(vendor=vendor).order_by('flight_no', 'zone', 'seat_no')
        logger.info(
            "[get_passengers_list] Fetched passengers | vendor_id=%s | count=%s",
            vendor.id, passengers_qs.count()
        )

        serialized_data = OrdersSerializer(passengers_qs, many=True, context={'request': request}).data
        logger.debug(
            "[get_passengers_list] Serialized passengers | count=%s", len(serialized_data)
        )

        grouped_data = {}
        for passenger in serialized_data:
            flight_no = passenger.get("flight_no")
            zone = passenger.get("zone")
            if not flight_no or not zone:
                continue

            # Initialize structure if not already present
            grouped_data.setdefault(flight_no, {}).setdefault(zone, {"passengers": [], "unread": 0})
            
            # Add passenger
            grouped_data[flight_no][zone]["passengers"].append(passenger)

            # Increment zone unread count
            if passenger.get("new_notifications", 0) > 0:
                grouped_data[flight_no][zone]["unread"] += 1

        # Aggregate overall counts
        status_counts = get_passenger_counts(passengers_qs, serialized_data)

        response_data = {
            "message": "Passengers retrieved successfully.",
            "count": len(serialized_data),
            "detail": grouped_data,
            **status_counts
        }

        logger.info(
            "[get_passengers_list] Returning grouped response | user=%s | total=%s",
            request.user.username, len(serialized_data)
        )

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(
            "[get_passengers_list] Unexpected error | user=%s | error=%s",
            request.user.username, str(e)
        )
        return Response({"error": "Internal server error"}, status=500)

# === Airline Flash Api ===
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_passengers_list(request):
    """
    Retrieve passengers list grouped as flight_no → zone → passengers,
    including zone-wise unread notification counts.
    """
    try:
        logger.info(
            "[get_active_passengers_list] Request started | user=%s | method=%s | path=%s",
            request.user.username, request.method, request.path
        )

        vendor = get_manager_vendor(request.user)
        logger.info(
            "[get_active_passengers_list] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )
        active_chat_sequences = ChatMessage.objects.filter(vendor=vendor).values_list("sequence_code", flat=True).distinct()
        passengers_qs = Order.objects.filter(
            vendor=vendor
        ).filter(sequence_code__in=active_chat_sequences).order_by(
            'flight_no', 'zone', 'seat_no')
        logger.info(
            "[get_active_passengers_list] Fetched passengers | vendor_id=%s | count=%s",
            vendor.id, passengers_qs.count()
        )

        serialized_data = OrdersSerializer(passengers_qs, many=True, context={'request': request}).data
        logger.debug(
            "[get_active_passengers_list] Serialized passengers | count=%s", len(serialized_data)
        )

        grouped_data = {}
        for passenger in serialized_data:
            flight_no = passenger.get("flight_no")
            zone = passenger.get("zone")
            if not flight_no or not zone:
                continue

            # Initialize structure if not already present
            grouped_data.setdefault(flight_no, {}).setdefault(zone, {"passengers": [], "unread": 0})
            
            # Add passenger
            grouped_data[flight_no][zone]["passengers"].append(passenger)

            # Increment zone unread count
            if passenger.get("new_notifications", 0) > 0:
                grouped_data[flight_no][zone]["unread"] += 1

        # Aggregate overall counts
        status_counts = get_passenger_counts(passengers_qs, serialized_data)

        response_data = {
            "message": "Passengers retrieved successfully.",
            "count": len(serialized_data),
            "detail": grouped_data,
            **status_counts
        }

        logger.info(
            "[get_active_passengers_list] Returning grouped response | user=%s | total=%s",
            request.user.username, len(serialized_data)
        )

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception(
            "[get_active_passengers_list] Unexpected error | user=%s | error=%s",
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
            "[get_suggestion_messages] Suggestions detail | vendor_id=%s | count=%s | suggestions=%s",
            vendor.id,len(suggestions), suggestions
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
        logger.debug("Request data: %s", request.data)

        data = request.data

        # === Step 0: Handle field requirements dynamically ===
        if project_name == "airline_flash":
            required_fields = ["status", "action"]
            optional_fields = ["sequence_code","flight_no", "zone"]
        else:
            required_fields = ["token_no", "status", "action"]
            optional_fields = []

        # Check for missing required fields
        missing = [f for f in required_fields if f not in data or data[f] in [None, ""]]

        if missing:
            logger.warning("⛔ Missing fields: %s", ', '.join(missing))
            return Response(
                {"message": f"Missing fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # === Step 1: Identify target ===
        if project_name == "airline_flash":
            identifier_field = "sequence_code"
            identifier_value = data["sequence_code"]
            flight_no = data.get("flight_no") or None
            zone = data.get("zone") or None
            action_list = ["final_call", "message", "departed","arrived","cancelled"]
        else:
            identifier_field = "token_no"
            identifier_value = int(data["token_no"])
            flight_no = None
            zone = None
            action_list = ["ready", "message", "delivered", "cancelled"]

        logger.info(
            "📨 Request context | Project: %s | Identifier: %s=%s | Flight: %s | Zone: %s",
            project_name, identifier_field, identifier_value, flight_no, zone
        )

        status_to_update = data['status']
        action = data.get("action", "").lower()
        if action not in action_list:
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
        if project_name == "airline_flash":
            if identifier_value:
                filters = {
                    identifier_field: identifier_value,
                    "vendor": vendor,
                }
            else:
                # No sequence_code: this must be a message broadcast (flight or zone)
                if not (flight_no or zone) :
                    return Response({"message": "Either sequence_code or flight_no or zone must be provided."}, status=status.HTTP_400_BAD_REQUEST)

                # Build filters for flight/zone broadcasts (no sequence_code)
                if flight_no:
                    filters = {"vendor": vendor, "flight_no": flight_no}
                if zone:
                    filters["zone"] = zone
        else:
            start_dt, end_dt = get_vendor_business_day_range(vendor)
            if not start_dt or not end_dt:
                logger.warning("Invalid date range for vendor_id=%s", vendor.id)
                return Response({"error": "Invalid date range"}, status=400)

            filters = {
                identifier_field: identifier_value,
                "vendor": vendor,
                "created_at__range": (start_dt, end_dt)
            }
        order = Order.objects.filter(**filters).first()
        if not order and project_name == "airline_flash":
            logger.warning("❌ No data found for sequence_code %s today.", identifier_value)
            return Response({"message": f"Data with sequence_code {identifier_value} not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            if not order:
                logger.warning("❌ No order found for token_no %s today.", identifier_value)
                return Response({"message": f"Order with token_no {identifier_value} not found."}, status=status.HTTP_404_NOT_FOUND)

        # === Step 5: Serialize vendor logo ===
        vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
        logo_url = vendor_serializer.data.get("logo_url", "")
        if not logo_url:
            logger.warning("⚠️ No logo URL for vendor %s", vendor.name)
            return Response({"message": "Vendor logo not found."}, status=status.HTTP_404_NOT_FOUND)

        # === Step 6: Prepare push payload ===
        message_type = (
            "manager" if action_type == "message" and project_name == 'food_flash'
            else "airline_manager" if action_type == "message" and project_name == 'airline_flash'
            else "foodstatus" if project_name == "food_flash" and action_type in action_list
            else "flightstatus" if project_name == "airline_flash" and action_type in action_list
            else None
        )

        payload = {
            "title": "Order Update by Manager",
            "body": f"Your order {identifier_value} status: {status_to_update.capitalize()}" if action_type == "ready"
                    else f"Your order {identifier_value} has an update from the manager." if action_type == "message"
                    else f"Your order {identifier_value} has been delivered." if action_type == "delivered"
                    else "Proceed to Aircraft, your journey awaits!" if action_type == "final_call"
                    else f"Your order {identifier_value} has an update." ,
            "status": status_to_update.lower(),
            "counter_no": order.counter_no,
            "name": vendor.name,
            'alias_name': vendor.alias_name,
            "vendor_id": vendor.vendor_id,
            "location_id": vendor.location_id,
            "logo_url": logo_url,
            "type": message_type,
            "message_id": None,
            "token_no": order.token_no,
        }
        if project_name == "airline_flash":
            payload["sequence_code"] = order.sequence_code
            payload["flight_no"] = order.flight_no
            payload["pnr_no"] = order.pnr_no
            payload["seat_no"] = order.seat_no
            payload["seat_no"]= order.zone,
            payload["passenger_name"] = order.passenger_name

        android_tv_success, android_tv_info, mqtt_success, push_errors = None, None,None ,[]

        # === Step 7: Handle different action types ===
        if action_type in ['ready', 'final_call']:
            # FCM push notifications if TV communication mode is not MQTT
            if vendor.config.tv_communication_mode == "Firebase":
                # 1. Notify Android TV
                android_tv_success, android_tv_info = notify_android_tv(vendor, data)
                logger.info("📺 Android TV notified | Success=%s | Info=%s", android_tv_success, android_tv_info)

            # 2. Update order in DB 
            if project_name == "airline_flash":
                data_status = update_existing_status_by_airlinemanager(identifier_value, vendor, None, action_type, manager)
            else:
                data_status = update_existing_order_by_manager(identifier_value, vendor, None, action_type, manager)
            if not data_status:
                logger.warning("❌ Failed to update status %s", identifier_value)
                return Response({"message": "Status update failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.info("✅ Status %s updated to %s", identifier_value, status_to_update)
            if vendor.config.tv_communication_mode == "AZURE_IOT":
                logger.info(f"[update_order] Azure IoT communication mode detected for vendor {vendor.vendor_id}")
                azure_iot = get_azure_devices(vendor)
                logger.info(f"[update_order] Azure IoT messages sent: {azure_iot}")
            if vendor.config.tv_communication_mode == "MQTT":
                # 3. Send MQTT update
                logger.info(f"📡 Sending MQTT update for vendor {vendor.vendor_id} with {identifier_field} {identifier_value}")
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
                order.refresh_from_db()  # ✅ ensures latest status from DB
                order.notified_at = timezone.now()
                order.save(update_fields=["notified_at"])
            else:
                logger.info("⏳ Cooldown active. Skipping web push for %s", identifier_value)

        elif action_type in ["delivered", "cancelled","arrived","departed"]:
            logger.info("🔔 %s order %s by manager %s", action_type.capitalize(), identifier_value, manager.name)
            if project_name == "airline_flash":
                data_status = update_existing_status_by_airlinemanager(identifier_value, vendor, None, action_type, manager)
            else:
                data_status = update_existing_order_by_manager(identifier_value, vendor, None, action_type, manager)
            if data_status:
                payload["title"] = f"Order {action_type.capitalize()}" if project_name == "food_flash" else f"Status {action_type.capitalize()}"
                push_errors = notify_web_push(order, vendor, payload)
                order.refresh_from_db()  # ✅ ensures latest status from DB
                order.notified_at = timezone.now()
                order.save(update_fields=["notified_at"])
                logger.info("🕒 Status %s marked as notified at %s", identifier_value, order.notified_at)

        else:  # action_type == "message"
            MAX_MESSAGE_LENGTH = 200
            if status_to_update and len(status_to_update) > MAX_MESSAGE_LENGTH:
                return Response({"error": f"Message too long. Limit is {MAX_MESSAGE_LENGTH} characters."}, status=400)

            logger.info("ℹ️ Sending manager message via web push")
            payload["status"] = status_to_update

            if project_name == "airline_flash" and (flight_no or zone):
                # Bulk create chat messages for all passengers
                chat_messages = create_bulk_chat_messages(vendor, order, status_to_update, sender="manager", zone=zone)
                chat_map = {cm.sequence_code: cm.id for cm in chat_messages}
                token_map = {cm.sequence_code: cm.token_no for cm in chat_messages}
                # Send notifications
                push_errors = notify_related_passengers(order, vendor, payload, zone=zone, chat_map=chat_map,token_map=token_map)

                # Handle push errors (update chat records if failed)
                if push_errors:
                    logger.warning("❌ Some web pushes failed for flight %s | Errors: %s", order.flight_no, push_errors)
                    # Example: if push_errors contain sequence_codes or we handle all failures generally
                    failed_chat_ids = [chat_map.get(seq) for seq in chat_map.keys()]
                    ChatMessage.objects.filter(id__in=failed_chat_ids).update(is_send=False)
                else:
                    logger.info("📤 Group web push sent successfully for flight %s", order.flight_no)

            else:
                # Normal single message for Food Flash
                chat_kwargs = {
                    "vendor": vendor,
                    "created_date": get_vendor_current_time(vendor).date(),
                    "sender": "manager",
                    "is_send": True,
                    "message_text": status_to_update,
                    "token_no": order.token_no
                }

                chat_message = ChatMessage.objects.create(**chat_kwargs)
                payload["message_id"] = chat_message.id
                if identifier_field == "sequence_code":
                    payload['sequence_code'] = order.sequence_code

                push_errors = notify_web_push(order, vendor, payload)

                if push_errors:
                    logger.warning("❌ Failed web push for %s | Errors: %s", identifier_value, push_errors)
                    chat_message.is_send = False
                    chat_message.save(update_fields=["is_send"])
                else:
                    logger.info("📤 Web push sent successfully for %s", identifier_value)

        # === Step 8: Return final response ===  
        response_payload = {
            "success": True,
            "message": f"Order {'updated and ' if action_type == 'ready' else ''}notified successfully.",
            "token_no":None if project_name == "airline_flash" else order.token_no ,
            "android_tv": android_tv_success,
            "android_tv_info": android_tv_info,
            "web_push": not push_errors,
            "web_push_info": push_errors,
            "mqtt":mqtt_success if action_type == "ready" else None
        }      
        if project_name == 'airline_flash':
            response_payload['sequence_code'] = order.sequence_code
        return Response(response_payload, status=status.HTTP_200_OK)

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
            'alias_name': vendor.alias_name,
            "vendor_id": vendor.vendor_id,
            "location_id": vendor.location_id,
            "logo_url": logo_url,
            "type": "foodstatus",
            "message_id":None
        }

        android_tv_success = False
        android_tv_info = False
        push_errors = []
        mqtt=False

        # FCM push notifications if TV communication mode is not MQTT
        if vendor.config.tv_communication_mode == "Firebase":
            # Notify Android TV
            android_tv_success, android_tv_info = notify_android_tv(vendor, data)
            logger.info(f"📺 Android TV FCM sent | Success: {android_tv_success} | Info: {android_tv_info}")
        if vendor.config.tv_communication_mode == "AZURE_IOT":
            logger.info(f"[update_order] Azure IoT communication mode detected for vendor {vendor.vendor_id}")
            azure_iot = get_azure_devices(vendor)
            logger.info(f"[update_order] Azure IoT messages sent: {azure_iot}")
        if vendor.config.tv_communication_mode == "MQTT":
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
            order.refresh_from_db()  # ✅ ensures latest status from DB
            order.notified_at = timezone.now()
            order.save(update_fields=["notified_at"])
            logger.info(f"🕒 Order {token_no} marked as notified at {order.notified_at}")
        else:
            logger.info(f"⏳ Cooldown active. Skipping web push for {token_no}.")
        title="Manager Device Alert"
        body=f"Order {token_no} is now ready to be served"
        # Notify managers via FCM
        send_to_managers(vendor, payload,title,body)
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
            