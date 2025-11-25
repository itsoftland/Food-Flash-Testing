from rest_framework import serializers
from vendors.models import (Vendor,AndroidDevice,
                            Device ,AdvertisementImage,
                            AdvertisementProfile,
                            AdvertisementProfileAssignment,
                            AdminOutlet,UserProfile,
                            AndroidAPK,MqttServerConfig,
                            VendorConfig,OrderStatusHistory,
                            AdvertisementSlot,TVDeviceConfig,Utility)
from django.contrib.auth.models import User
from django.db.models import Q
import json
import datetime
from django.conf import settings
from django.db import transaction
start_url = getattr(settings, "PROJECT_NAME", "calleron")

class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['id','vendor_id', 'name', 'location']  

class MqttServerConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = MqttServerConfig
        # adjust these fields to match your MqttServerConfig model
        fields = ['id', 'name', 'host', 'port']  # example fields

class VendorConfigSerializer(serializers.ModelSerializer):
    mqtt_server = MqttServerConfigSerializer(read_only=True)

    class Meta:
        model = VendorConfig
        fields = [
            'mqtt_server',
            'token_display_limit',
            'tv_communication_mode',
            'mqtt_mode',
            'business_day_start_hour',
            'timezone',
            'auto_delete_hours'
        ]
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
        fields = ['id', 'mac_address', 'vendor', 'created_at', 'updated_at']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['mac_address'] = representation.pop('mac_address', None)
        return representation

from vendors.models import Order

class OrderSerializer(serializers.ModelSerializer):
    outlet_name = serializers.SerializerMethodField()
    vendor_id = serializers.IntegerField(source='vendor.id')
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    device_id = serializers.IntegerField(source='device.id', allow_null=True, read_only=True)
    device_name = serializers.CharField(source='device.serial_no', allow_null=True, read_only=True)
    ready_status = serializers.SerializerMethodField()

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
            'ready_status'
        ]

    def get_outlet_name(self, obj):
        return obj.vendor.admin_outlet.customer_name if obj.vendor and obj.vendor.admin_outlet else None
    def get_ready_status(self, obj):
        if obj.status_history.exists():
            first_ready_status = obj.status_history.filter(new_status__iexact='ready').order_by('changed_at').first()
            if first_ready_status:
                return first_ready_status.changed_at
        return None

class UserProfileCreateSerializer(serializers.Serializer):
    ROLE_CHOICES = [
        ('admin_manager', 'Admin Manager'),
        ('outlet_manager', 'Outlet Manager'),
        ('order_manager', 'Order Manager'),
        ('web_user', 'Web User'),
        ('both', 'Both Manager and Web User'),
    ]
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    name = serializers.CharField()
    role = serializers.ChoiceField(choices=ROLE_CHOICES)
    customer_id = serializers.IntegerField()
    vendor_id = serializers.IntegerField()

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be empty or just spaces.")
        return value

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        
        if User.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError("Username already exists.")

        # Validate AdminOutlet via customer_id
        try:
            data['admin_outlet'] = AdminOutlet.objects.get(customer_id=data['customer_id'])
        except AdminOutlet.DoesNotExist:
            raise serializers.ValidationError("AdminOutlet with the given customer_id not found.")

        # Validate Vendor via vendor_id
        try:
            data['vendor'] = Vendor.objects.get(id=data['vendor_id'])
        except Vendor.DoesNotExist:
            raise serializers.ValidationError("Vendor with the given ID not found.")

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
            created_profiles.append(profile)

        return created_profiles if len(created_profiles) > 1 else created_profiles[0]

class UserListDetailSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    outlet_name = serializers.CharField(source='admin_outlet.name', read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True, default=None)

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'username',
            'email',
            'name',
            'outlet_name',
            'vendor_name',
            'created_at',
            'updated_at',
            # Note: We won't include `role` here; instead, we manually inject `roles`
        ]

class OrderStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ['previous_status', 'new_status', 'changed_by', 'changed_at']


ALLOWED_BOOKING_FIELDS = {"name", "phone", "guest_count", "datetime", "token"}

class TVDeviceConfigSerializer(serializers.ModelSerializer):
    admin_outlet = serializers.PrimaryKeyRelatedField(queryset=AdminOutlet.objects.all(), required=True)
    utilities = serializers.PrimaryKeyRelatedField(many=True, queryset=Utility.objects.all(), required=False, allow_empty=True)

    class Meta:
        model = TVDeviceConfig
        fields = [
            "id",
            "admin_outlet",
            "show_qr",
            "qr_alignment",
            "items_to_show",
            "booking_fields",
            "utility_name_mode",
            "screen_orientation",
            "utilities",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at", "id")

    def validate_items_to_show(self, value):
        if value < 1 or value > 3:
            raise serializers.ValidationError("items_to_show must be between 1 and 3.")
        return value

    def validate_booking_fields(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("booking_fields must be a list.")
        if len(value) == 0:
            raise serializers.ValidationError("At least one booking field must be selected.")
        invalid = [v for v in value if v not in ALLOWED_BOOKING_FIELDS]
        if invalid:
            raise serializers.ValidationError(f"Invalid booking_fields: {invalid}. Allowed values: {sorted(ALLOWED_BOOKING_FIELDS)}")
        return value

    def validate(self, attrs):
        show_qr = attrs.get("show_qr", getattr(self.instance, "show_qr", False))
        qr_alignment = attrs.get("qr_alignment", getattr(self.instance, "qr_alignment", None))
        if show_qr and not qr_alignment:
            raise serializers.ValidationError({"qr_alignment": "qr_alignment is required when show_qr is true."})

        # utilities -- ensure they belong to the same admin_outlet when provided
        utilities = attrs.get("utilities", None)
        admin_outlet = attrs.get("admin_outlet") or getattr(self.instance, "admin_outlet", None)
        if utilities and admin_outlet:
            bad = [u.id for u in utilities if u.vendor is None or u.vendor.admin_outlet != admin_outlet]
            # note: Utility has vendor relation; ensure vendor matches admin_outlet.vendor
            if bad:
                raise serializers.ValidationError({"utilities": f"Utilities {bad} do not belong to the same vendor as admin_outlet."})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        utilities = validated_data.pop("utilities", [])
        config = TVDeviceConfig.objects.create(**validated_data)
        if utilities:
            config.utilities.set(utilities)
        return config

    @transaction.atomic
    def update(self, instance, validated_data):
        utilities = validated_data.pop("utilities", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if utilities is not None:
            instance.utilities.set(utilities)
        return instance
