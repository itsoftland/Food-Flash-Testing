"""
core/config/icons.py

Centralized icon configuration for multi-flavour projects.
Used by context processors to dynamically inject flavour-specific
icons into templates (e.g., Food Flash, Airline Flash).
"""

# ----------------------------
# Default Icon Configuration
# ----------------------------
DEFAULT = {
    "sidebar": {
        "outlet_list": "fas fa-store",
        "configurations": "fas fa-cogs",
    }
}

# ----------------------------
# Food Flash Icon Configuration
# ----------------------------
FOOD_FLASH = {
    "sidebar": {
        "outlet_list": "fas fa-store",
        "configurations": "fas fa-cogs",
    }
}

# ----------------------------
# Airline Flash Icon Configuration
# ----------------------------
AIRLINE_FLASH = {
    "sidebar": {
        "outlet_list": "fas fa-plane-departure",
        "configurations": "fas fa-cogs",
    }
}


# ----------------------------
# DINE Flash Icon Configuration
# ----------------------------
DINE_FLASH = {
    "sidebar": {
        "outlet_list": "fas fa-store",
        "configurations": "fas fa-cogs",
    }
}

# ----------------------------
# Mapping of Project Key → Icon Sets
# ----------------------------
ICONS = {
    "default": DEFAULT,
    "food_flash": FOOD_FLASH,
    "airline_flash": AIRLINE_FLASH,
    "dine_flash":DINE_FLASH
}
