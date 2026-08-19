from django.db import models
import json
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator, FileExtensionValidator
from django.utils import timezone
import uuid
import pytz
from django.db.models.signals import post_save
from static.utils.functions.utils import get_vendor_current_time,get_default_closing_message
from django.conf import settings     
from core.config.status_choices import STATUS_CHOICES_MAP

class CustomManager(models.Manager):
    def bulk_create(self, objs, **kwargs):
        # Call the original bulk_create method to insert objects
        created_objs = super().bulk_create(objs, **kwargs)

        # Manually dispatch post_save signal for each created object
        for obj in created_objs:
            post_save.send(sender=obj.__class__, instance=obj, created=True)

        return created_objs 

class MqttServerConfig(models.Model):
    name = models.CharField(max_length=100, help_text="Friendly name for MQTT server")
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=1883)
    username = models.CharField(max_length=400, blank=True, null=True)
    password = models.CharField(max_length=400, blank=True, null=True)
    qos = models.PositiveSmallIntegerField(default=0)
    tls = models.BooleanField(default=False, help_text="Use TLS for secure connection")

    def __str__(self):
        return f"{self.name} ({self.host}:{self.port})"

class AdminOutlet(models.Model):  
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='admin_outlet',
        null=True, blank=True
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    gst_number = models.CharField(max_length=100, blank=True, null=True)
    customer_name = models.CharField(max_length=255, blank=True, null=True,db_index=True)
    customer_contact_person = models.CharField(max_length=255, blank=True, null=True)
    customer_address = models.TextField(blank=True, null=True)
    customer_address2 = models.TextField(blank=True, null=True)
    customer_city = models.CharField(max_length=100, blank=True, null=True)
    customer_state = models.CharField(max_length=100, blank=True, null=True)
    customer_contact = models.CharField(max_length=20, blank=True, null=True)
    authentication_status = models.CharField(max_length=50, default='Pending')
    product_registration_id = models.IntegerField(blank=True, null=True)
    unique_identifier = models.CharField(max_length=100, blank=True, null=True)
    customer_id = models.IntegerField(blank=True, null=True)
    product_from_date = models.DateTimeField(blank=True, null=True)
    product_to_date = models.DateTimeField(blank=True, null=True)
    total_count = models.CharField(max_length=10, blank=True, null=True)
    project_code = models.CharField(max_length=100, blank=True, null=True)
    web_login_count = models.IntegerField(blank=True, null=True)
    android_tv_count = models.IntegerField(blank=True, null=True)
    android_apk_count = models.IntegerField(blank=True, null=True)
    keypad_device_count = models.IntegerField(blank=True, null=True)
    led_display_count = models.IntegerField(blank=True, null=True)
    outlet_count = models.IntegerField(blank=True, null=True)
    locations = models.JSONField(blank=True, null=True) 
    customer_email = models.EmailField(blank=True, null=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.customer_name

class Vendor(models.Model):
    user = models.OneToOneField(
    User, on_delete=models.CASCADE, related_name='vendor',
    null=True, blank=True
    )
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE, related_name='vendors')
    name = models.CharField(max_length=255)
    alias_name = models.CharField(max_length=255,null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    place_id = models.CharField(max_length=255, blank=True, null=True)
    vendor_id = models.IntegerField(unique=True)
    location_id = models.CharField(max_length=20)  
    logo = models.ImageField(upload_to='vendor_logos/', blank=True, null=True)
    ads = models.TextField(blank=True, null=True)  
    menus = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_ads_list(self):
        return json.loads(self.ads or "[]")

    def get_menus_list(self):
        return json.loads(self.menus or "[]")
    
    def __str__(self):
        return f"{self.name} - {self.admin_outlet.customer_name}"

class VendorConfig(models.Model):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name="config")
    mqtt_server = models.ForeignKey(
        MqttServerConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_configs"
    )
    token_display_limit = models.PositiveIntegerField(default=8)
    tv_communication_mode = models.CharField(
        max_length=20,
        choices=[
            ("MQTT", "Model 1(M)"),
            ("Firebase", "Model 2(F)"),
            ("AZURE_IOT", "Model 3(A)"),
        ],
        default="MQTT"
    )
    mqtt_mode = models.CharField(
        max_length=20,
        choices=[
            ("All", "Broadcast to all TVs"),
            ("Individual", "Individual TV data"),
            # ("keypad", "Keypad-controlled TVs")
        ],
        default="All"
    )
    business_day_start_hour = models.TimeField(null=True, blank=True,default="00:00:00")
    timezone = models.CharField(
        max_length=50,
        choices=[(tz, tz) for tz in pytz.all_timezones], 
        default="UTC"
    )
    auto_delete_hours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Set after how many hours orders should be auto-deleted (min 2 hours)")
    use_utilities = models.BooleanField(default=False)
    # Dine Flash: one expiry setting per outlet/vendor, applied for all TV QR links.
    qr_expiry_minutes = models.PositiveSmallIntegerField(default=5)
    # -----------------------------
    # 🔔 VIBRATION CONFIGURATION
    # -----------------------------
    vibration_enabled = models.BooleanField(
        default=True,
        help_text="Enable or disable vibration for customer notifications"
    )

    vibration_pattern = models.CharField(
        max_length=50,
        default="alert_strong",
        help_text="Vibration pattern key for customer notification alerts"
    )

    vibration_duration = models.PositiveIntegerField(
        default=5,
        help_text="Vibration duration in seconds"
    )
    continuous_booking_counter = models.PositiveIntegerField(default=0)
    phone_number_enabled = models.BooleanField(default=False)
    mr_number_enabled = models.BooleanField(default=False)
    bill_number_enabled = models.BooleanField(default=False)
    closing_message = models.TextField(
        help_text="Custom closing/thank you message",
        default=get_default_closing_message
    )
    # Hospital Flash only: per-type spoken TTS template selection + custom text.
    # Shape: {"called": {"selected": "default"|"template_a"|"template_b"|"custom", "custom_text": "..."}}
    # Empty {} means use hardcoded defaults in the customer PWA (backward compatible).
    announcement_templates = models.JSONField(
        default=dict,
        blank=True,
        help_text="Hospital Flash: spoken announcement template selections (unused by other flavours)",
    )
    # Hospital Flash only: Called chat-card template. Empty => "Please move to {department}".
    called_chat_template = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Hospital Flash: Called chat-card template. Use {department}. "
            "Empty keeps the default: Please move to {department}."
        ),
    )
    # Hospital Flash only: Pre-announcement chat-card notice. Empty => default sentence.
    pre_announcement_chat_template = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Hospital Flash: Pre-announcement chat-card template. Use {minutes}. "
            "Empty keeps the default: You will be called in {minutes} minute(s)."
        ),
    )
    # Hospital Flash only: Completed chat-card text. Empty => "Thank You".
    completed_chat_template = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Hospital Flash: Completed chat-card template. Optional {department}. "
            "Empty keeps the default: Thank You."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Utility(models.Model):

    TOKEN_MODE_CONTINUOUS = "continuous"
    TOKEN_MODE_UTILITY_SPECIFIC = "utility_specific"

    TOKEN_MODE_CHOICES = [
        (TOKEN_MODE_CONTINUOUS, "Continuous"),
        (TOKEN_MODE_UTILITY_SPECIFIC, "Utility Specific"),
    ]

    FOOD_TYPE_VEG = "veg"
    FOOD_TYPE_NON_VEG = "non_veg"
    FOOD_TYPE_CHOICES = [
        (FOOD_TYPE_VEG, "Veg"),
        (FOOD_TYPE_NON_VEG, "Non Veg"),
    ]

    DEPARTMENT_TYPE_INDIVIDUAL = "INDIVIDUAL"
    DEPARTMENT_TYPE_GROUP = "GROUP"
    DEPARTMENT_TYPE_CHOICES = [
        (DEPARTMENT_TYPE_INDIVIDUAL, "Individual Department"),
        (DEPARTMENT_TYPE_GROUP, "Group Department"),
    ]

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name="utilities"
    )

    utility_name = models.CharField(
        max_length=100,
        help_text="Display name shown to system"
    )

    display_name = models.CharField(
        max_length=100,
        help_text="Display name shown to customers"
    )

    display_code = models.CharField(
        max_length=10,
        help_text="Short code used for UI display (e.g., AC, GD, VIP)"
    )

    token_mode = models.CharField(
        max_length=20,
        choices=TOKEN_MODE_CHOICES,
        default=TOKEN_MODE_CONTINUOUS,
        help_text="Controls token numbering behaviour"
    )

    prefix = models.CharField(
        max_length=4,
        blank=True,
        null=True,
        help_text="4-character prefix (e.g., ROM, VIP, OUT)"
    )

    utility_booking_counter = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)

    food_type = models.CharField(
        max_length=10,
        choices=FOOD_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Veg or Non Veg (Dine Flash Buffet only)",
    )

    description = models.TextField(
        blank=True,
        null=True,
        help_text="Optional description for Dine Flash Buffet utilities",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    buffet_utility_image = models.ImageField(
        upload_to="buffet_utilities/%Y/%m",
        blank=True,
        null=True,
        help_text="Uploaded image for Dine Flash Buffet utility display",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"]
            )
        ],
    )

    department_type = models.CharField(
        max_length=20,
        choices=DEPARTMENT_TYPE_CHOICES,
        default=DEPARTMENT_TYPE_INDIVIDUAL,
        help_text="Hospital Flash: individual department or group/package",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Hospital Flash: sort order for department listings",
    )
    approximate_service_time = models.PositiveIntegerField(
        default=0,
        help_text="Hospital Flash: estimated service time in minutes",
    )
    pre_announcement_count = models.PositiveIntegerField(
        default=0,
        help_text="Hospital Flash: number of patients to pre-announce",
    )
    priority_prefix = models.CharField(
        max_length=4,
        blank=True,
        null=True,
        help_text="Hospital Flash: priority prefix (e.g. PL, PA, VIP)",
    )
    group_departments = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="included_in_groups",
        help_text="Hospital Flash: individual departments included in a group/package",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "utility_name"],
                name="unique_utility_name_per_vendor"
            ),
            models.UniqueConstraint(
                fields=["vendor", "display_name"],
                name="unique_display_name_per_vendor"
            ),
            models.UniqueConstraint(
                fields=["vendor", "display_code"],
                name="unique_display_code_per_vendor"
            ),
            models.UniqueConstraint(
                fields=["vendor", "prefix"],
                name="unique_prefix_per_vendor"
            ),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.vendor.name})"


