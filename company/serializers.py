from rest_framework import serializers
from vendors.models import (Vendor,AndroidDevice,
                            Device ,AdvertisementImage,
                            AdvertisementProfile,
                            AdvertisementProfileAssignment,
                            AdminOutlet,UserProfile,
                            AndroidAPK,MqttServerConfig,
                            VendorConfig,OrderStatusHistory,
                            AdvertisementSlot,TVDeviceConfig,Utility,
                            TVAdvertisement)
from django.contrib.auth.models import User
from django.db.models import Q
import json
import datetime
from django.conf import settings
from django.db import transaction
from .tv_config_scope import (
    dine_flash_exclusive_tv_device_policy_applies,
    hospital_flash_tv_configuration_applies,
)

start_url = getattr(settings, "PROJECT_NAME", "calleron")


class MqttServerConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = MqttServerConfig
        # adjust these fields to match your MqttServerConfig model
        fields = ['id', 'name', 'host', 'port']  # example fields

class VendorConfigSerializer(serializers.ModelSerializer):
    mqtt_server = MqttServerConfigSerializer(read_only=True)

    def get_fields(self):
        fields = super().get_fields()
        current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        if current_project != "dine_flash":
            fields.pop("qr_expiry_minutes", None)
        if current_project != "hospital_flash":
            fields.pop("announcement_templates", None)
            fields.pop("called_chat_template", None)
            fields.pop("pre_announcement_chat_template", None)
        return fields

    class Meta:
        model = VendorConfig
        fields = [
            'mqtt_server',
            'token_display_limit',
            'tv_communication_mode',
            'mqtt_mode',
            'business_day_start_hour',
            'timezone',
            'auto_delete_hours',
            'use_utilities',
            'phone_number_enabled',
            'mr_number_enabled',
            'bill_number_enabled',
            'qr_expiry_minutes',
            'announcement_templates',
            'called_chat_template',
            'pre_announcement_chat_template',
        ]

class VendorSerializer(serializers.ModelSerializer):
    config = VendorConfigSerializer(read_only=True)

    class Meta:
        model = Vendor
        fields = ['id', 'vendor_id', 'name', 'location', 'config']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Buffet DBs may lag migrations and omit qr_expiry_minutes; loading full VendorConfig
        # then raises OperationalError. Other projects keep the default nested field + ORM path.
        if (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash_buffet":
            self.fields["config"] = serializers.SerializerMethodField()

    def get_config(self, obj):
        from vendors.models import VendorConfig

        cfg = VendorConfig.objects.defer("qr_expiry_minutes").filter(vendor_id=obj.pk).first()
        if not cfg:
            return None
        return VendorConfigSerializer(cfg, context=self.context).data

class VendorDetailSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    menu_files = serializers.SerializerMethodField()
    android_tvs = serializers.SerializerMethodField()
    keypad_devices = serializers.SerializerMethodField()
    vendor_config = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            'id',
            'vendor_id',
            'name',
            'alias_name',
            'place_id',
            'location_id',
            'logo_url',
            'menu_files',
            'android_tvs',
            'keypad_devices',
            'vendor_config'
        ]

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo and hasattr(obj.logo, 'url'):
            return request.build_absolute_uri(obj.logo.url).replace('http://', 'https://')
        return ''

    def get_menu_files(self, obj):
        request = self.context.get('request')
        try:
            menu_list = json.loads(obj.menus or "[]")  # assumes it's a JSON list like ["/media/menus/menu1.pdf", ...]
            full_menu_urls = []
            if request:
                for path in menu_list:
                    if not path.startswith("http"):
                        url = request.build_absolute_uri(f"/{start_url}/media/{path}")
                        full_menu_urls.append(url.replace("http://", "https://"))
                    else:
                        full_menu_urls.append(path)

            
            return list(full_menu_urls)
        except Exception:
            return []

    def get_android_tvs(self, obj):
        return list(obj.android_devices.values('mac_address')) if hasattr(obj, 'android_devices') else []

    def get_keypad_devices(self, obj):
        return list(obj.devices.values('serial_no')) if hasattr(obj, 'devices') else []
    
    def get_vendor_config(self, obj):
        """
        Returns serialized vendor config if exists, otherwise returns None.
        """
        try:
            cfg = getattr(obj, 'config', None)  # OneToOne related name 'config'
            if not cfg:
                return None
            # Use the nested serializer to return a clean structure
            return VendorConfigSerializer(cfg, context=self.context).data
        except Exception:
            # don't crash the whole response for a config serialization issue
            return None

