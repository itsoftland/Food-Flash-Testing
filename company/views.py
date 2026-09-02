import json
import logging
import random

from django.db import transaction
from django.db.models import Max, Q
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import Http404
from django.urls import reverse
from urllib.parse import quote
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from itertools import chain
from operator import attrgetter
from collections import defaultdict

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from vendors.models import (Vendor, Device, AdminOutlet,
                            AndroidDevice,AdvertisementImage,
                            AdvertisementProfileAssignment,
                            AdvertisementProfile,Order,
                            ArchivedOrder,UserProfile,
                            AndroidAPK,VendorConfig,
                            OrderStatusHistory,ArchivedOrderStatusHistory,
                            Utility,TVDeviceConfig,UtilityOption,
                            TVAdvertisement,BuffetOrderItem,ChatMessage)

from static.utils.functions.validation import validate_fields
from static.utils.functions.utils import (
    get_time_ranges,
    get_filtered_date_range,
    get_vendor_business_day_range,
)
from static.utils.functions.pagination import get_paginated_data
from vendors.dine_flash_tv_fcm import schedule_dine_flash_configuration_updated_for_vendors
from orders.buffet_table_qr import is_valid_buffet_table_no, sign_buffet_table_qr
from orders.hospital_qr import sign_hospital_branch_qr
from vendors.utils import (
    buffet_utility_image_payload,
    validate_buffet_food_type,
    normalize_buffet_utility_description,
    create_buffet_utility_images,
    apply_buffet_utility_image_changes,
    _collect_buffet_upload_files,
    _BUFFET_UTILITY_IMAGES_MAX_COUNT,
    _parse_positive_int,
    validate_hospital_utility_fields,
    hospital_utility_payload,
    apply_hospital_group_departments,
)
from .serializer.vendor_config import (VendorVibrationConfigSerializer,
                                       VendorConfigUpdateSerializer)
from .tv_config_scope import dine_flash_exclusive_tv_device_policy_applies
from .serializers import (VendorSerializer,
                          VendorDetailSerializer,
                          UnmappedVendorDetailSerializer,
                          VendorUpdateSerializer,
                          AdvertisementImageSerializer,
                          AdvertisementProfileSerializer,
                          AdvertisementProfileAssignmentSerializer,
                          AdvertisementProfileMiniSerializer,
                          DashboardMetricsSerializer,
                          DeviceSerializer,AndroidDeviceSerializer,
                          OrderSerializer,UserProfileCreateSerializer,
                          UserListDetailSerializer,ManagerDeviceSerializer,
                          OrderStatusHistorySerializer,TVDeviceConfigSerializer,
                          TVAdvertisementSerializer
                          )

logger = logging.getLogger(__name__)
base = getattr(settings, 'LOGIN_URL')


@login_required()
@never_cache
def dashboard(request):
    logger.info("Company Dashboard requested by user: %s", request.user)
    return render(request, 'company/dashboard.html')

@login_required(login_url=base)
def create_outlet(request):
    return render(request, 'company/outlets/create_outlet.html')

@login_required
def outlets(request):
    return render(request, 'company/outlets/outlets.html')

@login_required
def update_outlet_page(request):
    return render(request, "company/outlets/update_outlet.html")

@login_required
def create_users(request):
    return render(request, 'company/users/create_user.html')

@login_required
def user_list(request):
    return render(request, 'company/users/user_list.html')

@login_required
def manager_devices(request):
    return render(request, 'company/manager_devices.html')

@login_required
def utility_user_devices(request):
    return render(request, 'company/utility_user_devices.html')

@login_required
def keypad_devices(request):
    return render(request, 'company/keypad_devices.html')

@login_required
def android_tvs(request):
    return render(request, 'company/android_tvs.html')

@login_required
def android_tv_config(request):
    return render(request, 'company/android_tv_config.html')

@login_required
def tv_config_list_page(request):
    return render(request, 'company/tv_config_list.html')

@login_required
def tv_configuration_page(request):
    context = {}
    admin_outlet = getattr(request.user, "admin_outlet", None)
    outlet_project = (getattr(admin_outlet, "project_code", "") or "").strip().lower() if admin_outlet else ""
    current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    is_dine_flash = outlet_project == "dine_flash" or current_project == "dine_flash"
    if admin_outlet and is_dine_flash:
        context["mapped_android_devices"] = AndroidDevice.objects.filter(
            admin_outlet=admin_outlet,
            vendor__isnull=False,
            tv_config__isnull=True,
        ).select_related("vendor").order_by("-updated_at")
    return render(request, "company/tv_configuration.html", context)

@login_required
def banners(request):
    return render(request, 'company/banners.html')

@login_required
def new_profile(request):
    return render(request, 'company/profiles/new_profile.html')

@login_required
def profile_list(request):
    return render(request, 'company/profiles/profile_list.html')

@login_required
def map_profiles(request):
    return render(request, 'company/profiles/map_profiles.html')

@login_required
def mapped_list(request):
    return render(request, 'company/profiles/mapped_list.html')

@login_required
def configurations(request):
    current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    is_hospital = current_project == "hospital_flash"
    context = {
        "is_dine_flash": current_project == "dine_flash",
        "is_hospital_flash": is_hospital,
    }
    if is_hospital:
        from vendors.hospital_announcement_templates import catalog_for_admin
        import json

        context["hospital_announcement_catalog_json"] = json.dumps(catalog_for_admin())
    return render(
        request,
        "company/configurations.html",
        context,
    )

@login_required
def total_orders(request):
    return render(request, 'company/analytics/total_orders.html')

@login_required
def order_details(request):
    return render(request, 'company/analytics/order_details.html')

@login_required
def utilities_management(request):
    return render(request, 'company/utilities/utilities_management.html')

@login_required
def create_utility_page(request):
    return render(request, 'company/utilities/create_utility.html')

@api_view(['GET']) 
@permission_classes([IsAuthenticated])
def get_vendor_details(request):
    """
    API endpoint to fetch details of a vendor.
    """
    vendor_id = request.GET.get('vendor_id')
    logger.info("Fetching vendor details for vendor_id: %s (User: %s)", vendor_id, request.user)
    
    if not vendor_id:
        logger.warning("Vendor ID not provided in request by user: %s", request.user)
        return Response({'error': 'Vendor ID not provided'}, status=400)
    try:
        vendor = Vendor.objects.get(vendor_id=vendor_id)
        logger.debug("Vendor found: %s", vendor.name)
    except Vendor.DoesNotExist:
        logger.error("Vendor not found for vendor_id: %s", vendor_id)
        return Response({'error': 'Vendor not found'}, status=400)
    
    serializer = VendorDetailSerializer(
        vendor, context={'request': request}
        ).data

    unmapped_vendors_data = UnmappedVendorDetailSerializer(
        vendor, context={'request': request}
        ).data
    # Get TV communication mode choices from the VendorConfig model field
    try:
        tv_comm_field = VendorConfig._meta.get_field('tv_communication_mode')
        tv_comm_choices = [{'key': choice[0], 'value': choice[1]} for choice in tv_comm_field.choices]
    except Exception as e:
        logger.warning("Failed to fetch tv_communication_mode choices: %s", str(e))
        tv_comm_choices = []

    # Get mqtt_mode choices as well
    try:
        mqtt_mode_field = VendorConfig._meta.get_field('mqtt_mode')
        mqtt_mode_choices = [{'key': choice[0], 'value': choice[1]} for choice in mqtt_mode_field.choices]
    except Exception as e:
        logger.warning("Failed to fetch mqtt_mode choices: %s", str(e))
        mqtt_mode_choices = []
    
    logger.info("Successfully retrieved details for vendor: %s", vendor_id)
    return Response({
        "vendor_data": serializer,
        "unmapped_data":unmapped_vendors_data,
        'tv_communication_modes': tv_comm_choices,
        'mqtt_modes': mqtt_mode_choices,   
        "message": "Success"
        }, status=200)

