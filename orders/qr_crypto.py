from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

# Matches Android QrPayloadHelper.HASHED_QUERY_PARAM
HASHED_QUERY_PARAM = "data"


def _encode_key(value: str) -> str:
    """Android Uri.encode(key)."""
    return quote(value, safe="-._~")


def _encode_value(value: str) -> str:
    """Android Uri.encode(value, \":\")."""
    return quote(value, safe="-._~:")


def canonical_query_string(params: dict[str, str]) -> str:
    """
    Same as Android QrPayloadHelper.canonicalQueryString().
    Params must already be final string values.
    """
    parts = []
    for key in sorted(params.keys()):
        parts.append(f"{_encode_key(key)}={_encode_value(str(params[key]))}")
    return "&".join(parts)


def build_qr_hash(params: dict[str, str]) -> str:
    """Same SHA-256 lowercase hex as Android QrPayloadHelper.sha256Hex()."""
    payload = canonical_query_string(params)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_qr_hash(received_data: str, params: dict[str, str]) -> bool:
    """True when ?data= matches params (use when plain params are also in URL)."""
    if not received_data:
        return False
    return received_data.strip().lower() == build_qr_hash(params)


@dataclass
class ResolvedQrPayload:
    vendor_id: Optional[int]
    qr_date: str
    qr_time: str
    qr_expiry_minutes: int
    extra_params: dict[str, str]

    def as_dict(self) -> dict:
        return {
            "vendor_id": self.vendor_id,
            "qr_date": self.qr_date,
            "qr_time": self.qr_time,
            "qr_expiry_minutes": self.qr_expiry_minutes,
            **self.extra_params,
        }


def resolve_qr_data(
    received_data: str,
    *,
    vendor_ids: list[int],
    expiry_minutes_options: list[int] | None = None,
    extra_params: dict[str, str] | None = None,
    now: datetime | None = None,
    max_skew_seconds: int = 5,
) -> Optional[ResolvedQrPayload]:
    """
    Recover params from ?data=<hash> by recomputing hashes until one matches.

    Android QR currently contains ONLY:
        /table_booking?data=<sha256-hex>

    So qr_date / qr_time are found by trying timestamps inside the expiry window.
    """
    received = received_data.strip().lower()
    if not received or len(received) != 64:
        return None

    expiry_minutes_options = expiry_minutes_options or [1]
    extra_params = extra_params or {}
    now = now or datetime.now()

    for vendor_id in vendor_ids:
        for expiry in expiry_minutes_options:
            # Android: expiry=0 means QR does not auto-refresh; allow wider window
            window_minutes = max(expiry, 1) if expiry > 0 else 30
            start = now - timedelta(minutes=window_minutes)

            t = start
            while t <= now + timedelta(seconds=max_skew_seconds):
                params: dict[str, str] = {
                    **{k: str(v) for k, v in extra_params.items()},
                    "vendor_id": str(vendor_id),
                    "qr_date": t.strftime("%Y-%m-%d"),
                    "qr_time": t.strftime("%H:%M:%S"),
                    "qr_expiry_minutes": str(expiry),
                }

                if build_qr_hash(params) == received:
                    return ResolvedQrPayload(
                        vendor_id=vendor_id,
                        qr_date=params["qr_date"],
                        qr_time=params["qr_time"],
                        qr_expiry_minutes=expiry,
                        extra_params=extra_params,
                    )

                t += timedelta(seconds=1)

    return None
