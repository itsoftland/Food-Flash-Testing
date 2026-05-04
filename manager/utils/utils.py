# Food-Flash/manager/utils/utils.py
from collections import Counter
from datetime import datetime, timedelta
import logging
import hashlib
import pytz
from django.db import models
from rest_framework.exceptions import NotFound
from django.utils import timezone

from vendors.models import ArchivedOrder, ChatMessage, Order, UserProfile
from static.utils.functions.utils import (
    get_vendor_business_day_range,
    get_vendor_current_time,
)

from django.db.models import Q
from vendors.utils import notify_web_push

logger = logging.getLogger(__name__)

def get_manager_vendor(user):
    logger.info("Fetching vendor for manager user: %s", user)
    profile = user.profile_roles.first()
    if not profile or not profile.vendor:
        logger.warning("No vendor found for manager user: %s", user)
        raise NotFound("Vendor not found for this manager")
    logger.debug("Found vendor %s for manager user %s", profile.vendor, user)
    return profile.vendor


def get_manager_vendor_dine_flash(user):
    """
    Dine Flash: resolve the manager's vendor in a single query (profile + vendor row).
    Avoids user.profile_roles.first() which omits select_related and can add latency.
    Returns None if there is no profile or no vendor linked.
    """
    profile = (
        UserProfile.objects.filter(user=user)
        .select_related("vendor")
        .order_by("id")
        .first()
    )
    if not profile or not profile.vendor_id:
        return None
    return profile.vendor


def get_last_working_days(vendor, num_days=2):
    """
    Returns the last `num_days` working business days for a vendor (excluding today).
    A working day is one where at least one order exists.
    """
    logger.info("Getting last %s working days for vendor %s", num_days, vendor)

    working_days = []
    current_local = get_vendor_current_time(vendor) - timedelta(days=1)

    checked_days = 0
    while len(working_days) < num_days and checked_days < 10:  # prevent infinite loop
        start_dt, end_dt = get_vendor_business_day_range_for_date(vendor, current_local.date())
        logger.debug("Checking date %s (range %s - %s)", current_local.date(), start_dt, end_dt)

        has_order = (
            Order.objects.filter(vendor=vendor, created_at__range=(start_dt, end_dt)).exists()
            or ArchivedOrder.objects.filter(vendor=vendor, created_at__range=(start_dt, end_dt)).exists()
        )

        if has_order:
            logger.debug("Working day found: %s (range %s - %s)", current_local.date(), start_dt, end_dt)
            working_days.append((start_dt, end_dt))
        else:
            logger.debug("No orders found for %s", current_local.date())

        current_local -= timedelta(days=1)
        checked_days += 1

    logger.info("Last working days retrieved: %s", working_days)
    return working_days


def get_vendor_business_day_range_for_date(vendor, date_local):
    """
    Returns UTC start/end for a vendor's business day based on a specific local date.
    """
    logger.debug("Calculating business day range for vendor %s on date %s", vendor, date_local)

    start_hour = vendor.config.business_day_start_hour
    tz = pytz.timezone(vendor.config.timezone or "UTC")

    # ✅ Graceful handling if business_day_start_hour is None
    if start_hour is None:
        logger.info(
            f"[get_vendor_business_day_range_for_date] business_day_start_hour is None for vendor_id={vendor.id}. "
            "Defaulting to 00:00:00 (24/7 mode)."
        )
        start_hour = datetime.strptime("00:00:00", "%H:%M:%S").time()

    start_local = tz.localize(datetime.combine(date_local, start_hour))
    end_local = start_local + timedelta(days=1)

    start_local = start_local.astimezone(pytz.UTC)
    end_local = end_local.astimezone(pytz.UTC)

    logger.debug("Business day range: %s - %s", start_local, end_local)
    return start_local, end_local