class UnmappedVendorDetailSerializer(serializers.ModelSerializer):
    unmapped_android_tvs = serializers.SerializerMethodField()
    unmapped_locations = serializers.SerializerMethodField()
    unmapped_keypad_devices = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            'unmapped_android_tvs',
            'unmapped_locations',
            'unmapped_keypad_devices',
        ]

    def get_unmapped_android_tvs(self, obj):
        admin_outlet = obj.admin_outlet

        # Get unmapped and vendor-mapped android devices
        tvs = AndroidDevice.objects.filter(
            admin_outlet=admin_outlet
        ).filter(Q(vendor__isnull=True) | Q(vendor=obj)).values('mac_address')

        return list(tvs)
    
    def get_unmapped_locations(self, obj):
        admin_outlet = obj.admin_outlet
        current_location_code = obj.location_id

        try:
            all_locations = json.loads(admin_outlet.locations)
        except json.JSONDecodeError:
            return {'unmapped': []}

        used_codes = Vendor.objects.filter(
            admin_outlet=admin_outlet
        ).exclude(location_id=current_location_code).values_list('location_id', flat=True)

        unmapped = []

        for loc in all_locations:
            for name, code in loc.items():
                entry = {'key': name, 'value': code}
                if code not in used_codes:
                    unmapped.append(entry)

        return list(unmapped)
    
    def get_unmapped_keypad_devices(self, obj):
        admin_outlet = obj.admin_outlet
        unmapped = Device.objects.filter(
            admin_outlet=admin_outlet
        ).filter(Q(vendor__isnull=True) | Q(vendor=obj)).values('serial_no')
        return list(unmapped)

class VendorUpdateSerializer(serializers.Serializer):
    vendor_id = serializers.CharField(required=True)
    name = serializers.CharField(required=False, allow_blank=True)
    alias_name = serializers.CharField(required=False, allow_blank=True)
    location = serializers.CharField(required=False, allow_blank=True)
    place_id = serializers.CharField(required=False, allow_blank=True)
    location_id = serializers.CharField(required=False, allow_blank=True)
    auto_delete_hours = serializers.IntegerField(required=False, allow_null=True)
    business_day_start_hour = serializers.TimeField(required=False, allow_null=True)


    def validate_vendor_id(self, value):
        if not Vendor.objects.filter(vendor_id=value).exists():
            raise serializers.ValidationError("Invalid vendor ID.")
        return value

    def validate_alias_name(self, value):
        vendor_id = self.initial_data.get('vendor_id')
        vendor = Vendor.objects.filter(vendor_id=vendor_id).first()
        if vendor and Vendor.objects.exclude(id=vendor.id).filter(alias_name__iexact=value).exists():
            raise serializers.ValidationError("Alias name already exists.")
        return value

    def validate_name(self, value):
        vendor_id = self.initial_data.get('vendor_id')
        vendor = Vendor.objects.filter(vendor_id=vendor_id).first()
        if vendor and Vendor.objects.exclude(id=vendor.id).filter(name__iexact=value).exists():
            raise serializers.ValidationError("Vendor name already exists.")
        return value
    

class AdvertisementImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = AdvertisementImage
        fields = ['id', 'image_url']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url

class AdvertisementProfileSerializer(serializers.ModelSerializer):
    image_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True
    )
    time_slots = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField()
        ),
        write_only=True
    )
    
    images = AdvertisementImageSerializer(many=True, read_only=True)

    class Meta:
        model = AdvertisementProfile
        fields = [
            'id',
            'name',
            'date_start',
            'date_end',
            'days_active',
            'priority',
            'image_ids',
            'images',
            'created_at',
            'time_slots'
        ]

    def get_images(self, obj):
        return [img.id for img in obj.images.all()]

    def validate_image_ids(self, value):
        request = self.context.get('request')
        if not request or not hasattr(request.user, 'admin_outlet'):
            raise serializers.ValidationError("User context or admin outlet missing.")

        images = AdvertisementImage.objects.filter(
            id__in=value,
            admin_outlet=request.user.admin_outlet
        )

        if images.count() != len(set(value)):
            raise serializers.ValidationError("Some image IDs are invalid or not allowed.")

        return list(images)

    def validate_time_slots(self, value):
        """
        Time slots are optional.
        If none are given → interpreted as full day.
        If present → each must have start and end, start < end, and not overlap.
        """
        if not value:
            return []  # means full day

        prev_end = None
        for i, slot in enumerate(value):
            start = slot.get('start')
            end = slot.get('end')
            if not start or not end:
                raise serializers.ValidationError(f"Slot {i+1}: both start and end times are required.")
            try:
                start_time = datetime.datetime.strptime(start, "%H:%M").time()
                end_time = datetime.datetime.strptime(end, "%H:%M").time()
            except ValueError:
                raise serializers.ValidationError(f"Slot {i+1}: invalid time format.")
            if end_time <= start_time:
                raise serializers.ValidationError(f"Slot {i+1}: end time must be after start time.")
            if prev_end and start_time <= prev_end:
                raise serializers.ValidationError(f"Slot {i+1}: start time must be after previous slot's end time.")
            prev_end = end_time
        return value



    def create(self, validated_data):
        images = validated_data.pop('image_ids', [])
        time_slots = validated_data.pop('time_slots', [])
        profile = AdvertisementProfile.objects.create(
            admin_outlet=self.context['request'].user.admin_outlet,
            **validated_data
        )
        profile.images.set(images)
        for slot in time_slots:
            AdvertisementSlot.objects.create(
                profile=profile,
                start_time=slot['start'],
                end_time=slot['end']
            )
        return profile
    
    def validate(self, attrs):
        date_start = attrs.get('date_start')
        date_end = attrs.get('date_end')
        days_active = attrs.get('days_active')

        has_dates = date_start and date_end
        has_days = bool(days_active)

        if not (has_dates or has_days):
            raise serializers.ValidationError(
                "Either both start & end dates OR at least one active day must be provided."
            )

        return attrs

