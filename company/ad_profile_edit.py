"""Advertisement profile Edit feature — permitted PROJECT_NAME values only."""

from django.conf import settings

AD_PROFILE_EDIT_PROJECTS = frozenset(
    {
        "dine_flash",
        "dine_flash_buffet",
        "hospital_flash",
    }
)


def ad_profile_edit_enabled_for_project(project_name=None) -> bool:
    if project_name is None:
        project_name = getattr(settings, "PROJECT_NAME", "")
    return (project_name or "").strip().lower() in AD_PROFILE_EDIT_PROJECTS
