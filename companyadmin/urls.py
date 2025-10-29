from django.urls import path
from .import views

urlpatterns = [
    path('api/register-company/', views.register_company, name='register-company'),
    path('api/company_lists/', views.company_lists, name='company_lists'),
    path('registration/', views.registration, name='registration'),
    path('company_lists/', views.companies, name='company_lists'),
    path('create_outlet/', views.create_outlet, name='create_outlet'),
    path('outlet_lists/', views.outlet_lists, name='outlet_lists'),
    path('api/outlets/', views.all_outlets, name='all_outlets'),
    path('api/create_vendor/', views.create_vendor, name='create_vendor'),
    path('api/update_company_id/<int:id>/', views.update_company_id, name='update_company_id'),
    path('api/update_company/', views.update_company, name='update_company'),
    path('api/product-registration/', views.product_registration, name='product-registration'),
    path('api/product-authentication/', views.product_authentication, name='product-authentication'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('order_update/', views.order_update, name='order_update'),
    path('api/get_outlet_creation_data/<int:customer_id>/', views.get_outlet_creation_data, name='get_outlet_creation_data'),
]
 