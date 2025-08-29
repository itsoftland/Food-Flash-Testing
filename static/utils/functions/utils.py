# static/utils/functions/utils.py
from datetime import timedelta,datetime
from django.utils import timezone
import pytz
import logging

logger = logging.getLogger(__name__)

def get_time_ranges():
    now = timezone.now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = now - timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start_of_today, start_of_week, start_of_month

def get_vendor_current_time(vendor):
    """
    Returns the vendor's current localized datetime.
    Falls back to UTC if no timezone is configured.
    """
    vendor_tz = getattr(vendor.config, "timezone", None) or "UTC"
    tz = pytz.timezone(vendor_tz)
    return timezone.now().astimezone(tz)

def get_vendor_current_date(vendor):
    """
    Returns the vendor's current local date.
    """
    return get_vendor_current_time(vendor).date()


def get_vendor_business_day_range(vendor):
    """
    Returns the UTC start and end datetime for the vendor's current business day
    based on their configured start hour and timezone.

    Args:
        vendor (Vendor): Vendor instance with related VendorConfig.

    Returns:
        tuple: (start_datetime_utc, end_datetime_utc)
    """
    start_hour = vendor.config.business_day_start_hour
    vendor_tz = vendor.config.timezone or 'UTC'

    logger.info(f"[get_vendor_business_day_range] Vendor: id={vendor.id}, name={vendor.name}")
    logger.info(f"[get_vendor_business_day_range] Vendor timezone: {vendor_tz}")
    logger.info(f"[get_vendor_business_day_range] Business day start hour: {start_hour}")

    try:
        tz = pytz.timezone(vendor_tz)
    except pytz.UnknownTimeZoneError:
        logger.warning(f"[get_vendor_business_day_range] Invalid timezone '{vendor_tz}' for vendor_id={vendor.id}, defaulting to UTC")
        tz = pytz.UTC

    # Localize current time
    now_local = timezone.now().astimezone(tz)
    logger.info(f"[get_vendor_business_day_range] Local time: {now_local}")

    # Set today's start time in vendor's local time
    today_start_local = now_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)

    # If current time is before start hour, shift to previous day
    if now_local.hour < start_hour:
        today_start_local -= timedelta(days=1)

    today_end_local = today_start_local + timedelta(days=1)

    # Convert to UTC for DB queries
    today_start_utc = today_start_local.astimezone(pytz.UTC)
    today_end_utc = today_end_local.astimezone(pytz.UTC)

    logger.info(f"[get_vendor_business_day_range] Final UTC range: {today_start_utc} → {today_end_utc}")

    return today_start_utc, today_end_utc



def get_filtered_date_range(date_range, from_date_str=None, to_date_str=None):
    """
    Returns a (start, end) datetime tuple based on the date_range value.
    If range is 'custom', it uses from_date_str and to_date_str (YYYY-MM-DD).
    """
    now = timezone.now()
    start_of_today, start_of_week, start_of_month = get_time_ranges()

    if date_range == 'today':
        return start_of_today, now
    elif date_range == 'this_week':
        return start_of_week, now
    elif date_range == 'this_month':
        return start_of_month, now
    elif date_range == 'custom':
        try:
            from_dt = timezone.make_aware(datetime.strptime(from_date_str, "%Y-%m-%d"))
            to_dt = timezone.make_aware(datetime.strptime(to_date_str, "%Y-%m-%d") + timedelta(days=1))
            return from_dt, to_dt
        except (ValueError, TypeError):
            return None, None
    return None, None

