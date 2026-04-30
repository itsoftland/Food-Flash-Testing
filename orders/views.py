import json
import threading

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime, timedelta
import secrets
from django.http import JsonResponse,HttpResponseBadRequest
from django.db import IntegrityError, transaction, close_old_connections
from django.views.decorators.cache import never_cache

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from vendors.models import (Order, Vendor, AdminOutlet, AndroidDevice,
                            AdvertisementProfileAssignment,
                            UserProfile,ChatMessage,
                            Utility, UtilityOption, BuffetOrderItem)
from vendors.serializers import OrdersSerializer

from .utils import send_to_managers
from static.utils.functions.queries import get_vendor
from static.utils.functions.utils import get_vendor_business_day_range
from manager.utils.utils import reset_counters_if_new_business_day

from .models import DineFlashQrSession
from .serializers import (
    AdminOutletSerializer,
    VendorLogoSerializer,
    VendorAdsSerializer,
    FeedbackSerializer,
    VendorMenuSerializer
)

import logging

logger = logging.getLogger(__name__)
base = getattr(settings, 'LOGIN_URL')
project_name = getattr(settings, "PROJECT_NAME", "calleron")


def _send_to_managers_async(vendor, data, title=None, body=None):
    """
    Fire-and-forget manager notification so customer-facing APIs do not block.
    """
    try:
        close_old_connections()
        send_to_managers(vendor, data, title, body)
    except Exception:
        logger.exception(
            "[check_status] Async send_to_managers failed | vendor_id=%s",
            getattr(vendor, "vendor_id", None),
        )
    finally:
        close_old_connections()


def _get_dine_flash_qr_expiry_minutes(vendor_id):
    """
    Dine Flash only: resolve QR expiry minutes from vendor configuration.
    Falls back to latest mapped TV config and then default 5.
    """
    try:
        vendor = Vendor.objects.select_related("config").filter(vendor_id=vendor_id).first()
        if vendor and getattr(vendor, "config", None):
            cfg_val = getattr(vendor.config, "qr_expiry_minutes", None)
            if cfg_val:
                return int(cfg_val)

        device = (
            AndroidDevice.objects.select_related("tv_config")
            .filter(vendor__vendor_id=vendor_id, tv_config__isnull=False)
            .order_by("-updated_at")
            .first()
        )
        if device and device.tv_config and getattr(device.tv_config, "qr_expiry_minutes", None):
            return int(device.tv_config.qr_expiry_minutes)
    except Exception:
        pass
    return 5