class BuffetUtilityImage(models.Model):
    """Up to 3 images per utility (Dine Flash Buffet only)."""

    utility = models.ForeignKey(
        Utility,
        on_delete=models.CASCADE,
        related_name="buffet_images",
    )
    image = models.ImageField(
        upload_to="buffet_utilities/%Y/%m",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"]
            )
        ],
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Buffet image {self.id} for {self.utility_id}"


class UtilityOption(models.Model):
    utility = models.ForeignKey(Utility, on_delete=models.CASCADE, related_name='options')
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['utility', 'name'], name='unique_option_name_per_utility')
        ]

    def __str__(self):
        return f"{self.name} ({self.utility.display_name})"

class Device(models.Model):
    serial_no = models.CharField(max_length=255)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, related_name="devices",null=True,blank=True)
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE,null=True,blank=True,related_name='device')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('serial_no', 'admin_outlet')

    def __str__(self):
        return self.serial_no
    
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('admin_manager', 'Admin Manager'),
        ('outlet_manager', 'Outlet Manager'),
        ('order_manager', 'Order Manager'),
        ('manager', 'Manager (Android APK)'),
        ('web', 'Web User'),
        ('web_user', 'Web Manager'),
        ('utility_user', 'Utility User (Kitchen)'),
        ('airport_manager', 'Airport Manager'),
        ('outlet_staff', 'Outlet Staff'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_roles')
    name = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE,related_name='user_profiles')
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='user_profile')
    assigned_utilities = models.ManyToManyField(Utility, blank=True, related_name='assigned_users')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

