"""
Django/Python QR decryption — must match QrPayloadHelper.kt on Android.

Android flow:
  1. canonical query string (sorted keys, URL-encoded)
  2. UTF-8 bytes
  3. AES-256-CBC encrypt (key = SHA-256 of shared secret, random 16-byte IV prepended)
  4. base64url (no padding) -> ?data=<value>

Requires:
  pip install cryptography

settings.py:
  QR_ENCRYPTION_SECRET = "qflash-tv-qr-payload-v1"  # must match Android
  TIME_ZONE = "Asia/Kolkata"
  USE_TZ = True
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional, Union
from urllib.parse import parse_qs, quote, unquote, urlparse

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Must match QrPayloadHelper.QR_ENCRYPTION_SECRET on Android.
DEFAULT_QR_ENCRYPTION_SECRET = "qflash-tv-qr-payload-v1"

# Dine Flash only: tolerate scan-before-expiry / request-after-expiry boundary timing.
_DINE_FLASH_QR_SCAN_GRACE_SECONDS = 180


def get_qr_encryption_secret() -> str:
    try:
        from django.conf import settings

        secret = getattr(settings, "QR_ENCRYPTION_SECRET", None)
        if secret:
            return str(secret)
    except Exception:
        pass
    return DEFAULT_QR_ENCRYPTION_SECRET


@dataclass
class QrPayload:
    vendor_id: Optional[int]
    qr_date: str
    qr_time: str
    qr_expiry_minutes: int


def encode_key(value: str) -> str:
    return quote(value, safe="-._~")


def encode_value(value: str) -> str:
    return quote(value, safe="-._~:")


def canonical_query_string(params: dict[str, str]) -> str:
    parts = []
    for key in sorted(params):
        parts.append(f"{encode_key(key)}={encode_value(params[key])}")
    return "&".join(parts)


def parse_canonical_query_string(query: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for part in query.split("&"):
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        params[unquote(key)] = unquote(value)
    return params


def _derive_aes_key(secret: Optional[str] = None) -> bytes:
    value = (secret or get_qr_encryption_secret()).encode("utf-8")
    return hashlib.sha256(value).digest()


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def decrypt_utf8_payload(data_b64: str, *, secret: Optional[str] = None) -> str:
    raw = _b64url_decode(data_b64.strip())
    if len(raw) < 17:
        raise ValueError("encrypted payload too short")
    iv, ciphertext = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(_derive_aes_key(secret)), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return plain.decode("utf-8")


def extract_data_param(source: Union[str, Mapping[str, Any]]) -> str:
    """
    Read `data` from:
      - full scanned URL string
      - Django request.GET
      - plain dict {"data": "..."}
    """
    if hasattr(source, "GET"):
        return str(source.GET.get("data", "")).strip()

    if isinstance(source, Mapping):
        return str(source.get("data", "")).strip()

    text = str(source).strip()
    if "://" in text or text.startswith("/"):
        parsed = urlparse(text)
        return parse_qs(parsed.query).get("data", [""])[0].strip()
    return text


def decrypt_qr_data(
    data_value: str,
    *,
    now: Optional[datetime] = None,
    secret: Optional[str] = None,
    check_expiry: bool = True,
) -> Optional[QrPayload]:
    """
    Decrypt `data` from the scanned QR URL and return vendor_id, qr_date, qr_time, etc.
    Returns None when decryption fails or the QR is expired.
    """
    data_value = extract_data_param(data_value)
    if not data_value:
        return None

    # Legacy SHA-256 hex hashes are 64 chars and contain only hex digits.
    if len(data_value) == 64 and all(c in "0123456789abcdefABCDEF" for c in data_value):
        return resolve_legacy_hashed_qr_data(data_value.lower(), now=now)

    try:
        canonical_query = decrypt_utf8_payload(data_value, secret=secret)
        params = parse_canonical_query_string(canonical_query)
    except Exception:
        return None

    return qr_payload_from_params(params, now=now, check_expiry=check_expiry)


def decrypt_qr_from_request(request, *, check_expiry: bool = True) -> Optional[QrPayload]:
    """Django helper: decrypt QR opened via browser scan."""
    try:
        from django.utils import timezone

        now = timezone.localtime()
        if timezone.is_aware(now):
            now = timezone.make_naive(now, timezone.get_current_timezone())
    except Exception:
        now = datetime.now()

    return decrypt_qr_data(
        extract_data_param(request),
        now=now,
        check_expiry=check_expiry,
    )


def qr_payload_to_dict(payload: QrPayload) -> dict[str, Any]:
    return asdict(payload)


def qr_payload_from_params(
    params: dict[str, str],
    *,
    now: Optional[datetime] = None,
    check_expiry: bool = True,
) -> Optional[QrPayload]:
    now = now or datetime.now()
    qr_date = params.get("qr_date", "").strip()
    qr_time = params.get("qr_time", "").strip()
    if not qr_date or not qr_time:
        return None

    try:
        expiry_minutes = max(1, int(params.get("qr_expiry_minutes", "5")))
    except ValueError:
        expiry_minutes = 1

    vendor_raw = params.get("vendor_id", "").strip()
    vendor_id = int(vendor_raw) if vendor_raw.isdigit() else None

    try:
        issued_at = datetime.strptime(f"{qr_date} {qr_time}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    max_age = timedelta(minutes=expiry_minutes) + timedelta(
        seconds=_DINE_FLASH_QR_SCAN_GRACE_SECONDS
    )
    if check_expiry and now > issued_at + max_age:
        return None

    return QrPayload(
        vendor_id=vendor_id,
        qr_date=qr_date,
        qr_time=qr_time,
        qr_expiry_minutes=expiry_minutes,
    )


def build_qr_hash(params: dict[str, str]) -> str:
    return hashlib.sha256(canonical_query_string(params).encode("utf-8")).hexdigest()


def resolve_legacy_hashed_qr_data(
    data_hex: str,
    *,
    vendor_id_hint: Optional[int] = None,
    qr_expiry_minutes_hint: int = 1,
    now: Optional[datetime] = None,
    clock_skew_seconds: int = 90,
) -> Optional[QrPayload]:
    """Recover fields from legacy SHA-256 hashed QR codes."""
    now = now or datetime.now()
    expiry_minutes = max(1, int(qr_expiry_minutes_hint or 1))
    vendor_candidates: list[Optional[int]] = []
    if vendor_id_hint is not None and vendor_id_hint > 0:
        vendor_candidates.append(vendor_id_hint)
    vendor_candidates.append(None)

    for vendor_id in vendor_candidates:
        for delta_seconds in range(-clock_skew_seconds, clock_skew_seconds + 1):
            candidate_time = now + timedelta(seconds=delta_seconds)
            params: dict[str, str] = {
                "qr_date": candidate_time.strftime("%Y-%m-%d"),
                "qr_time": candidate_time.strftime("%H:%M:%S"),
                "qr_expiry_minutes": str(expiry_minutes),
            }
            if vendor_id is not None:
                params["vendor_id"] = str(vendor_id)

            if build_qr_hash(params) == data_hex.lower():
                issued_at = candidate_time
                expires_at = issued_at + timedelta(minutes=expiry_minutes)
                if now > expires_at:
                    return None
                return QrPayload(
                    vendor_id=vendor_id,
                    qr_date=params["qr_date"],
                    qr_time=params["qr_time"],
                    qr_expiry_minutes=expiry_minutes,
                )
    return None
