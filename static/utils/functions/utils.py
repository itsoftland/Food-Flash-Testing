# static/utils/functions/utils.py
from datetime import timedelta,datetime
from django.conf import settings
from django.utils import timezone
import pytz
import logging

logger = logging.getLogger(__name__)


def _is_dine_flash_project():
    return getattr(settings, "PROJECT_NAME", "").lower() in {"dine_flash", "dine_flash_buffet"}

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
    Falls back to UTC only for Dine Flash when config/timezone is invalid.
    """
    is_dine_flash = _is_dine_flash_project()
    vendor_tz = "UTC"
    cfg = None
    try:
        cfg = vendor.config
    except Exception as exc:
        if not is_dine_flash:
            raise
        logger.warning(
            "get_vendor_current_time: missing VendorConfig for vendor pk=%s, using UTC (%s)",
            getattr(vendor, "pk", None),
            exc,
        )
    if cfg is not None:
        vendor_tz = getattr(cfg, "timezone", None) or "UTC"
    try:
        tz = pytz.timezone(vendor_tz)
    except pytz.UnknownTimeZoneError:
        if not is_dine_flash:
            raise
        logger.warning("get_vendor_current_time: invalid timezone %r, using UTC", vendor_tz)
        tz = pytz.UTC
    return timezone.now().astimezone(tz)

def get_vendor_current_date(vendor):
    """
    Returns the vendor's current local date.
    """
    return get_vendor_current_time(vendor).date()

def get_vendor_business_day_range(vendor):
    """
    Returns the UTC start and end datetime for the vendor's current business day
    based on their configured start time and timezone.

    Args:
        vendor (Vendor): Vendor instance with related VendorConfig.

    Returns:
        tuple: (start_datetime_utc, end_datetime_utc)
    """
    is_dine_flash = _is_dine_flash_project()
    config = None
    try:
        config = vendor.config
    except Exception:
        if not is_dine_flash:
            raise
        logger.warning(
            "[get_vendor_business_day_range] no VendorConfig for vendor pk=%s; using UTC midnight window",
            getattr(vendor, "pk", None),
        )

    if config is None:
        start_time = datetime.strptime("00:00:00", "%H:%M:%S").time()
        vendor_tz = "UTC"
    else:
        start_time = config.business_day_start_hour
        if start_time is None:
            logger.info(
                "[get_vendor_business_day_range] business_day_start_hour is None for vendor_id=%s. "
                "Defaulting to 00:00:00 (24/7 mode).",
                vendor.id,
            )
            start_time = datetime.strptime("00:00:00", "%H:%M:%S").time()
        vendor_tz = config.timezone or "UTC"

    try:
        tz = pytz.timezone(vendor_tz)
    except pytz.UnknownTimeZoneError:
        if not is_dine_flash:
            raise
        logger.warning(
            f"[get_vendor_business_day_range] Invalid timezone '{vendor_tz}' "
            f"for vendor_id={vendor.id}, defaulting to UTC"
        )
        tz = pytz.UTC

    # Localize current time
    now_local = timezone.now().astimezone(tz)

    # Build today's start datetime using vendor's start_time
    today_start_local = now_local.replace(
        hour=start_time.hour,
        minute=start_time.minute,
        second=0,
        microsecond=0
    )

    # If current time is before today's start time, move start to previous day
    if now_local.time() < start_time:
        today_start_local -= timedelta(days=1)

    today_end_local = today_start_local + timedelta(days=1)

    # Convert to UTC for DB queries
    today_start_utc = today_start_local.astimezone(pytz.UTC)
    today_end_utc = today_end_local.astimezone(pytz.UTC)

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

def get_default_closing_message():
        from django.conf import settings

        project = getattr(settings, "PROJECT_NAME", "default").lower()

        defaults = {
            "food_flash": "Thank you for visiting us. Have a great day!",
            "airline_flash": "Thank you for choosing our service. Wish you a pleasant journey!",
            "dine_flash": "Thank you for dining with us today.We appreciate your visit. Have a wonderful day!",
            "default": "Thank you! Have a great day!",
        }

        return defaults.get(project, defaults["default"])