class Order(models.Model):
    STATUS_CHOICES = STATUS_CHOICES_MAP.get(getattr(settings, "PROJECT_NAME").lower(), [])

    USER_CHOICES = [
        ('keypad_device', 'Keypad Device'),
        ('customer', 'Customer'),
        ('manager', 'Manager'),
        ('admin', 'Admin'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="orders")
    device = models.ForeignKey(Device, on_delete=models.SET_NULL,null=True, blank=True, related_name="device_orders")
    user_profile = models.ForeignKey(UserProfile, on_delete=models.SET_NULL,null=True, blank=True, related_name="user_profile_orders")
    token_no = models.IntegerField(validators=[
            MinValueValidator(0),
            MaxValueValidator(9999)
        ])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preparing')
    counter_no = models.IntegerField(default=1)
    shown_on_tv = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True, default=None)
    updated_by = models.CharField(max_length=20, choices=USER_CHOICES, default='keypad_device')
    created_at = models.DateTimeField(auto_now_add=True,db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_date = models.DateField(auto_now_add=True,db_index=True) 

    # ---- Airline Flash–specific fields ----
    sequence_code = models.CharField(max_length=200, blank=True, null=True, unique=True)
    flight_no = models.CharField(max_length=20, blank=True, null=True)
    pnr_no = models.CharField(max_length=20, blank=True, null=True)
    seat_no = models.CharField(max_length=10, blank=True, null=True)
    zone = models.CharField(max_length=10, blank=True, null=True)
    passenger_name = models.CharField(max_length=100, blank=True, null=True)

    # ---- Dine Flash–specific fields ----
    customer_name = models.CharField(max_length=30, blank=True, null=True)
    no_of_packs = models.PositiveIntegerField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    table_booking_no = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    utility = models.ForeignKey(
        Utility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )
    current_utility = models.ForeignKey(
        Utility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_orders"
    )
    registration_batch_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        editable=False,
    )
    # ---- Hospital Flash – pre-announcement dedupe ----
    pre_announcement_notified_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        help_text="Hospital Flash: set when a pre-announcement push was last sent",
    )
    pre_announcement_notified_distance = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Hospital Flash: queue distance at last pre-announcement; "
            "allows re-notify when distance changes, blocks same-distance duplicates"
        ),
    )
    # ---- Airline Flash && Dine Flash –specific fields ----
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    call_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Token {self.token_no} ({self.vendor.name})"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'token_no']),
            models.Index(fields=['sequence_code']),
            models.Index(fields=['flight_no', 'pnr_no']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['vendor', '-created_at']),
            models.Index(fields=['vendor', 'created_date']),
            models.Index(fields=['table_booking_no']),
        ]
    
