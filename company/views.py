import json
import logging
import random

from django.db import transaction
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from itertools import chain
from operator import attrgetter
from collections import defaultdict

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from vendors.models import (Vendor, Device, AdminOutlet,
                            AndroidDevice,AdvertisementImage,
                            AdvertisementProfileAssignment,
                            AdvertisementProfile,Order,
                            ArchivedOrder,UserProfile,
                            AndroidAPK,VendorConfig,
                            OrderStatusHistory,ArchivedOrderStatusHistory,
                            Utility,TVDeviceConfig,UtilityOption)

from static.utils.functions.validation import validate_fields
from static.utils.functions.utils import get_time_ranges,get_filtered_date_range
from static.utils.functions.pagination import get_paginated_data
from .serializer.vendor_config import (VendorVibrationConfigSerializer,
                                       VendorConfigUpdateSerializer)
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
                          OrderStatusHistorySerializer,TVDeviceConfigSerializer
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
    return render(request, "company/configurations.html")

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
        is_buffet = settings.PROJECT_NAME == "dine_flash_buffet"
        vendor_config = VendorConfig.objects.create(
            vendor=vendor,
            tv_communication_mode=tv_communication_mode,
            business_day_start_hour=business_day_start_hour,
            timezone=timezone,
            mqtt_mode=mqtt_mode,
            use_utilities=is_buffet
        )
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
    serializer = UserProfileCreateSerializer(data=request.data)
    
    if serializer.is_valid():
        result = serializer.save()

        # If multiple profiles (i.e., role == 'both')
        if isinstance(result, list):
            return Response({
                "detail": "User created with both roles successfully.",
                "username": result[0].user.username,
                "roles": [profile.role for profile in result],
                "vendor": result[0].vendor.name if result[0].vendor else None,
                "admin_outlet": result[0].admin_outlet.customer_name if result[0].admin_outlet else None,
            }, status=status.HTTP_201_CREATED)

        # If single profile
        user_profile = result
        return Response({
            "detail": "User created successfully.",
            "username": user_profile.user.username,
            "role": user_profile.role,
            "vendor": user_profile.vendor.name if user_profile.vendor else None,
            "admin_outlet": user_profile.admin_outlet.customer_name if user_profile.admin_outlet else None,
        }, status=status.HTTP_201_CREATED)

    # If validation fails
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

    if filter_type == 'mapped':
        android_tvs = AndroidDevice.objects.filter(admin_outlet=admin_outlet,vendor__isnull=False)
    elif filter_type == 'unmapped':
        android_tvs = AndroidDevice.objects.filter(admin_outlet=admin_outlet, vendor__isnull=True)
    else:  # 'all' or invalid filter
        # Return both mapped (only for this admin_outlet) and unmapped devices
        android_tvs = AndroidDevice.objects.filter(admin_outlet=admin_outlet)

    serializer = AndroidDeviceSerializer(android_tvs, many=True)
    return Response({
        "message": "Android TV's fetched successfully.",
        "android_tvs": serializer.data,
        "count": android_tvs.count(),
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
    if status in ['preparing', 'ready']:
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
    
    start, end = get_filtered_date_range(date_range, from_date, to_date)
    if start and end:
        base_filter['created_at__gte'] = start
        base_filter['created_at__lt'] = end

    # ✅ Apply same filter to both Order and ArchivedOrder
    active_orders = Order.objects.filter(**base_filter)
    archived_orders = ArchivedOrder.objects.filter(**base_filter)

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

        logger.debug(
            f"[UtilityCreate] Received data: vendor_id={vendor_id}, "
            f"utility_name={utility_name}, display_name={display_name}, "
            f"display_code={display_code}, token_mode={token_mode}, prefix={prefix}, is_active={is_active}"
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

        if not token_mode and not is_buffet:
            logger.warning("[UtilityCreate] token_mode missing")
            return Response({"error": "token_mode is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not prefix and not is_buffet:
            logger.warning("[UtilityCreate] prefix missing")
            return Response({"error": "prefix is required"}, status=status.HTTP_400_BAD_REQUEST)

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

        # ---- Utility Feature Check ----
        config = getattr(vendor, 'config', None)
        if config.use_utilities is False and not is_buffet:
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
        # ---- Create Utility ----
        utility = Utility.objects.create(
            vendor=vendor,
            utility_name=utility_name,
            display_name=display_name,
            display_code=display_code,
            token_mode=token_mode,
            prefix=prefix,
            is_active=is_active
        )

        logger.info(f"[UtilityCreate] Utility created successfully | ID={utility.id}")

        return Response(
            {
                "message": "Utility created successfully",
                "utility": {
                    "id": utility.id,
                    "utility_name": utility.utility_name,
                    "display_name": utility.display_name,
                    "display_code": utility.display_code,
                    "token_mode": utility.token_mode,
                    "prefix": utility.prefix,
                    "is_active": utility.is_active
                },
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
        booking_display_count = data.get("items_to_show")
        booking_fields = data.get("booking_fields") or []
        utility_name_mode = data.get("utility_name_mode")
        screen_orientation = data.get("screen_orientation")
        utility_ids = data.get("utilities") or []
        # ------------------------------------------------------
        #                 DUPLICATE CHECK
        # ------------------------------------------------------
        existing_configs = TVDeviceConfig.objects.filter(
            admin_outlet=admin_outlet,
            show_qr=show_qr,
            qr_alignment=qr_alignment,
            items_to_show=booking_display_count,
            utility_name_mode=utility_name_mode,
            screen_orientation=screen_orientation,
        )

        for config in existing_configs:
            # Compare booking fields list
            if sorted(config.booking_fields) != sorted(booking_fields):
                continue

            # Compare utilities list
            existing_util_ids = list(config.utilities.values_list("id", flat=True))
            if sorted(existing_util_ids) != sorted(utility_ids):
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
                .prefetch_related("utilities")
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
        serializer = TVDeviceConfigSerializer(config)
        logger.info(f"tv_config_detail: Returned config id={config_id}.")
        return Response({"config": serializer.data}, status=status.HTTP_200_OK)
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
        serializer = TVDeviceConfigSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            config = serializer.save()
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
        config.delete()
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

# -------------------------
# Assign config to device
# POST /tv-config/assign/
# payload: { "device_id": <int>, "config_id": <int> }
# -------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def tv_config_assign(request):
    try:
        device_id = request.data.get("device_id")
        config_id = request.data.get("config_id")

        if not device_id or not config_id:
            logger.warning("tv_config_assign: device_id or config_id missing in request.")
            return Response({"error": "device_id and config_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        device = AndroidDevice.objects.filter(id=device_id).first()
        if not device:
            logger.warning(f"tv_config_assign: Invalid device_id '{device_id}'.")
            return Response({"error": "Invalid device_id."}, status=status.HTTP_404_NOT_FOUND)

        config = TVDeviceConfig.objects.filter(id=config_id).first()
        if not config:
            logger.warning(f"tv_config_assign: Invalid config_id '{config_id}'.")
            return Response({"error": "Invalid config_id."}, status=status.HTTP_404_NOT_FOUND)

        # Ensure config belongs to the same admin_outlet as device (optional safeguard)
        if device.admin_outlet_id != config.admin_outlet_id:
            logger.warning(f"tv_config_assign: Mismatched admin_outlet for device {device_id} and config {config_id}.")
            return Response({"error": "Config does not belong to the same admin outlet as device."}, status=status.HTTP_400_BAD_REQUEST)

        device.tv_config = config
        device.save(update_fields=["tv_config", "updated_at"])
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
        device_id = request.data.get("device_id")
        if not device_id:
            logger.warning("tv_config_clear: device_id missing in request.")
            return Response({"error": "device_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        device = AndroidDevice.objects.filter(id=device_id).first()
        if not device:
            logger.warning(f"tv_config_clear: Invalid device_id '{device_id}'.")
            return Response({"error": "Invalid device_id."}, status=status.HTTP_404_NOT_FOUND)

        device.tv_config = None
        device.save(update_fields=["tv_config", "updated_at"])
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

        if vendor_id:
            try:
                vendor_id = int(vendor_id)
                # Fetch utilities for specific vendor
                utilities = Utility.objects.filter(
                    vendor__vendor_id=vendor_id,
                    vendor__admin_outlet=admin_outlet
                ).values(
                    'id',
                    'utility_name',
                    'display_name',
                    'display_code',
                    'prefix',
                    'token_mode',
                    'is_active',
                    'vendor__id',
                    'vendor__vendor_id',
                    'vendor__name',
                    'vendor__location'
                )

                utilities_list = []
                for util in utilities:
                    utilities_list.append({
                        'id': util['id'],
                        'utility_name': util['utility_name'],
                        'display_name': util['display_name'],
                        'display_code': util['display_code'],
                        'prefix': util['prefix'],
                        'token_mode': util['token_mode'],
                        'is_active': util['is_active'],
                        'vendor': util['vendor__id'],
                        'vendor_id': util['vendor__vendor_id'],
                        'vendor_name': util['vendor__name'],
                        'vendor_location': util['vendor__location']
                    })

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
            # Fetch all utilities for all vendors of this admin outlet
            utilities = Utility.objects.filter(
                vendor__admin_outlet=admin_outlet
            ).values(
                'id',
                'utility_name',
                'display_name',
                'display_code',
                'prefix',
                'token_mode',
                'is_active',
                'vendor__id',
                'vendor__vendor_id',
                'vendor__name',
                'vendor__location'
            )

            utilities_list = []
            for util in utilities:
                utilities_list.append({
                    'id': util['id'],
                    'utility_name': util['utility_name'],
                    'display_name': util['display_name'],
                    'display_code': util['display_code'],
                    'prefix': util['prefix'],
                    'token_mode': util['token_mode'],
                    'is_active': util['is_active'],
                    'vendor': util['vendor__id'],
                    'vendor_id': util['vendor__vendor_id'],
                    'vendor_name': util['vendor__name'],
                    'vendor_location': util['vendor__location']
                })

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
        if not token_mode and not is_buffet:
            return Response({"error": "token_mode is required"}, status=status.HTTP_400_BAD_REQUEST)
        if prefix is None and not is_buffet:
            return Response({"error": "prefix is required"}, status=status.HTTP_400_BAD_REQUEST)

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

        if not is_buffet and Utility.objects.filter(vendor=vendor, prefix__iexact=prefix).exclude(id=utility.id).exists():
            return Response({"error": "prefix must be unique for each vendor"}, status=status.HTTP_400_BAD_REQUEST)

        # All validations passed; update utility
        utility.utility_name = utility_name
        utility.display_name = display_name
        utility.display_code = display_code
        utility.token_mode = token_mode
        utility.prefix = prefix
        utility.save()

        return Response({
            "success": True,
            "message": "Utility updated successfully",
            "utility": {
                "id": utility.id,
                "utility_name": utility.utility_name,
                "display_name": utility.display_name,
                "display_code": utility.display_code,
                "token_mode": utility.token_mode,
                "prefix": utility.prefix,
                "is_active": utility.is_active
            }
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