"""
Centralized role configuration for multi-flavour projects.
This file provides backend → frontend roles mapping.
"""

ROLES = {
    "food_flash": {
        "admin_manager": "Admin Manager",
        "outlet_manager": "Outlet Manager",
        "outlet_staff": "Outlet Staff",
        "web_user": "Web Manager",
    },

    "airline_flash": {
        # "airline_manager": "Airline Manager",
        # "gate_manager": "Gate Manager",
        "airport_manager": "Airport Manager",
        # "web_user": "Airline Web Manager",
    },
    "dine_flash": {
        "outlet_manager": "Outlet Manager",
    },
}
