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
]
