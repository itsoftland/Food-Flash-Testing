# core/context_processors.py

from django.conf import settings
from .config.labels import LABELS as _LABELS
from .config.icons import ICONS as _ICONS
from .config.roles import ROLES as _ROLES

def project_labels(request):
    """
    Return the label mapping dictionary for the active project flavour.

    Overview:
        This context processor dynamically injects the correct label set
        into all templates based on the current project's name. It allows
        multiple project flavours (e.g., Food Flash, Airline Flash) to use
        the same codebase while displaying different UI labels.

    Strategy:
        1. Retrieve `PROJECT_NAME` from Django settings.
        2. Normalize it to lowercase for consistent key lookup.
        3. Attempt to load the corresponding label set from LABELS.
        4. If unavailable, fall back to the default label set.
        5. Return the label set under the context variable `LABELS`.

    Context Variable:
        LABELS (dict):
            A dictionary containing all text labels specific to the
            active project flavour. It is automatically available in
            all templates.

    Example Usage in Template:
        {{ LABELS.sidebar.dashboard }}
        {{ LABELS.dashboard.title }}

    Example Behaviour:
        If PROJECT_NAME = "airline_flash", templates will render using
        values from AIRLINE_FLASH labels in `labels.py`.
        If no matching entry exists, it reverts to DEFAULT labels.
    """

    # Get project name from settings (fallback to 'default')
    project_name = getattr(settings, "PROJECT_NAME", "default") or "default"

    # Normalize project key for consistent lookup
    project_key = project_name.lower()

    # Fetch label dictionary with fallback
    labels = _LABELS.get(project_key, _LABELS.get("default", {}))

    # Return context variable for template access
    return {"LABELS": labels}

def project_icons(request):
    """
    Return the icon mapping dictionary for the active project flavour.

    Overview:
        Injects the correct icon set into all templates based on the
        current project's name (e.g., Food Flash, Airline Flash).
        Ensures that different UI flavours can use their own icon themes
        while sharing the same templates.

    Strategy:
        1. Retrieve `PROJECT_NAME` from Django settings.
        2. Normalize it to lowercase for consistent key lookup.
        3. Load the matching icon configuration from ICONS.
        4. If unavailable, fall back to the default icon set.
        5. Return the icons dictionary under the context variable `ICONS`.

    Context Variable:
        ICONS (dict):
            A dictionary containing all icon class mappings specific to
            the active project flavour. It is automatically available in
            all templates.

    Example Usage in Template:
        <i class="{{ ICONS.sidebar.orders }}"></i>
        <i class="{{ ICONS.sidebar.company }}"></i>

    Example Behaviour:
        If PROJECT_NAME = "airline_flash", templates will use
        icons from AIRLINE_FLASH in `icons.py`.
        Otherwise, it defaults to the generic icon set.
    """

    project_name = getattr(settings, "PROJECT_NAME", "default") or "default"
    project_key = project_name.lower()
    icons = _ICONS.get(project_key, _ICONS.get("default", {}))
    return {"ICONS": icons}

def project_roles(request):
    """
    Inject flavour-specific role mappings into templates.

    Provides:
        ROLES (dict):
            Example:
            {
                "admin_manager": "Admin Manager",
                "outlet_manager": "Outlet Manager",
            }
    """
    project_name = getattr(settings, "PROJECT_NAME", "default") or "default"
    project_key = project_name.lower()

    roles = _ROLES.get(project_key, {})

    return {"ROLES": roles}