class OrderStatusHistory(models.Model):
    order = models.ForeignKey(
        'Order',
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    previous_status = models.CharField(
        max_length=20,
        choices=Order.STATUS_CHOICES,
        null=True,
        blank=True
    )
    new_status = models.CharField(
        max_length=20,
        choices=Order.STATUS_CHOICES
    )
    previous_utility = models.ForeignKey(
        Utility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_old_utility"
    )

    new_utility = models.ForeignKey(
        Utility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_new_utility"
    )
    changed_by = models.CharField(
        max_length=20,
        choices=Order.USER_CHOICES,
        default='manager'
    )
    # How long the order stayed in previous_status (in seconds)
    processing_time_seconds = models.IntegerField(
        null=True,
        blank=True,
        help_text="Duration spent in previous status before this update."
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order} changed to {self.new_status} at {self.changed_at}"


class PushSubscription(models.Model):
    browser_id = models.CharField(max_length=255, unique=True)
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    tokens = models.ManyToManyField(Order, blank=True)  # Many-to-Many with orders
    last_push_status = models.CharField(
        max_length=20,
        choices=[('success','Success'),('failed','Failed'),('stale','Stale'),('pending','Pending')],
        default='pending'
    )
    last_push_response = models.TextField(blank=True, null=True)
    last_checked_at = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_as_stale(self, response_text=None):
        """Mark subscription as stale but keep record for analysis."""
        self.last_push_status = 'stale'
        self.last_push_response = response_text or 'Stale subscription detected (404/410).'
        self.save(update_fields=['last_push_status', 'last_push_response', 'updated_at'])

    def mark_as_success(self):
        self.last_push_status = 'success'
        self.last_push_response = None
        self.save(update_fields=['last_push_status', 'last_push_response', 'updated_at'])

    def __str__(self):
        return f"Subscription for {self.browser_id}"

class Feedback(models.Model):
    TYPE_CHOICES = [
        ('complaint', 'Complaint'),
        ('suggestion', 'Suggestion'),
        ('compliment', 'Compliment'),
    ]
    
    CATEGORY_CHOICES = [
        ('dish', 'Dish'),
        ('service', 'Service'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='feedbacks')
    feedback_type = models.CharField(max_length=10, choices=TYPE_CHOICES, null=True, blank=True)
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, null=True, blank=True)
    want_to_reach_us = models.BooleanField(default=False)
    name = models.CharField(max_length=255, blank=True, null=True)  
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Feedback for {self.vendor.name}"

class AndroidDevice(models.Model):
    token = models.CharField(max_length=255)
    # Optional dedicated FCM registration token for TV (longer / rotated separately from legacy `token`).
    fcm_token = models.TextField(blank=True, null=True)
    mac_address = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL,null=True, blank=True,related_name='android_devices')
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE,related_name='android_device')
    tv_config = models.ForeignKey(
        "TVDeviceConfig",     # forward reference
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('mac_address', 'admin_outlet')

        indexes = [
            # Speeds up queries where you search by mac + outlet
            models.Index(fields=['mac_address', 'admin_outlet']),

            # Optional: Index admin_outlet alone (commonly filtered)
            models.Index(fields=['admin_outlet']),

            # Optional: Index mac_address alone (helps fallback lookups)
            models.Index(fields=['mac_address']),
        ]

class AndroidAPK(models.Model):
    token = models.CharField(max_length=255)
    apk_version = models.CharField(max_length=255, blank=True, null=True)
    mac_address = models.CharField(max_length=255, blank=True, null=True)
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE,related_name='admin_outlet_apks')
    user_profile = models.ForeignKey(UserProfile, on_delete=models.SET_NULL,null=True, blank=True, related_name="user_profile_devices")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('mac_address', 'user_profile')

