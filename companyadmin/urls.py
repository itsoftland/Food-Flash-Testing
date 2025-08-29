from django.urls import path
from .import views

urlpatterns = [
    path('api/register-company/', views.register_company, name='register-company'),
    path('registration/', views.registration, name='registration'),
    path('api/product-registration/', views.product_registration, name='product-registration'),
    path('api/product-authentication/', views.product_authentication, name='product-authentication'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('order_update/', views.order_update, name='order_update'),
]
