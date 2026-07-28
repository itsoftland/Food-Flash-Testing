from django.contrib import admin
from django.utils.html import format_html
from django.utils.timezone import localtime

from .models import (
    AdminOutlet,TVDeviceConfig,
    Vendor,ArchivedOrderStatusHistory,
    VendorConfig,
    MqttServerConfig,
    Device,
    AndroidDevice,
    AndroidAPK,
    UserProfile,
    Order,AdvertisementSlot,
    PushSubscription,
    Feedback,
    AdvertisementImage,
    AdvertisementProfile,
    AdvertisementProfileAssignment,
    ArchivedOrder,
    ChatMessage,
    WebChatMessage,
    IoTDeviceCredential,
    Utility,OrderStatusHistory,
    UtilityOption,
    BuffetOrderLookup,
    BuffetActiveOrder,
    DineFlashBookingLookup,
)

#
# Admin registrations
#

@admin.register(AdminOutlet)
class AdminOutletAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'customer_email', 'customer_contact_person', 'phone_number', 'customer_id', 'authentication_status', 'last_updated')
    list_filter = ('authentication_status', 'customer_state', 'customer_city')
    search_fields = ('customer_name', 'customer_email', 'customer_contact_person', 'customer_id')
    readonly_fields = ('created_at', 'updated_at')
    list_display_links = ('customer_name',)

    def last_updated(self, obj):
        return localtime(obj.updated_at).strftime("%Y-%m-%d %H:%M")
    last_updated.short_description = 'Updated'


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'alias_name', 'admin_outlet', 'vendor_id', 'location', 'created_at')
    search_fields = ('name', 'alias_name', 'vendor_id', 'location')
    list_filter = ('location',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(VendorConfig)
class VendorConfigAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'timezone', 'tv_communication_mode', 'mqtt_mode', 'business_day_start_hour')
    list_filter = ('timezone', 'tv_communication_mode', 'mqtt_mode')
    search_fields = ('vendor__name',)
    readonly_fields = ()


@admin.register(MqttServerConfig)
class MqttServerConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "host", "port", "username", "qos", "tls")
    search_fields = ("name", "host")
    list_filter = ("tls",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('serial_no', 'vendor', 'admin_outlet', 'created_at')
    list_filter = ('vendor', 'admin_outlet')
    search_fields = ('serial_no',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AndroidDevice)
class AndroidDeviceAdmin(admin.ModelAdmin):
    list_display = ('mac_address', 'vendor', 'admin_outlet', 'created_at')
    list_filter = ('vendor', 'admin_outlet')
    search_fields = ('mac_address',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AndroidAPK)
class AndroidAPKAdmin(admin.ModelAdmin):
    list_display = ('token', 'apk_version', 'mac_address', 'admin_outlet', 'user_profile', 'created_at')
    search_fields = ('token', 'mac_address',)
    list_filter = ('apk_version',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'role', 'admin_outlet', 'vendor')
    search_fields = ('user__username', 'name')
    list_filter = ('role',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Order)
class OrdersAdmin(admin.ModelAdmin):
    list_display = ('token_no', 'vendor', 'admin_outlet', 'device', 'counter_no', 'status', 'updated_by', 'notified_at', 'created_at')
    list_filter = ('status', 'vendor', 'updated_by')
    search_fields = ('token_no',)
    readonly_fields = ('created_at', 'updated_at')
    
    def admin_outlet(self, obj):
        return obj.vendor.admin_outlet if obj.vendor and hasattr(obj.vendor, 'admin_outlet') else None
    admin_outlet.short_description = 'Admin Outlet'


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'browser_id', 'endpoint_short', 'created_at')
    search_fields = ('browser_id', 'endpoint')
    readonly_fields = ('created_at', 'updated_at')

    def endpoint_short(self, obj):
        if not obj.endpoint:
            return '-'
        ep = obj.endpoint
        return ep if len(ep) < 60 else f"{ep[:57]}..."
    endpoint_short.short_description = 'Endpoint'


@admin.register(BuffetOrderLookup)
class BuffetOrderLookupAdmin(admin.ModelAdmin):
    list_display = ('id', 'order_lookup_id', 'order', 'token_no', 'created_at', 'updated_at')
    search_fields = ('order_lookup_id', 'order__token_no')
    readonly_fields = ('created_at', 'updated_at')

    def token_no(self, obj):
        return obj.order.token_no if obj.order_id else None
    token_no.short_description = 'Token No'


@admin.register(BuffetActiveOrder)
class BuffetActiveOrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order_lookup_id',
        'token_no',
        'vendor_id',
        'order',
        'created_at',
        'updated_at',
    )
    search_fields = ('order_lookup_id', 'token_no', 'vendor_id')
    list_filter = ('vendor_id',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DineFlashBookingLookup)
class DineFlashBookingLookupAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'order_lookup_id',
        'order',
        'booking_no',
        'created_at',
        'updated_at',
    )
    search_fields = ('order_lookup_id', 'order__table_booking_no')
    readonly_fields = ('created_at', 'updated_at')

    def booking_no(self, obj):
        return obj.order.table_booking_no if obj.order_id else None
    booking_no.short_description = 'Booking No'


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'feedback_type', 'category', 'want_to_reach_us', 'name', 'created_at')
    list_filter = ('feedback_type', 'category', 'want_to_reach_us')
    search_fields = ('vendor__name', 'name', 'comment')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AdvertisementImage)
class AdvertisementImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'admin_outlet', 'image_preview', 'uploaded_at')
    readonly_fields = ('created_at', 'updated_at')

    def image_preview(self, obj):
        if not obj.image:
            return "(no image)"
        return format_html('<img src="{}" style="height:60px; object-fit:cover; border-radius:4px" />', obj.image.url)
    image_preview.short_description = 'Image'


@admin.register(AdvertisementProfile)
class AdvertisementProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'admin_outlet', 'date_start', 'date_end', 'priority', 'is_active_today')
    search_fields = ('name', 'admin_outlet__customer_name')
    list_filter = ('priority',)
    readonly_fields = ('created_at',)

    def is_active_today(self, obj):
        return obj.is_active_today()
    is_active_today.boolean = True
    is_active_today.short_description = 'Active Today'


@admin.register(AdvertisementProfileAssignment)
class AdvertisementProfileAssignmentAdmin(admin.ModelAdmin):
    list_display = ('profile', 'vendor', 'assigned_at')
    search_fields = ('profile__name', 'vendor__name')
    readonly_fields = ('assigned_at',)


@admin.register(ArchivedOrder)
class ArchivedOrderAdmin(admin.ModelAdmin):
    list_display = ('original_order_id', 'vendor', 'token_no', 'status', 'archived_at')
    search_fields = ('original_order_id',)
    readonly_fields = ('archived_at',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('message_id', 'vendor', 'sender', 'token_no', 'created_date', 'created_at', 'is_audio')
    search_fields = ('message_text',)
    list_filter = ('vendor', 'sender')
    readonly_fields = ('created_at',)


@admin.register(WebChatMessage)
class WebChatMessageAdmin(admin.ModelAdmin):
    list_display = ('message_id', 'vendor', 'sender', 'token_no', 'timestamp', 'is_read')
    search_fields = ('text',)
    list_filter = ('vendor',)
    readonly_fields = ('timestamp',)


@admin.register(IoTDeviceCredential)
class IoTDeviceCredentialAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'android_device', 'vendor', 'created_at', 'updated_at')
    search_fields = ('device_id',)
    list_filter = ('vendor',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Utility)
class UtilityAdmin(admin.ModelAdmin):
    list_display = (
        'utility_name',
        'display_name',
        'display_code',
        'vendor',
        'token_mode',
        'prefix',
        'is_active',
        'created_at',
    )

    list_filter = (
        'vendor',
        'token_mode',
        'is_active',
    )

    search_fields = (
        'utility_name',
        'display_name',
        'display_code',
        'vendor__name',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
    )

    list_display_links = ('utility_name',)

    ordering = ('-created_at',)

@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'previous_status',
        'new_status',
        'changed_by',
        'processing_time_seconds',
        'changed_at',
    )

    list_filter = (
        'new_status',
        'changed_by',
        'previous_status',
        'order__vendor',
    )

    search_fields = (
        'order__token_no',
        'previous_status',
        'new_status',
    )

    readonly_fields = (
        'changed_at',
    )

    ordering = ('-changed_at',)

@admin.register(TVDeviceConfig)
class TVDeviceConfigAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'admin_outlet',
        'show_qr',
        'qr_alignment',
        'items_to_show',
        'utility_name_mode',
        'screen_orientation',
        'created_at',
    )

    list_filter = (
        'show_qr',
        'qr_alignment',
        'utility_name_mode',
        'screen_orientation',
        'admin_outlet',
    )

    search_fields = (
        'admin_outlet__customer_name',
        'id',
    )

    filter_horizontal = ('utilities',)

    readonly_fields = (
        'created_at',
        'updated_at',
    )

    ordering = ('-created_at',)

@admin.register(AdvertisementSlot)
class AdvertisementSlotAdmin(admin.ModelAdmin):
    list_display = ("profile", "start_time", "end_time")
    list_filter = ("profile",)
    search_fields = ("profile__name",)

@admin.register(ArchivedOrderStatusHistory)
class ArchivedOrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("archived_order", "previous_status", "new_status", "changed_by", "changed_at")
    list_filter = ("new_status", "changed_by")
    search_fields = ("archived_order__id", "previous_status", "new_status", "changed_by")
    ordering = ("-changed_at",)

@admin.register(UtilityOption)
class UtilityOptionAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'utility',
        'is_active',
        'created_at',
        'updated_at'
    )
    list_filter = (
        'is_active',
        'utility',
    )
    search_fields = (
        'name',
        'utility__display_name',
        'utility__utility_name',
    )
    readonly_fields = (
        'created_at',
        'updated_at',
    )
    ordering = ('-created_at',)
