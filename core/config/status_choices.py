"""
core/config/status_choices.py

Centralized status configuration for multi-flavour projects.

Overview:
    This file defines distinct order or process status choices for each
    project flavour (e.g., Food Flash, Airline Flash). It allows a single
    codebase to handle multiple business domains while presenting
    appropriate terminology in both the backend and UI.

Purpose:
    - Keeps all status definitions centralized and flavour-specific.
    - Enables Django models to dynamically load their status choices
      based on the `PROJECT_NAME` value from settings.
    - Ensures readability and maintainability across flavours.

Usage:
    In models, import and assign dynamically:
        from core.config.status_choices import STATUS_CHOICES_MAP
        STATUS_CHOICES = STATUS_CHOICES_MAP.get(settings.PROJECT_NAME.lower(), [])

    Example:
        For PROJECT_NAME = "food_flash":
            → ('preparing', 'Preparing')

        For PROJECT_NAME = "airline_flash":
            → ('boarding', 'Boarding')

Structure:
    STATUS_CHOICES_MAP = {
        "<project_key>": [
            (<machine_value>, <human_readable_label>),
            ...
        ]
    }

Example in Model:
    class Order(models.Model):
        STATUS_CHOICES = STATUS_CHOICES_MAP.get(getattr(settings, "PROJECT_NAME").lower(), [])
        status = models.CharField(max_length=20, choices=STATUS_CHOICES)
"""

STATUS_CHOICES_MAP = {
    "food_flash": [
        ('created', 'Created'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ],
    "airline_flash": [
        ('waiting', 'Waiting'),
        ('boarding', 'Boarding'),
        ('final_call', 'Proceed to Aircraft'),
        ('departed', 'Departed'),
        ('arrived', 'Arrived'),
        ('cancelled', 'Cancelled'),
    ],
}
