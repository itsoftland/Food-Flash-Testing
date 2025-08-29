from django.urls import path
from . import views

urlpatterns = [
    # path('manage-order/', views.manage_order, name='manage-order'),
    path('api/update-order/', views.update_order, name='update-order'),
    path('api/get-current-time/', views.get_current_time, name='get-current-time'),
    path('api/list-order/', views.list_order, name='list-order'),
    path('api/save-subscription/', views.save_subscription, name='save-subscription'),
    path('api/send-offers/', views.send_offers, name='send-offers'),
    path('api/register_device/', views.register_device, name='register-device'),
    path('api/register_android_device/', views.register_android_device, name='register-android-device'),
    path('api/register_android_apk/', views.register_android_apk, name='register-android-apk'),
]