class TVDeviceConfig(models.Model):

    ORIENTATION_CHOICES = [
        ("portrait", "Portrait"),
        ("landscape", "Landscape"),
    ]

    QR_ALIGN_CHOICES = [
        ("left", "Left"),
        ("right", "Right"),
    ]

    QR_PLACEMENT_CHOICES = [
        ("top-left", "Top Left"),
        ("top-right", "Top Right"),
        ("bottom-left", "Bottom Left"),
        ("bottom-right", "Bottom Right"),
    ]
    AD_POSITION_CHOICES = [
        ("right", "Right Side"),
        ("left", "Left Side"),
        ("bottom", "Bottom Strip"),
        ("full_width", "Full Width Banner"),
    ]
    VIDEO_AD_MODE_CHOICES = [
        ("play_full", "Play Full Video"),
        ("respect_interval", "Respect Ad Interval"),
    ]
    HEADER_FONT_STYLE_CHOICES = [
        ("regular", "Regular"),
        ("medium", "Medium"),
        ("bold", "Bold"),
    ]

    FONT_SIZE_CHOICES = [
        ("small", "Small"),
        ("medium", "Medium"),
        ("large", "Large"),
        ("extra-large", "Extra Large"),
    ] + [(str(size), str(size)) for size in range(1, 101)]

    LANGUAGE_CHOICES = [
        ("English", "English"),
        ("Malayalam", "Malayalam"),
    ]

    UTILITY_DISPLAY_KEY_CHOICES = [
        ("name", "Utility Name"),
        ("display_name", "Display Name"),
        ("display_code", "Display Code"),
    ]

    admin_outlet = models.ForeignKey(
        AdminOutlet,
        on_delete=models.CASCADE,
        related_name="tv_device_configs",
        db_index=True
    )

    # 1. QR display settings
    show_qr = models.BooleanField(default=False)
    qr_alignment = models.CharField(max_length=10, choices=QR_ALIGN_CHOICES, default="left")

    # 2. How many bookings to show (1–3)
    items_to_show = models.PositiveSmallIntegerField(default=1)

    # 3. Fields to show inside booking card (multiselect)
    booking_fields = models.JSONField(default=list) 
    # Example: ["name", "phoneno", "packs", "datetime", "token"]

    # 4. Utility name mode (single select)
    utility_name_mode = models.CharField(max_length=20, choices=UTILITY_DISPLAY_KEY_CHOICES)

    # 5. Orientation
    screen_orientation = models.CharField(
        max_length=20,
        choices=ORIENTATION_CHOICES,
        default="landscape"
    )

    # 6. Selected utilities (multiselect)
    utilities = models.ManyToManyField(
        Utility,
        related_name="tv_configs",
        blank=True
    )

    # 7. Dine Flash Specific Configuration (Extended)
    # 7a. Display Settings
    display_rows = models.PositiveIntegerField(default=1)
    display_columns = models.PositiveIntegerField(default=1)
    token_font_size = models.CharField(max_length=20, choices=FONT_SIZE_CHOICES, default="large")
    counter_font_size = models.CharField(max_length=20, choices=FONT_SIZE_CHOICES, default="medium")
    utility_font_size = models.CharField(max_length=20, choices=FONT_SIZE_CHOICES, default="small")
    
    token_text_color = models.CharField(max_length=7, default="#000000") # Hex color
    counter_text_color = models.CharField(max_length=7, default="#000000")
    utility_text_color = models.CharField(max_length=7, default="#000000")

    # 7b. Visibility Settings
    show_customer_name = models.BooleanField(default=True)
    show_phone_number = models.BooleanField(default=True)
    show_partially_masked_phone_number = models.BooleanField(default=False)
    show_order_details = models.BooleanField(default=True)

    # 7c. Audio Settings
    audio_enabled = models.BooleanField(default=False)
    announcement_language = models.CharField(max_length=50, choices=LANGUAGE_CHOICES, default="English")

    # 7d. Animation Settings
    blink_token = models.BooleanField(default=False)
    blink_utility = models.BooleanField(default=False)

    # 7e. QR Code Settings (Extended)
    qr_placement = models.CharField(max_length=20, choices=QR_PLACEMENT_CHOICES, default="bottom-right")
    qr_base_url = models.CharField(max_length=500, blank=True, null=True)
    # How long a dynamically generated QR remains valid (Dine Flash only).
    # QR encodes generation date+time; backend allows scans only within this window.
    qr_expiry_minutes = models.PositiveSmallIntegerField(default=5)

    # 8. Config name
    config_name = models.CharField(max_length=255,blank=True,null=True)

    # 9. Dine Flash Ad Settings
    enable_ads = models.BooleanField(default=False)
    ad_position = models.CharField(max_length=20, choices=AD_POSITION_CHOICES, default="right")
    ad_interval = models.PositiveSmallIntegerField(default=8)
    video_ad_mode = models.CharField(max_length=20, choices=VIDEO_AD_MODE_CHOICES, default="play_full")
    advertisements = models.ManyToManyField(
        "TVAdvertisement",
        related_name="tv_configs",
        blank=True,
    )
    # 10. Dine Flash Token Header/Footer
    header_font_size = models.CharField(max_length=20, choices=FONT_SIZE_CHOICES, default="large")
    header_font_style = models.CharField(max_length=20, choices=HEADER_FONT_STYLE_CHOICES, default="bold")
    header_text_color = models.CharField(max_length=7, default="#000000")
    footer_font_size = models.CharField(max_length=20, choices=FONT_SIZE_CHOICES, default="16")
    footer_text_color = models.CharField(max_length=7, default="#000000")
    footer_enabled = models.BooleanField(default=False)
    footer_texts = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True,db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"TV Config #{self.id} — {self.admin_outlet.customer_name}"
    
    class Meta:
        indexes = [
            models.Index(fields=["admin_outlet", "-created_at"]),
        ]

