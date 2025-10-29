# core/context_processors.py

from django.conf import settings
from .config.labels import LABELS as _LABELS


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
