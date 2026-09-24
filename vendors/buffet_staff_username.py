"""Dine Flash Buffet staff username helpers (internal bf:{admin_outlet.id}: prefix)."""

from collections.abc import Iterable

from django.conf import settings
from django.contrib.auth.models import User

from vendors.models import AdminOutlet, UserProfile

BUFFET_STAFF_USERNAME_PREFIX = "bf:"


def is_dine_flash_buffet_project() -> bool:
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash_buffet"


def build_buffet_internal_username(admin_outlet_id: int, business_username: str) -> str:
    return f"{BUFFET_STAFF_USERNAME_PREFIX}{admin_outlet_id}:{business_username}"


def display_buffet_staff_username(django_username: str, admin_outlet_id: int | None = None) -> str:
    """
    Return the business username for display.

    Only strips bf:{admin_outlet_id}: when admin_outlet_id is provided and the
    stored username matches that exact prefix. Legacy plain usernames pass through.
    """
    if admin_outlet_id is not None:
        prefix = f"{BUFFET_STAFF_USERNAME_PREFIX}{admin_outlet_id}:"
        if django_username.startswith(prefix):
            return django_username[len(prefix) :]
    return django_username


def buffet_business_username_exists_for_admin_outlet(
    admin_outlet: AdminOutlet, business_username: str
) -> bool:
    """True if any staff profile under admin_outlet already uses this business username."""
    profiles = UserProfile.objects.filter(admin_outlet=admin_outlet).select_related("user")
    for profile in profiles:
        if display_buffet_staff_username(profile.user.username, admin_outlet.id) == business_username:
            return True
    return False


def resolve_buffet_staff_user(
    admin_outlets: AdminOutlet | Iterable[AdminOutlet],
    business_username: str,
    *,
    role: str | None = None,
) -> User | None:
    """
    Resolve a Buffet staff Django User by company outlet(s) + business username.

    Supports legacy (plain business username) and new prefixed usernames.
    """
    if isinstance(admin_outlets, AdminOutlet):
        outlets = [admin_outlets]
    else:
        outlets = list(admin_outlets)
    if not outlets:
        return None

    outlet_ids = [outlet.id for outlet in outlets]
    usernames = {business_username}
    for outlet_id in outlet_ids:
        usernames.add(build_buffet_internal_username(outlet_id, business_username))

    candidates = User.objects.filter(username__in=usernames)
    for user in candidates:
        profile_qs = UserProfile.objects.filter(user=user, admin_outlet_id__in=outlet_ids)
        if role:
            profile_qs = profile_qs.filter(role=role)
        if profile_qs.exists():
            return user
    return None
