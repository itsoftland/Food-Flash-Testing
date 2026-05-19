"""Dine Flash FCM audit log (written to fcm.log under the daily log folder)."""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional, Sequence

logger = logging.getLogger("dine_flash.fcm")


def _payload_str(payload: Mapping[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, default=str)


def _flush() -> None:
    for handler in logger.handlers:
        flush = getattr(handler, "flush", None)
        if callable(flush):
            flush()


def log_fcm_send_success(
    *,
    source: str,
    token: str,
    payload: Mapping[str, Any] | str,
    vendor_id: Optional[int] = None,
    label: str = "",
) -> None:
    """Record a successful FCM delivery with the registration token and data payload."""
    logger.info(
        "[fcm_success] source=%s vendor_id=%s label=%s token=%s payload=%s",
        source,
        vendor_id if vendor_id is not None else "",
        label,
        token,
        _payload_str(payload),
    )
    _flush()


def log_fcm_token_registered(
    *,
    action: str,
    mac_address: str,
    customer_id: Any,
    token: str,
    request_payload: Mapping[str, Any],
    vendor_id: Optional[int] = None,
    updated_fields: Optional[Sequence[str]] = None,
) -> None:
    """Record FCM token storage during Android TV device registration."""
    logger.info(
        "[fcm_register] action=%s vendor_id=%s customer_id=%s mac_address=%s "
        "token=%s updated_fields=%s request_payload=%s",
        action,
        vendor_id if vendor_id is not None else "",
        customer_id,
        mac_address,
        token or "(none)",
        ",".join(updated_fields) if updated_fields else "",
        _payload_str(request_payload),
    )
    _flush()
