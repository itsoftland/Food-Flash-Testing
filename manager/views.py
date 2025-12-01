import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.urls import reverse

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from orders.serializers import VendorLogoSerializer
from orders.utils import send_to_managers

from vendors.models import ChatMessage, Order,Utility
from vendors.serializers import OrdersSerializer
from vendors.services.order_service import send_order_update
from vendors.utils import notify_web_push
from vendors.order_utils import get_last_tokens 
from vendors.services.send_to_iot import get_azure_devices

from core.config.status_choices import STATUS_CHOICES_MAP

from .serializers import ChatMessageSerializer
from .utils.utils import (get_manager_vendor, get_suggestion_messages,
                          get_order_counts, generate_sequence_code,
                          get_passenger_counts,notify_related_passengers,
                          create_bulk_chat_messages,reset_counters_if_new_business_day)

from static.utils.functions.notifications import notify_android_tv
from static.utils.functions.queries import (update_existing_order_by_manager,
                                            update_existing_status_by_airlinemanager_bulk,
                                            )

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
        message = "Order created successfully by manager."
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
                'message': 'Passenger already exists for these details.',
            })
        return Response(order_data, status=status.HTTP_200_OK)

    # --- Step 5: Prepare new order data ---
    new_order_data = {
        'vendor': vendor.id,
        'token_no': token_no,
        'counter_no': 1,
        'updated_by': 'manager',
        'status':'created' if project_name == 'food_flash' else 'bp_issued',
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
        message = "Passenger Details Created Successfully"

    logger.debug("[create_order_by_manager] Prepared new order data | %s", new_order_data)

    # --- Step 6: Serialize and save ---
    serializer = OrdersSerializer(data=new_order_data)
    if serializer.is_valid():
        serializer.save()
        data = serializer.data
        data["tracking_url"] = tracking_url
        data["message"] = message
        logger.info("[create_order_by_manager] Order created successfully | token=%s | project=%s", token_no, project_name)
        return Response(data, status=status.HTTP_201_CREATED)
    else:
        logger.warning("[create_order_by_manager] Serializer validation failed | %s", serializer.errors)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def book_table(request):
    logger.info("[book_table] Started | remote_addr=%s", request.META.get("REMOTE_ADDR"))

    data = request.data or {}
    utility_id = data.get("utility_id")
    no_of_guests = data.get("no_of_guests")
    special_notes = data.get("special_notes")
    phone_number = data.get("phone_number") or None
    customer_name = data.get("customer_name")

    # ------------------------------
    # 1. Basic validation
    # ------------------------------
    required_base = {
        "no_of_guests": no_of_guests,
        "customer_name": customer_name,
    }
    missing = [k for k, v in required_base.items() if not v]
    if missing:
        logger.warning("[book_table] Missing required fields: %s", missing)
        return Response(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ------------------------------
    # 2. Vendor resolution (prefetch config)
    # ------------------------------
    vendor = get_manager_vendor(request.user)  # existing helper
    # Ensure vendor has config prefetched if possible (get_manager_vendor should ideally do this)
    vendor_config = getattr(vendor, "config", None)
    if vendor_config is None:
        logger.warning("[book_table] VendorConfig missing | vendor_id=%s", getattr(vendor, "vendor_id", None))
        return Response({"error": "Vendor configuration missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # ------------------------------
    # 3. Utility requirement
    # ------------------------------
    if vendor_config.use_utilities and not utility_id:
        return Response(
            {"error": "utility_id is required because utilities are enabled."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Resolve utility if provided (no update yet)
    utility = None
    if vendor_config.use_utilities and utility_id:
        utility = Utility.objects.filter(id=utility_id, vendor=vendor).first()
        if not utility:
            logger.warning("[book_table] Utility not found | utility_id=%s", utility_id)
            return Response({"error": "Utility not found for this vendor."}, status=status.HTTP_404_NOT_FOUND)

    # ------------------------------
    # 4. Atomic section with row-level locking
    #    - Lock vendor row (serializes token allocation)
    #    - Lock utility row if we will update its counter
    # ------------------------------
    try:
        with transaction.atomic():
            # Re-fetch vendor with select_for_update to serialize concurrent manager bookings
            vendor_locked = type(vendor).objects.select_for_update().select_related("config").get(pk=vendor.pk)

            # Token number (vendor-wide) — compute safely after locking vendor
            last_booking = (
                Order.objects.filter(vendor=vendor_locked).select_for_update(nowait=False).order_by("-token_no").first()
            )
            token_no = (last_booking.token_no + 1) if last_booking else 1

            # Booking number / counter handling
            if vendor_config.use_utilities and utility and getattr(utility, "prefix", None):
                # If we'll update utility counters, lock the utility
                # Re-fetch utility with select_for_update if we need to bump its counter
                if utility.token_mode == Utility.TOKEN_MODE_CONTINUOUS:
                    # continuous = vendor-level booking counter in vendor_config
                    # Lock vendor_config row implicitly by locking vendor (assumes config is FK on vendor)
                    vendor_config.continuous_booking_counter = (vendor_config.continuous_booking_counter or 0) + 1
                    vendor_config.save(update_fields=["continuous_booking_counter"])
                    booking_counter = vendor_config.continuous_booking_counter
                else:
                    locked_utility = type(utility).objects.select_for_update().get(pk=utility.pk)
                    locked_utility.utility_booking_counter = (locked_utility.utility_booking_counter or 0) + 1
                    locked_utility.save(update_fields=["utility_booking_counter"])
                    booking_counter = locked_utility.utility_booking_counter

                booking_no = f"{utility.prefix}-{booking_counter}"
            else:
                # Utilities disabled or missing prefix -> fallback to token_no
                booking_no = str(token_no)

            # Build tracking URL via reverse to avoid hardcoded paths
            try:
                # Attempt to use a named URL; fallback to previous pattern if reverse fails
                tracking_path = reverse("orders:home")  # adjust name to your URLconf
                tracking_url = request.build_absolute_uri(f"{tracking_path}?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}&booking_no={booking_no}")
            except Exception:
                # Fallback to original style using project_name variable
                tracking_url = request.build_absolute_uri(
                    f"/{project_name}/home/?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}&booking_no={booking_no}"
                )

            # Manager ID extraction (single DB hit)
            manager_id = (
                request.user.profile_roles.order_by("id").values_list("id", flat=True).first()
                if hasattr(request.user, "profile_roles")
                else None
            )

            # New booking payload
            new_booking_data = {
                "vendor": vendor.id,
                "token_no": token_no,
                "table_booking_no": booking_no,
                "counter_no": 1,
                "updated_by": "manager",
                "status": "created",
                "type": "dinestatus",
                "name": vendor.name,
                "location_id": vendor.location_id,
                "device": None,
                "no_of_packs": no_of_guests,
                "customer_name": customer_name,
                "remarks": special_notes,
                "phone_number": phone_number,
                "utility": utility.id if utility else None,
                "manager_id": manager_id,
            }

            serializer = OrdersSerializer(data=new_booking_data)
            if serializer.is_valid():
                serializer.save()

                resp_data = serializer.data
                resp_data["tracking_url"] = tracking_url
                resp_data["message"] = "Booking created successfully."

                logger.info(
                    "[book_table] Booking created | vendor=%s, token_no=%s, booking_no=%s, manager_id=%s",
                    vendor.vendor_id,
                    token_no,
                    booking_no,
                    manager_id,
                )
                return Response(resp_data, status=status.HTTP_201_CREATED)

            # Serializer invalid
            logger.warning("[book_table] Serializer validation failed | %s", serializer.errors)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as exc:
        logger.exception("[book_table] Exception while creating booking: %s", exc)
        return Response({"error": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            'alias_name': vendor.alias_name,
            "vendor_id": vendor.vendor_id,
            "location_id": vendor.location_id,
            "logo_url": logo_url,
            "type": "foodstatus" if action_type in ["ready", "delivered", "cancelled"] else "manager",
            "message_id": None,
            "vibration_pattern":vendor.config.vibration_pattern,
            "vibration_duration":vendor.config.vibration_duration
        }

        android_tv_success, android_tv_info, mqtt_success, push_errors = None, None,None ,[]

        # === Step 7: Handle different action types ===
        if action_type == "ready":
            # FCM push notifications if TV communication mode is not MQTT
            if vendor.config.tv_communication_mode == "Firebase":
                # 1. Notify Android TV
                android_tv_success, android_tv_info = notify_android_tv(vendor, data)
                logger.info("📺 Android TV notified | Success=%s | Info=%s", android_tv_success, android_tv_info)

            # 2. Update order in DB
            updated_order = update_existing_order_by_manager(token_no, vendor, None, action_type, manager)
            if not updated_order:
                logger.warning("❌ Failed to update order %s", token_no)
                return Response({"message": "Order update failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            logger.info("✅ Order %s updated to %s", updated_order.token_no, status_to_update)
            if vendor.config.tv_communication_mode == "AZURE_IOT":
                logger.info(f"[update_order] Azure IoT communication mode detected for vendor {vendor.vendor_id}")
                azure_iot = get_azure_devices(vendor)
                logger.info(f"[update_order] Azure IoT messages sent: {azure_iot}")
            if vendor.config.tv_communication_mode == "MQTT":
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
                order.refresh_from_db()  # ✅ ensures latest status from DB
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
                order.refresh_from_db()  # ✅ ensures latest status from DB
                order.notified_at = timezone.now()
                order.save(update_fields=["notified_at"])
                logger.info("🕒 Order %s marked as notified at %s", token_no, order.notified_at)

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

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def manager_passenger_update(request):
    """
    API endpoint: Allows a manager to update passenger/order status or send a custom message.
    Supports:
        - "boarding_shortly": Marks boarding soon, updates DB & pushes.
        - "message": Sends custom manager message to passengers.
        - "boarding_announced", "gate_change", "rescheduled", "cancelled": Broadcasts by flight/zone.
    """

    try:
        logger.debug("Request data: %s", request.data)
        data = request.data
        project_name = "airline_flash"

        # === Step 0: Validate required fields ===
        required_fields = ["status", "action"]
        missing = [f for f in required_fields if f not in data or data[f] in [None, ""]]
        if missing:
            return Response(
                {"success": False, "message": f"Missing fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract base fields
        flight_no = data.get("flight_no")
        zone = data.get("zone")
        sequence_code = data.get("sequence_code")
        status_to_update = data["status"]
        action_type = data.get("action", "").lower()

        # === Step 1: Action validation ===
        action_list = ["boarding_shortly", "message", "boarding_announced", "gate_change", "rescheduled", "cancelled"]
        if action_type not in action_list:
            return Response({"success": False, "message": "Invalid action type."}, status=400)

        # === Step 2: Validate manager/vendor ===
        manager = getattr(request.user, "profile_roles", None)
        if not manager or not manager.exists():
            return Response({"success": False, "message": "User is not a manager."}, status=403)
        manager = manager.first()

        vendor = getattr(manager, "vendor", None)
        if not vendor:
            return Response({"success": False, "message": "Manager has no associated vendor."}, status=403)

        logger.info("🔧 Manager: %s | Vendor: %s (%s)", manager.name, vendor.name, vendor.vendor_id)

        # === Step 3: Determine operation type & build filters ===
        operation_type = None
        filters = {"vendor": vendor}

        if sequence_code:
            filters["sequence_code"] = sequence_code
            operation_type = "AIRLINE_SEQUENCE"
            message = "Passenger notified successfully"
        elif flight_no and zone:
            filters.update({"flight_no": flight_no, "zone": zone})
            operation_type = "AIRLINE_FLIGHT_ZONE_BROADCAST"
            message = "Passengers notified successfully"
        elif flight_no:
            filters["flight_no"] = flight_no
            operation_type = "AIRLINE_FLIGHT_BROADCAST"
            message = "Passengers notified successfully"
        else:
            return Response(
                {"success": False, "message": "Either sequence_code or flight_no (with optional zone) required."},
                status=400,
            )

        logger.info("📨 Operation type: %s | Filters: %s", operation_type, filters)

        passengers = Order.objects.filter(**filters)
        if not passengers.exists():
            return Response({"success": False, "message": "No matching passengers found."}, status=404)

        # Representative order for payload reference
        passenger = passengers.first()

        # === Step 4: Vendor logo ===
        vendor_serializer = VendorLogoSerializer(vendor, context={"request": request})
        logo_url = vendor_serializer.data.get("logo_url")
        if not logo_url:
            return Response({"success": False, "message": "Vendor logo not found."}, status=404)

        # === Step 5: Base payload ===
        message_type = (
            "airline_manager" if action_type == "message" else "flightstatus"
        )

        payload = {
            "title": "Flight Update by Manager",
            "body": f"Passenger {sequence_code} has an update from the manager."
                    if action_type == "message"
                    else f"Update for flight {passenger.flight_no}",
            "status": status_to_update.lower(),
            "counter_no": getattr(passenger, "counter_no", None),
            "name": vendor.name,
            "alias_name": vendor.alias_name,
            "vendor_id": vendor.vendor_id,
            "location_id": getattr(vendor, "location_id", None),
            "logo_url": logo_url,
            "type": message_type,
            "message_id": None,
            "token_no": getattr(passenger, "token_no", None),
            "flight_no": getattr(passenger, "flight_no", None),
            "pnr_no": getattr(passenger, "pnr_no", None),
            "seat_no": getattr(passenger, "seat_no", None),
            "zone": getattr(passenger, "zone", None),
            "passenger_name": getattr(passenger, "passenger_name", None),
        }

        # === Step 6: Handle action logic ===
        if action_type != "message":
            if operation_type == "AIRLINE_SEQUENCE":
                update_existing_status_by_airlinemanager_bulk(sequence_code=sequence_code, vendor=vendor, device=None, status=action_type, manager=manager)
            elif operation_type in ["AIRLINE_FLIGHT_BROADCAST", "AIRLINE_FLIGHT_ZONE_BROADCAST"]:
                update_existing_status_by_airlinemanager_bulk(sequence_code=None, vendor=vendor, device=None, status=action_type, manager=manager, orders_queryset=passengers)

        else:
            MAX_MESSAGE_LENGTH = 200
            if status_to_update and len(status_to_update) > MAX_MESSAGE_LENGTH:
                return Response(
                    {"success": False, "message": f"Message too long. Limit is {MAX_MESSAGE_LENGTH}."},
                    status=400,
                )
            payload["status"] = status_to_update
        # === Step 7: Resolve display value ===
        status_choices = dict(STATUS_CHOICES_MAP.get(project_name, []))
        display_value = status_to_update if action_type == "message" else status_choices.get(status_to_update, status_to_update)

        push_errors = []

        # === Step 8: Operation branching ===
        if operation_type in ["AIRLINE_FLIGHT_BROADCAST", "AIRLINE_FLIGHT_ZONE_BROADCAST"]:
            # Bulk send (flight-level or zone-level)
            chat_messages = create_bulk_chat_messages(vendor, passenger, display_value, sender="manager", zone=zone)
            chat_map = {cm.sequence_code: cm.id for cm in chat_messages}
            token_map = {cm.sequence_code: cm.token_no for cm in chat_messages}

            push_errors = notify_related_passengers(
                passenger, vendor, payload, zone=zone,
                chat_map=chat_map, token_map=token_map,
            )

            if push_errors:
                ChatMessage.objects.filter(id__in=chat_map.values()).update(is_send=False)
                logger.warning("❌ Some broadcast pushes failed | %s", push_errors)
            else:
                logger.info("📤 Broadcast push success | Flight=%s Zone=%s", flight_no, zone)

        elif operation_type == "AIRLINE_SEQUENCE":
            # Single passenger push
            chat_message = ChatMessage.objects.create(
                vendor=vendor,
                created_date=get_vendor_current_time(vendor).date(),
                sender="manager",
                is_send=False,
                message_text=display_value,
                token_no=passenger.token_no,
                sequence_code=passenger.sequence_code,
            )
            payload["message_id"] = chat_message.id
            payload["sequence_code"] = passenger.sequence_code
            push_errors = notify_web_push(passenger, vendor, payload,passenger.sequence_code)

            passenger.refresh_from_db()
            passenger.notified_at = timezone.now()
            passenger.save(update_fields=["notified_at"])

            if not push_errors:
                chat_message.is_send = True
                chat_message.save(update_fields=["is_send"])
                logger.info("📤 Web push success for passenger %s", passenger.sequence_code)
            else:
                logger.warning("❌ Web push failed for passenger %s | %s", passenger.sequence_code, push_errors)

        # === Step 9: Response ===
        return Response(
            {
                "success": True,
                "operation_type": operation_type,
                "message":  message,
                "web_push": not bool(push_errors),
                "web_push_info": push_errors,
                "flight_no": flight_no,
                "zone": zone,
                "sequence_code": sequence_code,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("🔥 Unhandled exception in manager_passenger_update | user=%s", request.user.username)
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def chat_history(request):
    logger.debug("Request data: %s", request.GET)

    # ✅ 1. Input validation
    if project_name == "airline_flash":
        sequence_code = request.GET.get('sequence_code')
        if not sequence_code:
            logger.warning("[chat_history] Missing sequence_code parameter")
            return Response({"error": "sequence_code is required."}, status=status.HTTP_400_BAD_REQUEST)
        lookup_key = {"sequence_code": sequence_code}
        logger.info(f"[chat_history] Using sequence_code={sequence_code}")
    else:
        token_no = request.GET.get('token_no')
        if not token_no:
            logger.warning("[chat_history] Missing token_no parameter")
            return Response({"error": "token_no is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token_no = int(token_no)
            lookup_key = {"token_no": token_no}
            logger.info(f"[chat_history] Using token_no={token_no}")
        except ValueError:
            logger.error(f"[chat_history] Invalid token_no value: {token_no}")
            return Response({"error": "Invalid token_no."}, status=status.HTTP_400_BAD_REQUEST)

    # ✅ 2. Resolve vendor efficiently
    vendor = get_manager_vendor(request.user)
    logger.info(f"[chat_history] Vendor resolved: id={vendor.id}, name={vendor.name}")

    # ✅ 3. Filter by vendor’s current business date
    today_date = get_vendor_current_date(vendor)
    logger.info(f"[chat_history] Vendor current date: {today_date}")

    # ✅ 4. Use atomic update for marking as read (avoids race conditions)
    filter_kwargs = {"vendor": vendor, "sender": "user", "is_read": False, **lookup_key}
    if project_name != "airline_flash":
        filter_kwargs["created_date"] = today_date

    updated_count = ChatMessage.objects.filter(**filter_kwargs).update(is_read=True)
    logger.debug(f"[chat_history] Marked {updated_count} messages as read.")

    # ✅ 5. Query only relevant fields (lighter serialization)
    message_filter = {"vendor": vendor, **lookup_key}
    if project_name != "airline_flash":
        message_filter["created_date"] = today_date

    messages = (
        ChatMessage.objects
        .filter(**message_filter)
        .only("id", "sender", "message_text", "audio_file", "created_at", "is_read")
        .order_by("created_at")
    )

    # ✅ 6. Serializer execution
    serializer = ChatMessageSerializer(messages, many=True)
    logger.info(f"[chat_history] Returning {len(serializer.data)} messages for vendor={vendor.name}")

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
            "message_id":None,
            "vibration_pattern":vendor.config.vibration_pattern,
            "vibration_duration":vendor.config.vibration_duration
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
            