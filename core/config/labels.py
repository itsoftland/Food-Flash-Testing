"""
core/config/labels.py

Centralized label configuration for multi-flavour projects.
Used by context processors to dynamically inject flavour-specific
labels into templates (e.g., Food Flash, Airline Flash).
"""

# ----------------------------
# Default Label Configuration
# ----------------------------
DEFAULT = {
    "sidebar": {
        "dashboard": "Dashboard",
        "company": "Company",
        "register_company": "Register Company",
        "company_list": "Company List",
        "create_outlet": "Create Outlet",
        "outlet_list": "Outlet List",
        "order_update": "Order Update",
    },
    "dashboard": {
        "title": "Dashboard",
    },
    "registration": {
        "title": "Company Registration",
        "company_name": "Company Name",
        "contact_phone": "Contact Number",
        "email": "Company Email",
        "gst": "GST",
        "contact_person": "Contact Person",
        "contact_phone": "Contact Phone Number",
        "address1": "Company Address 1",
        "address2": "Company Address 2",
        "state": "State",
        "city": "City",
        "username": "Username",
        "password": "Password",
        "submit_button": "Register Company",
    },
}


# ----------------------------
# Food Flash Label Configuration
# ----------------------------
FOOD_FLASH = {
    "sidebar": {
        "dashboard": "Dashboard",
        "company": "Restaurant",
        "register_company": "Register Restaurant",
        "company_list": "Restaurant List",
        "create_outlet": "Create Outlet",
        "outlet_list": "Outlet List",
        "order_update": "Order Update",
    },
    "dashboard": {
        "title": "Food Flash Dashboard",
    },
    "registration": {
        "title": "Restaurant Registration",
        "company_name": "Restaurant Name",
        "contact_phone": "Contact Number",
        "email": "Restaurant Email",
        "gst": "GST Number",
        "contact_person": "Manager Name",
        "contact_manager_phone": "Manager Contact Number",
        "address1": "Restaurant Address 1",
        "address2": "Restaurant Address 2",
        "state": "State",
        "city": "City",
        "username": "Username",
        "password": "Password",
        "submit_button": "Register Restaurant",
    },
}


# ----------------------------
# Airline Flash Label Configuration
# ----------------------------
AIRLINE_FLASH = {
    "sidebar": {
        "dashboard": "Dashboard",
        "company": "Airline",
        "register_company": "Register Airline",
        "company_list": "Airline List",
        "create_outlet": "Add Airport",
        "outlet_list": "Airport List",
        "order_update": "Flight Update",
    },
    "dashboard": {
        "title": "Airline Flash Dashboard",
    },
    "registration": {
        "title": "Airline Registration",
        "company_name": "Airline Name",
        "contact_phone": "Contact Number",
        "email": "Airline Email",
        "gst": "GST / Tax ID",
        "contact_person": "Ground Manager",
        "contact_manager_phone": "Manager Contact Number",
        "address1": "Head Office Address 1",
        "address2": "Head Office Address 2",
        "state": "State",
        "city": "City",
        "username": "Username",
        "password": "Password",
        "submit_button": "Register Airline",
    },
}


# ----------------------------
# Mapping of Project Key → Labels
# ----------------------------
LABELS = {
    "default": DEFAULT,
    "food_flash": FOOD_FLASH,
    "airline_flash": AIRLINE_FLASH,
}
