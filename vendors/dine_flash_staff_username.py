"""Classic Dine Flash staff username helpers (internal df:{admin_outlet.id}: prefix)."""

from django.conf import settings
from django.contrib.auth.models import User

from vendors.models import AdminOutlet, UserProfile

DINE_FLASH_STAFF_USERNAME_PREFIX = "df:"

STAFF_PROFILE_ROLES = (
    "outlet_manager",
    "admin_manager",
    "outlet_staff",
    "utility_user",
    "airport_manager",
)


def is_dine_flash_project() -> bool:
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash"


def build_dine_flash_internal_username(admin_outlet_id: int, business_username: str) -> str:
    return f"{DINE_FLASH_STAFF_USERNAME_PREFIX}{admin_outlet_id}:{business_username}"


def display_dine_flash_staff_username(django_username: str, admin_outlet_id: int | None = None) -> str:
    """
    Return the business username for display.

    Only strips df:{admin_outlet_id}: when admin_outlet_id is provided and the
    stored username matches that exact prefix. Legacy plain usernames pass through.
    """
    if admin_outlet_id is not None:
        prefix = f"{DINE_FLASH_STAFF_USERNAME_PREFIX}{admin_outlet_id}:"
        if django_username.startswith(prefix):
            return django_username[len(prefix) :]
    return django_username


def _outlet_ids_for_customer_id(customer_id: int) -> list[int]:
    return list(AdminOutlet.objects.filter(customer_id=customer_id).values_list("id", flat=True))


def dine_flash_business_username_exists_for_company(
    admin_outlet: AdminOutlet, business_username: str
) -> bool:
    """True if any staff profile under the company (customer_id) uses this business username."""
    outlet_ids = _outlet_ids_for_customer_id(admin_outlet.customer_id)
    if not outlet_ids:
        outlet_ids = [admin_outlet.id]
    profiles = UserProfile.objects.filter(admin_outlet_id__in=outlet_ids).select_related("user")
    for profile in profiles:
        if (
            display_dine_flash_staff_username(profile.user.username, profile.admin_outlet_id)
            == business_username
        ):
            return True
    return False


class DineFlashStaffLoginResolution:
    """Result of company-scoped staff login resolution."""

    __slots__ = ("profile", "reason")

    def __init__(self, profile: UserProfile | None = None, reason: str | None = None):
        self.profile = profile
        self.reason = reason


def resolve_dine_flash_staff_profile(
    customer_id: int,
    business_username: str,
) -> DineFlashStaffLoginResolution:
    """
    Resolve exactly one staff UserProfile for classic Dine Flash login.

    Never falls back to global username matching; callers must not authenticate
    elsewhere when resolution fails.
    """
    outlets = list(AdminOutlet.objects.filter(customer_id=customer_id))
    if not outlets:
        return DineFlashStaffLoginResolution(reason="invalid_customer_id")

    outlet_ids = [outlet.id for outlet in outlets]
    candidate_usernames = {business_username}
    for outlet_id in outlet_ids:
        candidate_usernames.add(build_dine_flash_internal_username(outlet_id, business_username))

    matching_profiles: list[UserProfile] = []
    seen_profile_ids: set[int] = set()

    for user in User.objects.filter(username__in=candidate_usernames):
        for profile in UserProfile.objects.filter(
            user=user,
            admin_outlet_id__in=outlet_ids,
            role__in=STAFF_PROFILE_ROLES,
        ).select_related("user", "admin_outlet", "vendor"):
            if profile.id in seen_profile_ids:
                continue
            display = display_dine_flash_staff_username(
                profile.user.username, profile.admin_outlet_id
            )
            if display == business_username:
                seen_profile_ids.add(profile.id)
                matching_profiles.append(profile)

    if not matching_profiles:
        return DineFlashStaffLoginResolution(reason="not_found")
    if len(matching_profiles) > 1:
        return DineFlashStaffLoginResolution(reason="ambiguous")
    return DineFlashStaffLoginResolution(profile=matching_profiles[0])
