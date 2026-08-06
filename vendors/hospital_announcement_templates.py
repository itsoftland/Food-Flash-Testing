"""
Hospital Flash spoken announcement template catalog and validation.

Built-in templates live in code. Only administrator selections + custom text
are persisted on VendorConfig.announcement_templates.
"""

from __future__ import annotations

from django.conf import settings

# Announcement types editable in Company Admin Configurations.
ANNOUNCEMENT_TYPES = (
    "called",
    "waiting",
    "completed",
    "cancelled",
    "pre_announcement",
)

VALID_SELECTIONS = ("default", "template_a", "template_b", "custom")

# Primary (token + department) forms of today's hardcoded TTS — used for admin preview.
# Runtime "default" still uses the full branching logic in buildHospitalFlashSpokenMessage.
HOSPITAL_ANNOUNCEMENT_BUILTINS = {
    "called": {
        "default": (
            "Token {token}. Please proceed to the {department} department. "
            "Your token is now being called."
        ),
        "template_a": "Patient {token}, kindly proceed to the {department}.",
        "template_b": "Now serving token {token}. Please visit the {department}.",
    },
    "waiting": {
        "default": (
            "Token {token}. You are waiting for the {department} department. "
            "We will notify you when your turn is near."
        ),
        "template_a": (
            "Patient {token}, you are in the queue for {department}. "
            "Please wait for your turn."
        ),
        "template_b": (
            "Token {token} is waiting for {department}. "
            "We will announce when it is your turn."
        ),
    },
    "completed": {
        "default": "Token {token}. Your consultation is complete. Thank you.",
        "template_a": "Patient {token}, your consultation at {department} is complete. Thank you.",
        "template_b": "Token {token} completed. Thank you for visiting {department}.",
    },
    "cancelled": {
        "default": (
            "Token {token}. This visit has been cancelled. "
            "Please contact the hospital staff for assistance."
        ),
        "template_a": (
            "Patient {token}, your visit for {department} has been cancelled. "
            "Please contact hospital staff."
        ),
        "template_b": (
            "Token {token} cancelled for {department}. "
            "Please speak with hospital staff for assistance."
        ),
    },
    "pre_announcement": {
        "default": (
            "Token {token}. Your turn is approaching. "
            "Please be ready to proceed to the {department} department."
        ),
        "template_a": (
            "Patient {token}, your turn for {department} is approaching. Please be ready."
        ),
        "template_b": (
            "Token {token} will be called soon at {department}. Please stay nearby."
        ),
    },
}

SELECTION_LABELS = {
    "default": "Default",
    "template_a": "Template A",
    "template_b": "Template B",
    "custom": "Custom",
}


def is_hospital_flash() -> bool:
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "hospital_flash"


def empty_announcement_templates() -> dict:
    return {}


def normalize_announcement_templates(raw) -> dict:
    """
    Validate and normalize persisted announcement_templates JSON.

    Unknown types/keys are dropped. Invalid selections fall back to "default".
    Empty / non-dict input yields {}.
    """
    if not isinstance(raw, dict) or not raw:
        return {}

    normalized = {}
    for ann_type in ANNOUNCEMENT_TYPES:
        entry = raw.get(ann_type)
        if not isinstance(entry, dict):
            continue

        selected = str(entry.get("selected") or "default").strip().lower()
        if selected not in VALID_SELECTIONS:
            selected = "default"

        custom_text = entry.get("custom_text", "")
        if custom_text is None:
            custom_text = ""
        else:
            custom_text = str(custom_text).strip()

        # Persist only when something differs from implicit defaults.
        if selected == "default" and not custom_text:
            continue

        normalized[ann_type] = {
            "selected": selected,
            "custom_text": custom_text,
        }

    return normalized


def get_vendor_announcement_templates(vendor) -> dict:
    """Return normalized templates from vendor.config, or {} when unset/unavailable."""
    if not vendor:
        return {}
    config = getattr(vendor, "config", None)
    if config is None:
        return {}
    raw = getattr(config, "announcement_templates", None)
    return normalize_announcement_templates(raw)


def resolve_builtin_template(announcement_type: str, selection: str) -> str | None:
    """Return builtin template string for template_a/template_b, else None."""
    builtins = HOSPITAL_ANNOUNCEMENT_BUILTINS.get(announcement_type) or {}
    if selection in ("template_a", "template_b"):
        return builtins.get(selection)
    return None


def catalog_for_admin() -> dict:
    """Payload for Company Admin Configurations (hospital_flash only)."""
    types = []
    for ann_type in ANNOUNCEMENT_TYPES:
        builtins = HOSPITAL_ANNOUNCEMENT_BUILTINS[ann_type]
        types.append(
            {
                "id": ann_type,
                "label": ann_type.replace("_", " ").title(),
                "options": [
                    {
                        "id": "default",
                        "label": SELECTION_LABELS["default"],
                        "text": builtins["default"],
                    },
                    {
                        "id": "template_a",
                        "label": SELECTION_LABELS["template_a"],
                        "text": builtins["template_a"],
                    },
                    {
                        "id": "template_b",
                        "label": SELECTION_LABELS["template_b"],
                        "text": builtins["template_b"],
                    },
                    {
                        "id": "custom",
                        "label": SELECTION_LABELS["custom"],
                        "text": "",
                    },
                ],
            }
        )
    return {
        "types": types,
        "placeholders": ["{token}", "{department}"],
        "preview_token": "101",
        "preview_department": "Lab",
    }
