"""
Signed branch QR tokens for Hospital Flash only.

Reuses Django's signing framework (SECRET_KEY) — the same mechanism as
Dine Flash Buffet table QR codes. No custom crypto.

Printed branch QR codes are not time-limited; integrity is enforced via HMAC.
"""
from django.core import signing

HOSPITAL_BRANCH_QR_SALT = "hospital_flash.branch_qr"


def sign_hospital_branch_qr(vendor_id):
    """Return a URL-safe signed token embedding vendor_id."""
    vendor_text = str(vendor_id).strip() if vendor_id is not None else ""
    if not vendor_text:
        raise ValueError("vendor_id is required")
    payload = {
        "vendor_id": vendor_text,
    }
    return signing.dumps(payload, salt=HOSPITAL_BRANCH_QR_SALT, compress=True)


def unsign_hospital_branch_qr(token):
    """
    Decode and validate a hospital branch QR token.

    Returns {"vendor_id": str} or None if invalid/tampered.
    """
    if not token or not str(token).strip():
        return None
    try:
        payload = signing.loads(str(token).strip(), salt=HOSPITAL_BRANCH_QR_SALT)
    except signing.BadSignature:
        return None

    if not isinstance(payload, dict):
        return None

    vendor_id = str(payload.get("vendor_id", "")).strip()
    if not vendor_id:
        return None

    return {
        "vendor_id": vendor_id,
    }
