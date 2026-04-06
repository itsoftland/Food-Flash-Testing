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
    path('create_utility/', views.create_utility, name='create_utility'),
    path('manage_utilities/', views.manage_utilities, name='manage_utilities'),
    path('utility_user_mapping/', views.utility_user_mapping, name='utility_user_mapping'),
    path('api/get_all_utilities/', views.get_all_utilities, name='get_all_utilities'),
    path('api/get_all_users/', views.get_all_users, name='get_all_users'),
    path('api/update_user_utilities_sa/', views.update_user_utilities_sa, name='update_user_utilities_sa'),
    path('api/update_utility_status_sa/', views.update_utility_status_sa, name='update_utility_status_sa'),
    path('api/update_utility_sa/', views.update_utility_sa, name='update_utility_sa'),
    path('api/create_utility_option_sa/<int:utility_id>/', views.create_utility_option_sa, name='create_utility_option_sa'),
    path('api/update_utility_option_sa/<int:option_id>/', views.update_utility_option_sa, name='update_utility_option_sa'),
    path('api/delete_utility_option_sa/<int:option_id>/', views.delete_utility_option_sa, name='delete_utility_option_sa'),
    path('api/get_outlet_creation_data/<int:customer_id>/', views.get_outlet_creation_data, name='get_outlet_creation_data'),
    path('api/get_outlet_creation_data/<int:customer_id>/', views.get_outlet_creation_data, name='get_outlet_creation_data'),
]
 