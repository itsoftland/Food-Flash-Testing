from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional
from urllib.parse import parse_qs, quote, urlparse


@dataclass
class QrPayload:
    vendor_id: Optional[int]
    qr_date: str
    qr_time: str
    qr_expiry_minutes: int


def extract_data_from_url(url: str) -> str:
    """Get `data` from full scanned URL or from request path+query."""
    parsed = urlparse(url.strip())
    return parse_qs(parsed.query).get("data", [""])[0].strip()


def build_qr_hash(params: dict[str, str]) -> str:
    parts = []
    for key in sorted(params):
        encoded_key = quote(key, safe="-._~")
        encoded_value = quote(params[key], safe="-._~:")
        parts.append(f"{encoded_key}={encoded_value}")
    canonical = "&".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_qr_data(
    data_hex: str,
    *,
    vendor_id_hint: Optional[int] = None,
    vendor_id_candidates: Optional[Iterable[int]] = None,
    qr_expiry_minutes_hint: int = 1,
    now: Optional[datetime] = None,
    clock_skew_seconds: int = 90,
) -> Optional[QrPayload]:
    """
    Recover vendor_id, qr_date, qr_time from the `data` hash.
    Must use django.utils.timezone.localtime() for `now` in views.
    """
    data_hex = (data_hex or "").strip().lower()
    if len(data_hex) != 64:
        return None

    now = now or datetime.now()
    expiry_minutes = max(1, int(qr_expiry_minutes_hint or 1))

    vendor_candidates: list[Optional[int]] = []
    if vendor_id_hint and vendor_id_hint > 0:
        vendor_candidates.append(vendor_id_hint)
    if vendor_id_candidates:
        vendor_candidates.extend(v for v in vendor_id_candidates if v and v > 0)
    vendor_candidates.append(None)  # hash without vendor_id (fallback)

    seen: set[Optional[int]] = set()
    for vendor_id in vendor_candidates:
        if vendor_id in seen:
            continue
        seen.add(vendor_id)

        for delta_seconds in range(-clock_skew_seconds, clock_skew_seconds + 1):
            candidate_time = now + timedelta(seconds=delta_seconds)
            params: dict[str, str] = {
                "qr_date": candidate_time.strftime("%Y-%m-%d"),
                "qr_time": candidate_time.strftime("%H:%M:%S"),
                "qr_expiry_minutes": str(expiry_minutes),
            }
            if vendor_id is not None:
                params["vendor_id"] = str(vendor_id)

            if build_qr_hash(params) == data_hex:
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
