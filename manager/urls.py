from django.urls import path
from .import views
from . import buffet_views
from . import hospital_views

urlpatterns = [
    path('api/create_order/', views.create_order_by_manager,name='create_order_by_manager'),
    path('api/get_today_orders/', views.get_today_orders, name='get_today_orders'),
    path('api/get_passengers_list/',views.get_passengers_list,name='get_passengers_list'),
    path('api/get_active_passengers_list/',views.get_active_passengers_list,name='get_active_passengers_list'),
    path('api/manager_order_update/', views.manager_order_update, name='manager_order_update'),
    path('api/manager_passenger_update/', views.manager_passenger_update, name='manager_passenger_update'),
    path('api/chat_history/',views.chat_history,name='chat_history'),
    path('api/device_call/', views.device_call, name='device_call'),
    path('api/get_suggestions/', views.get_suggestions, name='get_suggestion_messages'),
    path('api/get_recent_tokens/', views.get_recent_tokens, name='get_recent_tokens'),
    ## DineFlash-specific-urls
    path('api/book_table/',views.book_table,name='book_table'),
    path('api/utility_list/',views.manager_utility_list,name='utility_list'),
    path('api/get_booking_list/',views.get_booking_list,name='get_booking_list'),
    path('api/get_allocated_booking_list/',views.get_allocated_booking_list,name='get_allocated_booking_list'),
    path('api/manager_booking_update/', views.manager_booking_update, name='manager_booking_update'),
    path('api/manager_patient_update/', hospital_views.manager_patient_update, name='manager_patient_update'),
    path('api/manager_patient_message/', hospital_views.manager_patient_message, name='manager_patient_message'),
    path('api/hospital_create_order/', hospital_views.hospital_create_order, name='hospital_create_order'),
    path('api/get_active_customers_list/',views.get_active_customers_list,name='get_active_customers_list'),
    path('api/get_contact_list/',views.get_contact_list,name='get_contact_list'),
    
    # DineFlash Buffet System URLs
    path('api/buffet_create_order/', buffet_views.buffet_create_order, name='buffet_create_order'),
    path('api/buffet_assigned_utilities/', buffet_views.get_assigned_buffet_utilities, name='buffet_assigned_utilities'),
    path('api/buffet_kitchen_items/', buffet_views.get_buffet_kitchen_items, name='buffet_kitchen_items'),
    path(
        'api/buffet_update_item_status/',
        buffet_views.buffet_update_item_status,
        name='buffet_update_item_status',
    ),
    path('api/buffet_mark_booking_delivered/', buffet_views.mark_booking_delivered, name='buffet_mark_booking_delivered'),
    path(
        'api/buffet_utilities_orders_summary/',
        buffet_views.buffet_utilities_orders_summary,
        name='buffet_utilities_orders_summary',
    ),
]
