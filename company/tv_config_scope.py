"""Scope rules for TV device configuration (multi-flavour codebase)."""

from django.conf import settings


def dine_flash_exclusive_tv_device_policy_applies(admin_outlet) -> bool:
    """
    When True, each TVDeviceConfig may be linked to at most one AndroidDevice.

    - Explicit ``project_code == "dine_flash"`` on the outlet always applies.
    - On a Dine Flash server build, outlets that are not explicitly another flavour
      (buffet / food / airline) also apply, so mapping is enforced even if
      ``project_code`` was left blank on legacy rows.
    """
    if not admin_outlet:
        return False
    code = (getattr(admin_outlet, "project_code", "") or "").strip().lower()
    if code in ("dine_flash_buffet", "food_flash", "airline_flash"):
        return False
    if code == "dine_flash":
        return True
    server = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    return server == "dine_flash"