def get_suggestion_messages(vendor,limit):
    """
    Extract manager messages from ChatMessage for today and last two working business days,
    count duplicates, and return them sorted by frequency (descending).
    """

    today_start, today_end = get_vendor_business_day_range(vendor)
    last_days = get_last_working_days(vendor, num_days=2)

    time_ranges = [(today_start, today_end)] + last_days

    qs = ChatMessage.objects.filter(
        vendor=vendor,
        sender="manager",
        message_text__isnull=False
    )

    q_filter = models.Q()
    for start_dt, end_dt in time_ranges:
        q_filter |= models.Q(created_at__range=(start_dt, end_dt))

    qs = qs.filter(q_filter)

    counter = Counter(msg.message_text.strip() for msg in qs if msg.message_text.strip())

    suggestions = [
        msg for msg, count in sorted(counter.items(), key=lambda x: (-x[1], x[0].lower()))
    ][:limit]

    return suggestions

def get_order_counts(orders_queryset, serialized_data):
    """
    Calculate counts for each order status and number of orders with unread notifications.
    Returns a flat dictionary suitable to merge directly into the response.
    """
    counts = {
        "unread": 0,
        "delivered": 0,
        "ready": 0,
        "preparing": 0,
        "created": 0,
        "cancelled": 0
    }

    # Count orders by status
    for order in orders_queryset:
        status_name = getattr(order, 'status', '').lower()
        if status_name in counts:
            counts[status_name] += 1

    # Count orders with new_notifications > 0 (Unread)
    counts["unread"] = sum(1 for item in serialized_data if item.get("new_notifications", 0) > 0)

    return counts

# ===  Airline Project Utility ===
def get_passenger_counts(passengers_queryset, serialized_data):
    counts = {
        "boarding": 0,
        "final_call": 0,
        "arrived": 0,
        "departed": 0,
        "cancelled": 0,
        "unread": 0,
    }

    for p in passengers_queryset:
        status_name = getattr(p, 'status', '').lower()
        if status_name in counts:
            counts[status_name] += 1

    counts["unread"] = sum(1 for item in serialized_data if item.get("new_notifications", 0) > 0)
    return counts

# ===  Airline Project Utility ===
def generate_sequence_code(flight_no: str, pnr_no: str, seat_no: str, zone:str,passenger_name: str) -> str:
    """
    Generates a short, unique sequence code for Airline Flash orders.

    Format example:
        AI203-7XZ-12A-RAM-84F
    Derived from: flight_no, pnr_no, seat_no, passenger_name

    """
    # Normalize input
    flight = (flight_no or "").strip().upper()[:4]
    pnr = (pnr_no or "").strip().upper()[-3:]  # last 3 characters
    seat = (seat_no or "").strip().upper()
    zone = (zone or "").strip().upper()
    name = (passenger_name or "").strip().title()[:3]
    

    # Build base code
    base = f"{flight}-{pnr}-{seat}-{zone}-{name}"

    # Add short hash suffix for uniqueness
    combined = f"{flight_no}{pnr_no}{seat_no}{zone}{passenger_name}".encode("utf-8")
    short_hash = hashlib.sha1(combined).hexdigest()[:3].upper()

    sequence_code = f"{base}-{short_hash}"
    return sequence_code

