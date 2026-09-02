"""Hospital Flash staff username helpers (internal hf:{admin_outlet.id}: prefix)."""

from django.conf import settings
from django.contrib.auth.models import User

from vendors.models import AdminOutlet, UserProfile

HOSPITAL_STAFF_USERNAME_PREFIX = "hf:"


def is_hospital_flash_project() -> bool:
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "hospital_flash"


def build_internal_username(admin_outlet_id: int, business_username: str) -> str:
    return f"{HOSPITAL_STAFF_USERNAME_PREFIX}{admin_outlet_id}:{business_username}"


def display_staff_username(django_username: str, admin_outlet_id: int | None = None) -> str:
    """
    Return the business username for display.

    Only strips hf:{admin_outlet_id}: when admin_outlet_id is provided and the
    stored username matches that exact prefix. Legacy plain usernames pass through.
    """
    if admin_outlet_id is not None:
        prefix = f"{HOSPITAL_STAFF_USERNAME_PREFIX}{admin_outlet_id}:"
        if django_username.startswith(prefix):
            return django_username[len(prefix) :]
    return django_username


def business_username_exists_for_admin_outlet(admin_outlet: AdminOutlet, business_username: str) -> bool:
    """True if any staff profile under admin_outlet already uses this business username."""
    profiles = UserProfile.objects.filter(admin_outlet=admin_outlet).select_related("user")
    for profile in profiles:
        if display_staff_username(profile.user.username, admin_outlet.id) == business_username:
            return True
    return False


def resolve_hospital_staff_user(admin_outlet: AdminOutlet, business_username: str) -> User | None:
    """
    Resolve a Hospital staff Django User by company + business username.

    Supports legacy (plain business username) and new prefixed usernames.
    """
    internal = build_internal_username(admin_outlet.id, business_username)
    candidates = User.objects.filter(username__in=[business_username, internal])
    for user in candidates:
        if UserProfile.objects.filter(
            user=user,
            admin_outlet=admin_outlet,
            role__in=[
                "outlet_manager",
                "admin_manager",
                "outlet_staff",
                "utility_user",
                "airport_manager",
            ],
        ).exists():
            return user
    return None
