"""
core/config/status_choices.py

Centralized status configuration for multi-flavour projects.

Overview:
    This module provides a unified configuration for order or process
    status definitions across different project flavours such as
    Food Flash and Airline Flash. Each project flavour has its own
    terminology and logical flow, but all are managed from this
    single file to ensure consistent access and maintainability.

Purpose:
    - Keeps all status definitions centralized and flavour-specific.
    - Enables Django models to dynamically load their status choices
      based on the `PROJECT_NAME` setting value.
    - Promotes clarity and maintainability by reducing hardcoded
      status duplication in models and views.
    - Provides a scalable structure for adding future project flavours.

Usage in Models:
    In any model where a status field is needed, dynamically assign
    choices as follows:

        from django.conf import settings
        from core.config.status_choices import STATUS_CHOICES_MAP

        class Order(models.Model):
            STATUS_CHOICES = STATUS_CHOICES_MAP.get(
                getattr(settings, "PROJECT_NAME").lower(), []
            )
            status = models.CharField(
                max_length=20,
                choices=STATUS_CHOICES,
                default='preparing'
            )

Example:
    For PROJECT_NAME = "food_flash":
        → ('preparing', 'Preparing')

    For PROJECT_NAME = "airline_flash":
        → ('boarding_announced', 'Boarding Announced')

Structure:
    STATUS_CHOICES_MAP = {
        "<project_key>": [
            (<machine_value>, <human_readable_label>),
            ...
        ]
    }

Notes:
    - The left element (<machine_value>) represents the internal code stored in the database.
    - The right element (<human_readable_label>) represents the display text shown in the UI.
    - Add new flavours as new dictionary keys following the same structure.

"""

# -------------------------------------------------------------------
# Centralized Status Definitions for Multi-Flavour Projects
# -------------------------------------------------------------------

STATUS_CHOICES_MAP = {
    # ---------------------------------------------------------------
    # 🍔 FOOD FLASH
    # ---------------------------------------------------------------
    "food_flash": [
        ('created', 'Created'),       # Order created, waiting to start
        ('preparing', 'Preparing'),   # Kitchen is preparing the order
        ('ready', 'Ready'),           # Order is ready for pickup/delivery
        ('delivered', 'Delivered'),   # Customer received the order
        ('cancelled', 'Cancelled'),   # Order cancelled by vendor or user
    ],

    # ---------------------------------------------------------------
    # ✈️ AIRLINE FLASH
    # ---------------------------------------------------------------
    "airline_flash": [
        ('bp_issued', 'B.Pass Issued'),   # Boarding pass generated for passenger
        ('checked_in', 'Checked-In'),            # Passenger has completed check-in
        ('boarding_shortly', 'Boarding Shortly'),# Boarding expected soon
        ('boarding_announced', 'Boarding Announced'), # Boarding officially announced
        ('gate_change', 'Gate Change'),          # Gate updated for the flight
        ('rescheduled', 'Rescheduled'),          # Flight time changed
        ('flightcancel', 'Cancelled'),              # Flight cancelled
    ],
}

# -------------------------------------------------------------------
# End of File
# -------------------------------------------------------------------