def _validate_dine_flash_qr_time(qr_date, qr_time, vendor_id):
    """
    Validate that the QR date+time represent a *current* QR within the configured window.
    Returns (ok: bool, error_msg: str|None).
    """
    if not qr_date or not qr_time:
        return False, "Invalid QR link. Date and time are required."

    try:
        naive = datetime.strptime(f"{qr_date} {qr_time}", "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False, "Invalid QR link. Date/time format is invalid."

    qr_dt = timezone.make_aware(naive, timezone.get_current_timezone())

    now_dt = timezone.localtime(timezone.now())

    expiry_min = max(1, _get_dine_flash_qr_expiry_minutes(vendor_id))
    max_age = timedelta(minutes=expiry_min)

    # Allow small client clock skew into the future.
    if qr_dt - now_dt > timedelta(seconds=30):
        return False, "Invalid QR link. QR time is not current."

    if now_dt - qr_dt > max_age:
        return False, "QR expired. Please scan the new QR code on the TV."

    return True, None


def _purge_stale_dine_flash_qr_sessions():
    """Best-effort trim so the table does not grow forever."""
    cutoff = timezone.now()
    stale_ids = list(
        DineFlashQrSession.objects.filter(expires_at__lt=cutoff).values_list("id", flat=True)[:400]
    )
    if stale_ids:
        DineFlashQrSession.objects.filter(id__in=stale_ids).delete()


def _create_dine_flash_qr_session(vendor_id: str, qr_dt: datetime, expiry_minutes: int):
    # Booking/session window starts at successful QR exchange (scan time),
    # not at QR generation time. QR freshness validation is still enforced
    # separately in _validate_dine_flash_qr_time.
    _purge_stale_dine_flash_qr_sessions()
    scan_dt = timezone.localtime(timezone.now())
    expires_at = scan_dt + timedelta(minutes=expiry_minutes)
    vid = int(vendor_id)

    for _ in range(6):
        token = secrets.token_urlsafe(24)
        try:
            DineFlashQrSession.objects.create(
                token=token,
                vendor_id=vid,
                expires_at=expires_at,
            )
            return token, int(expires_at.timestamp())
        except IntegrityError:
            continue

    raise RuntimeError("Unable to allocate Dine Flash qr_session token")


def _validate_dine_flash_qr_session(qr_session: str, vendor_id: str):
    if not qr_session:
        return False, "Invalid QR link."
    row = (
        DineFlashQrSession.objects.filter(token=qr_session)
        .only("vendor_id", "expires_at")
        .first()
    )
    if not row:
        return False, "QR expired. Please scan the new QR code on the TV."
    if str(row.vendor_id) != str(vendor_id):
        return False, "Invalid QR link."
    if row.expires_at <= timezone.now():
        return False, "QR expired. Please scan the new QR code on the TV."
    return True, None


def _is_manager_created_booking_link(request, vendor_id):
    """
    Allow Dine Flash tracking without qr_session only for manager-created bookings.
    Accepts either booking_id or booking_no in the query params.
    """
    booking_id = request.GET.get("booking_id")
    booking_no = request.GET.get("booking_no")

    base_qs = Order.objects.filter(vendor__vendor_id=vendor_id, updated_by="manager")

    if booking_id:
        try:
            return base_qs.filter(id=int(booking_id)).exists()
        except (TypeError, ValueError):
            return False

    if booking_no:
        return base_qs.filter(table_booking_no=str(booking_no)).exists()

    return False


@api_view(["GET"])
@permission_classes([AllowAny])
def dine_flash_qr_exchange(request):
    """
    Dine Flash only: exchange visible qr_date/qr_time into an opaque qr_session token.
    This prevents users from extending access by editing date/time in the URL.
    """
    if project_name != "dine_flash":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    vendor_id = request.GET.get("vendor_id")
    qr_date = request.GET.get("qr_date")
    qr_time = request.GET.get("qr_time")
    if not vendor_id:
        return Response({"error": "vendor_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    ok, msg = _validate_dine_flash_qr_time(qr_date, qr_time, vendor_id)
    if not ok:
        return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)

    naive = datetime.strptime(f"{qr_date} {qr_time}", "%Y-%m-%d %H:%M:%S")
    qr_dt = timezone.make_aware(naive, timezone.get_current_timezone())
    expiry_min = max(1, _get_dine_flash_qr_expiry_minutes(vendor_id))

    token, expires_at_epoch = _create_dine_flash_qr_session(vendor_id, qr_dt, expiry_min)
    return Response(
        {
            "qr_session": token,
            "expires_at_epoch": expires_at_epoch,
            "expiry_minutes": expiry_min,
        },
        status=status.HTTP_200_OK,
    )

def outlet_selection(request):
    location_id = request.GET.get("location_id")
    context = {}

    response = render(request, "orders/landing_page.html", context)

    if location_id:
        response.set_cookie(
            "activeLocation",
            location_id,
            max_age=30 * 24 * 60 * 60,  # 30 days
            samesite="Lax",            # Helps prevent CSRF
            secure=request.is_secure() # Only for HTTPS
        )

    return response

def home(request):
    if project_name == "dine_flash":
        vendor_id = request.GET.get("vendor_id")
        if not vendor_id:
            return HttpResponseBadRequest("Invalid QR link. Vendor ID is required.")
        qr_session = request.GET.get("qr_session")
        if qr_session:
            ok, msg = _validate_dine_flash_qr_session(qr_session, vendor_id)
            if not ok:
                return HttpResponseBadRequest(msg)
        else:
            # Manager-created booking links can open without QR session.
            if not _is_manager_created_booking_link(request, vendor_id):
                return HttpResponseBadRequest("Invalid QR link.")
    return render(request, 'orders/index.html')

def vibration_test(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid request method.")

    vendor_id = request.GET.get("vendor_id")

    context = {
        "vendor_id": vendor_id
    }

    return render(request, 'orders/vibration_test.html', context)


def public_register(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid request method.")

    vendor_id = request.GET.get("vendor_id")

    context = {
        "vendor_id": vendor_id
    }

    return render(request, 'orders/public_register.html', context)

def table_booking(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Invalid request method.")

    if project_name == "dine_flash":
        vendor_id_from_qr = request.GET.get("vendor_id")
        qr_date = request.GET.get("qr_date")
        qr_time = request.GET.get("qr_time")
        qr_session = request.GET.get("qr_session")
        if not vendor_id_from_qr:
            return HttpResponseBadRequest("Invalid QR link. Vendor ID is required.")
        if qr_session:
            ok, msg = _validate_dine_flash_qr_session(qr_session, vendor_id_from_qr)
        else:
            ok, msg = _validate_dine_flash_qr_time(qr_date, qr_time, vendor_id_from_qr)
        if not ok:
            return HttpResponseBadRequest(msg)

    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")

    utilities_enabled = False  # default fallback
    phone_number_enabled = False  # default fallback

    vendor = None
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
    if project_name == "dine_flash" and vendor:
        logo_url = ""
        if getattr(vendor, "logo", None) and hasattr(vendor.logo, "url"):
            logo_url = request.build_absolute_uri(vendor.logo.url)
        context.update(
            {
                "VENDOR_NAME": vendor.alias_name or vendor.name or "",
                "VENDOR_LOGO_URL": logo_url,
            }
        )
    context["IS_DINE_FLASH"] = project_name == "dine_flash"
    if project_name == "dine_flash":
        # Expose QR info for countdown + safe URL rewriting.
        context.update(
            {
                "QR_DATE": request.GET.get("qr_date") or "",
                "QR_TIME": request.GET.get("qr_time") or "",
                "QR_EXPIRY_MINUTES": _get_dine_flash_qr_expiry_minutes(vendor_id),
            }
        )

    return render(request, 'orders/dine_flash/table_booking.html', context)



# def token_display(request):
#     cache.clear()
#     return render(request, 'orders/token_display.html')

@api_view(['POST'])
@permission_classes([AllowAny])
def check_status(request):
    vendor_id = request.data.get('vendor_id')
    reply_text = request.data.get('reply_text')  # Optional reply message from user

    logger.debug(f"Check status request data: {request.data}")

    # ───── Validations ─────
    if not vendor_id:
        return Response({'error': 'Vendor ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
    
    if project_name == "airline_flash":
        identifier_field = "sequence_code"
        identifier_value = request.data.get("sequence_code")
        order_filter = {
            identifier_field: identifier_value,
            "vendor__vendor_id": vendor_id,
        }
        status_check_name = "bp_issued"
        status_to_update = "checked_in"
        title = "Flight Status Check"
        body = f"Passenger {identifier_value} is checking their flight status."
        status_type = 'flightstatus'
        message = 'Passenger details retrieved successfully.'
    elif project_name == "dine_flash_buffet":
        identifier_field = "token_no"
        identifier_value = request.data.get("token_no")
        order_filter = {
            identifier_field: identifier_value,
            "vendor__vendor_id": vendor_id,
        }
        status_check_name = None  # No auto-transition for buffet
        status_to_update = None
        title = "Buffet Tracking Check"
        body = f"Customer {identifier_value} is tracking their buffet items."
        status_type = 'buffetstatus'
        message = 'Buffet items retrieved successfully.'
    elif project_name == "dine_flash":
        booking_id = request.data.get("booking_id")
        booking_no = request.data.get("booking_no") or request.data.get("token_no")

        if booking_id:
            identifier_field = "id"
            identifier_value = booking_id
            order_filter = {
                identifier_field: identifier_value,
                "vendor__vendor_id": vendor_id,
            }
        else:
            # Backward compatibility: older clients may send booking_no/token_no.
            identifier_field = "table_booking_no"
            identifier_value = booking_no
            order_filter = {
                identifier_field: identifier_value,
                "vendor__vendor_id": vendor_id,
            }
        status_check_name = "created"
        status_to_update = "waiting"
        title = "Booking Status Check"
        body = f"Customer {identifier_value} is checking their booking status."
        status_type = 'dinestatus'
        message = 'Booking details retrieved successfully.'
    else:
        identifier_field = "token_no"
        identifier_value = request.data.get("token_no")
        order_filter = {
            identifier_field: identifier_value,
            "vendor__vendor_id": vendor_id,
            "created_date": timezone.now().date()
        }
        status_check_name = "created"
        status_to_update = "preparing"
        title = "Status Check"
        body = f"Customer {identifier_value} is checking their order status."
        status_type = 'foodstatus'
        message = 'Order retrieved successfully.'

    if not identifier_value:
        return Response({'error': f'{identifier_field} is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        vendor_id = int(vendor_id)
        if project_name == "dine_flash" and identifier_field == "table_booking_no":
            # booking_no can be alphanumeric (e.g. VIP-9); no int casting.
            pass
        elif project_name != "airline_flash":
            identifier_value = int(identifier_value)
            if identifier_value <= 0:
                return Response({'error': 'Token number must be a positive integer.'}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError:
        return Response({'error': 'Invalid data type for identifier or vendor ID.'}, status=status.HTTP_400_BAD_REQUEST)
    # ───── Main Logic ─────
    try:
        # ───── Existing Order ─────
        order = Order.objects.get(**order_filter)

        if status_check_name and order.status == status_check_name:
            if project_name == "airline_flash":
                title = "Passenger Connected to Your Flight"
                body = f"Passenger {identifier_value} has opened the status checking page."
            elif project_name == "dine_flash":
                title = "Customer Connected"
                body = f"Customer {order.table_booking_no} has opened the booking status page."
            else:
                title = "Customer Connected"
                body = f"Customer {identifier_value} has opened the order status page."
            order.status = status_to_update
            order.updated_by = 'customer'
            order.save()

        vendor_serializer = VendorLogoSerializer(order.vendor, context={'request': request})
        logo_url = vendor_serializer.data.get('logo_url', '')

        display_vendor_name = (
            (order.vendor.alias_name or "").strip() if project_name == "dine_flash" else order.vendor.name
        ) or order.vendor.name

        data = {
            'name': display_vendor_name,
            'alias_name': order.vendor.alias_name,
            'vendor': order.vendor.id,
            'token_no': order.token_no,
            'status': order.status,
            'counter_no': order.counter_no or 1,
            'device_id': order.device.id if order.device else None,
            'device_serial_no': order.device.serial_no if order.device else None,
            'manager_id': order.user_profile.id if order.user_profile else None,
            'manager_name': order.user_profile.name if order.user_profile else None,
            'vendor_id': order.vendor.vendor_id,
            'location_id': order.vendor.location_id,
            'logo_url': logo_url,
            'type': status_type,
            'updated_by': order.updated_by,
            'message': message,
            'reply_status': '',
            "vibration_pattern":order.vendor.config.vibration_pattern,
            "vibration_duration":order.vendor.config.vibration_duration,
        }
        if project_name == "airline_flash":
            data['sequence_code'] = order.sequence_code
            data['passenger_name'] = order.passenger_name
            data['pnr_no'] = order.pnr_no
            data['seat_no'] = order.seat_no
            data['zone'] = order.zone
            data['flight_no'] = order.flight_no
        elif project_name == "dine_flash":
            utility_display = order.utility.display_name if order.utility else "-"
            seat_display = (order.seat_no or "").strip() if isinstance(order.seat_no, str) else (order.seat_no or "")
            utility_with_seat = (
                f"{utility_display} ({seat_display})"
                if utility_display != "-" and seat_display
                else utility_display
            )
            data['booking_no'] = order.table_booking_no
            data['booking_id'] = order.id
            data['customer_name'] = order.customer_name
            data['no_of_packs'] = order.no_of_packs
            data['seat_no'] = order.seat_no
            data['utility_name'] = utility_with_seat
            data['remarks'] = order.remarks
        elif project_name == "dine_flash_buffet":
            data['booking_no'] = order.table_booking_no
            data['booking_id'] = order.id
            data['customer_name'] = order.customer_name
            data['phone_number'] = order.phone_number
            # Items (skipping 'created' status)
            buffet_items = order.buffet_items.exclude(status='created')
            data['items'] = [
                {
                    'id': item.id,
                    'name': item.utility.display_name if item.utility else 'Generic',
                    'status': item.status,
                    'quantity': item.quantity,
                    'updated_at': item.updated_at.isoformat()
                } for item in buffet_items
            ]


        if reply_text:
            data['message'] = "Reply message sent to managers."
            data['type'] = 'user_reply'
            data['reply_status'] = reply_text
            MAX_MESSAGE_LENGTH = 200

            if reply_text and len(reply_text) > MAX_MESSAGE_LENGTH:
                return Response(
                    {"error": f"Message too long. Limit is {MAX_MESSAGE_LENGTH} characters."},
                    status=400
                )
            
            chat_message = None
            try:
                chat_message = ChatMessage.objects.create(
                    vendor=order.vendor,
                    token_no=order.token_no,
                    booking_id = order.id if project_name == "dine_flash" else None,
                    booking_no = order.table_booking_no if project_name == "dine_flash" else None,
                    sequence_code = order.sequence_code if project_name == "airline_flash" else None,
                    created_date=timezone.now().date(),
                    sender='user',
                    is_send=True,
                    message_text=reply_text
                )
            except Exception as e:
                logger.exception("Failed to store user chat message")
                if chat_message:
                    chat_message.is_send = False
                    chat_message.save(update_fields=["is_send"])
            if project_name == "airline_flash":
                title = "Passenger Message Received"
                body = f"Passenger {order.sequence_code} has sent a new message."
            elif project_name == "dine_flash":
                title = "Customer Message Received"
                body = f"Customer {order.table_booking_no} has sent a new message."
            else:
                title = "Customer Message Received"
                body = f"Customer {order.token_no} has sent a new message."

        threading.Thread(
            target=_send_to_managers_async,
            args=(order.vendor, data, title, body),
            daemon=True,
        ).start()
        return Response(data, status=status.HTTP_200_OK)

    except Order.DoesNotExist:
        if project_name == 'airline_flash':
            return Response(
                {'error': 'Invalid passenger details. Please verify and try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if project_name == 'dine_flash':
            return Response(
                {'error': 'Invalid booking details. Please verify and try again.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ───── For other projects, continue creating a new order ─────
        try:
            vendor = Vendor.objects.get(vendor_id=vendor_id)
            vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
            logo_url = vendor_serializer.data.get('logo_url', '')

            new_order_data = {
                'name': vendor.name,
                'alias_name': vendor.alias_name,
                identifier_field: identifier_value,
                'vendor': vendor.id,
                'location_id': vendor.location_id,
                'counter_no': 1,
                'device': None,
                'status': 'preparing',
                'updated_by': 'customer',
                'type': 'foodstatus'
            }
            serializer = OrdersSerializer(data=new_order_data)
            if serializer.is_valid():
                order = serializer.save()

                data = {
                    'name': vendor.name,
                    'alias_name': vendor.alias_name,
                    'vendor': vendor.id,
                    identifier_field: identifier_value,
                    'status': 'preparing',
                    'counter_no': 1,
                    'device_id': None,
                    'device_serial_no': None,
                    'manager_id': None,
                    'manager_name': None,
                    'vendor_id': vendor.vendor_id,
                    'location_id': vendor.location_id,
                    'logo_url': logo_url,
                    'type': 'foodstatus',
                    'updated_by': 'customer',
                    'message': 'Order created with status preparing.',
                    'reply_status': '',
                    "vibration_pattern":vendor.config.vibration_pattern,
                    "vibration_duration":vendor.config.vibration_duration
                }
                if project_name == "airline_flash":
                    title = "Passenger Connected to Your Flight"
                    body = f"Passenger {identifier_value} is now connected."
                else:
                    title = "Customer Connected"
                    body = f"Customer {identifier_value} has opened the order status page."

                threading.Thread(
                    target=_send_to_managers_async,
                    args=(vendor, data, title, body),
                    daemon=True,
                ).start()

                return Response(data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        except Vendor.DoesNotExist:
            return Response({'error': 'Vendor not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception("Unexpected error while creating order.")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.exception("Unexpected error while processing order.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_outlets(request):
    location_id = request.GET.get('location_id', None)  # Fetch location ID from query params
    
    if not location_id:
        return Response({"error": "Location ID is required"}, status=status.HTTP_400_BAD_REQUEST)
    outlets = Vendor.objects.filter(location_id=location_id)
    
    data = [
        {
            "id": outlet.id,
            "name": outlet.name,
            "logo": f"{settings.MEDIA_URL}{outlet.logo}" if outlet.logo else None,
            "vendor_id":outlet.vendor_id
        }
        for outlet in outlets
    ]

    return Response(data, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def get_vendor_logos(request):
    try:
        vendor_ids = request.data.get("vendor_ids")
        
        # Validate input
        if vendor_ids is None or not isinstance(vendor_ids, list):
            return Response(
                {"error": "vendor_ids must be provided as a list."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ensure each ID is an integer
        if not all(isinstance(v_id, int) for v_id in vendor_ids):
            return Response(
                {"error": "All vendor_ids must be integers."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filter using vendor_id, not id
        vendors = Vendor.objects.filter(vendor_id__in=vendor_ids)

        if not vendors.exists():
            return Response(
                {"error": "No matching vendors found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serialized = VendorLogoSerializer(vendors, many=True, context={'request': request})
        return Response(serialized.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response(
            {"error": "An unexpected error occurred.", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def get_vendor_ads(request):
    try:
        vendor_ids = request.data.get("vendor_ids")

        if not vendor_ids or not isinstance(vendor_ids, list):
            return Response({"error": "vendor_ids must be provided as a list."}, status=400)

        vendors = Vendor.objects.filter(vendor_id__in=vendor_ids)

        # ✅ Use serializer to convert ad paths to full URLs
        serializer = VendorAdsSerializer(vendors, many=True, context={'request': request})
        return Response(serializer.data, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def get_vendor_menus(request):
    try:
        vendor_ids = request.data.get("vendor_ids")

        if not vendor_ids or not isinstance(vendor_ids, list):
            return Response({"error": "vendor_ids must be provided as a list."}, status=400)

        vendors = Vendor.objects.filter(vendor_id__in=vendor_ids)

        serializer = VendorMenuSerializer(vendors, many=True, context={'request': request})
        return Response(serializer.data, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
@api_view(['POST'])
@permission_classes([AllowAny])
def submit_feedback(request):
    vendor_id = request.data.get('vendor_id')

    if not vendor_id:
        return Response({'success': False, 'message': 'Vendor ID is required'}, status=400)

    try:
        vendor = Vendor.objects.get(vendor_id=vendor_id)
    except Vendor.DoesNotExist:
        return Response({'success': False, 'message': 'Vendor not found'}, status=404)

    # Prepare the complete data dictionary
    data = {
        'vendor': vendor.id,  # actual primary key
        'feedback_type': request.data.get('feedback_type'),
        'category': request.data.get('category'),
        'name': request.data.get('name'),
        'comment': request.data.get('comment'),
    }

    serializer = FeedbackSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response({'success': True, 'message': 'Feedback submitted successfully'}, status=201)
    else:
        return Response({'success': False, 'errors': serializer.errors}, status=400)

def login_view(request):
   return render(request, 'orders/login.html')


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def login_api_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    requested_role = request.data.get('role')

    if not username or not password:
        return Response({'error': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)

    if not user:
        logger.warning(f"Authentication failed for username: {username} from IP: {request.META.get('REMOTE_ADDR')}")
        return Response({'error': 'Invalid username or password.'}, status=status.HTTP_401_UNAUTHORIZED)
    login(request, user)
    refresh = RefreshToken.for_user(user)
    MANAGER_ROLE_MAP = {
        'admin_manager': 'Admin Manager',
        'outlet_manager': 'Outlet Manager',
        'outlet_staff': 'Outlet Staff',
        'web_manager': 'Web Manager',
        'utility_user': 'Utility User',
    }
    
    # 1. Manager Login (UserProfile with a specific role)
    if requested_role:
        try:
            profile = UserProfile.objects.get(
                user=user,
                role__in=['outlet_manager', 'admin_manager', 'outlet_staff', 'utility_user', 'airport_manager']
            )
            role_display = MANAGER_ROLE_MAP.get(profile.role, profile.role)
            return Response({
                'message': 'Login successful',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'username': user.username,
                    'role': role_display,
                    'vendor_id': profile.vendor.id if profile.vendor else None,
                    'vendor_name': profile.vendor.name if profile.vendor else None,
                    'customer_id': profile.admin_outlet.customer_id if profile.admin_outlet else None,
                    'outlet_name': profile.admin_outlet.customer_name if profile.admin_outlet else None,
                    'manager_id': profile.id,
                    'manager_name': profile.name,
                }
            }, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'error': f"This user does not have the '{requested_role}' role."}, status=status.HTTP_403_FORBIDDEN)

    # 2. Superadmin Login
    if user.is_superuser:
        return Response({
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'username': user.username,
                'role': 'Super Admin',
            }
        }, status=status.HTTP_200_OK)

    # 3. Company Login(AdminOutlet)
    if user.is_staff and hasattr(user, 'admin_outlet'):
        customer_id = user.admin_outlet.customer_id
        
        request.session['customer_id'] = customer_id
        return Response({
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'username': user.admin_outlet.customer_name,
                'role': 'Company',
                'customer_id': customer_id,
            }
        }, status=status.HTTP_200_OK)

    # 4. Outlet Login (Vendor)
    if Vendor.objects.filter(user=user).exists():
        vendor = Vendor.objects.get(user=user)
        return Response({
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'username': vendor.name,
                'role': 'Outlet',
                'vendor_id': vendor.id,
                'customer_id': vendor.admin_outlet.customer_id if vendor.admin_outlet else None,
            }
        }, status=status.HTTP_200_OK)

    return Response({'error': 'User type not recognized.'}, status=status.HTTP_403_FORBIDDEN)



@login_required
def outlet_dashboard(request):
    try:
        vendor = Vendor.objects.get(user=request.user)
    except Vendor.DoesNotExist:
        return redirect(base)

    context = {
        'vendor': vendor,
    }
    return render(request, 'orders/outlet/outlet_dashboard.html', context)

@never_cache
def logout_view(request):
    logout(request)
    request.session.flush()
    response = redirect(base)
    response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_api_view(request):
    refresh_token = request.data.get("refresh_token")
    if not refresh_token:
        return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()

        # Optional session cleanup (only needed if you use Django session auth)
        logout(request)
        request.session.flush()

        return Response({"detail": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['PUT'])
@permission_classes([IsAuthenticated]) 
def update_admin_outlet(request):
    customer_id = request.data.get('customer_id')
    if not customer_id:
        return Response({"error": "customer_id is required."},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        admin_outlet = AdminOutlet.objects.get(customer_id=customer_id)
    except AdminOutlet.DoesNotExist:
        return Response({"error": "AdminOutlet not found for this customer_id."},
                        status=status.HTTP_404_NOT_FOUND)

    # Ensure username is NOT changed, so remove user data or ignore it
    data = request.data.copy()
    if 'user' in data:
        data.pop('user')

    serializer = AdminOutletSerializer(admin_outlet, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_banners(request):
    vendor_ids_param = request.GET.get('vendor_ids')
    if not vendor_ids_param:
        return Response({"error": "vendor_ids is required"}, status=400)

    try:
        vendor_ids = json.loads(vendor_ids_param)
        if not isinstance(vendor_ids, list) or not all(isinstance(v, int) for v in vendor_ids):
            raise ValueError
    except ValueError:
        return Response({
            "error": "Invalid vendor_ids format. Use JSON list of integers, e.g., [101,104]"
        }, status=400)

    vendors = Vendor.objects.filter(vendor_id__in=vendor_ids).select_related('config')
    result = []

    for vendor in vendors:
        assignments = (
            AdvertisementProfileAssignment.objects
            .filter(vendor=vendor)
            .select_related('profile')
            .prefetch_related('profile__images', 'profile__slots')
        )

        active_profiles = [a.profile for a in assignments if a.profile.is_active_now(vendor)]
        active_profiles.sort(key=lambda p: p.priority)

        ads = []
        for profile in active_profiles:
            for img in profile.images.all():
                ads.append(request.build_absolute_uri(img.image.url))

        result.append({
            "vendor_id": vendor.vendor_id,
            "ads": ads,
            "name": vendor.name
        })

    return Response(result)


# views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from vendors.models import WebChatMessage, Vendor, PushSubscription
from .serializers import WebChatMessageSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def webchat_messages(request):
    try:
        vendor_id = request.GET.get('vendor_id', None)
        browser_id = request.GET.get('browser_id', None)
        logger.info("📥 GET /webchat_messages")
        logger.info(f"IP: {request.META.get('REMOTE_ADDR')}, UA: {request.META.get('HTTP_USER_AGENT')}")
        logger.debug(f"Query Params: vendor={vendor_id} browser_id={browser_id}")

        vendor = get_vendor(vendor_id)
        if not vendor:
            logger.warning(f"❌ Invalid vendor ID: {vendor_id}")
            return Response({'error': 'Invalid vendor ID'}, status=status.HTTP_400_BAD_REQUEST)
        
        subscription = PushSubscription.objects.filter(browser_id=browser_id).first()
        if not subscription:
            logger.warning(f"❌ No subscription found for browser_id: {browser_id}")
            return Response({'error': 'No subscription found for this browser ID'}, status=status.HTTP_404_NOT_FOUND)

        logger.info(f"✅ Vendor resolved: {vendor.name} ({vendor.vendor_id})")

        start_dt, end_dt = get_vendor_business_day_range(vendor)
        messages = WebChatMessage.objects.filter(
            vendor_id=vendor.id,
            subscription=subscription.id,
            timestamp__range=(start_dt, end_dt)
        ).order_by('timestamp')
        count = messages.count()
        logger.info(f"💬 Retrieved {count} messages for vendor {vendor.name} for business day ({start_dt} to {end_dt}).")

        serializer = WebChatMessageSerializer(messages, many=True)
        return Response({'messages': serializer.data}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("🔥 Unhandled exception in /webchat_messages:")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def webchat_message_create(request):
    try:
        logger.info("📥 POST /webchat_message_create")
        logger.info(f"IP: {request.META.get('REMOTE_ADDR')}, UA: {request.META.get('HTTP_USER_AGENT')}")
        logger.debug(f"Payload received: {request.data}")
 
        serializer = WebChatMessageSerializer(data=request.data)
        if serializer.is_valid():
            message = serializer.save()
            logger.info(f"✅ WebChatMessage created | ID: {message.id}, Vendor: {message.vendor_id}, Timestamp: {message.timestamp}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        logger.warning(f"⚠️ Validation failed for WebChatMessage: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("🔥 Unhandled exception in /webchat_message_create:")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_webchat_messages_read(request, vendor_id):
    """
    Mark all messages for a given vendor as read.
    """
    try:
        updated_count = WebChatMessage.objects.filter(
            vendor_id=vendor_id,
            is_read=False
        ).update(is_read=True)

        return Response({
            "status": "success",
            "updated_count": updated_count
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "status": "error",
            "message": str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

def manifest(request):
    project_name = getattr(settings, "PROJECT_NAME", "calleron")
    display_name = getattr(settings, "PROJECT_DISPLAY_NAME", "Caller On")
    app_version = getattr(settings, "APP_VERSION", "1.0.0")

    icon_map = {
        "food_flash": "foodflash-mini-logo.webp",
        "airline_flash": "airlineflash-mini-logo.webp",
        "service_flash": "serviceflash-mini-logo.webp",
        "dine_flash": "dineflash-mini-logo.webp",
        "calleron": "calleron-mini-logo.webp",
    }

    icon_filename = icon_map.get(project_name.lower(), "calleron-icon.webp")
    base_path = f"/{project_name}/"
    version_suffix = f"?v={app_version}"

    data = {
        # 👇 Unique stable ID — Chrome’s recommended fix
        "id": f"{base_path}?app_id={project_name}",

        "name": display_name,
        "short_name": display_name,
        "start_url": f"{base_path}?standalone=true&v={app_version}",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "version": app_version,
        "icons": [
            {
                "src": f"{base_path}static/utils/Images/{icon_filename}{version_suffix}",
                "sizes": "192x192",
                "type": "image/webp"
            },
            {
                "src": f"{base_path}static/utils/Images/{icon_filename}{version_suffix}",
                "sizes": "512x512",
                "type": "image/webp"
            }
        ]
    }

    response = JsonResponse(data)
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


#Airline Flash Specific Views
from manager.utils.utils import generate_sequence_code

@api_view(['POST'])
@permission_classes([AllowAny])
def public_create_passenger(request):
    """
    Public endpoint to create a passenger for Airline Flash.
    - Expects: vendor_id, flight_no, pnr_no, seat_no, zone, passenger_name
    - Duplicate rule: vendor + flight_no + seat_no
    - Returns existing passenger data if duplicate, otherwise creates new passenger and returns it.
    """
    logger.info("[public_create_passenger] Started | remote_addr=%s", request.META.get("REMOTE_ADDR"))

    # --- Input extraction & validation ---
    data = request.data or {}
    vendor_id = data.get("vendor_id") or request.query_params.get("vendor_id")
    flight_no = data.get("flight_no")
    pnr_no = data.get("pnr_no")
    seat_no = data.get("seat_no")
    zone = data.get("zone")
    passenger_name = data.get("passenger_name")

    required = {
        "vendor_id": vendor_id,
        "flight_no": flight_no,
        "pnr_no": pnr_no,
        "seat_no": seat_no,
        "zone": zone,
        "passenger_name": passenger_name,
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.warning("[public_create_passenger] Missing required fields: %s", missing)
        return Response(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Ensure vendor_id is an integer (vendor.vendor_id)
    try:
        vendor_id_int = int(vendor_id)
    except (ValueError, TypeError):
        return Response({"error": "Invalid vendor_id"}, status=status.HTTP_400_BAD_REQUEST)

    # --- Resolve vendor ---
    vendor = Vendor.objects.filter(vendor_id=vendor_id_int).first()
    if not vendor:
        logger.warning("[public_create_passenger] Vendor not found | vendor_id=%s ", vendor_id)
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    logger.info("[public_create_passenger] Vendor resolved | vendor_id=%s ", vendor.vendor_id)

    # --- Duplicate check: vendor + flight_no + seat_no ---
    existing_passenger = Order.objects.filter(
        vendor=vendor,
        flight_no=flight_no,
        seat_no=seat_no
    ).first()

    base_url = request.build_absolute_uri('/')

    # Build tracking_url pattern (same as manager)
    # Use sequence_code if exists, otherwise create a sequence for redirect (existing passenger should have sequence_code)
    if existing_passenger and existing_passenger.sequence_code:
        sequence = existing_passenger.sequence_code
    else:
        sequence = generate_sequence_code(flight_no, pnr_no, seat_no, zone, passenger_name)

    tracking_url = f"{base_url}{project_name}/home/?location_id={vendor.location_id}&vendor_id={vendor.vendor_id}&sequence_code={sequence}&passenger_name={passenger_name}"
    

    if existing_passenger:
        logger.info("[public_create_passenger] Duplicate found | vendor=%s | flight=%s | seat=%s", vendor.vendor_id, flight_no, seat_no)
        passenger_data = {
            'id': existing_passenger.id,
            'token_no': existing_passenger.token_no,
            'counter_no': existing_passenger.counter_no,
            'updated_by': existing_passenger.updated_by,
            'tracking_url': tracking_url,
            'status': existing_passenger.status,
            'vendor': existing_passenger.vendor.id,
            'vendor_name': existing_passenger.vendor.name,
            'device': existing_passenger.device.id if existing_passenger.device else None,
            'shown_on_tv': existing_passenger.shown_on_tv,
            'notified_at': existing_passenger.notified_at,
            'created_at': existing_passenger.created_at,
            'updated_at': existing_passenger.updated_at,
            'flight_no': existing_passenger.flight_no,
            'pnr_no': existing_passenger.pnr_no,
            'seat_no': existing_passenger.seat_no,
            'zone': existing_passenger.zone,
            'passenger_name': existing_passenger.passenger_name,
            'sequence_code': existing_passenger.sequence_code,
            'type': 'flightstatus',
            'message': 'Passenger already exists for these details.',
        }
        return Response(passenger_data, status=status.HTTP_200_OK)

    # --- Prepare new passenger data ---
    # Auto-generate token_no same as manager flow (last token + 1)
    last_passenger = Order.objects.filter(vendor=vendor).order_by("-token_no").first()
    token_no = (last_passenger.token_no + 1) if last_passenger else 1

    sequence_code = generate_sequence_code(flight_no, pnr_no, seat_no, zone, passenger_name)

    new_passenger_data = {
        'vendor': vendor.id,
        'token_no': token_no,
        'counter_no': 1,
        'updated_by': 'customer',
        'status': 'checked_in',  # per your instruction
        'type': 'flightstatus',
        'name': vendor.name,
        'location_id': vendor.location_id,
        'device': None,
        # Airline-specific fields
        'flight_no': flight_no,
        'pnr_no': pnr_no,
        'seat_no': seat_no,
        'zone': zone,
        'passenger_name': passenger_name,
        'sequence_code': sequence_code,
    }

    logger.debug("[public_create_passenger] Created new passenger data | %s", new_passenger_data)

    serializer = OrdersSerializer(data=new_passenger_data)
    if serializer.is_valid():
        serializer.save()
        resp_data = serializer.data
        resp_data["tracking_url"] = tracking_url
        resp_data["manager_id"] = None
        resp_data["message"] = "Passenger created successfully."
        logger.info("[public_create_passenger] Passenger created | vendor=%s | sequence=%s", vendor.vendor_id, sequence_code)
        return Response(resp_data, status=status.HTTP_201_CREATED)
    else:
        logger.warning("[public_create_passenger] Serializer validation failed | %s", serializer.errors)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

# DineFlash-specific-views

@api_view(['POST'])
@permission_classes([AllowAny])
def book_table(request):
    logger.info("[book_table] Started | remote_addr=%s", request.META.get("REMOTE_ADDR"))

    data = request.data or {}

    manager_profile = None
    manager_vendor = None
    try:
        if getattr(request.user, "is_authenticated", False) and hasattr(request.user, "profile_roles"):
            manager_profile = request.user.profile_roles.select_related("vendor").order_by("id").first()
            manager_vendor = getattr(manager_profile, "vendor", None)
    except Exception:
        manager_profile = None
        manager_vendor = None

    is_manager_created_booking = project_name == "dine_flash" and manager_vendor is not None

    vendor_id = data.get("vendor_id")
    utility_id = data.get("utility_id")
    no_of_guests = data.get("no_of_guests")
    special_notes = data.get("special_notes")
    phone_number = data.get("phone_number") or None
    customer_name = data.get("customer_name")
    requested_status = (data.get("status") or "waiting").strip().lower()
    qr_date = data.get("qr_date")
    qr_time = data.get("qr_time")
    qr_session = data.get("qr_session")

    # --------------------------------------------------------
    # 1. Validate required base fields (vendor-independent)
    # --------------------------------------------------------
    required_base = {
        "no_of_guests": no_of_guests,
        "customer_name": customer_name,
    }
    if not is_manager_created_booking:
        required_base["vendor_id"] = vendor_id

    missing = [k for k, v in required_base.items() if not v]
    if missing:
        logger.warning("[book_table] Missing required fields: %s", missing)
        return Response(
            {"error": f"Missing required fields: {', '.join(missing)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # --------------------------------------------------------
    # 2. Vendor resolution
    # --------------------------------------------------------
    if is_manager_created_booking:
        vendor = manager_vendor
        if not vendor:
            return Response({"error": "Manager vendor not found."}, status=status.HTTP_403_FORBIDDEN)
        if vendor_id and str(vendor_id) != str(vendor.vendor_id):
            return Response(
                {"error": "vendor_id does not match manager vendor."},
                status=status.HTTP_403_FORBIDDEN,
            )
    else:
        try:
            vendor_id_int = int(vendor_id)
        except (ValueError, TypeError):
            return Response({"error": "Invalid vendor_id"}, status=status.HTTP_400_BAD_REQUEST)
        vendor = Vendor.objects.filter(vendor_id=vendor_id_int).first()

    if not vendor:
        logger.warning("[book_table] Vendor not found | vendor_id=%s ", vendor_id)
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    if project_name == "dine_flash" and not is_manager_created_booking:
        ok, msg = _validate_dine_flash_qr_session(qr_session, vendor.vendor_id)
        if not ok:
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)

    allowed_statuses = {choice[0] for choice in Order.STATUS_CHOICES}
    if requested_status not in allowed_statuses:
        return Response(
            {
                "error": (
                    f"Invalid status '{requested_status}'. "
                    f"Allowed values: {sorted(allowed_statuses)}"
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    vendor_config = getattr(vendor, "config", None)
    if vendor_config is None:
        logger.warning("[book_table] VendorConfig missing | vendor_id=%s", vendor_id)
        return Response({"error": "Vendor configuration missing."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # --------------------------------------------------------
    # 3. Validate utility requirement based on vendor config
    # --------------------------------------------------------
    if vendor_config.use_utilities:
        if not utility_id:
            return Response(
                {"error": "utility_id is required because utilities are enabled."},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        utility_id = None  # Ensure clean state if utilities disabled

    # --------------------------------------------------------
    # 4. Utility resolution (only if applicable)
    # --------------------------------------------------------
    utility = None
    if vendor_config.use_utilities and utility_id:
        utility = Utility.objects.filter(id=utility_id, vendor=vendor).first()
        if not utility:
            logger.warning("[book_table] Utility not found | utility_id=%s", utility_id)
            return Response({"error": "Utility not found for this vendor."}, status=status.HTTP_404_NOT_FOUND)

    base_url = request.build_absolute_uri('/')

    # --------------------------------------------------------
    # 5. Atomic block for counter resets and booking creation
    # --------------------------------------------------------
    with transaction.atomic():

        # Reset counters based on vendor and optional utility
        reset_counters_if_new_business_day(vendor, utility)

        # -------------------------------
        # Token number (vendor-wide)
        # -------------------------------
        last_booking = Order.objects.filter(vendor=vendor).order_by("-token_no").first()
        token_no = (last_booking.token_no + 1) if last_booking else 1

        # -------------------------------
        # Booking number logic
        # -------------------------------
        if vendor_config.use_utilities and utility and utility.prefix:

            # Continuous mode: vendor-level counter
            if utility.token_mode == Utility.TOKEN_MODE_CONTINUOUS:
                vendor_config.continuous_booking_counter += 1
                vendor_config.save(update_fields=["continuous_booking_counter"])
                booking_counter = vendor_config.continuous_booking_counter

            # Non-continuous: utility-level counter
            else:
                utility.utility_booking_counter += 1
                utility.save(update_fields=["utility_booking_counter"])
                booking_counter = utility.utility_booking_counter

            booking_no = f"{utility.prefix}-{booking_counter}"

        else:
            # Utilities disabled or no prefix → fallback to token_no
            booking_no = str(token_no)

        # -------------------------------
        # New booking payload
        # -------------------------------
        new_booking_data = {
            'vendor': vendor.id,
            'token_no': token_no,
            'table_booking_no': booking_no,
            'counter_no': 1,
            'updated_by': 'manager' if is_manager_created_booking else 'customer',
            'status': requested_status,
            'name': vendor.name,
            'location_id': vendor.location_id,
            'device': None,
            "no_of_packs": no_of_guests,
            "customer_name": customer_name,
            "remarks": special_notes,
            "phone_number": phone_number,
            'utility': utility.id if utility else None,
        }
        if is_manager_created_booking and manager_profile:
            new_booking_data['manager_id'] = manager_profile.id

        serializer = OrdersSerializer(data=new_booking_data)

        if serializer.is_valid():
            booking_obj = serializer.save()  

            # -------------------------------
            # Tracking URL (after save)
            # -------------------------------
            tracking_url = (
                f"{base_url}{project_name}/home/"
                f"?location_id={vendor.location_id}"
                f"&vendor_id={vendor.vendor_id}"
                f"&booking_no={booking_no}"
                f"&booking_id={booking_obj.id}"
            )
            if qr_session:
                tracking_url = f"{tracking_url}&qr_session={qr_session}"

            resp_data = serializer.data
            resp_data["tracking_url"] = tracking_url
            resp_data["manager_id"] = manager_profile.id if is_manager_created_booking and manager_profile else None
            resp_data["created_by"] = "manager" if is_manager_created_booking else "customer"
            resp_data['type'] = 'dinestatus'
            resp_data["message"] = "Booking created successfully."

            logger.info(
                "[book_table] Booking created | vendor=%s, token_no=%s, booking_no=%s",
                vendor.vendor_id, token_no, booking_no
            )
            return Response(resp_data, status=status.HTTP_201_CREATED)


        logger.warning("[book_table] Serializer validation failed | %s", serializer.errors)
        return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def utility_list(request):
    vendor_id = request.GET.get('vendor_id')

    if not vendor_id:
        logger.warning("utility_list: vendor_id missing in request.")
        return Response(
            {"error": "vendor_id is required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        vendor = Vendor.objects.filter(vendor_id=vendor_id).first()
        if not vendor:
            logger.warning(f"utility_list: Invalid vendor_id '{vendor_id}'.")
            return Response(
                {"error": "Invalid vendor_id."},
                status=status.HTTP_404_NOT_FOUND
            )

        utilities = Utility.objects.filter(
            vendor=vendor,
            is_active=True
        ).prefetch_related('options').order_by("id")

        data = [
            {
                "id": util.id,
                "utility_name": util.utility_name,
                "display_name": util.display_name,
                "display_code": util.display_code,
                "token_mode": util.token_mode,
                "prefix": util.prefix,
                "options": [
                    {
                        "id": opt.id,
                        "name": opt.name,
                        "is_active": opt.is_active
                    } for opt in util.options.all() if opt.is_active
                ] if getattr(settings, 'PROJECT_NAME', '') == 'dine_flash_buffet' else []
            }
            for util in utilities
        ]

        logger.info(
            f"utility_list: Returned {len(data)} utilities for vendor_id {vendor_id}."
        )

        return Response(
            {
                "utilities": data,
                "count": len(data),
            },
            status=status.HTTP_200_OK
        )

    except Vendor.DoesNotExist as e:
        logger.error(f"utility_list: Vendor.DoesNotExist -> {str(e)}")
        return Response(
            {"error": "Vendor not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    except Utility.DoesNotExist as e:
        logger.error(f"utility_list: Utility.DoesNotExist -> {str(e)}")
        return Response(
            {"error": "Utility records not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    except ValueError as e:
        logger.error(f"utility_list: ValueError -> {str(e)}")
        return Response(
            {"error": "Invalid parameter."},
            status=status.HTTP_400_BAD_REQUEST
        )

    except Exception as e:
        logger.exception("utility_list: Unexpected server error.")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )




# # orders/views.py
# import io
# from PIL import Image
# from rest_framework.decorators import api_view, permission_classes
# from rest_framework.permissions import AllowAny
# from rest_framework.response import Response
# from rest_framework import status

# # pdf417decoder API
# from pdf417decoder import PDF417Decoder

# # helper parse
# import re

# def parse_bcbp(raw):
#     """
#     Parse minimal BCBP fields from raw decode string.
#     Returns dict with passenger_name, pnr_no, flight_no, seat_no, zone (if any), raw.
#     This mirrors your JS parser rules (PNR fix: drop leading 'E' on 7-char).
#     """
#     if not raw:
#         return {}
#     # normalize
#     s = str(raw).replace('\r', ' ').replace('\n', ' ').strip()
#     res = {"raw": s, "pnr_no": None, "seat_no": None, "flight_no": None, "passenger_name": None, "zone": None}

#     def fix_pnr(pnr):
#         if not pnr: return pnr
#         if len(pnr) == 6: return pnr
#         if len(pnr) == 7 and pnr.startswith("E"):
#             return pnr[1:]
#         return pnr

#     # name (standard BCBP starts with M + legs + name 20 chars)
#     name_match = re.match(r'^\s*M\d?([A-Z\/\-\s]+?)\s{2,}', s)
#     if name_match:
#         name_raw = name_match.group(1).strip()
#         if "/" in name_raw:
#             last, first = name_raw.split("/", 1)
#             res["passenger_name"] = f"{first.strip()} {last.strip()}"
#         else:
#             res["passenger_name"] = name_raw

#     # after-name remainder
#     after_name = re.sub(r'^\s*M\d?[A-Z\/\-\s]+\s{2,}', '', s)

#     # PNR: first 5-7 alnum token
#     pnr_m = re.search(r'\b([A-Z0-9]{5,7})\b', after_name)
#     if pnr_m:
#         res["pnr_no"] = fix_pnr(pnr_m.group(1))

#     # Seat: match 1-2 digits + letter; strip non-alnum trailing
#     seat_m = re.search(r'([0-9]{1,2}[A-Z])[^A-Z0-9]?', s, flags=re.IGNORECASE)
#     if seat_m:
#         res["seat_no"] = re.sub(r'[^0-9A-Z]', '', seat_m.group(1).upper())

#     # Flight: airline code (1-3 letters) + optional space + 3-4 digits (handles AI 0658 / AI658 / AI0658)
#     flight_m = re.search(r'\b([A-Z]{1,3})\s?0?(\d{3,4})\b', s, flags=re.IGNORECASE)
#     if flight_m:
#         res["flight_no"] = f"{flight_m.group(1).upper()}{flight_m.group(2)}"

#     # Zone (optional)
#     zone_m = re.search(r'\bZONE[:\s]*([A-Z0-9])\b', s, flags=re.IGNORECASE)
#     if zone_m:
#         res["zone"] = zone_m.group(1).upper()

#     return res

# @api_view(['POST'])
# @permission_classes([AllowAny])
# def decode_boarding_pass(request):
#     """
#     Accepts a multipart/form-data POST with field 'image' (camera photo).
#     Decodes PDF417 using pdf417decoder and parses BCBP fields.
#     Returns JSON with parsed values.
#     """
#     img_file = request.FILES.get('image')
#     if not img_file:
#         return Response({"error": "No image provided."}, status=status.HTTP_400_BAD_REQUEST)

#     try:
#         # Read into PIL Image
#         img_bytes = img_file.read()
#         image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

#         # pdf417decoder expects PIL Image (or numpy array) — usage depends on version
#         decoder = PDF417Decoder(image)
#         print(decoder)
#         results = decoder.decode()  # returns list of decoded payloads or a single string depending on lib
#         print(results)

#         # Normalize results: could be single string or list
#         if results is None:
#             return Response({"error": "No barcode detected."}, status=status.HTTP_200_OK)

#         # pdf417decoder often returns a list of rows (or a string). Normalize:
#         if isinstance(results, list):
#             # join multiple decoded blocks with space
#             raw_text = " ".join([str(r) for r in results if r])
#         else:
#             raw_text = str(results)

#         parsed = parse_bcbp(raw_text)

#         # Return parsed fields
#         return Response(parsed, status=status.HTTP_200_OK)

#     except Exception as e:
#         # Log the error server-side; return helpful message to client
#         import traceback, logging
#         logging.exception("decode_boarding_pass failed")
#         return Response({"error": "Decoding failed", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