# ===  Airline Project Utility ===
def notify_related_passengers(passenger, vendor, payload, zone=None, chat_map=None,token_map=None):
    """
    Notify all passengers of the same flight (or same flight+zone)
    in Airline Flash when a passenger update occurs.

    Args:
        passenger (Order): The current passenger triggering the update.
        vendor (Vendor): The vendor associated with the order.
        payload (dict): The push payload to send.
        by_zone (bool): Whether to narrow notifications to same zone too.
        chat_map (dict, optional): A mapping of sequence_code → message_id for
                                   passengers, used to include message IDs in payloads.

    Returns:
        list[str]: List of error messages (if any) from failed notifications.
    """
    if not passenger.flight_no:
        logger.warning("No flight number on passenger %s — skipping group notifications", passenger.id)
        return []

    filters = Q(vendor=vendor, flight_no=passenger.flight_no)
    if zone :
        filters &= Q(zone=zone)

    related_orders = Order.objects.filter(filters)
    if not related_orders.exists():
        logger.info("No related passengers found for flight %s (zone: %s)", passenger.flight_no, passenger.zone)
        return []

    logger.info("Sending grouped notifications to %d passengers", related_orders.count())

    errors = []
    for rel_order in related_orders:
        try:
            payload_copy = payload.copy()

            # Attach message_id from chat_map (if available)
            if chat_map and rel_order.sequence_code in chat_map:
                payload_copy["message_id"] = chat_map[rel_order.sequence_code]
            if token_map and rel_order.sequence_code in token_map:
                payload_copy["token_no"] = token_map[rel_order.sequence_code]

            # Personalize payload for each passenger
            payload_copy.update({
                "body": f"Passenger {rel_order.sequence_code} has an update from the manager.",
                "sequence_code": rel_order.sequence_code,
                "pnr_no": rel_order.pnr_no,
                "seat_no": rel_order.seat_no,
                "passenger_name": rel_order.passenger_name,
            })

            notify_web_push(rel_order, vendor, payload_copy,rel_order.sequence_code)
            rel_order.refresh_from_db()  # ✅ ensures latest status from DB
            rel_order.notified_at = timezone.now()
            rel_order.save(update_fields=["notified_at"])

        except Exception as e:
            logger.exception("Failed to notify passenger %s: %s", rel_order.sequence_code, e)
            errors.append(str(e))

    return errors


# ===  Airline Project Utility ===

def create_bulk_chat_messages(vendor, passenger, message_text, sender="manager", zone=None):
    """
    Create ChatMessage entries for all passengers in the same flight (and zone if applicable).

    Args:
        vendor (Vendor): Vendor instance.
        passenger (Order): The base passenger whose flight/zone are used to find related passengers.
        message_text (str): The message to broadcast.
        sender (str): Sender label (default 'manager').
        by_zone (bool): Whether to limit messages to same zone.

    Returns:
        list[ChatMessage]: List of created ChatMessage objects.
    """
    if not passenger.flight_no:
        logger.warning("⚠️ No flight number for passenger %s. Skipping bulk chat creation.", passenger.id)
        return []

    filters = Q(vendor=vendor, flight_no=passenger.flight_no)
    if zone:
        filters &= Q(zone=zone)

    related_orders = Order.objects.filter(filters)
    if not related_orders.exists():
        logger.info("No related passengers found for flight %s (zone: %s)", passenger.flight_no, passenger.zone)
        return []

    current_date = get_vendor_current_time(vendor).date()
    chat_messages = [
        ChatMessage(
            vendor=vendor,
            created_date=current_date,
            sender=sender,
            is_send=True,
            message_text=message_text,
            token_no=o.token_no,
            sequence_code=o.sequence_code,
        )
        for o in related_orders
    ]

    ChatMessage.objects.bulk_create(chat_messages)
    logger.info("💬 Created %d chat messages for flight %s (zone: %s)", len(chat_messages), passenger.flight_no, passenger.zone)
    return chat_messages


def reset_counters_if_new_business_day(vendor, utility=None):
    start_dt, end_dt = get_vendor_business_day_range(vendor)

    # ---------------------------------------------------
    # 1️⃣ Check vendor-level first order of the business day
    # ---------------------------------------------------
    vendor_last_order = Order.objects.filter(
        vendor=vendor,
        created_at__range=(start_dt, end_dt)
    ).order_by("-id").first()

    if vendor_last_order is None:
        # Reset vendor-level counter
        vendor.config.continuous_booking_counter = 0
        vendor.config.save(update_fields=["continuous_booking_counter"])

    # ---------------------------------------------------
    # 2️⃣ Check utility-level first order of the business day
    # ---------------------------------------------------
    if utility:
        utility_last_order = Order.objects.filter(
            vendor=vendor,
            utility=utility,
            created_at__range=(start_dt, end_dt)
        ).order_by("-id").first()

        if utility_last_order is None:
            # Reset utility-level counter only for this utility
            utility.utility_booking_counter = 0
            utility.save(update_fields=["utility_booking_counter"])

