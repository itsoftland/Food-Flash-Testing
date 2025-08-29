from django.db import models
import json
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid
import pytz

class MqttServerConfig(models.Model):
    name = models.CharField(max_length=100, help_text="Friendly name for MQTT server")
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=1883)
    username = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)
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
    customer_name = models.CharField(max_length=255, blank=True, null=True)
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
    auto_delete_hours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Set after how many hours orders should be auto-deleted (min 2 hours)")
    
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
        default=1,
        related_name="vendor_configs"
    )
    token_display_limit = models.PositiveIntegerField(default=8)
    tv_communication_mode = models.CharField(
        max_length=20,
        choices=[
            ("MQTT", "MQTT"),
            ("Firebase", "Firebase")
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
    business_day_start_hour = models.PositiveSmallIntegerField(default=0)
    timezone = models.CharField(
        max_length=50,
        choices=[(tz, tz) for tz in pytz.all_timezones], 
        default="UTC"
    )
    


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
        ('manager', 'Manager (Android APK)'),
        ('web', 'Web User'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='profile_roles')
    name = models.CharField(max_length=255, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE,related_name='user_profiles')
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='user_profile')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

class Order(models.Model):
    STATUS_CHOICES = [
        ('preparing', 'Preparing'),
        ('ready', 'Ready'),
        ('created', 'Created'),
    ]
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_date = models.DateField(auto_now_add=True) 

    def __str__(self):
        return f"Token {self.token_no}"

class PushSubscription(models.Model):
    browser_id = models.CharField(max_length=255, unique=True)
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    tokens = models.ManyToManyField(Order, blank=True)  # Many-to-Many with orders
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
    token = models.CharField(max_length=255, unique=True)
    mac_address = models.CharField(max_length=255, blank=True, null=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL,null=True, blank=True,related_name='android_devices')
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE,related_name='android_device')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('mac_address', 'admin_outlet')

class AndroidAPK(models.Model):
    token = models.CharField(max_length=255, unique=True)
    apk_version = models.CharField(max_length=255, blank=True, null=True)
    mac_address = models.CharField(max_length=255, blank=True, null=True)
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE,related_name='admin_outlet_apks')
    user_profile = models.ForeignKey(UserProfile, on_delete=models.SET_NULL,null=True, blank=True, related_name="user_profile_devices")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('mac_address', 'user_profile')

class SiteConfig(models.Model):
    maintenance_mode = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Site Configuration"

class AdvertisementImage(models.Model):
    admin_outlet = models.ForeignKey(AdminOutlet, on_delete=models.CASCADE, related_name='ad_images')
    image = models.ImageField(upload_to='ads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

    def __str__(self):
        return f"Archived Token {self.token_no}"

class ChatMessage(models.Model):
    SENDER_CHOICES = [
        ('user', 'User'),       # foodflash user
        ('manager', 'Manager'), # android apk
    ]

    message_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # 👇 Link to vendor 
    vendor = models.ForeignKey('Vendor', on_delete=models.CASCADE, related_name='chat_messages')

    # 👇 Order context
    token_no = models.IntegerField()
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
        ]
        constraints = [
            models.UniqueConstraint(fields=['vendor', 'token_no', 'created_date', 'message_id'], name='unique_chat_message_per_order'),
        ]

