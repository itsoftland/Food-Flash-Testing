"""
Dine Flash: process-local cache for the outlet-manager utility listing.

The outlet manager mobile app fetches `/dine_flash/manager/api/utility_list/`
on every login and on most screen transitions. Utilities for a given vendor
change very rarely (admin reconfiguration only), so we serve repeated calls
from a small in-memory cache instead of hitting the DB every time.

Scope
-----
This cache is intentionally restricted to `PROJECT_NAME == "dine_flash"`.
Other flavours (food_flash, airline_flash, dine_flash_buffet) bypass the
cache entirely and keep their existing behaviour.

Invalidation
------------
Entries are invalidated immediately when a `Utility` row is saved or deleted
(see vendors/signals.py). A short safety-net TTL acts as a fallback in case
a write somehow bypasses the model layer (raw SQL, manual `bulk_update`,
DB-level edits, etc.).

Concurrency
-----------
A re-entrant lock guards the dict so concurrent requests within the same
gunicorn worker stay consistent. The cache is process-local — each worker
keeps its own copy, which is acceptable for this workload (utilities are
read-heavy and rarely mutated).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings


_LOCK = threading.RLock()
_CACHE: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}


def _ttl_seconds() -> int:
    """TTL for safety-net cache expiry (signals normally invalidate sooner)."""
    try:
        return max(0, int(os.getenv("DINE_FLASH_UTILITY_CACHE_TTL", "60")))
    except (TypeError, ValueError):
        return 60


def is_enabled() -> bool:
    project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    return project == "dine_flash"


def get_cached_utilities(vendor_id: Optional[int]) -> Optional[List[Dict[str, Any]]]:
    """Return the cached utility list for `vendor_id` or None on miss/disabled."""
    if vendor_id is None or not is_enabled():
        return None

    ttl = _ttl_seconds()
    if ttl <= 0:
        return None

    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(vendor_id)
        if not entry:
            return None
        cached_at, data = entry
        if now - cached_at > ttl:
            _CACHE.pop(vendor_id, None)
            return None
        return data


def set_cached_utilities(vendor_id: Optional[int], data: List[Dict[str, Any]]) -> None:
    """Store the utility list for `vendor_id` (no-op outside Dine Flash)."""
    if vendor_id is None or not is_enabled():
        return
    with _LOCK:
        _CACHE[vendor_id] = (time.monotonic(), data)


def invalidate_vendor(vendor_id: Optional[int]) -> None:
    """Drop the cached entry for a single vendor. Safe to call from any project."""
    if vendor_id is None:
        return
    with _LOCK:
        _CACHE.pop(vendor_id, None)


def clear_all() -> None:
    """Drop every cached entry. Intended for tests and admin tooling."""
    with _LOCK:
        _CACHE.clear()
