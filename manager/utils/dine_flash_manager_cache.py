"""
Dine Flash: short-lived cache for outlet-manager vendor resolution.

The manager APK often calls utility_list and get_booking_list back-to-back on
login and on tab switches. Each call previously re-queried UserProfile +
Vendor + VendorConfig. This cache keeps that result for a few seconds per user
(process-local, same pattern as utility_cache).

Scope: PROJECT_NAME == "dine_flash" only.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

from django.conf import settings

from .utils import get_manager_vendor_dine_flash

_LOCK = threading.RLock()
_CACHE: Dict[int, Tuple[float, Any]] = {}


def _ttl_seconds() -> int:
    try:
        return max(0, int(os.getenv("DINE_FLASH_MANAGER_VENDOR_CACHE_TTL", "30")))
    except (TypeError, ValueError):
        return 30


def is_enabled() -> bool:
    project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    return project == "dine_flash"


def get_cached_manager_vendor(user):
    """
    Return the manager's Vendor (with config) or None.
    Falls back to a live DB lookup when cache is disabled or expired.
    """
    if user is None or not getattr(user, "pk", None):
        return get_manager_vendor_dine_flash(user)

    if not is_enabled():
        return get_manager_vendor_dine_flash(user)

    ttl = _ttl_seconds()
    if ttl <= 0:
        return get_manager_vendor_dine_flash(user)

    uid = user.pk
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(uid)
        if entry:
            cached_at, vendor = entry
            if now - cached_at <= ttl:
                return vendor
            _CACHE.pop(uid, None)

    vendor = get_manager_vendor_dine_flash(user)
    if vendor is not None:
        with _LOCK:
            _CACHE[uid] = (time.monotonic(), vendor)
    return vendor


def invalidate_user(user_id: Optional[int]) -> None:
    if user_id is None:
        return
    with _LOCK:
        _CACHE.pop(user_id, None)


def clear_all() -> None:
    with _LOCK:
        _CACHE.clear()
