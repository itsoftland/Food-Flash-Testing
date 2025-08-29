# Food-Flash/manager/utils/utils.py
from collections import Counter
from datetime import datetime, timedelta, time
import logging

import pytz
from django.db import models
from rest_framework.exceptions import NotFound

from vendors.models import ArchivedOrder, ChatMessage, Order
from static.utils.functions.utils import (
    get_vendor_business_day_range,
    get_vendor_current_time,
)

logger = logging.getLogger(__name__)



def get_manager_vendor(user):
    logger.info("Fetching vendor for manager user: %s", user)
    profile = user.profile_roles.first()
    if not profile or not profile.vendor:
        logger.warning("No vendor found for manager user: %s", user)
        raise NotFound("Vendor not found for this manager")
    logger.debug("Found vendor %s for manager user %s", profile.vendor, user)
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

    start_local = tz.localize(datetime.combine(date_local, time(hour=start_hour)))
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
    logger.info("Fetching suggestion messages for vendor %s", vendor)

    today_start, today_end = get_vendor_business_day_range(vendor)
    last_days = get_last_working_days(vendor, num_days=2)

    time_ranges = [(today_start, today_end)] + last_days
    logger.debug("Time ranges considered: %s", time_ranges)

    qs = ChatMessage.objects.filter(
        vendor=vendor,
        sender="manager",
        message_text__isnull=False
    )

    q_filter = models.Q()
    for start_dt, end_dt in time_ranges:
        q_filter |= models.Q(created_at__range=(start_dt, end_dt))

    qs = qs.filter(q_filter)
    logger.debug("Fetched %s manager messages", qs.count())

    counter = Counter(msg.message_text.strip() for msg in qs if msg.message_text.strip())
    logger.debug("Message frequency count: %s", counter)

    suggestions = [
        msg for msg, count in sorted(counter.items(), key=lambda x: (-x[1], x[0].lower()))
    ][:limit]
    # suggestions = [msg for msg, count in sorted(counter.items(), key=lambda x: (-x[1], x[0].lower()))]
    logger.info("Suggestions prepared: %s", suggestions)

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




