from rest_framework import serializers
from vendors.models import (Vendor,AndroidDevice,
                            Device ,AdvertisementImage,
                            AdvertisementProfile,
                            AdvertisementProfileAssignment,
                            AdminOutlet,UserProfile,
                            AndroidAPK)
from django.contrib.auth.models import User
from django.db.models import Q
import json

class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['id','vendor_id', 'name', 'location']  


class VendorDetailSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    menu_files = serializers.SerializerMethodField()
    android_tvs = serializers.SerializerMethodField()
    keypad_devices = serializers.SerializerMethodField()

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
                        url = request.build_absolute_uri(f"/media/{path}")
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

    def create(self, validated_data):
        images = validated_data.pop('image_ids', [])
        profile = AdvertisementProfile.objects.create(
            admin_outlet=self.context['request'].user.admin_outlet,
            **validated_data
        )
        profile.images.set(images)
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

class AdminOutletAutoDeleteSerializer(serializers.ModelSerializer):
    auto_delete_hours = serializers.IntegerField(
        required=False, allow_null=True, min_value=2,
        help_text="Auto-delete order data after these many hours. Set null to disable."
    )

    class Meta:
        model = AdminOutlet
        fields = ['auto_delete_hours']
    
    def to_internal_value(self, data):
        if 'auto_delete_hours' in data and data['auto_delete_hours'] == 'None':
            data['auto_delete_hours'] = None 
        return super().to_internal_value(data)

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
        ]

    def get_outlet_name(self, obj):
        return obj.vendor.admin_outlet.customer_name if obj.vendor and obj.vendor.admin_outlet else None

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
