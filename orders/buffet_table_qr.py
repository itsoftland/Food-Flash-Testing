"""
Signed table QR tokens for Dine Flash Buffet only.

Uses Django's signing framework (SECRET_KEY) — no custom crypto.
Printed table QR codes are not time-limited; integrity is enforced via HMAC.
"""
from django.core import signing

BUFFET_TABLE_QR_SALT = "dine_flash_buffet.table_qr"


def is_valid_buffet_table_no(value):
    """Positive integer table numbers only (>= 1)."""
    if value is None:
        return False
    text = str(value).strip()
    if not text or not text.isdigit():
        return False
    return int(text) >= 1


def sign_buffet_table_qr(vendor_id, table_no):
    """Return a URL-safe signed token embedding vendor_id and table_no."""
    if not is_valid_buffet_table_no(table_no):
        raise ValueError("table_no must be a positive integer")
    vendor_text = str(vendor_id).strip()
    if not vendor_text:
        raise ValueError("vendor_id is required")
    payload = {
        "vendor_id": vendor_text,
        "table_no": str(int(str(table_no).strip())),
    }
    return signing.dumps(payload, salt=BUFFET_TABLE_QR_SALT, compress=True)


def unsign_buffet_table_qr(token):
    """
    Decode and validate a buffet table QR token.

    Returns {"vendor_id": str, "table_no": str} or None if invalid/tampered.
    """
    if not token or not str(token).strip():
        return None
    try:
        payload = signing.loads(str(token).strip(), salt=BUFFET_TABLE_QR_SALT)
    except signing.BadSignature:
        return None

    if not isinstance(payload, dict):
        return None

    vendor_id = str(payload.get("vendor_id", "")).strip()
    table_no = str(payload.get("table_no", "")).strip()
    if not vendor_id or not is_valid_buffet_table_no(table_no):
        return None

    return {
        "vendor_id": vendor_id,
        "table_no": str(int(table_no)),
    }
