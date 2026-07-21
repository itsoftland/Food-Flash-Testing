import logging
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.db import transaction, close_old_connections
from django.db.models import Count, Exists, F, Max, OuterRef
from django.urls import reverse

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from orders.dine_flash_tracking_token import build_dine_flash_encrypted_tracking_url
from orders.serializers import VendorLogoSerializer
from orders.utils import send_to_managers

from vendors.models import ChatMessage, Order, Utility, OrderStatusHistory, Vendor
from vendors.serializers import OrdersSerializer
from vendors.services.order_service import send_order_update
from vendors.utils import notify_web_push
from vendors.order_utils import get_last_tokens 
from vendors.services.send_to_iot import get_azure_devices

from core.config.status_choices import STATUS_CHOICES_MAP

from .serializers import ChatMessageSerializer
from .serializer.booking_serializer import (
    BookingSerializer,
    serialize_dine_flash_manager_bookings,
)
from .utils.utils import (get_manager_vendor, get_manager_vendor_dine_flash,
                          get_dine_flash_manager_vendor_brief,
                          get_suggestion_messages,
                          get_order_counts, generate_sequence_code,
                          get_passenger_counts,notify_related_passengers,
                          create_bulk_chat_messages)
from .utils.booking_counts import get_booking_status_counts
from .utils.utility_cache import (
    get_cached_utilities as _get_cached_dine_flash_utilities,
    set_cached_utilities as _set_cached_dine_flash_utilities,
)
from .utils.dine_flash_manager_cache import get_cached_manager_vendor
from .utils.dine_flash_request_perf import (
    ensure_request_trace,
    log_trace_phase,
    record_handler_timing,
)

from static.utils.functions.notifications import notify_android_tv
from vendors.dine_flash_tv_fcm import (
    dine_flash_fcm_scope_applies,
    schedule_dine_flash_booking_status_fcm,
    schedule_dine_flash_manager_booking_tv_fcm,
    should_notify_dine_flash_booking_status_transition,
)
from static.utils.functions.queries import (update_existing_order_by_manager,
                                            update_existing_status_by_airlinemanager_bulk,
                                            update_booking_status_by_dinemanager,
                                            )
from .hospital_views import resolve_hospital_effective_departments

from static.utils.functions.utils import (
    get_vendor_business_day_range,
    get_vendor_current_date,
    get_vendor_current_time,
)
from django.utils import timezone
from datetime import timedelta





logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "food_flash").lower()


def _dine_flash_book_table_encrypted_tracking_url(vendor, order, request):
    """Signed tracking URL for manager book_table responses (Dine Flash only)."""
    if project_name != "dine_flash":
        return None
    return build_dine_flash_encrypted_tracking_url(vendor, order, request)


def _resolve_vendor_for_manager(request):
    """
    For Dine Flash deployments, resolve vendor in one DB round-trip.
    Other projects keep the shared get_manager_vendor() behaviour.
    """
    if project_name == "dine_flash":
        vendor = get_manager_vendor_dine_flash(request.user)
        if not vendor:
            raise NotFound("Vendor not found for this manager")
        return vendor
    return get_manager_vendor(request.user)


def _build_unread_notifications_map(vendor, booking_ids):
    """
    Build booking_id -> unread user message count in a single query.
    """
    if not booking_ids:
        return {}

    unread_rows = (
        ChatMessage.objects
        .filter(
            vendor=vendor,
            booking_id__in=booking_ids,
            sender="user",
            is_read=False,
        )
        .values("booking_id")
        .annotate(unread_count=Count("id"))
    )
    return {row["booking_id"]: row["unread_count"] for row in unread_rows}


def _build_unread_notifications_map_by_sequence(vendor, sequence_codes):
    """
    Build sequence_code -> unread user message count in one query.
    """
    if not sequence_codes:
        return {}

    unread_rows = (
        ChatMessage.objects
        .filter(
            vendor=vendor,
            sequence_code__in=sequence_codes,
            sender="user",
            is_read=False,
        )
        .values("sequence_code")
        .annotate(unread_count=Count("id"))
    )
    return {row["sequence_code"]: row["unread_count"] for row in unread_rows}


def _booking_list_serializer_context(request, unread_map):
    """Shared context for Dine Flash manager list APIs (skips per-row tracking URLs)."""
    ctx = {"request": request, "unread_notifications_map": unread_map}
    if project_name in ("dine_flash", "hospital_flash"):
        ctx["manager_list"] = True
    return ctx


def _dine_flash_requested_utility_filter(request):
    """
    Parse optional Dine Flash utility filters from query params.

    Supported params:
      - utility_id (preferred)
      - utility_code / display_code
    """
    params = getattr(request, "query_params", None) or {}
    raw_utility_id = (params.get("utility_id") or "").strip()
    raw_utility_code = (
        (params.get("utility_code") or params.get("display_code") or "").strip()
    )

    utility_id = None
    if raw_utility_id:
        try:
            utility_id = int(raw_utility_id)
        except (TypeError, ValueError):
            raise ValueError("utility_id must be a valid integer.")

    utility_code = raw_utility_code or None
    return utility_id, utility_code


def _dine_flash_bookings_queryset(vendor, start_dt, end_dt, utility_id=None, utility_code=None):
    """Lean queryset for outlet-manager booking lists (Dine Flash only)."""
    filters = {
        "vendor_id": vendor.pk,
        "created_at__range": (start_dt, end_dt),
    }
    if utility_id is not None:
        filters["utility_id"] = utility_id

    qs = (
        Order.objects.filter(**filters)
        .select_related("utility")
        .only(
            "id",
            "table_booking_no",
            "customer_name",
            "phone_number",
            "no_of_packs",
            "remarks",
            "status",
            "created_at",
            "seat_no",
            "utility_id",
            "utility__id",
            "utility__display_name",
            "utility__display_code",
            "call_count",
        )
    )
    if utility_code:
        qs = qs.filter(utility__display_code__iexact=utility_code)
    if utility_id is not None or utility_code:
        return qs.order_by("created_at")
    return qs.order_by("utility__display_name", "created_at")


def _group_serialized_bookings(booking_list, serialized):
    grouped = {}
    for booking, item in zip(booking_list, serialized):
        utility = booking.utility
        code = utility.display_code if utility else "Unassigned"

        if code not in grouped:
            grouped[code] = {"unread": 0, "bookings": []}

        grouped[code]["bookings"].append(item)

        if item.get("new_notifications", 0) > 0:
            grouped[code]["unread"] += 1
    return grouped


def _log_slow_manager_api(endpoint, started_at, threshold_ms=800, **segments):
    total_ms = int((time.perf_counter() - started_at) * 1000)
    if total_ms < threshold_ms:
        return
    segment_parts = []
    for key, value in segments.items():
        if key in {"count"}:
            segment_parts.append(f"{key}={int(value)}")
        else:
            segment_parts.append(f"{key}_ms={int(value)}")
    segment_str = " ".join(segment_parts)
    logger.warning(
        "[perf] endpoint=%s total_ms=%s %s",
        endpoint,
        total_ms,
        segment_str,
    )