@api_view(['GET']) 
@permission_classes([IsAuthenticated])
def get_vendors(request):
    """
    Returns all vendors associated with the logged-in admin outlet.
    """
    user = request.user
    logger.info("Fetching vendors list for user: %s", user)
    try:
        admin_outlet = user.admin_outlet
    except AdminOutlet.DoesNotExist:
        logger.error("AdminOutlet not found for user: %s", user)
        return Response(
            {"error": "AdminOutlet not found for this user."}
            , status=404)

    vendors = admin_outlet.vendors.all()
    vendors_data = VendorSerializer(vendors, many=True).data
    logger.debug("Found %d vendors for admin_outlet: %s", vendors.count(), admin_outlet.customer_name)
       
    return Response(
        {"vendors": vendors_data, "message": "Success"}
        , status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_outlet_creation_data(request):
    """
    GET /api/get_outlet_creation_data/
    """
    user = request.user
    logger.info("Fetching outlet creation data for user: %s", user)
    try:
        admin_outlet = user.admin_outlet
    except AdminOutlet.DoesNotExist:
        logger.error("AdminOutlet (customer_id) invalid or not found for user: %s", user)
        return Response(
            {'error': 'Invalid customer_id'}
            ,status=status.HTTP_404_NOT_FOUND)

    # Parse all locations from JSON field
    try:
        locations_data = json.loads(admin_outlet.locations)
    except json.JSONDecodeError:
        return Response(
            {'error': 'Invalid locations JSON'}
            , status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    # All locations
    locations = []
    for location in locations_data:
        for name, code in location.items():
            # if code not in mapped_codes:
            locations.append({'key': name, 'value': code})

    # Get unmapped keypad devices
    available_keypads = Device.objects.filter(
        admin_outlet=admin_outlet, vendor__isnull=True
        ).values('serial_no')

    # Get unmapped Android TVs
    available_android_tvs = AndroidDevice.objects.filter(
        admin_outlet=admin_outlet, vendor__isnull=True
        ).values('mac_address')
    
    # Get TV communication mode choices from the VendorConfig model field
    try:
        tv_comm_field = VendorConfig._meta.get_field('tv_communication_mode')
        tv_comm_choices = [{'key': choice[0], 'value': choice[1]} for choice in tv_comm_field.choices]
    except Exception as e:
        # Fallback — empty list if something goes wrong
        tv_comm_choices = []
        # Optionally log the exception

    # (Optional) Get mqtt_mode choices as well
    try:
        mqtt_mode_field = VendorConfig._meta.get_field('mqtt_mode')
        mqtt_mode_choices = [{'key': choice[0], 'value': choice[1]} for choice in mqtt_mode_field.choices]
    except Exception:
        mqtt_mode_choices = []

    return Response({
        'locations': locations,
        'keypad_devices': list(available_keypads),
        'android_tvs': list(available_android_tvs),
        'tv_communication_modes': tv_comm_choices,
        'mqtt_modes': mqtt_mode_choices,   # optional
    }, status=status.HTTP_200_OK)

def generate_unique_vendor_id():
    """
    Generates a unique 6-digit vendor ID by randomly generating a number
    between 100000 and 999999 until a unique ID is found.

    Returns:
        int: A unique 6-digit vendor ID.
    """
    while True:
        # Generate a random 6-digit number, first digit 1-9
        vendor_id = random.randint(100000, 999999)
        if not Vendor.objects.filter(vendor_id=vendor_id).exists():
            return vendor_id
        
@api_view(['POST'])
@validate_fields([
    'customer_id',
    'name',
    'alias_name',
    'location',
    'location_id',
    'tv_communication_mode',
    'business_day_start_hour',
    'timezone',
])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@transaction.atomic
def create_vendor(request):
    """
    Creates a new vendor for the given admin outlet.

    Parameters:
    request (Request): Django's request object

    Returns:
    Response: A response containing the vendor ID of the newly created vendor.

    Status Codes:
    201 Created: Vendor created successfully
    400 Bad Request: Error during vendor creation
    409 Conflict: Vendor with the same name already exists
    """
    try:
        logger.info("Vendor creation initiated by user: %s", request.user)
        logger.debug("Incoming vendor creation data: %s", dict(request.data))
        
        customer_id = request.data.get('customer_id')
        admin_outlet = get_object_or_404(AdminOutlet, customer_id=customer_id)

        name = request.data.get('name')
        alias_name = request.data.get('alias_name')
        location = request.data.get('location')
        place_id = request.data.get('place_id', '')
        location_id = request.data.get('location_id')
        tv_communication_mode = request.data.get('tv_communication_mode')
        business_day_start_hour = request.data.get('business_day_start_hour')
        timezone = request.data.get('timezone')
        mqtt_mode = request.data.get('mqtt_mode', 'All')  
        
        if Vendor.objects.filter(name__iexact=name).exists():
            logger.warning("Vendor with name '%s' already exists", name)
            return Response({
                'success': False,
                'error': 'Vendor with this name already exists.'
            }, status=status.HTTP_409_CONFLICT)

        # Generate unique vendor_id
        vendor_id = generate_unique_vendor_id()
        logger.debug("Generated unique vendor_id: %s", vendor_id)

        # Handle logo file upload
        logo_file = request.FILES.get('logo')
        logo_path = None
        if logo_file:
            logo_path = default_storage.save('vendor_logos/' + logo_file.name, ContentFile(logo_file.read()))
            logger.debug("Uploaded logo file to: %s", logo_path)

        # Handle multiple menu files
        menu_files = request.FILES.getlist('menu_files')
        menu_paths = []
        for file in menu_files:
            path = default_storage.save('menus/' + file.name, ContentFile(file.read()))
            menu_paths.append(path)
        logger.debug("Uploaded menu files: %s", menu_paths)
        
        # Create Vendor instance
        vendor = Vendor.objects.create(
            admin_outlet=admin_outlet,
            name=name,
            alias_name=alias_name,
            location=location,
            place_id=place_id,
            vendor_id=vendor_id,
            location_id=location_id,
            logo=logo_path,
            menus=json.dumps(menu_paths),
        )
        logger.info("Vendor created: %s", vendor.vendor_id)
        config_kwargs = {
            "vendor": vendor,
            "tv_communication_mode": tv_communication_mode,
            "business_day_start_hour": business_day_start_hour,
            "timezone": timezone,
            "mqtt_mode": mqtt_mode,
        }
        # Backward-compatible: older live schemas may not have `use_utilities`.
        vendor_config_fields = {f.name for f in VendorConfig._meta.get_fields()}
        if "use_utilities" in vendor_config_fields:
            config_kwargs["use_utilities"] = settings.PROJECT_NAME == "dine_flash_buffet"
        vendor_config = VendorConfig.objects.create(**config_kwargs)
        logger.info("Vendor Config created: %s", vendor_config.tv_communication_mode)
        
        # Handle multiple Device mappings (serial numbers)
        device_serials = request.data.getlist('device_mapping[]')
        for serial in device_serials:
            try:
                device = Device.objects.get(serial_no=serial)
                device.vendor = vendor
                device.save()
                logger.debug("Mapped device serial: %s", serial)
            except Device.DoesNotExist:
                logger.warning("Device not found for serial: %s", serial)

        # Handle multiple AndroidDevice mappings (MAC addresses)
        mac_addresses = request.data.getlist('tv_mapping[]')
        for mac in mac_addresses:
            try:
                android_device = AndroidDevice.objects.get(mac_address=mac)
                android_device.vendor = vendor
                android_device.save()
                logger.debug("Mapped Android device MAC: %s", mac)
            except AndroidDevice.DoesNotExist:
                logger.warning("AndroidDevice not found for MAC: %s", mac)

        return Response({
            'success': True,
            'message': 'Vendor created successfully.',
            'vendor_id': vendor.vendor_id,
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.exception("Error during vendor creation")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@transaction.atomic
def update_vendor(request):
    try:
        logger.info("Vendor update requested by user: %s", request.user)
        logger.debug("Incoming update data: %s", dict(request.data))
        serializer = VendorUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Validation failed: %s", serializer.errors)
            return Response({'errors': serializer.errors}, status=400)

        validated_data = serializer.validated_data
        vendor = Vendor.objects.get(vendor_id=validated_data['vendor_id'])
        # Update basic fields if provided
        for field in ['name', 'alias_name', 'location', 'place_id', 'location_id']:
            value = validated_data.get(field)
            if value:
                setattr(vendor, field, value.strip())
                logger.debug("Updated %s: %s", field, value.strip())

        # Update logo
        logo_file = request.FILES.get('logo')
        if logo_file:
                # Delete existing file if it exists.
            if vendor.logo and default_storage.exists(vendor.logo.name):
                default_storage.delete(vendor.logo.name)
                logger.debug("Deleted old logo: %s", vendor.logo.name)

            logo_path = default_storage.save('vendor_logos/' + logo_file.name, ContentFile(logo_file.read()))
            vendor.logo = logo_path
            logger.debug("Uploaded new logo: %s", logo_path)

        # Update menus
        menu_files = request.FILES.getlist('menus')
        if menu_files:
            if vendor.menus:
                try:
                    old_menu_paths = json.loads(vendor.menus)
                    for old_path in old_menu_paths:
                        if old_path and default_storage.exists(old_path):
                            default_storage.delete(old_path)
                            logger.debug("Deleted old menu file: %s", old_path)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse old menu JSON.")
                
            menu_paths = []
            for file in menu_files:
                path = default_storage.save('menus/' + file.name, ContentFile(file.read()))
                menu_paths.append(path)
            vendor.menus = json.dumps(menu_paths)
            logger.debug("Uploaded new menus: %s", menu_paths)

        vendor.save()
        logger.info("Vendor updated: %s", vendor.vendor_id)

        # Update device mappings
        device_serials = request.data.getlist('device_mapping[]')
        if device_serials:
            # Unmap all devices previously linked to this vendor
            vendor.devices.update(vendor=None)
            logger.debug("Unmapped all previous devices")
            for serial in device_serials:
                try:
                    device = Device.objects.get(serial_no=serial)
                    device.vendor = vendor
                    device.save()
                    logger.debug("Mapped device serial: %s", serial)
                except Device.DoesNotExist:
                    logger.warning("Device not found: %s", serial)

        #Update TV (AndroidDevice) mappings
        mac_addresses = request.data.getlist('tv_mapping[]')
        if mac_addresses:
            vendor.android_devices.update(vendor=None)
            logger.debug("Unmapped all previous Android devices")
            for mac in mac_addresses:
                try:
                    android_device = AndroidDevice.objects.get(mac_address=mac)
                    android_device.vendor = vendor
                    android_device.save()
                    logger.debug("Mapped Android MAC: %s", mac)
                except AndroidDevice.DoesNotExist:
                    logger.warning("AndroidDevice not found: %s", mac)
        
        # Update or create VendorConfig
        auto_delete_val = validated_data.get('auto_delete_hours')
        business_day_start_time = validated_data.get('business_day_start_hour')

        # Handle airline_flash safely
        if settings.PROJECT_NAME == "airline_flash":
            auto_delete_val = None
            business_day_start_time = None

        # Handle disable case
        if auto_delete_val == 0:
            auto_delete_val = None

        config = getattr(vendor, 'config', None)
        if config:
            config.business_day_start_hour = business_day_start_time
            config.auto_delete_hours = auto_delete_val
            config.save(update_fields=['auto_delete_hours', 'business_day_start_hour'])
            logger.info("VendorConfig updated for vendor: %s", vendor.vendor_id)
        else:
            VendorConfig.objects.create(
                vendor=vendor,
                auto_delete_hours=auto_delete_val,
                business_day_start_hour=business_day_start_time
            )
            logger.info("VendorConfig created for vendor: %s", vendor.vendor_id)

        return Response({
            'message': 'Vendor updated successfully.',
            'vendor_id': vendor.vendor_id,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("Error during vendor update")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
        
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_user(request):
    project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    serializer_kwargs = {"data": request.data}
    if project == "dine_flash_buffet":
        serializer_kwargs["context"] = {"request": request}
    serializer = UserProfileCreateSerializer(**serializer_kwargs)
    
    if serializer.is_valid():
        result = serializer.save()

        def _display_username(profile):
            from vendors.hospital_staff_username import display_staff_username
            if project == "hospital_flash":
                return display_staff_username(
                    profile.user.username, profile.admin_outlet_id
                )
            return profile.user.username

        # If multiple profiles (i.e., role == 'both')
        if isinstance(result, list):
            return Response({
                "detail": "User created with both roles successfully.",
                "username": _display_username(result[0]),
                "roles": [profile.role for profile in result],
                "vendor": result[0].vendor.name if result[0].vendor else None,
                "admin_outlet": result[0].admin_outlet.customer_name if result[0].admin_outlet else None,
            }, status=status.HTTP_201_CREATED)

        # If single profile
        user_profile = result
        return Response({
            "detail": "User created successfully.",
            "username": _display_username(user_profile),
            "role": user_profile.role,
            "vendor": user_profile.vendor.name if user_profile.vendor else None,
            "admin_outlet": user_profile.admin_outlet.customer_name if user_profile.admin_outlet else None,
        }, status=status.HTTP_201_CREATED)

    # If validation fails
    if project == "dine_flash_buffet":
        logger.warning(
            "Create user validation failed for user %s: %s",
            request.user,
            serializer.errors,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_users(request):
    """
    API to fetch all users for the logged-in admin's outlet with roles aggregated.
    """
    try:
        admin_outlet = request.user.admin_outlet
        users = UserProfile.objects.filter(admin_outlet=admin_outlet).select_related('user', 'admin_outlet', 'vendor')

        # Group users by user.id and aggregate roles
        grouped_users = defaultdict(lambda: {'roles': []})
        
        for u in users:
            uid = u.user.id
            if 'instance' not in grouped_users[uid]:
                grouped_users[uid]['instance'] = u
            grouped_users[uid]['roles'].append(u.role)

        # Serialize each user once, with aggregated roles
        serialized_data = []
        for data in grouped_users.values():
            instance = data['instance']
            serializer = UserListDetailSerializer(instance, context={'request': request}).data
            serializer['roles'] = list(set(data['roles']))  # Remove duplicates if any
            if settings.PROJECT_NAME == "hospital_flash":
                serializer['vendor'] = instance.vendor_id
            serialized_data.append(serializer)

        return Response({
            'message': 'Users retrieved successfully.',
            'users': serialized_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("Error retrieving users")
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_manager_devices(request):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not associated with this user."}, status=404)

    filter_type = request.GET.get('filter', 'all')  # Options: mapped, unmapped, all

    if filter_type == 'mapped':
        devices = AndroidAPK.objects.filter(admin_outlet=admin_outlet,user_profile__isnull=False)
    elif filter_type == 'unmapped':
        devices = AndroidAPK.objects.filter(admin_outlet=admin_outlet, user_profile__isnull=True)
    else:  # 'all' or invalid filter
        # Return both mapped (only for this admin_outlet) and unmapped devices
        devices = AndroidAPK.objects.filter(admin_outlet=admin_outlet)

    serializer = ManagerDeviceSerializer(devices, many=True)
    return Response({
        "message": "Manager Devices fetched successfully.",
        "devices": serializer.data,
        "count": devices.count(),
        }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_utility_user_devices(request):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not associated with this user."}, status=404)

    filter_type = request.GET.get('filter', 'all')  # Options: mapped, unmapped, all
    base_qs = AndroidAPK.objects.filter(admin_outlet=admin_outlet)
    utility_role_q = Q(user_profile__role='utility_user')

    if filter_type == 'mapped':
        devices = base_qs.filter(utility_role_q)
    elif filter_type == 'unmapped':
        # Keep only devices without any user mapping.
        devices = base_qs.filter(user_profile__isnull=True)
    else:  # 'all' or invalid filter
        # Utility devices and unmapped devices are manageable from this page.
        devices = base_qs.filter(utility_role_q | Q(user_profile__isnull=True))

    serializer = ManagerDeviceSerializer(devices, many=True)
    return Response({
        "message": "Utility user devices fetched successfully.",
        "devices": serializer.data,
        "count": devices.count(),
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unmap_manager_devices(request, device_id):
    try:
        manager_devices = AndroidAPK.objects.get(id=device_id)

        # Permission check
        admin_outlet = getattr(request.user, 'admin_outlet', None)
        if manager_devices.admin_outlet != admin_outlet:
            return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

        # Unlink vendor
        manager_devices.user_profile = None
        manager_devices.save(update_fields=['user_profile'])

        return Response({"message": "Manager unmapped from device successfully."}, status=status.HTTP_200_OK)

    except AndroidAPK.DoesNotExist:
        return Response({"error": "Manager Device not found."}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unmap_utility_user_devices(request, device_id):
    try:
        utility_device = AndroidAPK.objects.get(id=device_id)

        admin_outlet = getattr(request.user, 'admin_outlet', None)
        if utility_device.admin_outlet != admin_outlet:
            return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

        utility_device.user_profile = None
        utility_device.save(update_fields=['user_profile'])

        return Response({"message": "Utility user unmapped from device successfully."}, status=status.HTTP_200_OK)

    except AndroidAPK.DoesNotExist:
        return Response({"error": "Utility user device not found."}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def release_android_apk(request, device_id):
    project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    if project not in ("dine_flash", "dine_flash_buffet"):
        return Response({"error": "Not available for this project."}, status=status.HTTP_403_FORBIDDEN)

    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not associated with this user."}, status=status.HTTP_404_NOT_FOUND)

    try:
        apk_device = AndroidAPK.objects.get(id=device_id)
    except AndroidAPK.DoesNotExist:
        return Response({"error": "Android APK device not found."}, status=status.HTTP_404_NOT_FOUND)

    if apk_device.admin_outlet != admin_outlet:
        return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

    device_pk = apk_device.id
    mac_address = apk_device.mac_address
    customer_id = admin_outlet.customer_id
    username = request.user.username

    logger.info(
        "[APK_RELEASE] Releasing AndroidAPK — device_id=%s mac_address=%s customer_id=%s username=%s",
        device_pk,
        mac_address,
        customer_id,
        username,
    )

    apk_device.delete()

    return Response({"message": "Device released successfully."}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def map_manager_devices(request, device_id):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not found."}, status=status.HTTP_400_BAD_REQUEST)

    manager_id = request.data.get('manager_id')
    if not manager_id:
        return Response({"error": "manager_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        manager_devices = AndroidAPK.objects.get(id=device_id)
    except AndroidAPK.DoesNotExist:
        return Response({"error": "Manager device not found."}, status=status.HTTP_404_NOT_FOUND)

    if manager_devices.admin_outlet != admin_outlet:
        return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

    try:
        manager = UserProfile.objects.get(id=manager_id)
    except UserProfile.DoesNotExist:
        return Response({"error": "Manager not found."}, status=status.HTTP_404_NOT_FOUND)

    # ✅ Enforce same admin outlet
    if manager.admin_outlet != admin_outlet:
        return Response({"error": "Vendor does not belong to your admin outlet."}, status=status.HTTP_403_FORBIDDEN)

    manager_devices.user_profile = manager
    manager_devices.save(update_fields=['user_profile'])

    return Response({"message": "Manager mapped to Device successfully."}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def map_utility_user_devices(request, device_id):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not found."}, status=status.HTTP_400_BAD_REQUEST)

    user_id = request.data.get('utility_user_id')
    if not user_id:
        return Response({"error": "utility_user_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        utility_device = AndroidAPK.objects.get(id=device_id)
    except AndroidAPK.DoesNotExist:
        return Response({"error": "Utility user device not found."}, status=status.HTTP_404_NOT_FOUND)

    if utility_device.admin_outlet != admin_outlet:
        return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

    try:
        utility_user = UserProfile.objects.get(id=user_id)
    except UserProfile.DoesNotExist:
        return Response({"error": "Utility user not found."}, status=status.HTTP_404_NOT_FOUND)

    if utility_user.admin_outlet != admin_outlet:
        return Response({"error": "Utility user does not belong to your admin outlet."}, status=status.HTTP_403_FORBIDDEN)

    if utility_user.role != 'utility_user':
        return Response({"error": "Selected user is not a utility user."}, status=status.HTTP_400_BAD_REQUEST)

    utility_device.user_profile = utility_user
    utility_device.save(update_fields=['user_profile'])

    return Response({"message": "Utility user mapped to device successfully."}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unmap_user(request, user_id):
    try:
        user_details = UserProfile.objects.get(id=user_id)

        # Permission check
        admin_outlet = getattr(request.user, 'admin_outlet', None)
        if user_details.admin_outlet != admin_outlet:
            return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

        # Unlink vendor
        user_details.vendor = None
        user_details.save(update_fields=['vendor'])

        return Response({"message": "User unmapped from outlet successfully."}, status=status.HTTP_200_OK)

    except UserProfile.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def map_user(request, user_id):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not found."}, status=status.HTTP_400_BAD_REQUEST)

    vendor_id = request.data.get('vendor_id')
    if not vendor_id:
        return Response({"error": "vendor_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        vendor_detils = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    if vendor_detils.admin_outlet != admin_outlet:
        return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

    try:
        user_details = UserProfile.objects.get(id=user_id)
    except UserProfile.DoesNotExist:
        return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    # ✅ Enforce same admin outlet
    if user_details.admin_outlet != admin_outlet:
        return Response({"error": "Vendor does not belong to your admin outlet."}, status=status.HTTP_403_FORBIDDEN)

    user_details.vendor = vendor_detils
    user_details.save(update_fields=['vendor'])

    return Response({"message": "User mapped to Outlet successfully."}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_utilities(request):
    try:
        user_id = request.data.get('user_id')
        assigned_utilities = request.data.get('assigned_utilities', [])
        
        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        admin_outlet = getattr(request.user, 'admin_outlet', None)
        if not admin_outlet:
            return Response({"error": "AdminOutlet not found."}, status=status.HTTP_401_UNAUTHORIZED)
            
        try:
            user_profile = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response({"error": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)
            
        if user_profile.admin_outlet != admin_outlet:
            return Response({"error": "You do not have permission to modify this user."}, status=status.HTTP_403_FORBIDDEN)
            
        if user_profile.role != 'utility_user':
            return Response({"error": "User is not a utility_user."}, status=status.HTTP_400_BAD_REQUEST)
            
        if not user_profile.vendor:
            return Response({"error": "User does not belong to a vendor."}, status=status.HTTP_400_BAD_REQUEST)
            
        utilities = Utility.objects.filter(id__in=assigned_utilities, vendor=user_profile.vendor)
        if utilities.count() != len(set(assigned_utilities)):
            return Response({"error": "Some utilities are invalid or do not belong to this vendor."}, status=status.HTTP_400_BAD_REQUEST)
            
        user_profile.assigned_utilities.set(utilities)
        
        return Response({"message": "Assigned utilities updated successfully."}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Error updating user utilities")
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@login_required
def buffet_kitchen(request):
    return render(request, 'company/buffet_kitchen.html')

@login_required
def table_qr_generator(request):
    if (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() != "dine_flash_buffet":
        raise Http404()

    admin_outlet = getattr(request.user, "admin_outlet", None)
    vendors = []
    vendor_error = None

    if not admin_outlet:
        vendor_error = "Your account is not linked to a company outlet."
    else:
        vendors = list(admin_outlet.vendors.order_by("id"))
        if not vendors:
            vendor_error = "No outlet found for your account. Please create an outlet first."

    return render(
        request,
        "company/table_qr_generator.html",
        {
            "vendors": vendors,
            "vendor_error": vendor_error,
        },
    )


def _resolve_buffet_table_qr_vendor(admin_outlet, vendor_id):
    """
    Resolve the vendor for buffet table QR generation.

    - Single-vendor accounts: use that vendor when vendor_id is omitted.
    - Multi-vendor accounts: vendor_id is required and must belong to admin_outlet.
    """
    vendors_qs = admin_outlet.vendors.order_by("id")
    vendor_count = vendors_qs.count()
    if vendor_count == 0:
        return None, "No outlet configured for your account."

    vendor_id_text = str(vendor_id).strip() if vendor_id is not None else ""
    if not vendor_id_text:
        if vendor_count == 1:
            return vendors_qs.first(), None
        return None, "Please select an outlet."

    vendor = vendors_qs.filter(vendor_id=vendor_id_text).first()
    if not vendor:
        try:
            vendor = vendors_qs.filter(vendor_id=int(vendor_id_text)).first()
        except (TypeError, ValueError):
            vendor = None
    if not vendor:
        return None, "Invalid or unauthorized outlet."
    return vendor, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_buffet_table_qr(request):
    if (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() != "dine_flash_buffet":
        return Response({"error": "Not supported"}, status=status.HTTP_400_BAD_REQUEST)

    admin_outlet = getattr(request.user, "admin_outlet", None)
    if not admin_outlet:
        return Response({"error": "Outlet not found for this user."}, status=status.HTTP_403_FORBIDDEN)

    vendor, vendor_error = _resolve_buffet_table_qr_vendor(admin_outlet, request.data.get("vendor_id"))
    if vendor_error:
        status_code = status.HTTP_400_BAD_REQUEST
        if vendor is None and "unauthorized" in vendor_error.lower():
            status_code = status.HTTP_403_FORBIDDEN
        return Response({"error": vendor_error}, status=status_code)

    table_no = request.data.get("table_no")
    if not is_valid_buffet_table_no(table_no):
        return Response(
            {"error": "Table number must be a positive integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        qr_token = sign_buffet_table_qr(vendor.vendor_id, table_no)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    booking_path = reverse("buffet_table_booking")
    qr_url = request.build_absolute_uri(f"{booking_path}?qr_token={quote(qr_token, safe='')}")

    return Response(
        {
            "qr_url": qr_url,
            "qr_token": qr_token,
            "table_no": str(int(str(table_no).strip())),
            "vendor_name": vendor.name,
            "vendor_location": vendor.location or "",
        },
        status=status.HTTP_200_OK,
    )


@login_required
def branch_qr_generator(request):
    """Hospital Flash — branch QR generator page (Company Admin)."""
    if (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() != "hospital_flash":
        raise Http404()

    admin_outlet = getattr(request.user, "admin_outlet", None)
    vendors = []
    vendor_error = None

    if not admin_outlet:
        vendor_error = "Your account is not linked to a company outlet."
    else:
        vendors = list(admin_outlet.vendors.order_by("id"))
        if not vendors:
            vendor_error = "No branch found for your account. Please create a branch first."

    return render(
        request,
        "company/branch_qr_generator.html",
        {
            "vendors": vendors,
            "vendor_error": vendor_error,
        },
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_hospital_branch_qr(request):
    """Hospital Flash — generate a signed branch QR URL for patient registration."""
    if (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() != "hospital_flash":
        return Response({"error": "Not supported"}, status=status.HTTP_400_BAD_REQUEST)

    admin_outlet = getattr(request.user, "admin_outlet", None)
    if not admin_outlet:
        return Response({"error": "Outlet not found for this user."}, status=status.HTTP_403_FORBIDDEN)

    # Reuse Buffet's vendor-resolution helper (generic admin_outlet scoping).
    vendor, vendor_error = _resolve_buffet_table_qr_vendor(admin_outlet, request.data.get("vendor_id"))
    if vendor_error:
        status_code = status.HTTP_400_BAD_REQUEST
        if vendor is None and "unauthorized" in vendor_error.lower():
            status_code = status.HTTP_403_FORBIDDEN
        # Hospital-facing copy: "outlet" → "branch"
        hospital_error = (
            vendor_error.replace("outlet", "branch").replace("Outlet", "Branch")
        )
        return Response({"error": hospital_error}, status=status_code)

    try:
        qr_token = sign_hospital_branch_qr(vendor.vendor_id)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    registration_path = reverse("hospital_patient_registration")
    qr_url = request.build_absolute_uri(
        f"{registration_path}?qr_token={quote(qr_token, safe='')}"
    )

    return Response(
        {
            "qr_url": qr_url,
            "qr_token": qr_token,
            "vendor_id": str(vendor.vendor_id),
            "vendor_name": vendor.name,
            "vendor_location": vendor.location or "",
        },
        status=status.HTTP_200_OK,
    )


@login_required
def utility_user_mapping(request):
    return render(request, 'company/utility_user_mapping.html')

# save individually
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser])
def upload_banner(request):
    try:
        images = request.FILES.getlist('banner_images[]')
        if not images:
            return Response({'error': 'No image file provided.'}, status=400)
        
        admin_outlet = request.user.admin_outlet
        saved_count = 0

        for img in images:
            banner = AdvertisementImage(admin_outlet=admin_outlet, image=img)
            banner.save()  # save individually

            saved_count += 1

        return Response({
            'message': f'{saved_count} banner(s) uploaded successfully.',
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("Error during Banner upload")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_banners(request):
    try:
        admin_outlet = request.user.admin_outlet
        banners = admin_outlet.ad_images.order_by('-uploaded_at')
        serializer = AdvertisementImageSerializer(banners, many=True, context={'request': request})

        return Response({
            'message': 'Banners retrieved successfully.',
            'banners': serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.exception("Error during Banner Listing.")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_banner(request):
    try:
        banner_id = request.GET.get('banner_id')
        if not banner_id or not banner_id.isdigit():
            return Response({
                'error': 'A valid banner_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        admin_outlet = request.user.admin_outlet
        banner = admin_outlet.ad_images.filter(id=banner_id).first()
        # Delete the image file from storage
        banner.image.delete(save=False)

        # Delete the DB record
        banner.delete()

        return Response({
            'message': 'Banner deleted successfully.'
        }, status=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        logger.exception("Error during banner deletion.")
        return Response({
            'error': 'An unexpected error occurred while deleting the banner.'
        }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_advertisement_profile(request):
    try:
        serializer = AdvertisementProfileSerializer(
            data=request.data, context={'request': request})

        if serializer.is_valid():
            profile = serializer.save()
            response_data = AdvertisementProfileSerializer(profile, context={'request': request}).data
            return Response({
                'message': 'Advertisement profile created successfully.',
                'profile': response_data
            }, status=status.HTTP_201_CREATED)

        return Response({
            'error': 'Invalid input.',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.exception("Error during Advertisement Profile creation.")
        return Response({
            'error': str(e)
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_advertisement_profiles(request):
    try:
        # If the user is an outlet admin, filter profiles by their outlet
        admin_outlet = request.user.admin_outlet
        profiles = admin_outlet.ad_profiles

        serializer = AdvertisementProfileSerializer(profiles, context={'request': request}, many=True)
        return Response({
            'message': 'Advertisement profiles fetched successfully.',
            'profiles': serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_available_profiles(request, vendor_id):
    try:
        admin_outlet = request.user.admin_outlet

        # Step 1: Get all profiles created by this outlet admin
        all_profiles = AdvertisementProfile.objects.filter(admin_outlet=admin_outlet)

        # Step 2: Get profile IDs already assigned to this vendor
        assigned_profile_ids = AdvertisementProfileAssignment.objects.filter(
            vendor_id=vendor_id
        ).values_list('profile_id', flat=True)

        # Step 3: Exclude assigned ones
        available_profiles = all_profiles.exclude(id__in=assigned_profile_ids)

        serializer = AdvertisementProfileMiniSerializer(
            available_profiles, context={'request': request}, many=True
        )
        return Response({
            'message': 'Available profiles fetched successfully.',
            'profiles': serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def unmap_profile(request, vendor_id, profile_id):
    try:
        assignment = AdvertisementProfileAssignment.objects.get(
            vendor_id=vendor_id, profile_id=profile_id)
        assignment.delete()

        return Response({
            'message': 'Profile unmapped from vendor successfully.'
        }, status=status.HTTP_204_NO_CONTENT)

    except AdvertisementProfileAssignment.DoesNotExist:
        return Response({
            'error': 'No such mapping found between this vendor and profile.'
        }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_ad_profiles(request):
    try:
        ad_profile_id = request.GET.get('ad_profile_id')
        if not ad_profile_id or not ad_profile_id.isdigit():
            return Response({
                'error': 'A valid ad_profile_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        admin_outlet = request.user.admin_outlet
        ad_profile = admin_outlet.ad_profiles.filter(id=ad_profile_id).first()

        # Delete the DB record
        ad_profile.delete()

        return Response({
            'message': 'Advertisement Profile deleted successfully.'
        }, status=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        logger.exception("Error during Advertisement Profile deletion.")
        return Response({
            'error': 'An unexpected error occurred while deleting the Advertisement Profile.'
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_ad_profile(request):
    try:
        serializer = AdvertisementProfileAssignmentSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response({
                'message': 'Advertisement profiles assigned successfully.',
                'summary': f"{result['vendor_count']} outlets were mapped with {result['profile_count']} profiles each "
                        f"(total {result['total_assigned']} assignments).",
                'duplicates_skipped': result['skipped']
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'error': 'Validation failed.',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'error': 'An unexpected error occurred.',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assigned_profiles(request):
    try:
        vendors = request.user.admin_outlet.vendors.all()
        result = []

        for vendor in vendors:
            assignments = vendor.assigned_profiles.all()
            profiles = [a.profile for a in assignments]
            profile_data = AdvertisementProfileMiniSerializer(profiles, many=True).data

            result.append({
                'outlet_id': vendor.id,
                'outlet_name': vendor.name,
                'assigned_count': len(profiles),
                'assigned_profiles': profile_data
            })

        return Response({
            'message': 'Assigned profiles fetched successfully.',
            'profiles': result
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': 'Something went wrong while fetching assigned profiles.',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_metrics(request):
    try:
        admin_outlet = getattr(request.user, 'admin_outlet', None)

        if not admin_outlet:
            return Response(
                {"error": "Admin outlet not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = DashboardMetricsSerializer(admin_outlet)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": "Something went wrong.", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_devices(request):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not associated with this user."}, status=404)

    filter_type = request.GET.get('filter', 'all')  # Options: mapped, unmapped, all

    if filter_type == 'mapped':
        devices = Device.objects.filter(admin_outlet=admin_outlet,vendor__isnull=False)
    elif filter_type == 'unmapped':
        devices = Device.objects.filter(admin_outlet=admin_outlet, vendor__isnull=True)
    else:  # 'all' or invalid filter
        # Return both mapped (only for this admin_outlet) and unmapped devices
        devices = Device.objects.filter(admin_outlet=admin_outlet)

    serializer = DeviceSerializer(devices, many=True)
    return Response({
        "message": "Devices fetched successfully.",
        "devices": serializer.data,
        "count": devices.count(),
        }, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unmap_device(request, device_id):
    try:
        device = Device.objects.get(id=device_id)

        # Permission check
        admin_outlet = getattr(request.user, 'admin_outlet', None)
        if device.admin_outlet != admin_outlet:
            return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

        # Unlink vendor
        device.vendor = None
        device.save(update_fields=['vendor'])

        return Response({"message": "Vendor unmapped from device successfully."}, status=status.HTTP_200_OK)

    except Device.DoesNotExist:
        return Response({"error": "Device not found."}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def map_device(request, device_id):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not found."}, status=status.HTTP_400_BAD_REQUEST)

    vendor_id = request.data.get('vendor_id')
    if not vendor_id:
        return Response({"error": "vendor_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        device = Device.objects.get(id=device_id)
    except Device.DoesNotExist:
        return Response({"error": "Device not found."}, status=status.HTTP_404_NOT_FOUND)

    if device.admin_outlet != admin_outlet:
        return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    # ✅ Enforce same admin outlet
    if vendor.admin_outlet != admin_outlet:
        return Response({"error": "Vendor does not belong to your admin outlet."}, status=status.HTTP_403_FORBIDDEN)

    device.vendor = vendor
    device.save(update_fields=['vendor'])

    return Response({"message": "Vendor mapped to device successfully."}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_android_tvs(request):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not associated with this user."}, status=404)

    filter_type = request.GET.get('filter', 'all')  # Options: mapped, unmapped, all
    mac_search = (request.GET.get('mac_search') or '').strip()
    outlet_search = (request.GET.get('outlet_search') or '').strip()

    if filter_type == 'mapped':
        android_tvs = AndroidDevice.objects.filter(admin_outlet=admin_outlet,vendor__isnull=False)
    elif filter_type == 'unmapped':
        android_tvs = AndroidDevice.objects.filter(admin_outlet=admin_outlet, vendor__isnull=True)
    else:  # 'all' or invalid filter
        # Return both mapped (only for this admin_outlet) and unmapped devices
        android_tvs = AndroidDevice.objects.filter(admin_outlet=admin_outlet)

    if mac_search:
        normalized_search = ''.join(ch for ch in mac_search if ch.isalnum())
        if normalized_search:
            colon_mac = ':'.join(
                normalized_search[i:i + 2] for i in range(0, len(normalized_search), 2)
            )
            hyphen_mac = '-'.join(
                normalized_search[i:i + 2] for i in range(0, len(normalized_search), 2)
            )
            android_tvs = android_tvs.filter(
                Q(mac_address__icontains=normalized_search) |
                Q(mac_address__icontains=colon_mac) |
                Q(mac_address__icontains=hyphen_mac)
            )

    if outlet_search:
        android_tvs = android_tvs.filter(vendor__name__icontains=outlet_search)

    android_tvs = android_tvs.order_by('-created_at')
    paginated_data = get_paginated_data(android_tvs, request, AndroidDeviceSerializer)
    return Response({
        "message": "Android TV's fetched successfully.",
        "android_tvs": paginated_data["data"],
        "count": paginated_data["total"],
        "meta": {
            "total": paginated_data["total"],
            "page": paginated_data["page"],
            "page_size": paginated_data["page_size"],
            "has_next": paginated_data["has_next"],
            "has_previous": paginated_data["has_previous"],
        },
        }, status=status.HTTP_200_OK)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unmap_android_tvs(request, device_id):
    try:
        android_tvs = AndroidDevice.objects.get(id=device_id)

        # Permission check
        admin_outlet = getattr(request.user, 'admin_outlet', None)
        if android_tvs.admin_outlet != admin_outlet:
            return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

        # Unlink vendor
        android_tvs.vendor = None
        android_tvs.save(update_fields=['vendor'])

        return Response({"message": "Vendor unmapped from device successfully."}, status=status.HTTP_200_OK)

    except AndroidDevice.DoesNotExist:
        return Response({"error": "Android TV not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unmap_and_delete_android_tvs(request, device_id):
    """
    Dine Flash-only action:
    unlink (if needed) and permanently delete Android TV device.
    """
    admin_outlet = getattr(request.user, "admin_outlet", None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not found."}, status=status.HTTP_400_BAD_REQUEST)
    if not dine_flash_exclusive_tv_device_policy_applies(admin_outlet):
        return Response(
            {"error": "This action is available only for Dine Flash."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        android_tvs = AndroidDevice.objects.get(id=device_id)
    except AndroidDevice.DoesNotExist:
        return Response({"error": "Android TV not found."}, status=status.HTTP_404_NOT_FOUND)

    if android_tvs.admin_outlet != admin_outlet:
        return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

    try:
        mac_address = android_tvs.mac_address
        # Break links explicitly before delete; helps with legacy rows/migrations.
        android_tvs.vendor = None
        android_tvs.tv_config = None
        android_tvs.save(update_fields=["vendor", "tv_config"])
        android_tvs.delete()
        return Response(
            {"message": "Android TV unlinked and deleted successfully.", "mac_address": mac_address},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.exception("unmap_and_delete_android_tvs: failed for device_id=%s", device_id)
        return Response(
            {"error": f"Unable to delete device: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def map_android_tvs(request, device_id):
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet:
        return Response({"error": "AdminOutlet not found."}, status=status.HTTP_400_BAD_REQUEST)

    vendor_id = request.data.get('vendor_id')
    if not vendor_id:
        return Response({"error": "vendor_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        android_tvs = AndroidDevice.objects.get(id=device_id)
    except AndroidDevice.DoesNotExist:
        return Response({"error": "Android TV not found."}, status=status.HTTP_404_NOT_FOUND)

    if android_tvs.admin_outlet != admin_outlet:
        return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    # ✅ Enforce same admin outlet
    if vendor.admin_outlet != admin_outlet:
        return Response({"error": "Vendor does not belong to your admin outlet."}, status=status.HTTP_403_FORBIDDEN)

    android_tvs.vendor = vendor
    android_tvs.save(update_fields=['vendor'])

    return Response({"message": "Android TV mapped to  Vendor successfully."}, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_counts_summary(request):
    user = request.user
    admin_outlet = getattr(user, 'admin_outlet', None)

    if not admin_outlet:
        return Response({'error': 'No admin outlet found for this user.'}, status=403)

    vendors = admin_outlet.vendors.all()
    
    start_today, start_week, start_month = get_time_ranges()

    def count_orders_for_range(start_time):
        return (
            Order.objects.filter(vendor__in=vendors, created_at__gte=start_time).count() +
            ArchivedOrder.objects.filter(vendor__in=vendors, created_at__gte=start_time).count()
        )

    return Response({
        "orders_today": count_orders_for_range(start_today),
        "orders_this_week": count_orders_for_range(start_week),
        "orders_this_month": count_orders_for_range(start_month)
    })


def _buffet_business_day_date_q(vendors_qs, outlet_id=None):
    """
    Dine Flash Buffet: match kitchen/manager "today" using each vendor's business day
    window (timezone + business_day_start_hour), not calendar midnight UTC.
    """
    vendors = vendors_qs
    if outlet_id:
        vendors = vendors.filter(id=outlet_id)
    clauses = []
    for vendor in vendors:
        start, end = get_vendor_business_day_range(vendor)
        if start and end:
            clauses.append(Q(vendor=vendor, created_at__gte=start, created_at__lt=end))
    if not clauses:
        return Q(pk__in=[])
    date_q = clauses[0]
    for clause in clauses[1:]:
        date_q |= clause
    return date_q


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def filtered_orders(request):
    """ Fetches and filters both active and archived orders based on various query parameters.
    """
    try:
        admin_outlet = request.user.admin_outlet
    except AttributeError:
        return Response({"error": "Admin outlet not linked to this user."}, status=403)

    vendors_qs = admin_outlet.vendors.all()
    is_buffet = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() == "dine_flash_buffet"

    # ✅ Prepare base queryset for both models
    base_filter = {
        'vendor__in': vendors_qs
    }

    # Optional filters
    outlet_id = request.GET.get('outlet_id')
    if outlet_id:
        base_filter['vendor__id'] = outlet_id

    device_id = request.GET.get('device_id')
    if device_id:
        base_filter['device__id'] = device_id

    status = request.GET.get('status')
    if status:
        if is_buffet:
            buffet_statuses = {
                'created', 'preparing', 'ready', 'delivered', 'cancelled', 'operation_closed',
            }
            if status in buffet_statuses:
                item_qs = BuffetOrderItem.objects.filter(
                    status=status,
                    order__vendor__in=vendors_qs,
                )
                if outlet_id:
                    item_qs = item_qs.filter(order__vendor__id=outlet_id)
                base_filter['id__in'] = item_qs.values('order_id').distinct()
        elif status in ['preparing', 'ready']:
            base_filter['status'] = status

    shown = request.GET.get('shown_on_tv')

    if shown == 'true':
        base_filter['shown_on_tv'] = True
    elif shown == 'false':
        base_filter['shown_on_tv'] = False


    notified = request.GET.get('notified')
    if notified == 'true':
        base_filter['notified_at__isnull'] = False
    elif notified == 'false':
        base_filter['notified_at__isnull'] = True

    # ✅ Date filter
    date_range = request.GET.get('range', 'today')
    from_date = request.GET.get('from')
    to_date = request.GET.get('to')

    buffet_date_q = None
    if is_buffet and date_range == 'today':
        buffet_date_q = _buffet_business_day_date_q(vendors_qs, outlet_id)
    else:
        start, end = get_filtered_date_range(date_range, from_date, to_date)
        if start and end:
            base_filter['created_at__gte'] = start
            base_filter['created_at__lt'] = end

    # ✅ Apply same filter to both Order and ArchivedOrder
    active_orders = Order.objects.filter(**base_filter)
    archived_orders = ArchivedOrder.objects.filter(**base_filter)
    if buffet_date_q is not None:
        active_orders = active_orders.filter(buffet_date_q)
        archived_orders = archived_orders.filter(buffet_date_q)

    # ✅ Combine both lists and sort by created_at descending
    combined_orders = sorted(
        chain(active_orders, archived_orders),
        key=attrgetter('created_at'),
        reverse=True
    )
    # ✅ Serialize the combined queryset
    paginated_data = get_paginated_data(combined_orders, request, OrderSerializer)

    return Response({
        "data": paginated_data["data"],
        "meta": {
            "total": paginated_data["total"],
            "page": paginated_data["page"],
            "page_size": paginated_data["page_size"],
            "has_next": paginated_data["has_next"],
            "has_previous": paginated_data["has_previous"]
        }
    }, status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def order_status_timeline(request, order_id):
    """
    Returns the complete status history (timeline) for a given order.
    - Checks if the order exists in active or archived table.
    - Fetches the timeline from the relevant source.
    - If the order was archived, also includes its active history (if any) before archiving.
    """

    # ✅ Step 1: Try to find order in active table
    active_order = Order.objects.filter(id=order_id).first()
    archived_order = None

    # ✅ Step 2: If not found, try archived table
    if not active_order:
        archived_order = ArchivedOrder.objects.filter(id=order_id).first()
        if not archived_order:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    # ✅ Step 3: Fetch status histories based on type
    active_history = []
    archived_history = []

    if active_order:
        active_history = OrderStatusHistory.objects.filter(order=active_order).order_by('changed_at')

    if archived_order:
        # archived order might have history in both tables
        archived_history = ArchivedOrderStatusHistory.objects.filter(
            archived_order=archived_order
        ).order_by('changed_at')

        # Also pull history from active table before it was archived (optional but useful)
        prev_active_history = OrderStatusHistory.objects.filter(order_id=archived_order.original_order_id)
        active_history = list(prev_active_history)

    # ✅ Step 4: Combine and sort the timeline
    combined_history = sorted(
        chain(active_history, archived_history),
        key=attrgetter('changed_at')
    )

    if not combined_history:
        return Response({"detail": "No status history found."}, status=status.HTTP_404_NOT_FOUND)

    # ✅ Step 5: Serialize combined data
    serializer = OrderStatusHistorySerializer(combined_history, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


def _buffet_item_status_history_from_chat(booking_id, vendor_id):
    """
    Dine Flash Buffet: derive per-line status history from system ChatMessage rows
    (each buffet_item_update is recorded when kitchen/manager changes item status).
    Returns item_id -> {status, changed_at, item_name, customizations, remarks}.
    """
    history = {}
    messages = ChatMessage.objects.filter(
        booking_id=booking_id,
        vendor_id=vendor_id,
        sender='system',
    ).order_by('-created_at')

    for msg in messages:
        if not msg.message_text:
            continue
        try:
            payload = json.loads(msg.message_text)
        except (json.JSONDecodeError, TypeError):
            continue
        if payload.get('type') != 'buffet_item_update':
            continue
        raw_item_id = payload.get('item_id')
        if raw_item_id is None:
            continue
        try:
            item_id = int(raw_item_id)
        except (TypeError, ValueError):
            continue
        if item_id in history:
            continue
        history[item_id] = {
            'status': payload.get('status'),
            'changed_at': msg.created_at,
            'item_name': payload.get('item_name'),
            'customizations': payload.get('customizations') if isinstance(payload.get('customizations'), list) else [],
            'remarks': (payload.get('remarks') or '').strip(),
        }
    return history


def _buffet_latest_status_change_at(item, chat_history):
    """
    Latest status change time for a buffet line.
    - created (no chat transition yet): item.created_at
    - all other statuses: most recent buffet_item_update ChatMessage, with
      updated_at fallback when chat is missing but a status save occurred.
    """
    entry = chat_history.get(item.id)
    if entry and entry.get('changed_at'):
        return entry['changed_at']
    status = (item.status or '').strip().lower()
    if status == 'created':
        return item.created_at
    if item.updated_at and item.created_at and item.updated_at > item.created_at:
        return item.updated_at
    return None


def _resolve_buffet_order_for_company(order_id, vendors_qs):
    """
    Resolve list-row id to the source Order id used by BuffetOrderItem / ChatMessage.
    Active rows use Order.id; archived rows use ArchivedOrder.original_order_id.
    """
    order = (
        Order.objects.filter(id=order_id, vendor__in=vendors_qs)
        .select_related('vendor')
        .first()
    )
    if order:
        return order, order.id, order.token_no, order.table_booking_no, order.vendor

    archived = (
        ArchivedOrder.objects.filter(id=order_id, vendor__in=vendors_qs)
        .select_related('vendor')
        .first()
    )
    if archived:
        return None, archived.original_order_id, archived.token_no, None, archived.vendor
    return None, None, None, None, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def buffet_order_utilities_detail(request, order_id):
    """
    Dine Flash Buffet company Order Details: utilities/services for one order.
    Each BuffetOrderItem is returned separately with current status and latest
    status change time (ChatMessage for transitions; created_at when still created).
    """
    if (getattr(settings, "PROJECT_NAME", "") or "").strip().lower() != "dine_flash_buffet":
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        admin_outlet = request.user.admin_outlet
    except AttributeError:
        return Response({"error": "Admin outlet not linked to this user."}, status=403)

    vendors_qs = admin_outlet.vendors.all()
    order, source_order_id, token_no, table_booking_no, vendor = _resolve_buffet_order_for_company(
        order_id, vendors_qs
    )
    if source_order_id is None or vendor is None:
        return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

    chat_history = _buffet_item_status_history_from_chat(source_order_id, vendor.id)

    if order and table_booking_no is None:
        table_booking_no = order.table_booking_no

    items = list(
        BuffetOrderItem.objects.filter(order_id=source_order_id)
        .select_related('utility')
        .order_by('utility_id', 'id')
    )

    utilities = []
    if items:
        for item in items:
            latest_change = _buffet_latest_status_change_at(item, chat_history)
            customizations = item.customizations if isinstance(item.customizations, list) else []
            utilities.append({
                'id': item.id,
                'utility_name': item.utility.display_name if item.utility else 'Unknown',
                'status': item.status,
                'latest_status_change_at': latest_change.isoformat() if latest_change else None,
                'quantity': item.quantity,
                'customizations': customizations,
                'remarks': (item.remarks or '').strip(),
                'is_grouped': item.is_grouped,
            })
    else:
        for item_id, entry in sorted(chat_history.items()):
            changed_at = entry.get('changed_at')
            utilities.append({
                'id': item_id,
                'utility_name': entry.get('item_name') or 'Unknown',
                'status': entry.get('status') or 'unknown',
                'latest_status_change_at': changed_at.isoformat() if changed_at else None,
                'quantity': 1,
                'customizations': entry.get('customizations') or [],
                'remarks': entry.get('remarks') or '',
                'is_grouped': False,
            })

    if not utilities:
        return Response({"detail": "No utilities found for this order."}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'order_id': order_id,
        'token_no': token_no,
        'table_booking_no': table_booking_no,
        'utilities': utilities,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def license_check(request):
    """
    Returns license status for a given company/customer.
    """
    customer_id = request.query_params.get('customer_id')

    if not customer_id:
        return Response({"detail": "CustomerId is required."}, status=status.HTTP_400_BAD_REQUEST)

    company_data = AdminOutlet.objects.filter(customer_id=customer_id).first()

    if not company_data:
        return Response({"detail": "Company not found."}, status=status.HTTP_404_NOT_FOUND)

    if company_data.authentication_status == "Approve":
        return Response({
            "status": "success",
            "message": "License Approved",
            "data":company_data.product_to_date
        }, status=status.HTTP_200_OK)
    
    return Response({
        "status": "failed",
        "message": "License Expired"
    }, status=status.HTTP_200_OK)

# DINEFLASH SPECIFIC API: Create Utility
@api_view(["POST"])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def create_utility(request):
    """
    Creates a Utility entry for a Vendor.
    """

    logger.info("[UtilityCreate] Incoming request to create utility")

    try:
        vendor_id = request.data.get("vendor_id")
        utility_name = request.data.get("utility_name")
        display_name = request.data.get("display_name")
        display_code = request.data.get("display_code")
        token_mode = request.data.get("token_mode")
        prefix = request.data.get("prefix", "")
        is_active = request.data.get("is_active")
        food_type = request.data.get("food_type")
        description = request.data.get("description")

        logger.debug(
            f"[UtilityCreate] Received data: vendor_id={vendor_id}, "
            f"utility_name={utility_name}, display_name={display_name}, "
            f"display_code={display_code}, token_mode={token_mode}, prefix={prefix}, "
            f"is_active={is_active}, food_type={food_type}, description={description}"
        )

        # ---- Basic Field Validations ----
        if not vendor_id:
            logger.warning("[UtilityCreate] vendor_id missing")
            return Response({"error": "vendor_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not utility_name:
            logger.warning("[UtilityCreate] utility_name missing")
            return Response({"error": "utility_name is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not display_name:
            logger.warning("[UtilityCreate] display_name missing")
            return Response({"error": "display_name is required"}, status=status.HTTP_400_BAD_REQUEST)

        is_buffet = settings.PROJECT_NAME == "dine_flash_buffet"
        is_hospital = settings.PROJECT_NAME == "hospital_flash"

        buffet_pre_announcement_count = None
        buffet_approximate_service_time = None
        if is_buffet:
            food_type_err = validate_buffet_food_type(food_type)
            if food_type_err:
                return Response({"error": food_type_err}, status=status.HTTP_400_BAD_REQUEST)
            description, description_err = normalize_buffet_utility_description(description)
            if description_err:
                return Response({"error": description_err}, status=status.HTTP_400_BAD_REQUEST)
            buffet_pre_announcement_count, pre_announce_err = _parse_positive_int(
                request.data.get("pre_announcement_count", 0),
                "pre_announcement_count",
            )
            if pre_announce_err:
                return Response({"error": pre_announce_err}, status=status.HTTP_400_BAD_REQUEST)
            # Dine Flash Buffet only: reuse Utility.approximate_service_time for ETA.
            buffet_approximate_service_time, service_time_err = _parse_positive_int(
                request.data.get("approximate_service_time", 0),
                "approximate_service_time",
            )
            if service_time_err:
                return Response({"error": service_time_err}, status=status.HTTP_400_BAD_REQUEST)

        # ---- Buffet Flavor Defaults (Before Uniqueness Check) ----
        if is_buffet:
            if not display_code or display_code == "BFFT":
                import re
                base_code = re.sub(r'[^a-zA-Z0-9]', '', utility_name).upper()[:10]
                display_code = base_code if base_code else "BFFT"
            
            if not token_mode:
                token_mode = "continuous"
            
            if not prefix:
                prefix = None # Use None to avoid uniqueness conflicts with ''

        if not display_code and not is_buffet:
            logger.warning("[UtilityCreate] display_code missing")
            return Response({"error": "display_code is required"}, status=status.HTTP_400_BAD_REQUEST)

        hospital_department_type = None
        if is_hospital:
            from vendors.utils import validate_hospital_department_type
            hospital_department_type, _ = validate_hospital_department_type(
                request.data.get("department_type")
            )
        is_hospital_group = is_hospital and hospital_department_type == Utility.DEPARTMENT_TYPE_GROUP

        if not token_mode and not is_buffet and not is_hospital_group:
            logger.warning("[UtilityCreate] token_mode missing")
            return Response({"error": "token_mode is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not prefix and not is_buffet and not is_hospital_group:
            logger.warning("[UtilityCreate] prefix missing")
            return Response({"error": "prefix is required"}, status=status.HTTP_400_BAD_REQUEST)

        if is_hospital_group and not token_mode:
            token_mode = Utility.TOKEN_MODE_CONTINUOUS
        if is_hospital_group and not prefix:
            prefix = None

        if len(utility_name) > 30:
            logger.warning(f"[UtilityCreate] Utility name too long: {utility_name}")
            return Response({"error": "utility_name must be max 50 characters"}, status=status.HTTP_400_BAD_REQUEST)

        if len(display_name) > 20:
            logger.warning(f"[UtilityCreate] Display name too long: {display_name}")
            return Response({"error": "display_name must be max 50 characters"}, status=status.HTTP_400_BAD_REQUEST)

        if display_code and len(display_code) > 10:
            logger.warning(f"[UtilityCreate] Display code too long: {display_code}")
            return Response({"error": "display_code must be max 10 characters"}, status=status.HTTP_400_BAD_REQUEST)

        if prefix and len(prefix) > 4:
            logger.warning(f"[UtilityCreate] Prefix too long: {prefix}")
            return Response({"error": "prefix must be max 4 characters"}, status=status.HTTP_400_BAD_REQUEST)

        if token_mode not in ["continuous", "utility_specific"]:
            logger.warning(f"[UtilityCreate] Invalid token_mode: {token_mode}")
            return Response({"error": "Invalid token_mode"}, status=status.HTTP_400_BAD_REQUEST)

        # ---- Vendor Validation ----
        try:
            vendor = Vendor.objects.get(vendor_id=vendor_id)
            logger.debug(f"[UtilityCreate] Vendor found: {vendor_id}")
        except Vendor.DoesNotExist:
            logger.error(f"[UtilityCreate] Vendor not found: {vendor_id}")
            return Response({"error": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

        hospital_fields = None
        if is_hospital:
            hospital_fields, hospital_err = validate_hospital_utility_fields(
                request.data,
                vendor=vendor,
                prefix=prefix,
            )
            if hospital_err:
                return Response({"error": hospital_err}, status=status.HTTP_400_BAD_REQUEST)

        # ---- Utility Feature Check ----
        config = getattr(vendor, 'config', None)
        if config and config.use_utilities is False and not is_buffet:
            logger.warning(f"[UtilityCreate] Vendor {vendor_id} has utilities disabled")
            return Response(
                {"error": "Utilities feature is disabled for this vendor"},
                status=status.HTTP_400_BAD_REQUEST
            )
        # ---- Utility Name Uniqueness Check ----
        if Utility.objects.filter(vendor=vendor, utility_name__iexact=utility_name).exists():
            logger.warning(f"[UtilityCreate] Duplicate utility_name '{utility_name}' for vendor {vendor_id}")
            return Response(
                {"error": "Utility name already exists for this vendor"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---- Display Name Uniqueness Check ----
        if Utility.objects.filter(vendor=vendor, display_name__iexact=display_name).exists():
            logger.warning(f"[UtilityCreate] Duplicate display_name '{display_name}' for vendor {vendor_id}")
            return Response(
                {"error": "Display name already exists for this vendor"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---- Display Code Uniqueness Check ----
        if Utility.objects.filter(vendor=vendor, display_code__iexact=display_code).exists():
            logger.warning(f"[UtilityCreate] Duplicate display_code '{display_code}' for vendor {vendor_id}")
            return Response(
                {"error": "Display code already exists for this vendor"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---- Prefix Uniqueness Check ----
        if prefix and Utility.objects.filter(vendor=vendor, prefix__iexact=prefix).exists():
            logger.warning(f"[UtilityCreate] Duplicate prefix '{prefix}' for vendor {vendor_id}")
            return Response(
                {"error": "prefix must be unique for each vendor"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---- Active Status Normalization ----
        if isinstance(is_active, str):
            is_active = is_active.lower() in ["true", "1", "yes"]

        is_active = bool(int(is_active)) if isinstance(is_active, (int, str)) else bool(is_active)

        print("is_active:", is_active)

        buffet_uploads = []
        if is_buffet:
            buffet_uploads = _collect_buffet_upload_files(request)
            if len(buffet_uploads) > _BUFFET_UTILITY_IMAGES_MAX_COUNT:
                return Response(
                    {
                        "error": (
                            f"At most {_BUFFET_UTILITY_IMAGES_MAX_COUNT} images "
                            "allowed per utility."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ---- Create Utility ----
        create_kwargs = {
            "vendor": vendor,
            "utility_name": utility_name,
            "display_name": display_name,
            "display_code": display_code,
            "token_mode": token_mode,
            "prefix": prefix,
            "is_active": is_active,
        }
        if is_buffet:
            create_kwargs["food_type"] = food_type
            create_kwargs["description"] = description
            if buffet_pre_announcement_count is not None:
                create_kwargs["pre_announcement_count"] = buffet_pre_announcement_count
            if buffet_approximate_service_time is not None:
                create_kwargs["approximate_service_time"] = buffet_approximate_service_time
        if is_hospital and hospital_fields:
            create_kwargs.update({
                "department_type": hospital_fields["department_type"],
                "display_order": hospital_fields["display_order"],
                "approximate_service_time": hospital_fields["approximate_service_time"],
                "pre_announcement_count": hospital_fields["pre_announcement_count"],
                "priority_prefix": hospital_fields["priority_prefix"],
            })

        utility = Utility.objects.create(**create_kwargs)

        if is_hospital and hospital_fields:
            apply_hospital_group_departments(utility, hospital_fields["group_members"])

        if is_buffet and buffet_uploads:
            upload_err = create_buffet_utility_images(utility, buffet_uploads)
            if upload_err:
                utility.delete()
                return Response(
                    {"error": upload_err},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        logger.info(f"[UtilityCreate] Utility created successfully | ID={utility.id}")

        utility_payload = {
            "id": utility.id,
            "utility_name": utility.utility_name,
            "display_name": utility.display_name,
            "display_code": utility.display_code,
            "token_mode": utility.token_mode,
            "prefix": utility.prefix,
            "is_active": utility.is_active,
        }
        if is_buffet:
            utility = Utility.objects.prefetch_related("buffet_images").get(pk=utility.pk)
            utility_payload["food_type"] = utility.food_type
            utility_payload["description"] = utility.description
            utility_payload["pre_announcement_count"] = utility.pre_announcement_count
            utility_payload["approximate_service_time"] = utility.approximate_service_time
            utility_payload.update(buffet_utility_image_payload(request, utility))
        if is_hospital:
            utility = Utility.objects.prefetch_related("group_departments").get(pk=utility.pk)
            utility_payload.update(hospital_utility_payload(utility))

        return Response(
            {
                "message": "Utility created successfully",
                "utility": utility_payload,
            },
            status=status.HTTP_201_CREATED
        )

    except Exception as e:
        # 🔥 500 ERROR LOGGING
        logger.error(
            f"[UtilityCreate] Internal server error: {str(e)}",
            exc_info=True
        )

        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# # ---- Utility List ----
# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def utility_list(request):
        
# -------------------------
# Create TV Configuration
# -------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tv_config_create(request):
    try:
        admin_outlet = getattr(request.user, "admin_outlet", None)

        if not admin_outlet:
            return Response(
                {"error": "User is not associated with any admin outlet."},
                status=status.HTTP_403_FORBIDDEN
            )

        data = request.data.copy()
        data["admin_outlet"] = admin_outlet.id

        # Extract fields for duplicate check
        show_qr = data.get("show_qr")
        qr_alignment = data.get("qr_alignment")
        qr_placement = data.get("qr_placement")
        booking_display_count = data.get("items_to_show")
        booking_fields = data.get("booking_fields") or []
        utility_name_mode = data.get("utility_name_mode")
        screen_orientation = data.get("screen_orientation")
        utility_ids = data.get("utilities") or []
        enable_ads = data.get("enable_ads")
        ad_position = data.get("ad_position")
        ad_interval = data.get("ad_interval")
        video_ad_mode = data.get("video_ad_mode")
        header_font_size = data.get("header_font_size")
        header_font_style = data.get("header_font_style")
        header_text_color = data.get("header_text_color")
        footer_enabled = data.get("footer_enabled")
        footer_texts = data.get("footer_texts") or []
        advertisement_ids = data.get("advertisement_ids") or []

        def _sorted_int_ids(raw):
            """Avoid TypeError from sorted() on lists with None or mixed types (e.g. JSON null)."""
            if not raw:
                return []
            out = []
            for x in raw:
                if x is None:
                    continue
                try:
                    out.append(int(x))
                except (TypeError, ValueError):
                    continue
            return sorted(out)

        utility_ids = _sorted_int_ids(utility_ids)
        advertisement_ids = _sorted_int_ids(advertisement_ids)
        data["utilities"] = utility_ids
        data["advertisement_ids"] = advertisement_ids

        if isinstance(booking_fields, (list, tuple)):
            booking_fields = list(booking_fields)
        else:
            booking_fields = [booking_fields] if booking_fields not in (None, "") else []
        data["booking_fields"] = booking_fields

        # ------------------------------------------------------
        #                 DUPLICATE CHECK
        # ------------------------------------------------------
        # Dine Flash (table): each physical TV has its own config row; identical
        # settings must be allowed so edits on one TV do not affect another.
        if not dine_flash_exclusive_tv_device_policy_applies(admin_outlet):
            filter_kwargs = {
                "admin_outlet": admin_outlet,
                "show_qr": show_qr,
                "items_to_show": booking_display_count,
                "utility_name_mode": utility_name_mode,
                "screen_orientation": screen_orientation,
                "enable_ads": enable_ads,
                "ad_position": ad_position,
                "ad_interval": ad_interval,
                "video_ad_mode": video_ad_mode,
                "header_font_size": header_font_size,
                "header_font_style": header_font_style,
                "header_text_color": header_text_color,
                "footer_enabled": footer_enabled,
            }
            if qr_alignment is not None:
                filter_kwargs["qr_alignment"] = qr_alignment
            if qr_placement is not None:
                filter_kwargs["qr_placement"] = qr_placement

            existing_configs = TVDeviceConfig.objects.filter(**filter_kwargs)

            for config in existing_configs:
                # Compare booking fields list
                db_booking_fields = config.booking_fields or []
                if sorted(db_booking_fields) != sorted(booking_fields):
                    continue

                # Compare utilities list
                existing_util_ids = list(config.utilities.values_list("id", flat=True))
                if sorted(existing_util_ids) != utility_ids:
                    continue
                existing_ad_ids = list(config.advertisements.values_list("id", flat=True))
                if sorted(existing_ad_ids) != advertisement_ids:
                    continue
                if (config.footer_texts or []) != (footer_texts or []):
                    continue

                # All params matched → duplicate
                return Response(
                    {"message": "A configuration with the same settings already exists."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # ------------------------------------------------------
        #                    CREATE NEW CONFIG
        # ------------------------------------------------------
        serializer = TVDeviceConfigSerializer(data=data)
        if serializer.is_valid():
            config = serializer.save()
            vendor_ids = list(
                config.devices.exclude(vendor_id__isnull=True).values_list("vendor_id", flat=True).distinct()
            )
            schedule_dine_flash_configuration_updated_for_vendors(vendor_ids)
            return Response(
                {
                    "message": "TV configuration created successfully.",
                    "config": TVDeviceConfigSerializer(config).data
                },
                status=status.HTTP_201_CREATED
            )

        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    except Exception:
        logger.exception("tv_config_create: Unexpected server error.")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# -------------------------
# List TV Configurations
# -------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tv_config_list(request):
    admin_outlet = getattr(request.user, "admin_outlet", None)

    if not admin_outlet:
        return Response(
            {"error": "User is not associated with any admin outlet."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        configs = (
            admin_outlet.tv_device_configs
                .select_related("admin_outlet")
                .prefetch_related("utilities", "advertisements", "devices")
                .order_by("-created_at")
        )
        serializer = TVDeviceConfigSerializer(configs, many=True)

        logger.info(
            f"tv_config_list: Returned {len(serializer.data)} configs for admin_outlet {admin_outlet.id}."
        )

        return Response(
            {"configs": serializer.data, "count": len(serializer.data)},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.exception("tv_config_list: Unexpected server error.")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
# -------------------------
# Detail GET
# GET /tv-config/detail/<int:config_id>/
# -------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def tv_config_detail(request, config_id):
    try:
        config = get_object_or_404(TVDeviceConfig, pk=config_id)
        admin_outlet = getattr(request.user, "admin_outlet", None)
        if not admin_outlet or config.admin_outlet_id != admin_outlet.id:
            return Response(
                {"error": "You do not have permission to view this configuration."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TVDeviceConfigSerializer(config)
        payload = {"config": serializer.data}
        if dine_flash_exclusive_tv_device_policy_applies(config.admin_outlet):
            linkable = (
                AndroidDevice.objects.filter(
                    admin_outlet=config.admin_outlet,
                    vendor__isnull=False,
                )
                .filter(Q(tv_config__isnull=True) | Q(tv_config=config))
                .select_related("vendor")
                .order_by("-updated_at")
            )
            payload["linkable_android_devices"] = [
                {
                    "id": d.id,
                    "mac_address": d.mac_address or "",
                    "vendor_name": d.vendor.name if d.vendor else "",
                }
                for d in linkable
            ]
        logger.info(f"tv_config_detail: Returned config id={config_id}.")
        return Response(payload, status=status.HTTP_200_OK)
    except Exception:
        logger.exception("tv_config_detail: Unexpected server error.")
        return Response({"error": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# -------------------------
# Update config
# POST /tv-config/update/<int:config_id>/
# -------------------------
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def tv_config_update(request, config_id):
    try:
        config = get_object_or_404(TVDeviceConfig, pk=config_id)
        admin_outlet = getattr(request.user, "admin_outlet", None)
        if not admin_outlet or config.admin_outlet_id != admin_outlet.id:
            return Response(
                {"error": "You do not have permission to update this configuration."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = TVDeviceConfigSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            config = serializer.save()
            vendor_ids = list(
                config.devices.exclude(vendor_id__isnull=True).values_list("vendor_id", flat=True).distinct()
            )
            schedule_dine_flash_configuration_updated_for_vendors(vendor_ids)
            logger.info(f"tv_config_update: Updated config id={config_id}.")
            return Response({"message": "Configuration updated.", "config": TVDeviceConfigSerializer(config).data}, status=status.HTTP_200_OK)

        logger.warning(f"tv_config_update: Validation failed for config id={config_id}. Errors: {serializer.errors}")
        return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    except Exception:
        logger.exception("tv_config_update: Unexpected server error.")
        return Response({"error": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# -------------------------
# Assign config to device
# POST /tv-config/assign/
# payload: { "device_id": <int>, "config_id": <int> }

# -------------------------
# Delete config
# DELETE /tv-config/delete/<int:config_id>/
# -------------------------
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def tv_config_delete(request, config_id):
    try:
        admin_outlet = getattr(request.user, "admin_outlet", None)
        if not admin_outlet:
            return Response(
                {"error": "User is not associated with any admin outlet."},
                status=status.HTTP_403_FORBIDDEN
            )

        config = get_object_or_404(TVDeviceConfig, pk=config_id)
        
        # Verify ownership
        if config.admin_outlet != admin_outlet:
            return Response(
                {"error": "You do not have permission to delete this configuration."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        config_id_deleted = config.id
        vendor_ids = list(
            config.devices.exclude(vendor_id__isnull=True).values_list("vendor_id", flat=True).distinct()
        )
        config.delete()
        schedule_dine_flash_configuration_updated_for_vendors(vendor_ids)
        logger.info(f"tv_config_delete: Deleted config id={config_id_deleted}.")
        return Response(
            {"message": "Configuration deleted successfully."},
            status=status.HTTP_200_OK
        )

    except Exception:
        logger.exception("tv_config_delete: Unexpected server error.")
        return Response(
            {"error": "Internal server error."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _ensure_tv_ads_admin_outlet(request):
    admin_outlet = getattr(request.user, "admin_outlet", None)
    if not admin_outlet:
        return None, Response(
            {"error": "User is not associated with any admin outlet."},
            status=status.HTTP_403_FORBIDDEN,
        )
    outlet_project = (getattr(admin_outlet, "project_code", "") or "").strip().lower()
    current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    allowed = {"dine_flash", "hospital_flash"}
    if outlet_project in allowed or current_project in allowed:
        return admin_outlet, None
    return None, Response(
        {"error": "This endpoint is available only for Dine Flash and Hospital Flash."},
        status=status.HTTP_403_FORBIDDEN,
    )


MAX_TV_AD_FILE_BYTES = 100 * 1024 * 1024


def _validate_tv_ad_media(media, media_type):
    if media_type not in ("image", "video"):
        return False, "Unsupported media type."
    if media.size > MAX_TV_AD_FILE_BYTES:
        return False, "File exceeds 100MB limit."
    return True, None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def tv_ads_list(request):
    admin_outlet, error_response = _ensure_tv_ads_admin_outlet(request)
    if error_response:
        return error_response
    ads = TVAdvertisement.objects.filter(admin_outlet=admin_outlet).order_by("sequence", "created_at", "id")
    return Response({"ads": TVAdvertisementSerializer(ads, many=True, context={"request": request}).data}, status=200)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def tv_ads_upload(request):
    admin_outlet, error_response = _ensure_tv_ads_admin_outlet(request)
    if error_response:
        return error_response

    files = request.FILES.getlist("ads")
    if not files:
        return Response({"error": "No files uploaded."}, status=400)

    validated = []
    errors = []
    for media in files:
        content_type = (getattr(media, "content_type", "") or "").lower()
        media_type = (
            "image" if content_type.startswith("image/") else "video" if content_type.startswith("video/") else None
        )
        if not media_type:
            errors.append(f"{getattr(media, 'name', 'file')}: only image and video files are allowed.")
            continue
        is_valid, reason = _validate_tv_ad_media(media, media_type)
        if not is_valid:
            errors.append(f"{getattr(media, 'name', 'file')}: {reason}")
            continue
        validated.append((media, media_type))

    if errors:
        return Response({"error": " ".join(errors)}, status=400)
    if not validated:
        return Response({"error": "No valid image/video files uploaded."}, status=400)

    created_ads = []
    next_sequence = (TVAdvertisement.objects.filter(admin_outlet=admin_outlet).aggregate(max_seq=Max("sequence"))["max_seq"] or 0) + 1
    for media, media_type in validated:
        created_ads.append(
            TVAdvertisement.objects.create(
                admin_outlet=admin_outlet,
                title=request.data.get("title") or media.name,
                media_file=media,
                media_type=media_type,
                sequence=next_sequence,
            )
        )
        next_sequence += 1

    payload = TVAdvertisementSerializer(created_ads, many=True, context={"request": request}).data
    return Response({"message": "Advertisements uploaded.", "ads": payload}, status=201)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def tv_ads_update(request, ad_id):
    admin_outlet, error_response = _ensure_tv_ads_admin_outlet(request)
    if error_response:
        return error_response

    ad = get_object_or_404(TVAdvertisement, id=ad_id, admin_outlet=admin_outlet)
    title = request.data.get("title")
    is_active = request.data.get("is_active")
    sequence = request.data.get("sequence")
    update_fields = []

    if title is not None:
        ad.title = title
        update_fields.append("title")
    if is_active is not None:
        ad.is_active = str(is_active).lower() in ("true", "1", "yes")
        update_fields.append("is_active")
    if sequence is not None:
        try:
            seq = int(sequence)
            if seq < 1:
                return Response({"error": "sequence must be >= 1."}, status=400)
            ad.sequence = seq
            update_fields.append("sequence")
        except (TypeError, ValueError):
            return Response({"error": "sequence must be an integer."}, status=400)
    if update_fields:
        ad.save(update_fields=update_fields + ["updated_at"])

    return Response(
        {"message": "Advertisement updated.", "ad": TVAdvertisementSerializer(ad, context={"request": request}).data},
        status=200,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def tv_ads_delete(request, ad_id):
    admin_outlet, error_response = _ensure_tv_ads_admin_outlet(request)
    if error_response:
        return error_response

    ad = get_object_or_404(TVAdvertisement, id=ad_id, admin_outlet=admin_outlet)
    ad.delete()
    return Response({"message": "Advertisement deleted."}, status=200)


# -------------------------
# Assign config to device
# POST /tv-config/assign/
# payload: { "device_id": <int>, "config_id": <int> }
# -------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tv_config_assign(request):
    try:
        admin_outlet = getattr(request.user, "admin_outlet", None)
        if not admin_outlet:
            return Response({"error": "Admin outlet not found."}, status=status.HTTP_400_BAD_REQUEST)

        device_id = request.data.get("device_id")
        config_id = request.data.get("config_id")

        if not device_id or not config_id:
            logger.warning("tv_config_assign: device_id or config_id missing in request.")
            return Response({"error": "device_id and config_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        device = AndroidDevice.objects.filter(id=device_id).first()
        if not device:
            logger.warning(f"tv_config_assign: Invalid device_id '{device_id}'.")
            return Response({"error": "Invalid device_id."}, status=status.HTTP_404_NOT_FOUND)
        if device.admin_outlet_id != admin_outlet.id:
            logger.warning("tv_config_assign: User tried assigning config to unauthorized device.")
            return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

        config = TVDeviceConfig.objects.filter(id=config_id).first()
        if not config:
            logger.warning(f"tv_config_assign: Invalid config_id '{config_id}'.")
            return Response({"error": "Invalid config_id."}, status=status.HTTP_404_NOT_FOUND)

        # Ensure config belongs to the same admin_outlet as device (optional safeguard)
        if device.admin_outlet_id != config.admin_outlet_id:
            logger.warning(f"tv_config_assign: Mismatched admin_outlet for device {device_id} and config {config_id}.")
            return Response({"error": "Config does not belong to the same admin outlet as device."}, status=status.HTTP_400_BAD_REQUEST)

        if dine_flash_exclusive_tv_device_policy_applies(config.admin_outlet):
            with transaction.atomic():
                TVDeviceConfig.objects.select_for_update().get(pk=config.id)
                if AndroidDevice.objects.filter(tv_config=config).exclude(id=device.id).exists():
                    return Response(
                        {
                            "error": (
                                "This configuration is already linked to another TV. "
                                "In Dine Flash each TV must use its own configuration."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                device.tv_config = config
                device.save(update_fields=["tv_config", "updated_at"])
        else:
            device.tv_config = config
            device.save(update_fields=["tv_config", "updated_at"])
        schedule_dine_flash_configuration_updated_for_vendors([device.vendor_id])
        logger.info(f"tv_config_assign: Assigned config id={config_id} to device id={device_id}.")
        return Response({"message": "Configuration assigned to device.", "device_id": device_id, "config_id": config_id}, status=status.HTTP_200_OK)

    except Exception:
        logger.exception("tv_config_assign: Unexpected server error.")
        return Response({"error": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# -------------------------
# Clear config from device
# POST /tv-config/clear/
# payload: { "device_id": <int> }
# -------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tv_config_clear(request):
    try:
        admin_outlet = getattr(request.user, "admin_outlet", None)
        if not admin_outlet:
            return Response({"error": "Admin outlet not found."}, status=status.HTTP_400_BAD_REQUEST)

        device_id = request.data.get("device_id")
        if not device_id:
            logger.warning("tv_config_clear: device_id missing in request.")
            return Response({"error": "device_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        device = AndroidDevice.objects.filter(id=device_id).first()
        if not device:
            logger.warning(f"tv_config_clear: Invalid device_id '{device_id}'.")
            return Response({"error": "Invalid device_id."}, status=status.HTTP_404_NOT_FOUND)
        if device.admin_outlet_id != admin_outlet.id:
            logger.warning("tv_config_clear: User tried clearing config from unauthorized device.")
            return Response({"error": "You do not have permission to modify this device."}, status=status.HTTP_403_FORBIDDEN)

        vendor_id = device.vendor_id
        device.tv_config = None
        device.save(update_fields=["tv_config", "updated_at"])
        schedule_dine_flash_configuration_updated_for_vendors([vendor_id])
        logger.info(f"tv_config_clear: Cleared config for device id={device_id}.")
        return Response({"message": "Configuration cleared from device.", "device_id": device_id}, status=status.HTTP_200_OK)

    except Exception:
        logger.exception("tv_config_clear: Unexpected server error.")
        return Response({"error": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_outlet_settings(request):
    data = request.data

    vendor_id = data.get("vendor_id")
    logger.info(f"[OutletSettings] Update received | vendor_id={vendor_id} | user={request.user}")

    # -----------------------------------
    # Check only missing vendor_id
    # -----------------------------------
    if not vendor_id:
        return Response({
            "status": False,
            "message": "vendor_id is required"
        }, status=400)

    try:
        vendor = Vendor.objects.filter(id=vendor_id).first()

        if not vendor:
            logger.warning(f"[OutletSettings] Vendor not found | vendor_id={vendor_id}")
            return Response({
                "status": False,
                "message": "Vendor not found"
            }, status=404)

        config = vendor.config

        serializer = VendorVibrationConfigSerializer(
            config,
            data=data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            logger.info(f"[OutletSettings] Settings updated | vendor_id={vendor_id}")

            return Response({
                "status": True,
                "message": "Outlet settings updated successfully",
                "data": serializer.data
            }, status=200)

        # Serializer handles all other validation errors
        logger.error(
            f"[OutletSettings] Validation failed | vendor_id={vendor_id} | errors={serializer.errors}"
        )

        return Response({
            "status": False,
            "message": "Invalid outlet configuration data",
            "errors": serializer.errors
        }, status=400)

    except Exception as e:
        logger.exception(f"[OutletSettings] Unexpected error | vendor_id={vendor_id}")

        return Response({
            "status": False,
            "message": "Unexpected error while updating outlet settings",
            "error": str(e)
        }, status=500)

# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def vendor_configurations(request):
#     serializer = VendorConfigUpdateSerializer(data=request.data)
#     serializer.is_valid(raise_exception=True)

#     vendor_ids = serializer.validated_data.pop("vendor_ids")
#     update_fields = serializer.validated_data

#     if not update_fields:
#         return Response(
#             {"message": "No configuration values provided"},
#             status=status.HTTP_400_BAD_REQUEST
#         )

#     updated_vendors = []

#     with transaction.atomic():
#         for vendor_id in vendor_ids:
#             config, _ = VendorConfig.objects.get_or_create(
#                 vendor_id=vendor_id
#             )

#             for field, value in update_fields.items():
#                 setattr(config, field, value)

#             config.save(update_fields=list(update_fields.keys()))
#             updated_vendors.append(vendor_id)

#     return Response(
#         {
#             "message": "Vendor configurations updated successfully",
#             "updated_vendors": updated_vendors
#         },
#         status=status.HTTP_200_OK
#     )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def vendor_configurations(request):
    serializer = VendorConfigUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    vendor_id = serializer.validated_data.pop("vendor_id")
    update_fields = serializer.validated_data

    # Never persist hospital-only announcement templates or chat copy on other flavours.
    current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    if current_project != "hospital_flash":
        update_fields.pop("announcement_templates", None)
        update_fields.pop("called_chat_template", None)
        update_fields.pop("pre_announcement_chat_template", None)
        update_fields.pop("completed_chat_template", None)

    if not update_fields:
        return Response(
            {"message": "No configuration values provided"},
            status=status.HTTP_400_BAD_REQUEST
        )

    with transaction.atomic():
        config, _ = VendorConfig.objects.get_or_create(
            vendor_id=vendor_id
        )

        for field, value in update_fields.items():
            setattr(config, field, value)

        config.save(update_fields=list(update_fields.keys()))

    return Response(
        {
            "message": "Vendor configurations updated successfully",
            "updated_vendor": vendor_id
        },
        status=status.HTTP_200_OK
    )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_utilities(request):
    """
    API endpoint to fetch utilities for a specific vendor.
    Query parameter: vendor_id (optional) - if provided, returns utilities for that vendor only
    """
    try:
        # Get admin outlet from user
        admin_outlet = request.user.admin_outlet
        if not admin_outlet:
            return Response(
                {"error": "Admin outlet not found for this user"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get vendor_id from query parameter
        vendor_id = request.query_params.get('vendor_id')
        is_buffet = settings.PROJECT_NAME == "dine_flash_buffet"
        is_hospital = settings.PROJECT_NAME == "hospital_flash"

        def _utilities_queryset():
            qs = Utility.objects.filter(
                vendor__admin_outlet=admin_outlet
            ).select_related("vendor")
            if is_buffet:
                qs = qs.prefetch_related("buffet_images")
            if is_hospital:
                qs = qs.prefetch_related("group_departments")
            if is_hospital:
                qs = qs.order_by("display_order", "id")
            return qs

        def _utility_row(utility):
            row = {
                "id": utility.id,
                "utility_name": utility.utility_name,
                "display_name": utility.display_name,
                "display_code": utility.display_code,
                "prefix": utility.prefix,
                "token_mode": utility.token_mode,
                "is_active": utility.is_active,
                "vendor": utility.vendor_id,
                "vendor_id": utility.vendor.vendor_id,
                "vendor_name": utility.vendor.name,
                "vendor_location": utility.vendor.location,
            }
            if is_buffet:
                row["food_type"] = utility.food_type
                row["description"] = utility.description
                row["pre_announcement_count"] = utility.pre_announcement_count
                row["approximate_service_time"] = utility.approximate_service_time
                row.update(buffet_utility_image_payload(request, utility))
            if is_hospital:
                row.update(hospital_utility_payload(utility))
            return row

        if vendor_id:
            try:
                vendor_id = int(vendor_id)
                utilities = _utilities_queryset().filter(vendor__vendor_id=vendor_id)

                utilities_list = [_utility_row(util) for util in utilities]

                # Attach options
                utility_ids = [u['id'] for u in utilities_list]
                options = UtilityOption.objects.filter(utility_id__in=utility_ids).values('id', 'utility_id', 'name', 'is_active')
                options_by_utility = defaultdict(list)
                for opt in options:
                    options_by_utility[opt['utility_id']].append({
                        'id': opt['id'],
                        'name': opt['name'],
                        'is_active': opt['is_active']
                    })
                
                for util in utilities_list:
                    util['options'] = options_by_utility.get(util['id'], [])

                return Response(
                    {
                        "success": True,
                        "utilities": utilities_list,
                        "count": len(utilities_list)
                    },
                    status=status.HTTP_200_OK
                )

            except ValueError:
                return Response(
                    {"error": "Invalid vendor_id format"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            utilities = _utilities_queryset()
            utilities_list = [_utility_row(util) for util in utilities]

            # Attach options
            utility_ids = [u['id'] for u in utilities_list]
            options = UtilityOption.objects.filter(utility_id__in=utility_ids).values('id', 'utility_id', 'name', 'is_active')
            options_by_utility = defaultdict(list)
            for opt in options:
                options_by_utility[opt['utility_id']].append({
                    'id': opt['id'],
                    'name': opt['name'],
                    'is_active': opt['is_active']
                })
            
            for util in utilities_list:
                util['options'] = options_by_utility.get(util['id'], [])

            return Response(
                {
                    "success": True,
                    "utilities": utilities_list,
                    "count": len(utilities_list)
                },
                status=status.HTTP_200_OK
            )

    except Exception as e:
        logger.error(f"[GetUtilities] Error: {str(e)}")
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_utility_status(request):
    """
    Update utility status (activate/deactivate)
    Accepts PATCH requests with utility_id and is_active in request body
    """
    try:
        utility_id = request.data.get('utility_id')
        is_active = request.data.get('is_active')

        if not utility_id:
            return Response(
                {"error": "Utility ID is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if is_active is None:
            return Response(
                {"error": "Status value is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get admin outlet for security
        try:
            admin_outlet = AdminOutlet.objects.get(user=request.user)
        except AdminOutlet.DoesNotExist:
            return Response(
                {"error": "Admin outlet not found"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get the utility and verify it belongs to the admin outlet
        try:
            utility = Utility.objects.get(id=utility_id)
        except Utility.DoesNotExist:
            return Response(
                {"error": "Utility not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify the utility's vendor belongs to the admin_outlet for this user
        try:
            vendor_admin_outlet = utility.vendor.admin_outlet
        except Exception:
            return Response(
                {"error": "Unable to determine utility owner"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if vendor_admin_outlet != admin_outlet:
            return Response(
                {"error": "You don't have permission to modify this utility"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Update status
        utility.is_active = is_active
        utility.save()

        logger.info(f"[UpdateUtilityStatus] Utility {utility_id} status updated to {is_active}")

        return Response(
            {
                "success": True,
                "message": f"Utility {'activated' if is_active else 'deactivated'} successfully",
                "utility": {
                    'id': utility.id,
                    'utility_name': utility.utility_name,
                    'is_active': utility.is_active
                }
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"[UpdateUtilityStatus] Error: {str(e)}")
        return Response(
            {"error": f"An error occurred: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PATCH'])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def update_utility(request):
    """
    Update utility fields: utility_name, display_name, display_code, token_mode, prefix
    Validations mirror create_utility but uniqueness checks exclude the current utility.
    """
    try:
        utility_id = request.data.get('utility_id')
        utility_name = request.data.get('utility_name')
        display_name = request.data.get('display_name')
        display_code = request.data.get('display_code')
        token_mode = request.data.get('token_mode')
        prefix = request.data.get('prefix', '')
        food_type = request.data.get('food_type')
        description = request.data.get('description')

        if not utility_id:
            return Response({"error": "utility_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            utility = Utility.objects.get(id=utility_id)
        except Utility.DoesNotExist:
            return Response({"error": "Utility not found"}, status=status.HTTP_404_NOT_FOUND)

        # Permission: ensure this utility belongs to user's admin_outlet
        admin_outlet = getattr(request.user, 'admin_outlet', None)
        if not admin_outlet:
            return Response({"error": "Admin outlet not found for this user"}, status=status.HTTP_403_FORBIDDEN)

        if utility.vendor.admin_outlet != admin_outlet:
            return Response({"error": "You don't have permission to modify this utility"}, status=status.HTTP_403_FORBIDDEN)

        is_buffet = settings.PROJECT_NAME == "dine_flash_buffet"
        is_hospital = settings.PROJECT_NAME == "hospital_flash"

        buffet_pre_announcement_count = None
        buffet_approximate_service_time = None
        if is_buffet:
            # Keep existing food type when the client omits it (e.g. description-only edit).
            if not food_type or not str(food_type).strip():
                food_type = utility.food_type
            food_type_err = validate_buffet_food_type(food_type)
            if food_type_err:
                return Response({"error": food_type_err}, status=status.HTTP_400_BAD_REQUEST)
            description, description_err = normalize_buffet_utility_description(description)
            if description_err:
                return Response({"error": description_err}, status=status.HTTP_400_BAD_REQUEST)
            if "pre_announcement_count" in request.data:
                buffet_pre_announcement_count, pre_announce_err = _parse_positive_int(
                    request.data.get("pre_announcement_count"),
                    "pre_announcement_count",
                )
                if pre_announce_err:
                    return Response({"error": pre_announce_err}, status=status.HTTP_400_BAD_REQUEST)
            # Dine Flash Buffet only: reuse Utility.approximate_service_time for ETA.
            if "approximate_service_time" in request.data:
                buffet_approximate_service_time, service_time_err = _parse_positive_int(
                    request.data.get("approximate_service_time"),
                    "approximate_service_time",
                )
                if service_time_err:
                    return Response({"error": service_time_err}, status=status.HTTP_400_BAD_REQUEST)

        # ---- Buffet Flavor Defaults (Before Uniqueness Check) ----
        if is_buffet:
            if not display_code or display_code == "BFFT":
                import re
                base_code = re.sub(r'[^a-zA-Z0-9]', '', utility_name).upper()[:10]
                display_code = base_code if base_code else "BFFT"
            
            if not token_mode:
                token_mode = "continuous"
            
            if not prefix:
                prefix = None

        # Basic validations (presence)
        if not utility_name:
            return Response({"error": "utility_name is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not display_name:
            return Response({"error": "display_name is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not display_code and not is_buffet:
            return Response({"error": "display_code is required"}, status=status.HTTP_400_BAD_REQUEST)

        hospital_department_type = None
        if is_hospital:
            from vendors.utils import validate_hospital_department_type
            hospital_department_type, _ = validate_hospital_department_type(
                request.data.get("department_type", utility.department_type)
            )
        is_hospital_group = is_hospital and hospital_department_type == Utility.DEPARTMENT_TYPE_GROUP

        if not token_mode and not is_buffet and not is_hospital_group:
            return Response({"error": "token_mode is required"}, status=status.HTTP_400_BAD_REQUEST)
        if prefix is None and not is_buffet and not is_hospital_group:
            return Response({"error": "prefix is required"}, status=status.HTTP_400_BAD_REQUEST)

        if is_hospital_group and not token_mode:
            token_mode = Utility.TOKEN_MODE_CONTINUOUS
        if is_hospital_group and prefix is None:
            prefix = utility.prefix

        # Length validations (match create_utility checks)
        if len(utility_name) > 30:
            return Response({"error": "utility_name must be max 50 characters"}, status=status.HTTP_400_BAD_REQUEST)
        if len(display_name) > 20:
            return Response({"error": "display_name must be max 50 characters"}, status=status.HTTP_400_BAD_REQUEST)
        if len(display_code) > 10:
            return Response({"error": "display_code must be max 50 characters"}, status=status.HTTP_400_BAD_REQUEST)
        if prefix is not None and len(prefix) > 4:
            return Response({"error": "prefix must be max 4 characters"}, status=status.HTTP_400_BAD_REQUEST)

        if token_mode not in [Utility.TOKEN_MODE_CONTINUOUS, Utility.TOKEN_MODE_UTILITY_SPECIFIC]:
            return Response({"error": "Invalid token_mode"}, status=status.HTTP_400_BAD_REQUEST)

        vendor = utility.vendor

        hospital_fields = None
        if is_hospital:
            hospital_fields, hospital_err = validate_hospital_utility_fields(
                request.data,
                vendor=vendor,
                utility=utility,
                prefix=prefix,
            )
            if hospital_err:
                return Response({"error": hospital_err}, status=status.HTTP_400_BAD_REQUEST)

        # Check vendor config allows utilities
        config = getattr(vendor, 'config', None)
        if config and config.use_utilities is False:
            return Response({"error": "Utilities feature is disabled for this vendor"}, status=status.HTTP_400_BAD_REQUEST)

        # Uniqueness checks excluding current utility
        if Utility.objects.filter(vendor=vendor, utility_name__iexact=utility_name).exclude(id=utility.id).exists():
            return Response({"error": "Utility name already exists for this vendor"}, status=status.HTTP_400_BAD_REQUEST)

        if Utility.objects.filter(vendor=vendor, display_name__iexact=display_name).exclude(id=utility.id).exists():
            return Response({"error": "Display name already exists for this vendor"}, status=status.HTTP_400_BAD_REQUEST)

        if Utility.objects.filter(vendor=vendor, display_code__iexact=display_code).exclude(id=utility.id).exists():
            return Response({"error": "Display code already exists for this vendor"}, status=status.HTTP_400_BAD_REQUEST)

        if not is_buffet and prefix and Utility.objects.filter(vendor=vendor, prefix__iexact=prefix).exclude(id=utility.id).exists():
            return Response({"error": "prefix must be unique for each vendor"}, status=status.HTTP_400_BAD_REQUEST)

        # All validations passed; update utility
        utility.utility_name = utility_name
        utility.display_name = display_name
        utility.display_code = display_code
        utility.token_mode = token_mode
        utility.prefix = prefix
        if is_buffet:
            utility.food_type = food_type
            utility.description = description
            if buffet_pre_announcement_count is not None:
                utility.pre_announcement_count = buffet_pre_announcement_count
            if buffet_approximate_service_time is not None:
                utility.approximate_service_time = buffet_approximate_service_time
        if is_hospital and hospital_fields:
            utility.department_type = hospital_fields["department_type"]
            utility.display_order = hospital_fields["display_order"]
            utility.approximate_service_time = hospital_fields["approximate_service_time"]
            utility.pre_announcement_count = hospital_fields["pre_announcement_count"]
            utility.priority_prefix = hospital_fields["priority_prefix"]

        if is_buffet:
            image_err = apply_buffet_utility_image_changes(utility, request)
            if image_err:
                return Response(
                    {"error": image_err},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        utility.save()

        if is_hospital and hospital_fields:
            apply_hospital_group_departments(utility, hospital_fields["group_members"])

        utility_response = {
            "id": utility.id,
            "utility_name": utility.utility_name,
            "display_name": utility.display_name,
            "display_code": utility.display_code,
            "token_mode": utility.token_mode,
            "prefix": utility.prefix,
            "is_active": utility.is_active,
        }
        if is_buffet:
            utility = Utility.objects.prefetch_related("buffet_images").get(pk=utility.pk)
            utility_response["food_type"] = utility.food_type
            utility_response["description"] = utility.description
            utility_response["pre_announcement_count"] = utility.pre_announcement_count
            utility_response["approximate_service_time"] = utility.approximate_service_time
            utility_response.update(buffet_utility_image_payload(request, utility))
        if is_hospital:
            utility = Utility.objects.prefetch_related("group_departments").get(pk=utility.pk)
            utility_response.update(hospital_utility_payload(utility))

        return Response({
            "success": True,
            "message": "Utility updated successfully",
            "utility": utility_response,
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"[UpdateUtility] Error: {str(e)}", exc_info=True)
        return Response({"error": "An error occurred while updating utility"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_utility_option(request, utility_id):
    if settings.PROJECT_NAME != 'dine_flash_buffet':
        return Response({"error": "Not supported"}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        utility = Utility.objects.get(id=utility_id)
    except Utility.DoesNotExist:
        return Response({"error": "Utility not found"}, status=status.HTTP_404_NOT_FOUND)
        
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet or utility.vendor.admin_outlet != admin_outlet:
        return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
    name = request.data.get("name")
    if not name:
        return Response({"error": "Option name is required"}, status=status.HTTP_400_BAD_REQUEST)
        
    if UtilityOption.objects.filter(utility=utility, name__iexact=name).exists():
        return Response({"error": "Option with this name already exists for this utility"}, status=status.HTTP_400_BAD_REQUEST)
        
    option = UtilityOption.objects.create(utility=utility, name=name)
    return Response({"message": "Option created", "option": {"id": option.id, "name": option.name, "is_active": option.is_active}}, status=status.HTTP_201_CREATED)

@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_utility_option(request, option_id):
    if settings.PROJECT_NAME != 'dine_flash_buffet':
        return Response({"error": "Not supported"}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        option = UtilityOption.objects.get(id=option_id)
    except UtilityOption.DoesNotExist:
        return Response({"error": "Option not found"}, status=status.HTTP_404_NOT_FOUND)
        
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet or option.utility.vendor.admin_outlet != admin_outlet:
        return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
    name = request.data.get("name")
    is_active = request.data.get("is_active")
    
    if name:
        if UtilityOption.objects.filter(utility=option.utility, name__iexact=name).exclude(id=option_id).exists():
            return Response({"error": "Option with this name already exists"}, status=status.HTTP_400_BAD_REQUEST)
        option.name = name
    
    if is_active is not None:
        if isinstance(is_active, str):
            is_active = is_active.lower() == 'true'
        option.is_active = is_active
        
    option.save()
    return Response({"message": "Option updated", "option": {"id": option.id, "name": option.name, "is_active": option.is_active}}, status=status.HTTP_200_OK)

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_utility_option(request, option_id):
    if settings.PROJECT_NAME != 'dine_flash_buffet':
        return Response({"error": "Not supported"}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        option = UtilityOption.objects.get(id=option_id)
    except UtilityOption.DoesNotExist:
        return Response({"error": "Option not found"}, status=status.HTTP_404_NOT_FOUND)
        
    admin_outlet = getattr(request.user, 'admin_outlet', None)
    if not admin_outlet or option.utility.vendor.admin_outlet != admin_outlet:
        return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
    option.delete()
    return Response({"message": "Option deleted"}, status=status.HTTP_200_OK)