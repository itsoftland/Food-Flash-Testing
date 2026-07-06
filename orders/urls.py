from django.urls import path
from .import views
from . import buffet_views
from . import hospital_views
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView       # For refreshing access token
)

urlpatterns = [
    path('home/', views.home, name='home'),
    path('vibration_test/', views.vibration_test, name='vibration_test'),
    # path('token_display/',views.token_display,name='token_display'),
    # path('api/get_recent_orders/',views.get_recent_ready_orders,name='get_recent_orders'),
    path('', views.outlet_selection, name="outlet_selection"),
    path('check-status/', views.check_status, name='check_status'),
    path('api/outlets/', views.get_outlets, name="get_outlets"),
    path('api/get_vendor_logos/', views.get_vendor_logos, name='get_vendor_logos'),
    path('api/get_vendor_ads/', views.get_vendor_ads, name='get_vendor_ads'),
    path('api/get_banners/', views.get_banners, name='get_banners'),
    path('api/menus/', views.get_vendor_menus, name='get_vendor_menu'),
    path('api/submit_feedback/', views.submit_feedback, name='submit-feedback'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/login/', views.login_api_view, name='login_api_view'), 
    path('api/logout/', views.logout_api_view, name='logout_api_view'),
    path('login/', views.login_view, name='login_view'),
    path('logout/', views.logout_view, name='logout'),
    path('outlet_dashboard/', views.outlet_dashboard, name='outlet_dashboard'),
    path('api/company-update/', views.update_admin_outlet, name='company_update_api'),
    path('api/webchat-messages/', views.webchat_messages, name='webchat_messages_api'),  # New endpoint for webchat messages
    path('api/webchat-messages-create/', views.webchat_message_create, name='webchat_message_create'),  # New endpoint to create message
    path('api/mark-messages-read/<int:vendor_id>/', views.mark_webchat_messages_read, name='mark_webchat_messages_read'),  # New endpoint to mark messages as read
    path("manifest.json", views.manifest, name="manifest"),
    # AirlineFlash-specific-urls
    path('public_register/',views.public_register,name='public_register'),
    path('api/public_create_passenger/',views.public_create_passenger,name='public_create_passenger'),
    # path('api/decode_boarding_pass/', views.decode_boarding_pass, name='decode_boarding_pass'),
    # DineFlash-specific-urls
    path('table_booking/',views.table_booking,name='table_booking'),
    path('api/dine_flash_qr_exchange/', views.dine_flash_qr_exchange, name='dine_flash_qr_exchange'),
    path(
        'api/dine_flash/resolve_booking/',
        views.resolve_booking,
        name='dine_flash_resolve_booking'
    ),
    path('api/book_table/',views.book_table,name='book_table'),
    path('api/utility_list/',views.utility_list,name='utility_list'),
    # ⚠️ TEMP DIAGNOSTIC (iOS push-delivery chain). Remove with the `[diag]` logs.
    path('api/dine_flash_client_diag/', views.dine_flash_client_diag, name='dine_flash_client_diag'),
    # DineFlash Buffet System URLs
    path('api/buffet_submit_order/', buffet_views.buffet_submit_order, name='buffet_submit_order'),
    path('api/buffet/utility-login/', buffet_views.buffet_utility_login, name='buffet_utility_login'),
    path('buffet/table_booking/', buffet_views.buffet_table_booking, name='buffet_table_booking'),
    path('buffet/utility_selection/', buffet_views.buffet_utility_selection, name='buffet_utility_selection'),
    path('buffet/combined_options/', buffet_views.buffet_combined_options, name='buffet_combined_options'),
    path('buffet/order_confirmation/', buffet_views.buffet_order_confirmation, name='buffet_order_confirmation'),
    # Hospital Flash URLs
    path(
        'hospital/patient_registration/',
        hospital_views.hospital_patient_registration,
        name='hospital_patient_registration',
    ),
    path(
        'hospital/department_selection/',
        hospital_views.hospital_department_selection,
        name='hospital_department_selection',
    ),
    path(
        'hospital/registration_confirmation/',
        hospital_views.hospital_registration_confirmation,
        name='hospital_registration_confirmation',
    ),
    path(
        'api/hospital_patient_submit/',
        hospital_views.hospital_patient_submit,
        name='hospital_patient_submit',
    ),
]