def _send_manager_message_push_async(order, vendor, payload, chat_message_id):
    """
    Send manager chat push in background so API responses do not block on slow push endpoints.
    """
    try:
        close_old_connections()
        push_errors = notify_web_push(order, vendor, payload)
        if push_errors:
            logger.warning(
                "❌ Async web push failed for booking %s | errors=%s",
                getattr(order, "id", None),
                push_errors,
            )
            ChatMessage.objects.filter(id=chat_message_id).update(is_send=False)
    except Exception:
        logger.exception(
            "❌ Async web push exception for booking %s",
            getattr(order, "id", None),
        )
        ChatMessage.objects.filter(id=chat_message_id).update(is_send=False)
    finally:
        close_old_connections()

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
    vendor = _resolve_vendor_for_manager(request)
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
    vendor = _resolve_vendor_for_manager(request)  # existing helper
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
    # 3b. Duplicate Booking Check (5-minute window)
    # ------------------------------
    time_threshold = timezone.now() - timedelta(minutes=5)
    duplicate_query = Order.objects.filter(
        vendor=vendor,
        customer_name__iexact=customer_name,
        no_of_packs=no_of_guests,
        created_at__gte=time_threshold
    )
    if utility:
        duplicate_query = duplicate_query.filter(utility=utility)
    
    if phone_number:
        duplicate_query = duplicate_query.filter(phone_number=phone_number)
    else:
        duplicate_query = duplicate_query.filter(phone_number__isnull=True)

    existing_order = duplicate_query.first()
    if existing_order:
        logger.info("[book_table] Duplicate booking detected | token=%s", existing_order.token_no)
        
        try:
            tracking_path = reverse("orders:home")
            tracking_url = request.build_absolute_uri(
                f"{tracking_path}?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}"
                f"&booking_no={existing_order.table_booking_no}&booking_id={existing_order.id}"
            )
        except Exception:
            tracking_url = request.build_absolute_uri(
                f"/{project_name}/home/?location_id={vendor.location_id}"
                f"&vendor_id={vendor.vendor_id}&booking_no={existing_order.table_booking_no}&booking_id={existing_order.id}"
            )

        resp_data = {
            "id": existing_order.id,
            "token_no": existing_order.token_no,
            "table_booking_no": existing_order.table_booking_no,
            "tracking_url": tracking_url,
            "message": "Duplicate booking detected. Returning existing ticket.",
        }
        encrypted_tracking_url = _dine_flash_book_table_encrypted_tracking_url(
            vendor, existing_order, request
        )
        if encrypted_tracking_url is not None:
            resp_data["encrypted_tracking_url"] = encrypted_tracking_url
        return Response(resp_data, status=status.HTTP_200_OK)


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
                "name": (vendor.alias_name or "").strip() or vendor.name,
                "location_id": vendor.location_id,
                "device": None,
                "no_of_packs": no_of_guests,
                "customer_name": customer_name,
                "remarks": special_notes,
                "phone_number": phone_number,
                "utility": utility.id if utility else None,
                # "current_utility": utility.id if utility else None,
                "manager_id": manager_id,
            }

            serializer = OrdersSerializer(data=new_booking_data)
            if serializer.is_valid():
                booking_obj = serializer.save()

                # Build tracking URL via reverse to avoid hardcoded paths

                try:
                    tracking_path = reverse("orders:home")
                    tracking_url = request.build_absolute_uri(
                        f"{tracking_path}?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}"
                        f"&booking_no={booking_no}&booking_id={booking_obj.id}"
                    )
                except Exception:
                    tracking_url = request.build_absolute_uri(
                        f"/{project_name}/home/?location_id={vendor.location_id}"
                        f"&vendor_id={vendor.vendor_id}&booking_no={booking_no}&booking_id={booking_obj.id}"
                    )

                resp_data = {
                    "id": booking_obj.id,
                    "token_no": booking_obj.token_no,
                    "table_booking_no": booking_obj.table_booking_no,
                    "tracking_url": tracking_url,
                    "message": "Booking created successfully.",
                }
                encrypted_tracking_url = _dine_flash_book_table_encrypted_tracking_url(
                    vendor_locked, booking_obj, request
                )
                if encrypted_tracking_url is not None:
                    resp_data["encrypted_tracking_url"] = encrypted_tracking_url

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