class AdvertisementProfileAssignmentSerializer(serializers.Serializer):
    vendor_ids = serializers.ListField(
        child=serializers.IntegerField(), required=True
    )
    profile_ids = serializers.ListField(
        child=serializers.IntegerField(), required=True
    )

    def validate(self, data):
        vendor_ids = data.get('vendor_ids')
        profile_ids = data.get('profile_ids')

        if not vendor_ids:
            raise serializers.ValidationError("vendor_ids is required and cannot be empty.")
        if not profile_ids:
            raise serializers.ValidationError("profile_ids is required and cannot be empty.")
        
        # Validate vendors
        existing_vendor_ids = set(Vendor.objects.filter(id__in=vendor_ids).values_list('id', flat=True))
        missing_vendors = set(vendor_ids) - existing_vendor_ids
        if missing_vendors:
            raise serializers.ValidationError(f"Vendor(s) not found: {sorted(missing_vendors)}")

        # Validate profiles
        existing_profile_ids = set(AdvertisementProfile.objects.filter(id__in=profile_ids).values_list('id', flat=True))
        missing_profiles = set(profile_ids) - existing_profile_ids
        if missing_profiles:
            raise serializers.ValidationError(f"AdvertisementProfile(s) not found: {sorted(missing_profiles)}")

        return data
    def create(self, validated_data):
        vendor_ids = validated_data['vendor_ids']
        profile_ids = validated_data['profile_ids']

        vendors = Vendor.objects.filter(id__in=vendor_ids)
        profiles = AdvertisementProfile.objects.filter(id__in=profile_ids)

        assigned_count = 0
        skipped_count = 0

        for vendor in vendors:
            for profile in profiles:
                if AdvertisementProfileAssignment.objects.filter(profile=profile, vendor=vendor).exists():
                    skipped_count += 1
                else:
                    AdvertisementProfileAssignment.objects.create(profile=profile, vendor=vendor)
                    assigned_count += 1

        return {
            'vendor_count': vendors.count(),
            'profile_count': profiles.count(),
            'total_assigned': assigned_count,
            'skipped': skipped_count
        }


class AdvertisementProfileMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvertisementProfile
        fields = ['id', 'name']

class DashboardMetricsSerializer(serializers.ModelSerializer):
    keypad_devices = serializers.SerializerMethodField()
    android_tvs = serializers.SerializerMethodField()
    # unmapped_keypad_devices = serializers.SerializerMethodField()
    # mapped_keypad_devices = serializers.SerializerMethodField()
    # unmapped_android_tvs = serializers.SerializerMethodField()
    # mapped_android_tvs = serializers.SerializerMethodField()
    outlets = serializers.SerializerMethodField()

    class Meta:
        model = AdminOutlet
        fields = [
            "outlets",
            # "mapped_keypad_devices",
            # "unmapped_keypad_devices", 
            # "mapped_android_tvs", 
            # "unmapped_android_tvs", 
            "android_tvs",
            "keypad_devices"
        ]

    def get_outlets(self, obj):
        return obj.vendors.count() if hasattr(obj, 'vendors') else 0
    
    def get_keypad_devices(self, obj):
        return obj.device.count() if hasattr(obj, 'device') else 0
    
    def get_android_tvs(self, obj):
        return obj.android_device.count() if hasattr(obj, 'android_device') else 0
    
    def get_mapped_keypad_devices(self, obj):
        unmapped = obj.device.all().filter(vendor__isnull=False).count()
        return unmapped
    
    def get_unmapped_keypad_devices(self, obj):
        unmapped = obj.device.all().filter(vendor__isnull=True).count()
        return unmapped
    
    def get_mapped_android_tvs(self, obj):
        mapped = obj.android_device.filter(vendor__isnull=False).count()
        return mapped
    
    def get_unmapped_android_tvs(self, obj):
        unmapped = obj.android_device.filter(vendor__isnull=True).count()
        return unmapped

