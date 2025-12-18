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
        "outlet_update":"Outlet Update",
        "order_update": "Order Update",
        "total_orders":"Total Orders",
        "order_details":"Orders Details",
        "configurations":"Configurations"
    },
    "dashboard": {
        "title": "Dashboard",
        "body": "You can manage companies and view analytics from here.",
    },
    "company_dashboard": {
        "title": "Dashboard",
    },
    "outlet_list":{
        "title":"You can manage companies from here."
    },
    "outlet_update": {
        "outlet_name": "Outlet Name",
        "outlet_alias_name": "Outlet Alias Name",
        "button":"Update Outlet Data"
    },
    "create_user":{
        "outlet":"Outlet",
        "select_outlet":"Select Outlet"
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
        "outlet_update":"Update Outlet Data",
        "order_update": "Order Update",
        "total_orders":"Total Orders",
        "order_details":"Orders Details",
        "configurations":"Configurations"
    },
    "dashboard": {
        "title": "Food Flash Dashboard",
        "body": "You can manage companies and view analytics from here.",
    },
    "company_dashboard": {
        "title": "Company Dashboard",
    },
    "outlet_list":{
        "title":"You can manage outlets from here."
    },
    "outlet_update": {
        "outlet_name": "Outlet Name",
        "outlet_alias_name": "Outlet Alias Name",
        "button":"Update Outlet Data"
    },
    "create_user":{
        "outlet":"Outlet",
        "select_outlet":"Select Outlet"
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
    "select_outlet_modal": {
        "title": "Select Outlet",
        "instruction": "Please select your outlet to proceed.",
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
        "outlet_update":"Update Airport Data",
        "order_update": "Flight Update",
        "total_orders":"Total Passengers",
        "order_details":"Passenger Details",
        "configurations":"Configurations"
    },
    "dashboard": {
        "title": "Airline Flash Dashboard",
        "body": "You can manage Airports and view analytics from here.",
    },
    "company_dashboard": {
        "title": "Airline Dashboard",
    },
    "outlet_list":{
        "title":"You can manage airports from here."
    },
    "outlet_update": {
        "outlet_name": "Airport Name",
        "outlet_alias_name": "Airport Alias Name",
        "button":"Update Airport Data"
    },
    "create_user":{
        "outlet":"Airport",
        "select_outlet":"Select Airport"
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
    "select_outlet_modal": {
        "title": "Select Airport",
        "instruction": "Please select your airport to proceed.",
    },
}
# ----------------------------
# Airline Flash Label Configuration
# ----------------------------
DINE_FLASH = {
    "sidebar": {
        "dashboard": "Dashboard",
        "company": "Restaurant",
        "register_company": "Register Restaurant",
        "company_list": "Restaurant List",
        "create_outlet": "Create Outlet",
        "outlet_list": "Outlet List",
        "outlet_update":"Update Outlet Data",
        "order_update": "Table Allot",
        "total_orders":"Total Bookings",
        "order_details":"Booking Details",
        "configurations":"Configurations"
    },
    "dashboard": {
        "title": "Dine Flash Dashboard",
        "body": "You can manage companies and view analytics from here.",
    },
    "company_dashboard": {
        "title": "Company Dashboard",
    },
    "outlet_list":{
        "title":"You can manage outlets from here."
    },
    "outlet_update": {
        "outlet_name": "Outlet Name",
        "outlet_alias_name": "Outlet Alias Name",
        "button":"Update Outlet Data"
    },
    "create_user":{
        "outlet":"Outlet",
        "select_outlet":"Select Outlet"
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
    "select_outlet_modal": {
        "title": "Select Outlet",
        "instruction": "Please select your outlet to proceed.",
    },
}



# ----------------------------
# Mapping of Project Key → Labels
# ----------------------------
LABELS = {
    "default": DEFAULT,
    "food_flash": FOOD_FLASH,
    "airline_flash": AIRLINE_FLASH,
    "dine_flash":DINE_FLASH
}