# === Dine Flash API ===
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def manager_utility_list(request):
    """
    Returns active utilities for the vendor associated with the logged-in manager.

    Dine Flash fast-path (only when PROJECT_NAME == "dine_flash"):
      - Vendor lookup avoids loading VendorConfig (we don't need it here).
      - Result is served from a process-local cache that is invalidated by
        Utility post_save/post_delete signals.
      Other flavours retain the original behaviour exactly.
    """

    started_at = time.perf_counter()
    try:
        # --------------------------------------------------------
        # Dine Flash: lightweight vendor lookup + cached utilities
        # --------------------------------------------------------
        if project_name == "dine_flash":
            handler_started = time.perf_counter()
            ensure_request_trace(request)
            log_trace_phase(request, "handler_start", endpoint="manager_utility_list")

            t0 = time.perf_counter()
            vendor_brief = get_dine_flash_manager_vendor_brief(request.user)
            if not vendor_brief:
                raise NotFound("Vendor not found for this manager")
            vendor_pk = vendor_brief["vendor_id"]
            vendor_external_id = vendor_brief["vendor_external_id"]
            t_vendor_ms = (time.perf_counter() - t0) * 1000

            t1 = time.perf_counter()
            cached = _get_cached_dine_flash_utilities(vendor_pk)
            if cached is not None:
                data = cached
                cache_status = "hit"
            else:
                data = list(
                    Utility.objects.filter(vendor_id=vendor_pk, is_active=True)
                    .order_by("id")
                    .values(
                        "id",
                        "utility_name",
                        "display_name",
                        "display_code",
                        "token_mode",
                        "prefix",
                    )
                )
                _set_cached_dine_flash_utilities(vendor_pk, data)
                cache_status = "miss"
            t_query_ms = (time.perf_counter() - t1) * 1000

            record_handler_timing(
                request,
                "manager_utility_list",
                handler_started,
                vendor=t_vendor_ms,
                query=t_query_ms,
                cache=cache_status,
                count=len(data),
                vendor_external_id=vendor_external_id,
            )
            logger.info(
                "[manager_utility_list] Returned %s utilities for vendor_id=%s cache=%s "
                "vendor_ms=%s query_ms=%s handler_ms=%s",
                len(data),
                vendor_external_id,
                cache_status,
                int(t_vendor_ms),
                int(t_query_ms),
                int((time.perf_counter() - handler_started) * 1000),
            )
            _log_slow_manager_api(
                "manager_utility_list",
                started_at,
                vendor=t_vendor_ms,
                query=t_query_ms,
                count=len(data),
            )

            return Response(
                {
                    "utilities": data,
                    "count": len(data),
                },
                status=status.HTTP_200_OK,
            )

        # --------------------------------------------------------
        # Other flavours: unchanged behaviour
        # --------------------------------------------------------
        t0 = time.perf_counter()
        vendor = _resolve_vendor_for_manager(request)
        t_vendor_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        utilities = Utility.objects.filter(
            vendor=vendor,
            is_active=True,
        ).order_by("id")
        data = [
            {
                "id": util.id,
                "utility_name": util.utility_name,
                "display_name": util.display_name,
                "display_code": util.display_code,
                "token_mode": util.token_mode,
                "prefix": util.prefix,
            }
            for util in utilities
        ]
        t_query_ms = (time.perf_counter() - t1) * 1000

        logger.info(
            "[manager_utility_list] Returned %s utilities for vendor_id=%s",
            len(data), vendor.vendor_id
        )
        _log_slow_manager_api(
            "manager_utility_list",
            started_at,
            vendor=t_vendor_ms,
            query=t_query_ms,
            count=len(data),
        )

        return Response(
            {
                "utilities": data,
                "count": len(data),
            },
            status=status.HTTP_200_OK
        )

    except NotFound as nf:
        logger.warning("[manager_utility_list] Vendor not found | %s", nf)
        return Response(
            {"error": "Vendor not associated with this manager."},
            status=status.HTTP_404_NOT_FOUND,
        )

    except Exception as e:
        logger.exception("[manager_utility_list] Unexpected error. %s", e)
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_today_orders(request):
    """
    API endpoint: Retrieve all orders for today for the manager's vendor.
    - Returns order details only.
    """

    started_at = time.perf_counter()
    try:
        # === Step 1: Request start log ===
        logger.info(
            "[get_today_orders] Request started | user=%s | method=%s | path=%s",
            request.user.username, request.method, request.path
        )

        # === Step 2: Resolve vendor for the logged-in manager ===
        t0 = time.perf_counter()
        vendor = _resolve_vendor_for_manager(request)
        t_vendor_ms = (time.perf_counter() - t0) * 1000
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
        t1 = time.perf_counter()
        todays_orders = (
            Order.objects.filter(
                vendor=vendor,
                created_at__range=(start_dt, end_dt),
            )
            .select_related("vendor")
            .order_by("-updated_at")
        )
        order_list = list(todays_orders)
        t_query_ms = (time.perf_counter() - t1) * 1000
        logger.info(
            "[get_today_orders] Fetched orders | vendor_id=%s | count=%s",
            vendor.id, len(order_list)
        )

        # === Step 5: Serialize orders ===
        t2 = time.perf_counter()
        unread_map = (
            _build_unread_notifications_map(vendor, [order.id for order in order_list])
            if project_name in {"dine_flash", "dine_flash_buffet"}
            else None
        )
        serializer_context = {"request": request}
        if unread_map is not None:
            serializer_context["unread_notifications_map"] = unread_map
        data = OrdersSerializer(order_list, many=True, context=serializer_context).data
        t_serialize_ms = (time.perf_counter() - t2) * 1000
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
        status_counts = get_order_counts(order_list, data)
        _log_slow_manager_api(
            "get_today_orders",
            started_at,
            vendor=t_vendor_ms,
            query=t_query_ms,
            serialize=t_serialize_ms,
            count=len(data),
        )
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

        vendor = _resolve_vendor_for_manager(request)
        logger.info(
            "[get_passengers_list] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )

        passengers_qs = (
            Order.objects.filter(vendor=vendor)
            .select_related("vendor")
            .order_by('flight_no', 'zone', 'seat_no')
        )
        passenger_list = list(passengers_qs)
        logger.info(
            "[get_passengers_list] Fetched passengers | vendor_id=%s | count=%s",
            vendor.id, len(passenger_list)
        )

        unread_map = _build_unread_notifications_map_by_sequence(
            vendor,
            [p.sequence_code for p in passenger_list if p.sequence_code],
        )
        serialized_data = OrdersSerializer(
            passenger_list,
            many=True,
            context={
                "request": request,
                "unread_notifications_map_by_sequence": unread_map,
            },
        ).data
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
        status_counts = get_passenger_counts(passenger_list, serialized_data)

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

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_booking_list(request):
    started_at = time.perf_counter()

    # Dine Flash outlet manager: cached vendor, lean query, fast serialization.
    if project_name == "dine_flash":
        try:
            handler_started = time.perf_counter()
            ensure_request_trace(request)
            log_trace_phase(request, "handler_start", endpoint="get_booking_list")

            t0 = time.perf_counter()
            vendor = get_cached_manager_vendor(request.user)
            if not vendor:
                raise NotFound("Vendor not found for this manager")
            t_vendor_ms = (time.perf_counter() - t0) * 1000

            try:
                utility_id_filter, utility_code_filter = _dine_flash_requested_utility_filter(request)
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            start_dt, end_dt = get_vendor_business_day_range(vendor)
            if not start_dt or not end_dt:
                return Response({"error": "Invalid date range"}, status=400)

            t1 = time.perf_counter()
            booking_list = list(
                _dine_flash_bookings_queryset(
                    vendor,
                    start_dt,
                    end_dt,
                    utility_id=utility_id_filter,
                    utility_code=utility_code_filter,
                )
            )
            t_query_ms = (time.perf_counter() - t1) * 1000
            total_count = len(booking_list)

            t2 = time.perf_counter()
            unread_map = _build_unread_notifications_map(
                vendor, [booking.id for booking in booking_list]
            )
            serialized = serialize_dine_flash_manager_bookings(
                booking_list, unread_map, vendor=vendor, request=request
            )
            t_serialize_ms = (time.perf_counter() - t2) * 1000

            grouped = _group_serialized_bookings(booking_list, serialized)
            status_counts = get_booking_status_counts(booking_list, serialized)

            utility_filter = utility_id_filter if utility_id_filter is not None else utility_code_filter
            record_handler_timing(
                request,
                "get_booking_list",
                handler_started,
                vendor=t_vendor_ms,
                query=t_query_ms,
                serialize=t_serialize_ms,
                count=total_count,
                utility_filter=utility_filter or "all",
            )
            logger.info(
                "[get_booking_list] dine_flash count=%s utility_filter=%s "
                "vendor_ms=%s query_ms=%s serialize_ms=%s handler_ms=%s",
                total_count,
                utility_filter or "all",
                int(t_vendor_ms),
                int(t_query_ms),
                int(t_serialize_ms),
                int((time.perf_counter() - handler_started) * 1000),
            )
            _log_slow_manager_api(
                "get_booking_list",
                started_at,
                vendor=t_vendor_ms,
                query=t_query_ms,
                serialize=t_serialize_ms,
                count=total_count,
            )

            return Response(
                {
                    "message": "Bookings retrieved successfully.",
                    "count": total_count,
                    "detail": grouped,
                    "status_counts": status_counts,
                },
                status=status.HTTP_200_OK,
            )

        except NotFound:
            return Response(
                {"error": "Vendor not associated with this manager."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("get_booking_list: Unexpected error (dine_flash)")
            return Response(
                {"error": "Internal server error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    if project_name == "hospital_flash":
        try:
            vendor = _resolve_vendor_for_manager(request)
            user_profile = request.user.profile_roles.first()
            if not user_profile:
                return Response({"error": "User profile not found."}, status=status.HTTP_403_FORBIDDEN)

            start_dt, end_dt = get_vendor_business_day_range(vendor)
            if not start_dt or not end_dt:
                return Response({"error": "Invalid date range"}, status=400)

            bookings_qs = (
                Order.objects.filter(vendor=vendor, created_at__range=(start_dt, end_dt))
                .select_related("utility", "vendor")
                .order_by("utility__display_name", "created_at")
            )
            # Hospital utility_user: fail closed when unassigned (empty list → no orders).
            # Package/group assignments expand to their individual departments.
            if user_profile.role == "utility_user":
                assigned_utilities = user_profile.assigned_utilities.all()
                if not assigned_utilities.exists():
                    bookings_qs = bookings_qs.none()
                else:
                    effective_departments = resolve_hospital_effective_departments(
                        assigned_utilities
                    )
                    if not effective_departments:
                        bookings_qs = bookings_qs.none()
                    else:
                        bookings_qs = bookings_qs.filter(utility__in=effective_departments)

            booking_list = list(bookings_qs)
            unread_map = _build_unread_notifications_map(vendor, [booking.id for booking in booking_list])
            serialized = BookingSerializer(
                booking_list,
                many=True,
                context=_booking_list_serializer_context(request, unread_map),
            ).data
            grouped = _group_serialized_bookings(booking_list, serialized)

            return Response(
                {
                    "message": "Patients retrieved successfully.",
                    "count": len(booking_list),
                    "detail": grouped,
                },
                status=status.HTTP_200_OK,
            )
        except NotFound:
            return Response(
                {"error": "Vendor not associated with this manager."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception:
            logger.exception("get_booking_list: Unexpected error (hospital_flash)")
            return Response(
                {"error": "Internal server error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    logger.info("🔵 get_booking_list: API called.")

    try:
        t0 = time.perf_counter()
        vendor = _resolve_vendor_for_manager(request)
        t_vendor_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"get_booking_list: Resolved vendor → ID: {vendor.id}, Name: {vendor.name}")

        start_dt, end_dt = get_vendor_business_day_range(vendor)
        if not start_dt or not end_dt:
            logger.warning("Invalid date range for vendor_id=%s", vendor.id)
            return Response({"error": "Invalid date range"}, status=400)

        logger.info(f"get_booking_list: Business day range → Start: {start_dt}, End: {end_dt}")

        t1 = time.perf_counter()
        bookings_qs = (
            Order.objects
            .filter(vendor=vendor, created_at__range=(start_dt, end_dt))
            .select_related("utility", "vendor")
            .order_by("utility__display_name", "created_at")
        )

        booking_list = list(bookings_qs)
        t_query_ms = (time.perf_counter() - t1) * 1000
        total_count = len(booking_list)
        logger.info(f"get_booking_list: Retrieved {total_count} bookings")

        t2 = time.perf_counter()
        unread_map = _build_unread_notifications_map(vendor, [booking.id for booking in booking_list])

        serialized = BookingSerializer(
            booking_list,
            many=True,
            context=_booking_list_serializer_context(request, unread_map),
        ).data
        t_serialize_ms = (time.perf_counter() - t2) * 1000

        grouped = _group_serialized_bookings(booking_list, serialized)
        status_counts = get_booking_status_counts(bookings_qs, serialized)
        _log_slow_manager_api(
            "get_booking_list",
            started_at,
            vendor=t_vendor_ms,
            query=t_query_ms,
            serialize=t_serialize_ms,
            count=total_count,
        )

        logger.info("get_booking_list: Returning success response.")

        return Response(
            {
                "message": "Bookings retrieved successfully.",
                "count": total_count,
                "detail": grouped,
                "status_counts": status_counts,
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.exception("get_booking_list: Unexpected error")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_allocated_booking_list(request):
    """
    Dine Flash only: list allocated bookings for the current business day.
    """
    if project_name != "dine_flash":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    logger.info("get_allocated_booking_list: API called.")
    incoming_vendor_id = (
        request.query_params.get("vendor_id")
        or request.headers.get("X-Vendor-Id")
        or request.COOKIES.get("vendor_id")
    )
    logger.info("[TV_DEBUG] incoming vendor_id=%s", incoming_vendor_id)

    try:
        if request.user and request.user.is_authenticated:
            vendor = _resolve_vendor_for_manager(request)
        else:
            vendor_id = (
                request.query_params.get("vendor_id")
                or request.headers.get("X-Vendor-Id")
                or request.COOKIES.get("vendor_id")
            )
            if not vendor_id:
                return Response(
                    {"error": "vendor_id is required for public access."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                vendor = Vendor.objects.select_related("config").get(
                    vendor_id=int(vendor_id)
                )
            except (ValueError, Vendor.DoesNotExist):
                return Response(
                    {"error": "Invalid vendor_id."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        logger.info(
            "get_allocated_booking_list: Resolved vendor -> ID: %s, Name: %s",
            vendor.id,
            vendor.name,
        )

        start_dt, end_dt = get_vendor_business_day_range(vendor)
        if not start_dt or not end_dt:
            logger.warning("Invalid date range for vendor_id=%s", vendor.id)
            return Response({"error": "Invalid date range"}, status=status.HTTP_400_BAD_REQUEST)

        bookings_qs = (
            Order.objects.filter(
                vendor=vendor,
                status="allocated",
                created_at__range=(start_dt, end_dt),
            )
            .select_related("utility", "vendor")
            .order_by("utility__display_name", "created_at")
        )

        booking_list = list(bookings_qs)
        total_count = len(booking_list)
        logger.debug(
            "[TV_DEBUG] allocated queryset count=%s vendor_id=%s",
            total_count,
            vendor.vendor_id,
        )
        booking_ids = [booking.id for booking in booking_list]
        unread_map = _build_unread_notifications_map(vendor, booking_ids)
        serialized = BookingSerializer(
            booking_list,
            many=True,
            context=_booking_list_serializer_context(request, unread_map),
        ).data
        allocated_time_map = {
            row["order_id"]: row["allocated_time"]
            for row in (
                OrderStatusHistory.objects.filter(
                    order_id__in=booking_ids,
                    new_status="allocated",
                )
                .values("order_id")
                .annotate(allocated_time=Max("changed_at"))
            )
        }

        grouped = {}
        for booking, item in zip(booking_list, serialized):
            utility = booking.utility
            code = utility.display_code if utility else "Unassigned"
            booked_time = item.pop("booked_time", None)
            item["allocated_time"] = allocated_time_map.get(booking.id) or booked_time
            table_no = item.get("table_no")
            booking_no = item.get("table_booking_no")
            if booking_no is not None and table_no is not None:
                table_no_text = str(table_no).strip()
                if table_no_text:
                    item["table_booking_no"] = f"{booking_no}[{table_no_text}]"

            if code not in grouped:
                grouped[code] = {"unread": 0, "bookings": []}

            grouped[code]["bookings"].append(item)
            if item.get("new_notifications", 0) > 0:
                grouped[code]["unread"] += 1

        logger.info(
            "[TV_DEBUG] response count=%s vendor_id=%s",
            total_count,
            vendor.vendor_id,
        )
        return Response(
            {
                "message": "Allocated bookings retrieved successfully.",
                "count": total_count,
                "detail": grouped,
            },
            status=status.HTTP_200_OK,
        )

    except Exception:
        logger.exception("get_allocated_booking_list: Unexpected error")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_customers_list(request):
    
    started_at = time.perf_counter()
    try:
        logger.info(
            "[get_active_customers_list] Request started | user=%s | method=%s | path=%s",
            request.user.username, request.method, request.path
        )

        t0 = time.perf_counter()
        if project_name == "dine_flash":
            vendor = get_cached_manager_vendor(request.user)
            if not vendor:
                raise NotFound("Vendor not found for this manager")
        else:
            vendor = _resolve_vendor_for_manager(request)
        t_vendor_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[get_active_customers_list] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )

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

        t1 = time.perf_counter()
        if project_name == "dine_flash":
            try:
                utility_id_filter, utility_code_filter = _dine_flash_requested_utility_filter(request)
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            business_date = get_vendor_current_date(vendor)
            active_booking_ids = list(
                ChatMessage.objects.filter(
                    vendor_id=vendor.id,
                    booking_id__isnull=False,
                    created_date=business_date,
                )
                .values_list("booking_id", flat=True)
                .distinct()
            )
            if active_booking_ids:
                customer_list = list(
                    _dine_flash_bookings_queryset(
                        vendor,
                        start_dt,
                        end_dt,
                        utility_id=utility_id_filter,
                        utility_code=utility_code_filter,
                    ).filter(
                        id__in=active_booking_ids
                    )
                )
            else:
                customer_list = []
        else:
            has_chat_message = ChatMessage.objects.filter(
                vendor_id=vendor.id,
                booking_id=OuterRef("pk"),
            )
            customers_qs = (
                Order.objects.filter(vendor=vendor, created_at__range=(start_dt, end_dt))
                .filter(Exists(has_chat_message))
                .select_related("utility", "vendor")
                .order_by("utility__display_name", "created_at")
            )
            customer_list = list(customers_qs)
        t_query_ms = (time.perf_counter() - t1) * 1000
        total_count = len(customer_list)

        logger.info(
            "[get_active_customers_list] Fetched passengers | vendor_id=%s | count=%s",
            vendor.id, total_count
        )

        t2 = time.perf_counter()
        unread_map = _build_unread_notifications_map(vendor, [customer.id for customer in customer_list])
        if project_name == "dine_flash":
            serialized_data = serialize_dine_flash_manager_bookings(customer_list, unread_map)
        else:
            serialized_data = BookingSerializer(
                customer_list,
                many=True,
                context=_booking_list_serializer_context(request, unread_map),
            ).data
        t_serialize_ms = (time.perf_counter() - t2) * 1000
        logger.debug(
            "[get_active_customers_list] Serialized passengers | count=%s", len(serialized_data)
        )

        grouped_data = _group_serialized_bookings(customer_list, serialized_data)

        status_counts = get_booking_status_counts(customer_list, serialized_data)
        _log_slow_manager_api(
            "get_active_customers_list",
            started_at,
            vendor=t_vendor_ms,
            query=t_query_ms,
            serialize=t_serialize_ms,
            count=total_count,
        )

        logger.info("get_booking_list: Returning success response.")

        return Response(
            {
                "message": "Customers retrieved successfully.",
                "count": total_count,
                "detail": grouped_data,
                "status_counts": status_counts,
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.exception(
            "[get_active_customers_list] Unexpected error | user=%s | error=%s",
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

        vendor = _resolve_vendor_for_manager(request)
        logger.info(
            "[get_active_passengers_list] Vendor resolved | vendor_id=%s | vendor_name=%s | user=%s",
            vendor.id, vendor.name, request.user.username
        )
        active_chat_sequences = (
            ChatMessage.objects
            .filter(vendor=vendor)
            .values_list("sequence_code", flat=True)
            .distinct()
        )
        passengers_qs = (
            Order.objects.filter(vendor=vendor)
            .filter(sequence_code__in=active_chat_sequences)
            .select_related("vendor")
            .order_by('flight_no', 'zone', 'seat_no')
        )
        passenger_list = list(passengers_qs)
        logger.info(
            "[get_active_passengers_list] Fetched passengers | vendor_id=%s | count=%s",
            vendor.id, len(passenger_list)
        )

        unread_map = _build_unread_notifications_map_by_sequence(
            vendor,
            [p.sequence_code for p in passenger_list if p.sequence_code],
        )
        serialized_data = OrdersSerializer(
            passenger_list,
            many=True,
            context={
                "request": request,
                "unread_notifications_map_by_sequence": unread_map,
            },
        ).data
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
        status_counts = get_passenger_counts(passenger_list, serialized_data)

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
        vendor = _resolve_vendor_for_manager(request)
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
        is_buffet_project = project_name == "dine_flash_buffet"
        if is_buffet_project:
            buffet_alias = (vendor.alias_name or "").strip() or vendor.name
            status_push_type = "buffet_item_ready"
            manager_push_type = "buffet_manager"
        else:
            buffet_alias = vendor.alias_name
            status_push_type = "foodstatus"
            manager_push_type = "manager"

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
            'alias_name': buffet_alias,
            "vendor_id": vendor.vendor_id,
            "location_id": vendor.location_id,
            "logo_url": logo_url,
            "type": status_push_type if action_type in ["ready", "delivered", "cancelled"] else manager_push_type,
            "message_id": None,
            "vibration_pattern":vendor.config.vibration_pattern,
            "vibration_duration":vendor.config.vibration_duration
        }
        if is_buffet_project:
            payload["booking_id"] = order.id

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
            chat_message_kwargs = {
                "vendor": vendor,
                "token_no": token_no,
                "created_date": get_vendor_current_time(vendor).date(),
                "sender": "manager",
                "is_send": True,
                "message_text": status_to_update,
            }
            if is_buffet_project:
                chat_message_kwargs["booking_id"] = order.id
                chat_message_kwargs["booking_no"] = order.table_booking_no
            chat_message = ChatMessage.objects.create(**chat_message_kwargs)
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

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def manager_booking_update(request):
    if project_name == "hospital_flash":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    try:
        logger.debug("Request data: %s", request.data)

        data = request.data
        # Validate required fields
        required_fields = ['booking_id', 'status', 'action', 'utility_id']
        missing = [f for f in required_fields if f not in data or data[f] in [None, ""]]

        # === Step 1: Validate required fields ===
        if missing:
            logger.warning("⛔ Missing fields: %s", ', '.join(missing))
            return Response(
                {"message": f"Missing fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # === Step 2: Validate booking_id ===
        try:
            booking_id = int(data['booking_id'])
        except (TypeError, ValueError):
            logger.warning("❌ booking_id must be a valid integer | value=%s", data['booking_id'])
            return Response({"message": "booking_id must be a valid integer."}, status=status.HTTP_400_BAD_REQUEST)

        status_to_update = data['status']
        action = request.data.get("action", "").lower()

        # === Step 3: Validate action type ===
        allowed_actions = ["allocated", "occupied", "operation_closed", "booking_cancelled", "message",
                           "utility_transfer"]
        if project_name == "dine_flash":
            allowed_actions.append("call")

        if action not in allowed_actions:
            return Response({"message": "Invalid action type."}, status=status.HTTP_400_BAD_REQUEST)
        
        action_type = action

        # === Step 4: Validate manager & vendor ===
        manager_qs = getattr(request.user, 'profile_roles', None)
        if not manager_qs or not manager_qs.exists():
            logger.warning("⚠️ No manager profile found for user=%s", request.user.username)
            return Response({"message": "User is not a manager."}, status=status.HTTP_403_FORBIDDEN)
        manager = manager_qs.first()
        if not manager.vendor:
            logger.warning("⚠️ Manager %s has no vendor", manager.name)
            return Response({"message": "Manager does not have an associated vendor."}, status=status.HTTP_403_FORBIDDEN)

        vendor = manager.vendor
        logger.info("🔧 Manager: %s | Vendor: %s (%s)", manager.name, vendor.name, vendor.vendor_id)

        # === Step 5: Get today's business day range & booking ===
        start_dt, end_dt = get_vendor_business_day_range(vendor)
        if not start_dt or not end_dt:
            logger.warning("Invalid date range for vendor_id=%s", vendor.id)
            return Response({"error": "Invalid date range"}, status=400)

        booking = Order.objects.filter(id=booking_id, vendor=vendor, created_at__range=(start_dt, end_dt)).first()
        if not booking:
            logger.warning("❌ No booking found for booking_id=%s today.", booking_id)
            return Response({"message": f"Booking with booking_id {booking_id} not found."}, status=status.HTTP_404_NOT_FOUND)
        previous_booking_status = (booking.status or "").strip().lower()

        # === Step 5: Serialize vendor logo (unchanged) ===
        vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
        logo_url = vendor_serializer.data.get("logo_url", "")
        if not logo_url:
            logger.warning("⚠️ No logo URL for vendor %s", vendor.name)
            return Response({"message": "Vendor logo not found."}, status=status.HTTP_404_NOT_FOUND)

        booking_no = booking.table_booking_no
        utility_display = booking.utility.display_name if booking.utility else "-"
        # === Step 6: Prepare base push payload (unchanged) ===
        payload = {
            "title": "Booking Update by Manager",
            "body": f"Your Booking {booking_no} status: {status_to_update}" if action_type == "allocated"
                    else f"Your Booking {booking_no} has an update from the manager." if action_type == "message"
                    else f"Your Booking {booking_no} has been marked occupied." if action_type == "occupied"
                    else f"Your Booking {booking_no} operation has been closed." if action_type == "operation_closed"
                    else f"Your Booking {booking_no} has been transferred." if action_type == "utility_transfer"
                    else f"Your Booking {booking_no} has been cancelled.",
            "token_no": booking.token_no,
            "status": status_to_update.lower(),
            "counter_no": booking.counter_no,
            "name": (vendor.alias_name or "").strip() or vendor.name,
            "alias_name": vendor.alias_name,
            "vendor_id": vendor.vendor_id,
            "location_id": vendor.location_id,
            "logo_url": logo_url,
            "type": "dinestatus" if action_type in ["allocated", "occupied", "operation_closed", "booking_cancelled"] else "dine_manager",
            "message_id": None,
            "booking_id": booking_id,
            "booking_no": booking_no,
            "customer_name": booking.customer_name,
            "no_of_packs": booking.no_of_packs,
            "seat_no": booking.seat_no,
            "table_number": booking.seat_no,
            "utility_name": utility_display,
            "vibration_pattern": vendor.config.vibration_pattern,
            "vibration_duration": vendor.config.vibration_duration
        }

        android_tv_success, android_tv_info, mqtt_success, push_errors = None, None, None, []

        # -------------------------
        # === Step 7: Handle different action types ===
        # -------------------------
        # This will update booking.utility and run the normal notification / mqtt / tv flows.
        # -------------------------
        if action_type in ["allocated", "utility_transfer"]:
            utility_id = data['utility_id']

            # === Validate utility_id ===o
            try:
                utility_id = int(utility_id)
            except (TypeError, ValueError):
                logger.warning("❌ utility_id must be a valid integer | value=%s", data.get('utility_id'))
                return Response({"message": "utility_id must be a valid integer."}, status=status.HTTP_400_BAD_REQUEST)
            
            target_utility = Utility.objects.filter(id=utility_id).first()
            if not target_utility:
                logger.warning("❌ No utility found for utility_id %s.", utility_id)
                return Response({"message": f"Utility with utility_id {utility_id} not found."}, status=status.HTTP_404_NOT_FOUND)

            booking.utility = target_utility

            if "table_number" in data or "table_no" in data:
                raw_table = data.get("table_number")
                if raw_table is None:
                    raw_table = data.get("table_no")
                if raw_table is None:
                    booking.seat_no = None
                else:
                    s = str(raw_table).strip()
                    booking.seat_no = (s[:10] or None) if s else None

            # 🛡️ FIX: If it is a transfer, do not overwrite the DB with "utility_transfer" as a status.
            # Preserve the existing valid status (e.g., 'allocated' or 'occupied').
            if action_type == "utility_transfer":
                status_to_update = booking.status

            # Optionally update status if client provided a status that should apply
            updated_booking = update_booking_status_by_dinemanager(booking, status_to_update, manager)

            new_booking_status = (updated_booking.status or "").strip().lower()

            if action_type == "allocated":
                logger.info(
                    "[TV_ALLOCATED] saved booking_id=%s status=%s utility_id=%s table_no=%s vendor_id=%s",
                    booking_id,
                    updated_booking.status,
                    utility_id,
                    updated_booking.seat_no,
                    vendor.vendor_id,
                )

            logger.info("✅ Booking %s transferred to utility %s", booking_id, target_utility.display_name)

            seat_display = (
                (updated_booking.seat_no or "").strip()
                if isinstance(updated_booking.seat_no, str)
                else (updated_booking.seat_no or "")
            )
            payload["seat_no"] = updated_booking.seat_no

            # Update payload fields for notifications
            target_utility_name = target_utility.display_name
            payload["table_number"] = updated_booking.seat_no
            payload["utility_name"] = target_utility_name
            payload["status"] = "utility_transfer" if action_type == "utility_transfer" else booking.status
            payload["type"] = "dinestatus"

            tv_mode = str(getattr(vendor.config, "tv_communication_mode", "") or "").strip().upper()
            fcm_scope = dine_flash_fcm_scope_applies(vendor)
            logger.info(
                "[TV_FCM] allocate path booking_id=%s vendor_id=%s tv_mode=%s dine_flash_scope=%s",
                booking.id,
                vendor.vendor_id,
                tv_mode or "UNSET",
                fcm_scope,
            )

            # For Android TV (Firebase), push normalized booking payload.
            # Normalize comparison so values like "firebase"/" Firebase " are handled.
            if tv_mode == "FIREBASE":
                tv_payload = {
                    "action": action_type,
                    "status": payload["status"],
                    "booking_id": booking.id,
                    "booking_no": booking.table_booking_no,
                    "token_no": booking.token_no,
                    "vendor_id": vendor.vendor_id,
                    "location_id": vendor.location_id,
                    "utility_id": target_utility.id,
                    "table_number": booking.seat_no,
                    "utility_name": target_utility.display_name,
                    "customer_name": booking.customer_name,
                    "no_of_packs": booking.no_of_packs,
                    "seat_no": booking.seat_no,
                }
                if fcm_scope:
                    schedule_dine_flash_manager_booking_tv_fcm(
                        vendor.id,
                        booking.id,
                        new_booking_status or status_to_update,
                        extra=tv_payload,
                    )
                    android_tv_success = True
                    android_tv_info = {"queued": True}
                else:
                    android_tv_success, android_tv_info = notify_android_tv(vendor, tv_payload)
                logger.info(
                    "[TV_FCM] allocate result action=%s booking_id=%s success=%s info=%s",
                    action_type,
                    booking.id,
                    android_tv_success,
                    android_tv_info,
                )
            else:
                android_tv_success = False
                android_tv_info = {"skipped": f"TV notification skipped: mode is {tv_mode or 'UNSET'}"}
                logger.info(
                    "[TV_FCM] allocate skipped booking_id=%s vendor_id=%s reason=%s",
                    booking.id,
                    vendor.vendor_id,
                    android_tv_info.get("skipped"),
                )

            # If MQTT mode, ensure vendor has mqtt config and send update
            if tv_mode == "MQTT":
                logger.info(f"📡 Sending MQTT update for vendor {vendor.vendor_id} with booking_id {booking_id}")
                if not hasattr(vendor, 'config') or not vendor.config.mqtt_mode:
                    logger.warning(f"⚠️ Vendor {vendor.vendor_id} has no MQTT configuration.")
                    return Response({"message": "Vendor has no MQTT configuration."}, status=status.HTTP_400_BAD_REQUEST)

                mqtt_success = send_order_update(vendor)
                if mqtt_success:
                    logger.info(f"✅ MQTT update sent successfully for vendor {vendor.vendor_id}")
                else:
                    logger.error(f"❌ Failed to send MQTT update for vendor {vendor.vendor_id}")
                    # we continue, but report failure

            # For Azure IoT
            if tv_mode == "AZURE_IOT":
                logger.info(f"[utility_transfer] Azure IoT communication mode detected for vendor {vendor.vendor_id}")
                azure_iot = get_azure_devices(vendor)
                logger.info(f"[utility_transfer] Azure IoT messages sent: {azure_iot}")

            # Web push: obey cooldown as in existing allocated flow
            cooldown = getattr(settings, "PUSH_COOLDOWN_SECONDS", 1)
            if not booking.notified_at or (timezone.now() - booking.notified_at) > timedelta(seconds=cooldown):
                if project_name == "dine_flash":
                    logger.info(
                        "[dine_flash] Sending web push | action=%s booking_id=%s status=%s type=%s",
                        action_type,
                        booking_id,
                        payload.get("status"),
                        payload.get("type"),
                    )
                else:
                    logger.info("📤 Sending web push for utility_transfer...")
                push_errors = notify_web_push(booking, vendor, payload)
                if project_name == "dine_flash":
                    logger.info(
                        "[dine_flash] Web push complete | action=%s booking_id=%s "
                        "success=%s errors=%s",
                        action_type,
                        booking_id,
                        not bool(push_errors),
                        push_errors or "none",
                    )
                booking.refresh_from_db()
                booking.notified_at = timezone.now()
                booking.save(update_fields=["notified_at"])
                logger.info("🕒 Booking %s marked as notified at %s", booking_id, booking.notified_at)
            else:
                if project_name == "dine_flash":
                    logger.info(
                        "[dine_flash] Web push skipped (cooldown) | action=%s booking_id=%s",
                        action_type,
                        booking_id,
                    )
                else:
                    logger.info("⏳ Cooldown active. Skipping web push for %s", booking_id)
        elif action_type == "occupied":
            logger.info("🔔 Occupied Booking %s by manager %s", booking_id, manager.name)
            status_to_update = "occupied"  # Enforce correct state
            payload["status"] = "occupied" # Enforce payload string
            updated_booking = update_booking_status_by_dinemanager(booking, status_to_update, manager)
            new_booking_status = (updated_booking.status or "").strip().lower()
            if should_notify_dine_flash_booking_status_transition(previous_booking_status, new_booking_status):
                schedule_dine_flash_booking_status_fcm(vendor.id, booking.id, new_booking_status)
            if updated_booking:
                payload["title"] = "Table Occupied"
                push_errors = notify_web_push(updated_booking, vendor, payload)
                updated_booking.refresh_from_db()
                updated_booking.notified_at = timezone.now()
                updated_booking.save(update_fields=["notified_at"])
                logger.info("🕒 Booking %s marked as notified at %s", booking_id, booking.notified_at)
        elif action_type  ==  "booking_cancelled":
            logger.info("🔔 %s Booking %s by manager %s", action_type.capitalize(), booking_id, manager.name)
            status_to_update = "booking_cancelled"  # Enforce correct state
            payload["status"] = "booking_cancelled" # Enforce payload string
            updated_booking = update_booking_status_by_dinemanager(booking, status_to_update,manager)
            new_booking_status = (updated_booking.status or "").strip().lower()
            if should_notify_dine_flash_booking_status_transition(previous_booking_status, new_booking_status):
                schedule_dine_flash_booking_status_fcm(vendor.id, booking.id, new_booking_status)
            if updated_booking:
                payload["title"] = f"Order {action_type.capitalize()}"
                push_errors = notify_web_push(updated_booking, vendor, payload)
                updated_booking.refresh_from_db()  # ✅ ensures latest status from DB
                updated_booking.notified_at = timezone.now()
                updated_booking.save(update_fields=["notified_at"])
                logger.info("🕒 Booking %s marked as notified at %s", booking_id, booking.notified_at)
        
        elif action_type == "operation_closed":
            logger.info("🔔 %s Booking %s by manager %s", action_type.capitalize(), booking_id, manager.name)
            status_to_update = "operation_closed"  # Enforce correct state
            payload["status"] = "operation_closed" # Enforce payload string
            updated_booking = update_booking_status_by_dinemanager(booking, status_to_update, manager)
            new_booking_status = (updated_booking.status or "").strip().lower()
            if should_notify_dine_flash_booking_status_transition(previous_booking_status, new_booking_status):
                schedule_dine_flash_booking_status_fcm(vendor.id, booking.id, new_booking_status)
            if updated_booking:
                if vendor.config:
                    payload['thank_you_note'] = vendor.config.closing_message
                payload["title"] = f"Operation Closed"
                payload['type'] = "thankyou"
                push_errors = notify_web_push(updated_booking, vendor, payload)
                updated_booking.refresh_from_db()  # ✅ ensures latest status from DB
                updated_booking.notified_at = timezone.now()
                updated_booking.save(update_fields=["notified_at"])
                logger.info("🕒 Booking %s marked as notified at %s", booking_id, booking.notified_at)

        elif action_type == "message":
            if project_name != "dine_flash":
                return Response(
                    {"message": "Manager message action is only supported for Dine Flash."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            MAX_MESSAGE_LENGTH = 200
            if status_to_update and len(status_to_update) > MAX_MESSAGE_LENGTH:
                return Response({"error": f"Message too long. Limit is {MAX_MESSAGE_LENGTH} characters."}, status=400)

            logger.info("ℹ️ Sending manager message via web push")
            chat_message = ChatMessage.objects.create(
                vendor=vendor,
                token_no=booking.token_no,
                booking_id = booking_id,
                booking_no = booking_no,
                created_date=get_vendor_current_time(vendor).date(),
                sender='manager',
                is_send=True,
                message_text=status_to_update
            )
            payload["message_id"] = chat_message.id
            payload["status"] = status_to_update
            threading.Thread(
                target=_send_manager_message_push_async,
                args=(booking, vendor, payload, chat_message.id),
                daemon=True,
            ).start()
            push_errors = []
            logger.info("📤 Manager message push queued asynchronously for booking %s", booking_id)

        elif action_type == "call":
            if project_name != "dine_flash":
                return Response({"message": "Invalid action type."}, status=status.HTTP_400_BAD_REQUEST)

            logger.info("📞 Call action for booking %s by manager %s", booking_id, manager.name)
            Order.objects.filter(pk=booking.pk).update(call_count=F("call_count") + 1)

        # === Step 8: Return final response ===
        return Response({
            "success": True,
            "message": "Booking status updated.",
            "booking_id": booking.id,
            "utility": booking.utility.display_name,
            "android_tv": android_tv_success,
            "android_tv_info": android_tv_info,
            "web_push": not push_errors,
            "web_push_info": push_errors,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("🔥 Unhandled exception in manager_booking_update | user=%s", request.user.username)
        return Response({"success": False, "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
    elif project_name in ("dine_flash", "hospital_flash"):
        booking_id  = request.GET.get('booking_id')
        if not booking_id:
            logger.warning("[chat_history] Missing booking_id parameter")
            return Response({"error": "booking_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        lookup_key = {"booking_id": booking_id}
        logger.info(f"[chat_history] Using booking_id={booking_id}")
        
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
    vendor = _resolve_vendor_for_manager(request)
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

    response = Response({"messages": serializer.data}, status=status.HTTP_200_OK)
    if project_name == "dine_flash":
        response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
    return response

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
        vendor = _resolve_vendor_for_manager(request)
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

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_contact_list(request):
    logger.info("📘 get_contact_list: API called.")

    started_at = time.perf_counter()
    try:
        # 1. Get vendor mapped with manager
        t0 = time.perf_counter()
        vendor = _resolve_vendor_for_manager(request)
        t_vendor_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"get_contact_list: Resolved vendor → ID: {vendor.id}, Name: {vendor.name}")

        # 2. BUSINESS DAY RANGE
        start_dt, end_dt = get_vendor_business_day_range(vendor)
        if not start_dt or not end_dt:
            logger.warning("Invalid date range for vendor_id=%s", vendor.id)
            return Response({"error": "Invalid date range"}, status=400)

        logger.info(f"get_contact_list: Business day → Start: {start_dt}, End: {end_dt}")

        # 3. Query only customers with phone numbers (single evaluation + vendor for serializer URLs)
        contacts_qs = (
            Order.objects
            .filter(
                vendor=vendor,
                created_at__range=(start_dt, end_dt),
                phone_number__isnull=False,
            )
            .exclude(phone_number="")
            .select_related("utility")
            .order_by("utility__display_name", "created_at")
        )

        t1 = time.perf_counter()
        orders = list(contacts_qs)
        t_query_ms = (time.perf_counter() - t1) * 1000
        total_count = len(orders)
        logger.info(f"get_contact_list: Retrieved {total_count} contacts")

        # 4–5. Build grouped payload in one pass (avoids count() + second full queryset scan)
        t2 = time.perf_counter()
        grouped = {}
        for order in orders:
            item = {
                "booking_id": order.id,
                "customer_name": order.customer_name,
                "booking_no": order.table_booking_no,
                "phone_number": order.phone_number,
            }
            code = order.utility.display_code if order.utility else "NA"
            if code not in grouped:
                grouped[code] = {"count": 0, "customers": []}
            grouped[code]["customers"].append(item)
            grouped[code]["count"] += 1
        t_build_ms = (time.perf_counter() - t2) * 1000

        _log_slow_manager_api(
            "get_contact_list",
            started_at,
            vendor=t_vendor_ms,
            query=t_query_ms,
            build=t_build_ms,
            count=total_count,
        )
        logger.info("get_contact_list: Success response prepared.")

        return Response(
            {
                "message": "Contacts retrieved successfully.",
                "count": total_count,
                "detail": grouped,
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.exception("get_contact_list: Unexpected error")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

        