class SiteConfig(models.Model):
    maintenance_mode = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Site Configuration"


class TVAdvertisement(models.Model):
    MEDIA_TYPE_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
    ]

    admin_outlet = models.ForeignKey(
        AdminOutlet,
        on_delete=models.CASCADE,
        related_name="tv_advertisements",
    )
    title = models.CharField(max_length=120, blank=True, null=True)
    media_file = models.FileField(upload_to="tv_ads/")
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES)
    sequence = models.PositiveIntegerField(default=1, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        label = self.title or self.media_file.name
        return f"{label} ({self.media_type})"

    class Meta:
        ordering = ["sequence", "created_at", "id"]

class AdvertisementImage(models.Model):
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE, related_name='ad_images')
    image = models.ImageField(upload_to='ads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_converted = models.BooleanField(default=False)

    objects = CustomManager()

class AdvertisementProfile(models.Model):
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE, related_name='ad_profiles')
    name = models.CharField(max_length=100)
    date_start = models.DateField(blank=True, null=True)
    date_end = models.DateField(blank=True, null=True)
    days_active = models.JSONField(blank=True, default=list,null=True) 
    priority = models.PositiveSmallIntegerField(default=1)  # 1–5
    images = models.ManyToManyField(AdvertisementImage, related_name='profiles', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def is_active_today(self):
        today = timezone.now().date()
        weekday = today.strftime('%A')

        # Only match if both dates are provided
        is_date_match = (
            self.date_start is not None and
            self.date_end is not None and
            self.date_start <= today <= self.date_end
        )

        is_day_match = (
            self.days_active and (
                'All' in self.days_active or
                weekday in self.days_active
            )
        )

        return is_date_match or is_day_match
    
    def is_active_now(self, vendor):
        """
        Checks if the profile is active for the given vendor at the vendor's local time.
        - Date range: if both start/end are None → all dates allowed
        - Days active: must match vendor's weekday or 'All'
        - Time slots: if slots exist, current time must be within at least one slot
        """
        # 🌍 Vendor local datetime
        now = get_vendor_current_time(vendor)
        today = now.date()
        weekday = now.strftime('%A')
        current_time = now.time()

        # 🗓 Date range
        if self.date_start and self.date_end:
            if not (self.date_start <= today <= self.date_end):
                return False

        # 📅 Days active
        days = self.days_active or []
        if not days:
            return False  # inactive if empty list
        if 'All' not in days and weekday not in days:
            return False

        # ⏰ Time slots
        slots = self.slots.all()
        # If no slots defined → full day active
        if slots.exists():
            if not any(slot.start_time <= current_time <= slot.end_time for slot in slots):
                return False


        return True
    
class AdvertisementSlot(models.Model):
    profile = models.ForeignKey(
        'AdvertisementProfile',
        on_delete=models.CASCADE,
        related_name='slots'
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    def __str__(self):
        return f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')} ({self.profile.name})"


class AdvertisementProfileAssignment(models.Model):
    profile = models.ForeignKey(
        AdvertisementProfile, on_delete=models.CASCADE,
        related_name='assigned_vendors'
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE,
        related_name='assigned_profiles'
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('profile', 'vendor')  

class ArchivedOrder(models.Model):
    original_order_id = models.IntegerField()
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True)
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    user_profile = models.ForeignKey(UserProfile, on_delete=models.SET_NULL,null=True, blank=True)
    token_no = models.IntegerField()
    status = models.CharField(max_length=20)
    counter_no = models.IntegerField()
    shown_on_tv = models.BooleanField()
    notified_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.CharField(max_length=20)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)
    created_date = models.DateField(auto_now_add=True)

    # -------- Dine Flash Specific Fields --------
    customer_name = models.CharField(max_length=100, blank=True, null=True)
    no_of_packs = models.PositiveIntegerField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    registration_batch_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        editable=False,
    )

    def __str__(self):
        return f"Archived Token {self.token_no}"