class DeviceSerializer(serializers.ModelSerializer):
    vendor = VendorSerializer(read_only=True)
    class Meta:
        model = Device
        fields = ['id', 'serial_no', 'vendor', 'created_at', 'updated_at']
class ManagerDeviceSerializer(serializers.ModelSerializer):
    admin_outlet = serializers.CharField(source='admin_outlet.name', read_only=True)
    user_profile = serializers.SerializerMethodField()

    class Meta:
        model = AndroidAPK
        fields = [
            'id', 'token', 'mac_address', 'apk_version',
            'admin_outlet', 'user_profile', 'created_at', 'updated_at'
        ]

    def get_user_profile(self, obj):
        if obj.user_profile:
            return {
                "id": obj.user_profile.id if obj.user_profile else None,
                "name": obj.user_profile.name if obj.user_profile else None,
                "role": obj.user_profile.role if obj.user_profile else None
            }
        return None


class AndroidDeviceSerializer(serializers.ModelSerializer):
    vendor = VendorSerializer(read_only=True)

    class Meta:
        model = AndroidDevice
        fields = ['id', 'mac_address', 'vendor', 'created_at', 'updated_at',]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['mac_address'] = representation.pop('mac_address', None)
        # Include tv_config name
        if instance.tv_config:
            representation['tv_config'] = {
                'id': instance.tv_config.id,
                'config_name': instance.tv_config.config_name or f'Config #{instance.tv_config.id}'
            }
        else:
            representation['tv_config'] = None
        return representation

from vendors.models import Order

class OrderSerializer(serializers.ModelSerializer):
    outlet_name = serializers.SerializerMethodField()
    vendor_id = serializers.IntegerField(source='vendor.id')
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    device_id = serializers.IntegerField(source='device.id', allow_null=True, read_only=True)
    device_name = serializers.CharField(source='device.serial_no', allow_null=True, read_only=True)
    ready_status = serializers.SerializerMethodField()
    # Dine Flash only. ArchivedOrder has no table_booking_no, so read it safely.
    table_booking_no = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'token_no',
            'status',
            'counter_no',
            'shown_on_tv',
            'notified_at',
            'updated_by',
            'created_at',
            'updated_at',
            'vendor_id',
            'vendor_name',
            'device_id',
            'device_name',
            'outlet_name',
            'ready_status',
            'table_booking_no'
        ]

    def get_outlet_name(self, obj):
        return obj.vendor.admin_outlet.customer_name if obj.vendor and obj.vendor.admin_outlet else None

    def get_table_booking_no(self, obj):
        return getattr(obj, 'table_booking_no', None)
    def get_ready_status(self, obj):
        if obj.status_history.exists():
            first_ready_status = obj.status_history.filter(new_status__iexact='ready').order_by('changed_at').first()
            if first_ready_status:
                return first_ready_status.changed_at
        return None

class UserProfileCreateSerializer(serializers.Serializer):
    # Keep API role choices aligned with UserProfile.role (plus synthetic "both").
    ROLE_CHOICES = list(UserProfile.ROLE_CHOICES) + [
        ('both', 'Both Manager and Web User'),
    ]
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    vendor_id = serializers.IntegerField(required=False, allow_null=True)
    assigned_utilities = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty or just spaces.")
        return value

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        
        if User.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError("Username already exists.")

        # Validate AdminOutlet via customer_id or current user
        customer_id = data.get('customer_id')
        request = self.context.get('request')
        
        if customer_id:
            try:
                data['admin_outlet'] = AdminOutlet.objects.get(customer_id=customer_id)
            except AdminOutlet.DoesNotExist:
                raise serializers.ValidationError("AdminOutlet with the given customer_id not found.")
        elif request and hasattr(request.user, 'admin_outlet'):
            data['admin_outlet'] = request.user.admin_outlet
        else:
            raise serializers.ValidationError("customer_id is required or user must have an associated AdminOutlet.")

        # Validate Vendor via vendor_id (Optional for some roles)
        vendor_id = data.get('vendor_id')
        if vendor_id:
            try:
                data['vendor'] = Vendor.objects.get(id=vendor_id)
            except Vendor.DoesNotExist:
                raise serializers.ValidationError("Vendor with the given ID not found.")
        else:
            data['vendor'] = None

        if 'assigned_utilities' in data and data['assigned_utilities']:
            utilities = Utility.objects.filter(id__in=data['assigned_utilities'], vendor=data['vendor'])
            if utilities.count() != len(set(data['assigned_utilities'])):
                raise serializers.ValidationError("Some utilities are invalid or do not belong to this vendor.")
            data['validated_utilities'] = utilities

        project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        if project in ("dine_flash_buffet", "hospital_flash"):
            role = data.get("role")
            vendor = data.get("vendor")
            admin_outlet = data.get("admin_outlet")
            if role in ("utility_user", "outlet_manager") and not vendor:
                raise serializers.ValidationError(
                    {"vendor_id": ["Select an outlet for this role."]}
                )
            if vendor and admin_outlet and vendor.admin_outlet_id != admin_outlet.id:
                raise serializers.ValidationError(
                    {"vendor_id": ["Selected outlet does not belong to your account."]}
                )

        return data

    def create(self, validated_data):
        username = validated_data['username']
        password = validated_data['password']
        role = validated_data['role']
        admin_outlet = validated_data['admin_outlet']
        vendor = validated_data['vendor']
        name = validated_data['name']

        # Create the user only after validation
        user = User.objects.create_user(username=username, password=password)

        # Decide roles to create
        requested_roles = ['manager', 'web'] if role == 'both' else [role]

        utilities = validated_data.pop('validated_utilities', [])

        created_profiles = []
        for r in requested_roles:
            if UserProfile.objects.filter(user=user, role=r).exists():
                raise serializers.ValidationError(f"User already has a '{r}' profile.")
            profile = UserProfile.objects.create(
                user=user,
                name=name,
                role=r,
                admin_outlet=admin_outlet,
                vendor=vendor
            )
            if r == 'utility_user' and utilities:
                profile.assigned_utilities.set(utilities)
            created_profiles.append(profile)

        return created_profiles if len(created_profiles) > 1 else created_profiles[0]

class UserListDetailSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    outlet_name = serializers.CharField(source='admin_outlet.name', read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True, default=None)
    assigned_utilities = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'username',
            'email',
            'name',
            'outlet_name',
            'vendor_name',
            'assigned_utilities',
            'created_at',
            'updated_at',
            # Note: We won't include `role` here; instead, we manually inject `roles`
        ]

    def get_assigned_utilities(self, obj):
        return list(obj.assigned_utilities.values('id', 'display_name'))

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ['previous_status', 'new_status', 'changed_by', 'changed_at']


ALLOWED_BOOKING_FIELDS = {"name", "phone", "guest_count", "datetime", "token"}
MAX_FOOTER_TEXTS = 8
MAX_TV_ADS_PER_CONFIGURATION = 15

# Fields exposed only for Dine Flash (stripped for Food/Airline/Buffet and partially for Hospital).
DINE_FLASH_ONLY_TV_CONFIG_FIELDS = [
    "display_rows", "display_columns",
    "token_font_size", "counter_font_size", "utility_font_size",
    "token_text_color", "counter_text_color", "utility_text_color",
    "show_customer_name", "show_phone_number", "show_partially_masked_phone_number", "show_order_details",
    "audio_enabled", "announcement_language",
    "blink_token", "blink_utility",
    "qr_placement", "qr_base_url", "qr_expiry_minutes",
    "enable_ads", "ad_position", "ad_interval",
    "video_ad_mode",
    "header_font_size", "header_font_style", "header_text_color",
    "footer_font_size", "footer_text_color", "footer_enabled", "footer_texts",
    "advertisements", "advertisement_ids", "device_ids",
]

# Hospital Flash allows presentation + ads but not Dine visibility/QR/link-to-TV fields.
HOSPITAL_FLASH_FORBIDDEN_TV_CONFIG_FIELDS = [
    "show_customer_name", "show_phone_number", "show_partially_masked_phone_number", "show_order_details",
    "qr_placement", "qr_base_url", "qr_expiry_minutes",
    "device_ids", "linked_tv_mac",
]

HOSPITAL_FLASH_FORBIDDEN_TV_CONFIG_REP_FIELDS = HOSPITAL_FLASH_FORBIDDEN_TV_CONFIG_FIELDS + [
    "show_no_of_packs",
]


class TVAdvertisementSerializer(serializers.ModelSerializer):
    media_url = serializers.SerializerMethodField()
    media_cache_key = serializers.SerializerMethodField()

    class Meta:
        model = TVAdvertisement
        fields = [
            "id",
            "title",
            "media_type",
            "media_url",
            "sequence",
            "is_active",
            "media_cache_key",
            "created_at",
            "updated_at",
        ]

    def get_media_url(self, obj):
        request = self.context.get("request")
        if not obj.media_file:
            return None
        if request:
            return request.build_absolute_uri(obj.media_file.url)
        return obj.media_file.url

    def get_media_cache_key(self, obj):
        return int(obj.updated_at.timestamp()) if obj.updated_at else None

