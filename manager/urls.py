from django.urls import path
from .import views
from . import buffet_views

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
    path('api/get_active_customers_list/',views.get_active_customers_list,name='get_active_customers_list'),
    path('api/get_contact_list/',views.get_contact_list,name='get_contact_list'),
    
    # DineFlash Buffet System URLs
    path('api/buffet_kitchen_items/', buffet_views.get_buffet_kitchen_items, name='buffet_kitchen_items'),
    path('api/buffet_mark_item_preparing/', buffet_views.mark_buffet_item_preparing, name='buffet_mark_item_preparing'),
    path('api/buffet_mark_item_ready/', buffet_views.mark_buffet_item_ready, name='buffet_mark_item_ready'),
    path('api/buffet_mark_item_cancelled/', buffet_views.mark_buffet_item_cancelled, name='buffet_mark_item_cancelled'),
    path('api/buffet_mark_item_delivered/', buffet_views.mark_buffet_item_delivered, name='buffet_mark_item_delivered'),
    path('api/buffet_mark_booking_delivered/', buffet_views.mark_booking_delivered, name='buffet_mark_booking_delivered'),
]