class ArchivedOrderStatusHistory(models.Model):
    archived_order = models.ForeignKey(
        'ArchivedOrder',
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    previous_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20)
    changed_by = models.CharField(max_length=20)
    changed_at = models.DateTimeField()
    def __str__(self):
        return f"{self.archived_order} changed to {self.new_status} at {self.changed_at}"

class ChatMessage(models.Model):
    SENDER_CHOICES = [
        ('user', 'User'),       # foodflash user
        ('manager', 'Manager'), # android apk
        ('system', 'System'),   # automated updates
    ]

    message_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # 👇 Link to vendor 
    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE, related_name='chat_messages')

    # 👇 Order context
    token_no = models.IntegerField()
    booking_id = models.IntegerField(null=True, blank=True)
    booking_no = models.CharField(max_length=50, blank=True, null=True)
    sequence_code = models.CharField(max_length=100, blank=True, null=True)
    created_date = models.DateField()

    # 👇 Identify sender
    sender = models.CharField(max_length=10, choices=SENDER_CHOICES)

    # 👇 Message content
    message_text = models.TextField(blank=True, null=True)
    audio_file = models.FileField(upload_to='chat/audio/', blank=True, null=True)

    # 👇 Optional reply threading
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')

    is_read = models.BooleanField(default=False)
    is_send = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def is_audio(self):
        return bool(self.audio_file)

    def __str__(self):
        return f"[{self.created_at}] {self.sender}: {'(audio)' if self.audio_file else self.message_text}"

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['vendor', 'token_no', 'created_date']),
            models.Index(
                fields=['vendor', 'booking_id', 'sender', 'is_read'],
                name='chatmsg_vendor_booking_unread',
            ),
        ]
        constraints = [
            models.UniqueConstraint(fields=['vendor', 'token_no', 'created_date', 'message_id'], name='unique_chat_message_per_order'),
        ]