class TVDeviceConfigSerializer(serializers.ModelSerializer):
    admin_outlet = serializers.PrimaryKeyRelatedField(queryset=AdminOutlet.objects.all(), required=True)
    utilities = serializers.PrimaryKeyRelatedField(many=True, queryset=Utility.objects.all(), required=False, allow_empty=True)
    advertisement_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=TVAdvertisement.objects.all(),
        required=False,
        write_only=True,
        source="advertisements",
    )
    device_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=AndroidDevice.objects.all(),
        required=False,
        write_only=True,
        source="devices",
    )
    advertisements = serializers.SerializerMethodField(read_only=True)
    linked_tv_mac = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TVDeviceConfig
        fields = [
            "id",
            "admin_outlet",
            "config_name",
            "show_qr",
            "qr_alignment",
            "items_to_show",
            "booking_fields",
            "utility_name_mode",
            "screen_orientation",
            "utilities",
            "created_at",
            "updated_at",
            # New fields
            "display_rows",
            "display_columns",
            "token_font_size",
            "counter_font_size",
            "utility_font_size",
            "token_text_color",
            "counter_text_color",
            "utility_text_color",
            "show_customer_name",
            "show_phone_number",
            "show_partially_masked_phone_number",
            "show_order_details",
            "audio_enabled",
            "announcement_language",
            "blink_token",
            "blink_utility",
            "qr_placement",
            "qr_base_url",
            "qr_expiry_minutes",
            "enable_ads",
            "ad_position",
            "ad_interval",
            "video_ad_mode",
            "header_font_size",
            "header_font_style",
            "header_text_color",
            "footer_font_size",
            "footer_text_color",
            "footer_enabled",
            "footer_texts",
            "advertisements",
            "advertisement_ids",
            "device_ids",
            "linked_tv_mac",
        ]
        read_only_fields = ("created_at", "updated_at", "id")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If we have an instance or data, we can check the outlet
        # NOTE: DRF commonly passes `instance` positionally, so rely on self.instance.
        instance = getattr(self, "instance", None)
        data = kwargs.get('data')
        
        admin_outlet = None
        if instance:
            if hasattr(instance, "admin_outlet"):
                admin_outlet = instance.admin_outlet
            elif hasattr(instance, "first"):
                first_instance = instance.first()
                admin_outlet = getattr(first_instance, "admin_outlet", None) if first_instance else None
            elif isinstance(instance, (list, tuple)):
                first_instance = instance[0] if instance else None
                admin_outlet = getattr(first_instance, "admin_outlet", None) if first_instance else None
        elif data:
            outlet_id = data.get('admin_outlet')
            if outlet_id:
                try:
                    admin_outlet = AdminOutlet.objects.get(id=outlet_id)
                except (AdminOutlet.DoesNotExist, ValueError, TypeError):
                    pass
        
        outlet_project = (getattr(admin_outlet, "project_code", "") or "").strip().lower() if admin_outlet else ""
        current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        is_dine_flash = (
            (admin_outlet and dine_flash_exclusive_tv_device_policy_applies(admin_outlet))
            or outlet_project == "dine_flash"
            or current_project == "dine_flash"
        )
        is_hospital_flash = hospital_flash_tv_configuration_applies(admin_outlet)

        if is_dine_flash:
            return

        if is_hospital_flash:
            for field in HOSPITAL_FLASH_FORBIDDEN_TV_CONFIG_FIELDS:
                if field in self.fields:
                    self.fields.pop(field)
            return

        for field in DINE_FLASH_ONLY_TV_CONFIG_FIELDS:
            if field in self.fields:
                self.fields.pop(field)

    def validate_items_to_show(self, value):
        admin_outlet = None
        if self.instance is not None:
            if hasattr(self.instance, "admin_outlet"):
                admin_outlet = self.instance.admin_outlet
            elif hasattr(self.instance, "first"):
                first_instance = self.instance.first()
                admin_outlet = getattr(first_instance, "admin_outlet", None) if first_instance else None
            elif isinstance(self.instance, (list, tuple)):
                first_instance = self.instance[0] if self.instance else None
                admin_outlet = getattr(first_instance, "admin_outlet", None) if first_instance else None

        if admin_outlet is None:
            raw_outlet = self.initial_data.get("admin_outlet") if hasattr(self, "initial_data") else None
            try:
                admin_outlet = AdminOutlet.objects.filter(id=raw_outlet).first()
            except (TypeError, ValueError):
                admin_outlet = None

        outlet_project = (getattr(admin_outlet, "project_code", "") or "").strip().lower() if admin_outlet else ""
        current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        is_dine_flash = outlet_project == "dine_flash" or current_project == "dine_flash"

        max_items = 20 if is_dine_flash else 5
        if value < 1 or value > max_items:
            raise serializers.ValidationError(f"items_to_show must be between 1 and {max_items}.")
        return value

    def validate_booking_fields(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("booking_fields must be a list.")

        admin_outlet = None
        if self.instance is not None:
            admin_outlet = getattr(self.instance, "admin_outlet", None)
        if admin_outlet is None and hasattr(self, "initial_data"):
            raw_outlet = self.initial_data.get("admin_outlet")
            try:
                admin_outlet = AdminOutlet.objects.filter(id=raw_outlet).first()
            except (TypeError, ValueError):
                admin_outlet = None

        outlet_project = (getattr(admin_outlet, "project_code", "") or "").strip().lower() if admin_outlet else ""
        current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        is_hospital_flash = outlet_project == "hospital_flash" or current_project == "hospital_flash"

        if len(value) == 0:
            if is_hospital_flash:
                return value
            raise serializers.ValidationError("At least one booking field must be selected.")
        invalid = [v for v in value if v not in ALLOWED_BOOKING_FIELDS]
        if invalid:
            raise serializers.ValidationError(f"Invalid booking_fields: {invalid}. Allowed values: {sorted(ALLOWED_BOOKING_FIELDS)}")
        return value

    def validate(self, attrs):
        show_qr = attrs.get("show_qr", getattr(self.instance, "show_qr", False))
        qr_alignment = attrs.get("qr_alignment", getattr(self.instance, "qr_alignment", None))
        qr_placement = attrs.get("qr_placement", getattr(self.instance, "qr_placement", None))
        if show_qr and not qr_alignment and not qr_placement:
            raise serializers.ValidationError({"qr_alignment": "qr_alignment or qr_placement is required when show_qr is true."})

        # utilities -- ensure they belong to the same admin_outlet when provided
        utilities = attrs.get("utilities", None)
        admin_outlet = attrs.get("admin_outlet") or getattr(self.instance, "admin_outlet", None)
        if utilities and admin_outlet:
            bad = [u.id for u in utilities if u.vendor is None or u.vendor.admin_outlet != admin_outlet]
            # note: Utility has vendor relation; ensure vendor matches admin_outlet.vendor
            if bad:
                raise serializers.ValidationError({"utilities": f"Utilities {bad} do not belong to the same vendor as admin_outlet."})

        ad_interval = attrs.get("ad_interval", getattr(self.instance, "ad_interval", 8))
        if ad_interval < 3 or ad_interval > 120:
            raise serializers.ValidationError({"ad_interval": "ad_interval must be between 3 and 120 seconds."})

        advertisements = attrs.get("advertisements", None)
        if advertisements is not None and admin_outlet:
            if len(advertisements) > MAX_TV_ADS_PER_CONFIGURATION:
                raise serializers.ValidationError(
                    {
                        "advertisement_ids": (
                            f"A maximum of {MAX_TV_ADS_PER_CONFIGURATION} advertisements can be assigned per configuration."
                        )
                    }
                )

        devices = attrs.get("devices", None)
        if devices is not None and admin_outlet:
            invalid_devices = [
                device.id for device in devices
                if device.admin_outlet_id != admin_outlet.id or device.vendor_id is None
            ]
            if invalid_devices:
                raise serializers.ValidationError(
                    {"device_ids": f"Devices {invalid_devices} are not vendor-mapped devices of this outlet."}
                )
            already_assigned = []
            for device in devices:
                if not device.tv_config_id:
                    continue
                if self.instance and device.tv_config_id == self.instance.id:
                    continue
                already_assigned.append(device.id)
            if already_assigned:
                raise serializers.ValidationError(
                    {"device_ids": f"Devices {already_assigned} are already mapped to a TV configuration."}
                )
            if dine_flash_exclusive_tv_device_policy_applies(admin_outlet) and len(devices) > 1:
                raise serializers.ValidationError(
                    {
                        "device_ids": (
                            "Dine Flash allows only one TV device per configuration. "
                            "Create a separate configuration for each TV."
                        )
                    }
                )
            if advertisements is not None:
                invalid_ads = [ad.id for ad in advertisements if ad.admin_outlet_id != admin_outlet.id]
                if invalid_ads:
                    raise serializers.ValidationError(
                        {"advertisement_ids": f"Advertisements {invalid_ads} do not belong to this outlet."}
                    )

        footer_enabled = attrs.get("footer_enabled", getattr(self.instance, "footer_enabled", False))
        footer_texts = attrs.get("footer_texts", getattr(self.instance, "footer_texts", []))
        if footer_texts is None:
            footer_texts = []
        if not isinstance(footer_texts, list):
            raise serializers.ValidationError({"footer_texts": "footer_texts must be a list of strings."})
        cleaned_footer_texts = []
        for item in footer_texts:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                cleaned_footer_texts.append(text[:120])
        if len(cleaned_footer_texts) > MAX_FOOTER_TEXTS:
            raise serializers.ValidationError(
                {"footer_texts": f"Maximum {MAX_FOOTER_TEXTS} footer texts are allowed."}
            )
        if footer_enabled and len(cleaned_footer_texts) == 0:
            raise serializers.ValidationError(
                {"footer_texts": "Add at least one footer text when footer is enabled."}
            )
        attrs["footer_texts"] = cleaned_footer_texts

        admin_outlet_for_create = attrs.get("admin_outlet") or getattr(self.instance, "admin_outlet", None)
        if self.instance is None and dine_flash_exclusive_tv_device_policy_applies(admin_outlet_for_create):
            devices_for_create = attrs.get("devices")
            if not devices_for_create:
                raise serializers.ValidationError(
                    {"device_ids": "Select a TV to link to this configuration."}
                )

        if self.instance is not None and admin_outlet and dine_flash_exclusive_tv_device_policy_applies(admin_outlet):
            devices_in_attrs = attrs.get("devices")
            if devices_in_attrs is not None and len(devices_in_attrs) == 0:
                raise serializers.ValidationError(
                    {"device_ids": "Select a TV to link; mapping cannot be cleared for Dine Flash."}
                )
            if not self.instance.devices.exists() and not devices_in_attrs:
                raise serializers.ValidationError(
                    {
                        "device_ids": (
                            "This configuration has no linked TV. Edit it, choose an Android TV "
                            "under Linked Android TV (MAC), and save."
                        )
                    }
                )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        utilities = validated_data.pop("utilities", [])
        advertisements = validated_data.pop("advertisements", [])
        devices = validated_data.pop("devices", [])
        config = TVDeviceConfig.objects.create(**validated_data)
        if utilities:
            config.utilities.set(utilities)
        if advertisements:
            config.advertisements.set(advertisements)
        if devices:
            AndroidDevice.objects.filter(id__in=[device.id for device in devices]).update(tv_config=config)
        return config

    @transaction.atomic
    def update(self, instance, validated_data):
        utilities = validated_data.pop("utilities", None)
        advertisements = validated_data.pop("advertisements", None)
        devices = validated_data.pop("devices", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if utilities is not None:
            instance.utilities.set(utilities)
        if advertisements is not None:
            if hospital_flash_tv_configuration_applies(instance.admin_outlet):
                # Hospital edit UI may omit inactive / unavailable ads from the selectable list.
                # Preserve those existing links unless they were explicitly included and removed
                # (they cannot be selected in UI, so always keep currently-linked inactive ads).
                submitted_ids = {ad.id for ad in advertisements}
                preserve_inactive = list(
                    instance.advertisements.filter(is_active=False).exclude(id__in=submitted_ids)
                )
                instance.advertisements.set(list(advertisements) + preserve_inactive)
            else:
                instance.advertisements.set(advertisements)
        if devices is not None:
            AndroidDevice.objects.filter(tv_config=instance).exclude(id__in=[device.id for device in devices]).update(tv_config=None)
            AndroidDevice.objects.filter(id__in=[device.id for device in devices]).update(tv_config=instance)
        return instance

    def get_advertisements(self, instance):
        ads_qs = instance.advertisements.order_by("sequence", "created_at", "id")
        # Hospital edit round-trip needs inactive assigned ads visible to the client.
        # Dine and other flavours keep the active-only contract.
        if not hospital_flash_tv_configuration_applies(getattr(instance, "admin_outlet", None)):
            ads_qs = ads_qs.filter(is_active=True)
        return TVAdvertisementSerializer(ads_qs, many=True, context=self.context).data

    def get_linked_tv_mac(self, obj):
        if not obj.admin_outlet or not dine_flash_exclusive_tv_device_policy_applies(obj.admin_outlet):
            return None
        dev = obj.devices.first()
        if not dev:
            return None
        mac = (getattr(dev, "mac_address", None) or "").strip()
        return mac or None

    def to_representation(self, instance):
        """
        Exclude new fields from representation if the outlet is NOT Dine Flash.
        """
        rep = super().to_representation(instance)
        
        # Check if it's Dine Flash using the same policy helper used by views/validation.
        is_dine_flash = bool(
            instance.admin_outlet and dine_flash_exclusive_tv_device_policy_applies(instance.admin_outlet)
        )
        is_hospital_flash = hospital_flash_tv_configuration_applies(instance.admin_outlet)

        if instance.admin_outlet and dine_flash_exclusive_tv_device_policy_applies(instance.admin_outlet):
            rep["mapped_device_ids"] = list(instance.devices.values_list("id", flat=True))
        else:
            rep.pop("linked_tv_mac", None)

        # Dine Flash API/UI contract: expose only show_no_of_packs in responses.
        # Keep underlying DB field as show_order_details for backward-compatible writes.
        if is_dine_flash and "show_order_details" in rep:
            rep["show_no_of_packs"] = rep.get("show_order_details")
            rep.pop("show_order_details", None)

        if is_hospital_flash:
            for field in HOSPITAL_FLASH_FORBIDDEN_TV_CONFIG_REP_FIELDS:
                rep.pop(field, None)
            # Full M2M id list (active + inactive) for safe Hospital edit round-trips.
            rep["assigned_advertisement_ids"] = list(
                instance.advertisements.values_list("id", flat=True)
            )
            return rep

        if not is_dine_flash:
            for field in DINE_FLASH_ONLY_TV_CONFIG_FIELDS + ["show_no_of_packs"]:
                rep.pop(field, None)
                
        return rep
