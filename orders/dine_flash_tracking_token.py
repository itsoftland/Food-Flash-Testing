"""
Signed tracking tokens for Dine Flash manager booking URLs only.

Uses Django's signing framework (SECRET_KEY) — no custom crypto.
"""
from django.conf import settings
from django.core import signing
from django.urls import reverse

DINE_FLASH_TRACKING_TOKEN_SALT = "dine_flash.tracking_token"


def _normalize_tracking_field(value):
    if value is None:
        return ""
    return str(value).strip()


def sign_dine_flash_tracking_token(vendor_id, location_id, booking_id, booking_no):
    """
    Return a URL-safe signed token embedding Dine Flash tracking context.

    All payload values are stored as strings to match legacy query-param URLs.
    """
    vendor_text = _normalize_tracking_field(vendor_id)
    location_text = _normalize_tracking_field(location_id)
    booking_id_text = _normalize_tracking_field(booking_id)
    booking_no_text = _normalize_tracking_field(booking_no)
    if not vendor_text or not location_text:
        raise ValueError("vendor_id and location_id are required")
    if not booking_id_text and not booking_no_text:
        raise ValueError("booking_id or booking_no is required")

    payload = {
        "vendor_id": vendor_text,
        "location_id": location_text,
        "booking_id": booking_id_text,
        "booking_no": booking_no_text,
    }
    return signing.dumps(payload, salt=DINE_FLASH_TRACKING_TOKEN_SALT, compress=True)


def unsign_dine_flash_tracking_token(token):
    """
    Decode and validate a Dine Flash tracking token.

    Returns {"vendor_id", "location_id", "booking_id", "booking_no"} or None.
    """
    if not token or not str(token).strip():
        return None
    try:
        payload = signing.loads(str(token).strip(), salt=DINE_FLASH_TRACKING_TOKEN_SALT)
    except signing.BadSignature:
        return None

    if not isinstance(payload, dict):
        return None

    vendor_id = _normalize_tracking_field(payload.get("vendor_id"))
    location_id = _normalize_tracking_field(payload.get("location_id"))
    booking_id = _normalize_tracking_field(payload.get("booking_id"))
    booking_no = _normalize_tracking_field(payload.get("booking_no"))
    if not vendor_id or not location_id:
        return None
    if not booking_id and not booking_no:
        return None

    return {
        "vendor_id": vendor_id,
        "location_id": location_id,
        "booking_id": booking_id,
        "booking_no": booking_no,
    }


def build_dine_flash_encrypted_tracking_url(vendor, order, request):
    """Build /dine_flash/home/?t=<signed_token> for a manager booking row."""
    if vendor is None or request is None or order is None:
        return None

    project = getattr(settings, "PROJECT_NAME", "").lower()
    try:
        tracking_path = reverse("orders:home")
        home_url = request.build_absolute_uri(tracking_path)
    except Exception:
        home_url = request.build_absolute_uri(f"/{project}/home/")

    token = sign_dine_flash_tracking_token(
        vendor_id=vendor.vendor_id,
        location_id=vendor.location_id,
        booking_id=order.id,
        booking_no=order.table_booking_no or "",
    )
    separator = "&" if "?" in home_url else "?"
    return f"{home_url}{separator}t={token}"
