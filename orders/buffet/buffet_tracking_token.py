"""
Signed tracking tokens for Dine Flash Buffet tracking URLs.

Uses Django's signing framework (SECRET_KEY) for integrity and tamper detection.
Note: Django signing does NOT encrypt payloads; it protects integrity and detects tampering.
"""
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.urls import NoReverseMatch, reverse

BUFFET_TRACKING_TOKEN_SALT = "dine_flash_buffet.tracking_token"


def _normalize_tracking_field(value):
    if value is None:
        return ""
    return str(value).strip()


def sign_buffet_tracking_token(vendor_id, token_no):
    """
    Return a URL-safe signed token embedding Dine Flash Buffet tracking context.

    Payload contains minimum identifiers needed to resolve Buffet tracking:
    - vendor_id
    - token_no
    All payload values are normalized strings.
    """
    vendor_text = _normalize_tracking_field(vendor_id)
    token_text = _normalize_tracking_field(token_no)
    if not vendor_text:
        raise ValueError("vendor_id is required")
    if not token_text:
        raise ValueError("token_no is required")

    payload = {
        "vendor_id": vendor_text,
        "token_no": token_text,
    }
    return signing.dumps(payload, salt=BUFFET_TRACKING_TOKEN_SALT, compress=True)


def unsign_buffet_tracking_token(token):
    """
    Decode and validate a Dine Flash Buffet tracking token.

    Returns {"vendor_id": str, "token_no": str} or None.
    """
    if not token or not str(token).strip():
        return None
    try:
        payload = signing.loads(str(token).strip(), salt=BUFFET_TRACKING_TOKEN_SALT)
    except signing.BadSignature:
        return None

    if not isinstance(payload, dict):
        return None

    vendor_id = _normalize_tracking_field(payload.get("vendor_id"))
    token_no = _normalize_tracking_field(payload.get("token_no"))
    if not vendor_id or not token_no:
        return None

    return {
        "vendor_id": vendor_id,
        "token_no": token_no,
    }


def build_buffet_encrypted_tracking_url(request, vendor, token_no):
    """
    Build /dine_flash_buffet/home/?t=<signed_token> for Buffet tracking.

    Returns absolute URL or None if inputs are invalid.
    """
    if vendor is None or request is None or token_no is None:
        return None

    vendor_id = getattr(vendor, "vendor_id", None) or vendor
    token = sign_buffet_tracking_token(
        vendor_id=vendor_id,
        token_no=token_no,
    )
    encoded_token = quote(token, safe="")

    project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    try:
        tracking_path = reverse("home")
        home_url = request.build_absolute_uri(tracking_path)
    except NoReverseMatch:
        home_url = request.build_absolute_uri(f"/{project}/home/")

    separator = "&" if "?" in home_url else "?"
    return f"{home_url}{separator}t={encoded_token}"
