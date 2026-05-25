"""
Dine Flash only: thin wrapper kept for stable imports from views/signals.

Token resolution and FCM formatting live in ``orders.utils``.
"""
from __future__ import annotations

from typing import Any

from orders.utils import collect_manager_fcm_tokens, send_dine_flash_manager_chat_sync
from vendors.models import Vendor

__all__ = [
    "collect_manager_fcm_tokens",
    "invalidate_manager_token_cache",
    "notify_managers_customer_chat_sync",
]


def invalidate_manager_token_cache(vendor_pk: int | None) -> None:
    """No-op: tokens are loaded fresh each send (legacy cache hook)."""
    return None


def notify_managers_customer_chat_sync(
    vendor: Vendor,
    data: dict[str, Any],
    title: str,
    body: str,
) -> None:
    send_dine_flash_manager_chat_sync(vendor, data, title, body)
