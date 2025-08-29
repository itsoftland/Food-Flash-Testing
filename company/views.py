import json
import logging
import random

from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
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
                            AndroidAPK)

from static.utils.functions.validation import validate_fields
from static.utils.functions.utils import get_time_ranges,get_filtered_date_range
from static.utils.functions.pagination import get_paginated_data
from .serializers import (VendorSerializer,
                          VendorDetailSerializer,
                          UnmappedVendorDetailSerializer,
                          VendorUpdateSerializer,
                          AdvertisementImageSerializer,
                          AdvertisementProfileSerializer,
                          AdvertisementProfileAssignmentSerializer,
                          AdvertisementProfileMiniSerializer,
                          AdminOutletAutoDeleteSerializer,
                          DashboardMetricsSerializer,
                          DeviceSerializer,AndroidDeviceSerializer,
                          OrderSerializer,UserProfileCreateSerializer,
                          UserListDetailSerializer,ManagerDeviceSerializer
                          )

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    return render(request, 'company/dashboard.html')

@login_required(login_url='/login/')
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

@api_view(['GET']) 
@permission_classes([IsAuthenticated])
def get_vendor_details(request):
    vendor_id = request.GET.get('vendor_id')
    
    if not vendor_id:
        return Response({'error': 'Vendor ID not provided'}, status=400)
    try:
        vendor = Vendor.objects.get(vendor_id=vendor_id)
    except Vendor.DoesNotExist:
        return Response({'error': 'Vendor not found'}, status=400)
    
    serializer = VendorDetailSerializer(
        vendor, context={'request': request}
        ).data

    unmapped_vendors_data = UnmappedVendorDetailSerializer(
        vendor, context={'request': request}
        ).data
    
    return Response({
        "vendor_data": serializer,
        "unmapped_data":unmapped_vendors_data,
        "message": "Success"
        }, status=200)

@api_view(['GET']) 
@permission_classes([IsAuthenticated])
def get_vendors(request):
    user = request.user
    try:
        admin_outlet = user.admin_outlet
    except AdminOutlet.DoesNotExist:
        return Response(
            {"error": "AdminOutlet not found for this user."}
            , status=404)

    vendors = admin_outlet.vendors.all()
    vendors_data = VendorSerializer(vendors, many=True).data
       
    return Response(
        {"vendors": vendors_data, "message": "Success"}
        , status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_outlet_creation_data(request):
    user = request.user
    try:
        admin_outlet = user.admin_outlet
    except AdminOutlet.DoesNotExist:
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

    # Get all location codes already used in vendors
    mapped_codes = Vendor.objects.filter(
        admin_outlet=admin_outlet
        ).values_list('location_id', flat=True)

    # Filter unmapped locations
    unmapped_locations = []
    for location in locations_data:
        for name, code in location.items():
            if code not in mapped_codes:
                unmapped_locations.append({'key': name, 'value': code})

    # Get unmapped keypad devices
    available_keypads = Device.objects.filter(
        admin_outlet=admin_outlet, vendor__isnull=True
        ).values('serial_no')

    # Get unmapped Android TVs
    available_android_tvs = AndroidDevice.objects.filter(
        admin_outlet=admin_outlet, vendor__isnull=True
        ).values('mac_address')

    return Response({
        'locations': unmapped_locations,
        'keypad_devices': list(available_keypads),
        'android_tvs': list(available_android_tvs),
    }, status=status.HTTP_200_OK)

def generate_unique_vendor_id():
    while True:
        # Generate a random 6-digit number, first digit 1-9
        vendor_id = random.randint(100000, 999999)
        if not Vendor.objects.filter(vendor_id=vendor_id).exists():
            return vendor_id
        
@api_view(['POST'])
@validate_fields(['customer_id', 'name', 'location', 'place_id',
                  'location_id','logo','menu_files','alias_name'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@transaction.atomic
def create_vendor(request):
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
@parser_classes([MultiPartParser])
def upload_banner(request):
    try:
        images = request.FILES.getlist('banner_images[]')
        if not images:
            return Response({'error': 'No image file provided.'}, status=400)
        admin_outlet = request.user.admin_outlet
        banner_objs = []
        for img in images:
            banner = AdvertisementImage(admin_outlet=admin_outlet, image=img)
            banner_objs.append(banner)
        AdvertisementImage.objects.bulk_create(banner_objs)
        # ad = AdvertisementImage.objects.create(admin_outlet=admin_outlet, image=images)
        return Response({
                'message': f'{len(banner_objs)} banner(s) uploaded successfully.',
                # 'banner_id': ad.id,
                # 'image_url': ad.image.url
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

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def config(request):
    admin_outlet = request.user.admin_outlet

    if request.method == 'GET':
        serializer = AdminOutletAutoDeleteSerializer(admin_outlet)
        return Response(serializer.data)

    if request.method == 'POST':
        serializer = AdminOutletAutoDeleteSerializer(admin_outlet, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Auto-delete setting updated successfully.',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        return Response({
            'error': 'Validation failed.',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
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



