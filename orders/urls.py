from django.urls import path
from .import views
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView       # For refreshing access token
)

urlpatterns = [
    path('home/', views.home, name='home'),
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
    # Airline-specific-urls
    path('public_register/',views.public_register,name='public_register'),
    path('api/public_create_passenger/',views.public_create_passenger,name='public_create_passenger'),
    path('api/decode_boarding_pass/', views.decode_boarding_pass, name='decode_boarding_pass'),
]