class WebChatMessage(models.Model):
    message_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    subscription = models.ForeignKey(
        'PushSubscription',
        on_delete=models.CASCADE,
        related_name='messages'
    )
    vendor = models.ForeignKey(
        'Vendor',
        on_delete=models.CASCADE,
        related_name='messages'
    )
    token_no = models.IntegerField(null=True, blank=True)
    sequence_code = models.CharField(max_length=100, blank=True, null=True)
    booking_no = models.CharField(max_length=50, blank=True, null=True)
    booking_id = models.IntegerField(null=True, blank=True)
    sender = models.CharField(max_length=20)   
    type = models.CharField(max_length=48, default='chat')
    text = models.JSONField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    is_send = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['vendor', 'timestamp']),
        ]

    def __str__(self):
        token_info = f"[T{self.token_no}] " if self.token_no else ""
        return f"{token_info}{self.sender} → {self.type} ({self.text})"

class IoTDeviceCredential(models.Model):
    android_device = models.OneToOneField(
        AndroidDevice, on_delete=models.CASCADE, related_name="iot_credentials"
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='iot_device_credentials')
    device_id = models.CharField(max_length=255, unique=True, db_index=True)
    primary_connection_string = models.TextField(null=False, blank=False)
    secondary_connection_string = models.TextField(null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"IoT Credentials for {self.device_id}"


class BuffetOrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='buffet_items')
    utility = models.ForeignKey(Utility, on_delete=models.SET_NULL, null=True, related_name='buffet_ordered_items')
    status = models.CharField(max_length=20, default='created')
    customizations = models.JSONField(blank=True, null=True, default=list) # e.g. ["No Onion"]
    remarks = models.TextField(blank=True, null=True)
    is_grouped = models.BooleanField(default=False)
    quantity = models.PositiveIntegerField(default=1) # For grouped utilities
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Item for Order {self.order.token_no} - {self.utility.display_name if self.utility else 'Unknown'}"


class BuffetOrderLookup(models.Model):
    """
    Buffet-only opaque recovery pointer: order_lookup_id → current Order.

    Not a browser identity. Not PushSubscription. Latest Order Wins (pointer, not history).
    Deleted automatically when the mapped Order is deleted (CASCADE).
    """
    order_lookup_id = models.CharField(max_length=255, unique=True, db_index=True)
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="buffet_order_lookup",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"BuffetOrderLookup {self.order_lookup_id} → Order {self.order_id}"


class BuffetActiveOrder(models.Model):
    """
    Dine Flash Buffet only — Active Order Registry entry.

    Tracks concurrently active buffet orders for an opaque order_lookup_id.
    Additive to BuffetOrderLookup (Latest Order Wins). Does not replace recovery,
    browser_id, PushSubscription, cookies, or WebChatMessage.

    One registry row per Order (OneToOne). Many rows may share the same
    order_lookup_id (multi-order). Deleted when the Order is deleted (CASCADE).
    """

    order_lookup_id = models.CharField(max_length=255, db_index=True)
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="buffet_active_order",
    )
    # Denormalized from Order at registration (token/vendor do not change).
    token_no = models.IntegerField()
    vendor_id = models.IntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["order_lookup_id", "vendor_id"],
                name="buffet_act_vendor_idx",
            ),
        ]

    @property
    def booking_id(self):
        return self.order_id

    def __str__(self):
        return (
            f"BuffetActiveOrder lookup={self.order_lookup_id} "
            f"token={self.token_no} order_id={self.order_id}"
        )


class DineFlashBookingLookup(models.Model):
    """
    Dine Flash only opaque recovery pointer: order_lookup_id → current booking Order.

    Not a browser identity. Not PushSubscription. Latest Booking Wins (pointer, not history).
    Independent from BuffetOrderLookup. Deleted when the mapped Order is deleted (CASCADE).
    """
    order_lookup_id = models.CharField(max_length=255, unique=True, db_index=True)
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="dine_flash_booking_lookup",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"DineFlashBookingLookup {self.order_lookup_id} → Order {self.order_id}"
