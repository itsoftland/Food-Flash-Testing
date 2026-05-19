"""Dine Flash FCM success audit log (written to fcm.log under the daily log folder)."""
from __future__ import annotations

import json
import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger("dine_flash.fcm")


def _payload_str(payload: Mapping[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, ensure_ascii=False, default=str)


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
