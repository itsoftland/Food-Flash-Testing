"""
core/config/status_choices.py

Centralized status configuration for multi-flavour projects.

Overview:
    This module provides a unified configuration for order or process
    status definitions across different project flavours such as
    Food Flash, Airline Flash, and Dine Flash. Each project flavour has
    its own terminology and logical flow, but all definitions are
    maintained in this single location to ensure consistency.

Purpose:
    - Keeps all status definitions centralized and flavour-specific.
    - Enables Django models to dynamically load their status choices
      based on the `PROJECT_NAME` setting value.
    - Reduces hardcoded duplication across models and views.
    - Provides a scalable structure for new flavours.

Usage in Models:
    In any model needing a status field:

        from django.conf import settings
        from core.config.status_choices import STATUS_CHOICES_MAP

        class Order(models.Model):
            STATUS_CHOICES = STATUS_CHOICES_MAP.get(
                getattr(settings, "PROJECT_NAME").lower(), []
            )
            status = models.CharField(
                max_length=30,
                choices=STATUS_CHOICES,
                default='created'
            )

Example:
    For PROJECT_NAME = "food_flash":
        → ('preparing', 'Preparing')

    For PROJECT_NAME = "airline_flash":
        → ('boarding_announced', 'Boarding Announced')

    For PROJECT_NAME = "dine_flash":
        → ('waiting', 'Allocation Pending')

Structure:
    STATUS_CHOICES_MAP = {
        "<project_key>": [
            (<machine_value>, <human_readable_label>),
            ...
        ]
    }

Notes:
    - <machine_value> is stored in the database.
    - <human_readable_label> is shown in UI.
    - New flavours can be added by defining a new key and choices list.
"""

# -------------------------------------------------------------------
# Centralized Status Definitions for Multi-Flavour Projects
# -------------------------------------------------------------------

STATUS_CHOICES_MAP = {
    # ---------------------------------------------------------------
    # 🍔 FOOD FLASH
    # ---------------------------------------------------------------
    "food_flash": [
        ('created', 'Created'),          # Order created
        ('preparing', 'Preparing'),      # Kitchen preparing the order
        ('ready', 'Ready'),              # Order is ready for delivery/pickup
        ('delivered', 'Delivered'),      # Customer received the order
        ('cancelled', 'Cancelled'),      # Order cancelled
    ],

    # ---------------------------------------------------------------
    # ✈️ AIRLINE FLASH
    # ---------------------------------------------------------------
    "airline_flash": [
        ('bp_issued', 'B.Pass Issued'),          # Boarding pass generated
        ('checked_in', 'Checked-In'),            # Passenger checked in
        ('boarding_shortly', 'Boarding Shortly'),
        ('boarding_announced', 'Boarding Announced'),
        ('gate_change', 'Gate Change'),          # Gate updated
        ('rescheduled', 'Rescheduled'),          # Flight timing changed
        ('flightcancel', 'Cancelled'),           # Flight cancelled
    ],

    # ---------------------------------------------------------------
    # 🍽️ DINE FLASH
    # ---------------------------------------------------------------
    # Additional keys are standardized for internal usage
    # Right side labels are shown in UI
    # ---------------------------------------------------------------
    "dine_flash": [
        ('created', 'Request Created'),          # Customer request submitted
        ('waiting', 'Allocation Pending'),        # Waiting for table allocation
        ('allocated', 'Allocated'),                # Table allocated
        ('occupied', 'Occupied'),                 # Customer seated / table in use
        ('booking_cancelled', 'Booking Cancelled'), # Booking cancelled
        ('operation_closed', 'Close Operation'),   # Operation closed for the day or seat closure
    ],
}

# -------------------------------------------------------------------
# End of File
# -------------------------------------------------------------------
