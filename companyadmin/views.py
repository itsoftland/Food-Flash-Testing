import json
import logging
import random
from collections import defaultdict

import pytz
import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    parser_classes,
    permission_classes,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

    
from .serializers import VendorListSerializer
from orders.serializers import AdminOutletSerializer
from static.utils.functions.validation import validate_fields
from vendors.models import (
    AdminOutlet,
    AndroidDevice,
    Device,
    Utility,
    UtilityOption,
    UserProfile,
    Vendor,
    VendorConfig,
)

logger = logging.getLogger(__name__)
base = getattr(settings, 'LOGIN_URL')
PROJECT_NAME = getattr(settings, "PROJECT_NAME", "").lower()

@login_required
def registration(request):
    logger.info("Registration page requested by user: %s", request.user)
    # Clear only cache entries relevant to this view
    cache.delete_many([
        'registration_page_data',
    ])
    return render(request, 'companyadmin/registration.html')

@login_required
def companies(request):
    logger.info("Companies list page requested by user: %s", request.user)
    # Clear only cache entries relevant to this view
    cache.delete_many([
        'registration_page_data',
    ])
    return render(request, 'companyadmin/company_lists.html')

@login_required
def create_outlet(request):
    # Clear only cache entries relevant to this view
    cache.delete_many([
        'create_outlet_page_data',
    ])
    return render(request, 'companyadmin/create_outlet.html')

@login_required
def outlet_lists(request):
    # Clear only cache entries relevant to this view
    cache.delete_many([
        'outlet_list_page_data',
    ])
    return render(request, 'companyadmin/outlet_list.html')

@login_required
def order_update(request):
    # Clear only cache entries relevant to this view
    cache.delete_many([
        'update_order_page_data',
    ])
    return render(request, 'companyadmin/update_order.html')

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def product_registration(request):
    product_registration_url = getattr(settings, "LICENSE_PORTAL_URL")
    external_url = product_registration_url + "api/ProductRegistration"

    try:
        # Forward the received JSON payload to the external API
        response = requests.post(
            external_url,
            json=request.data,  # forwards JSON data as-is
            timeout=10  # seconds
        )

        if response.status_code == 200:
            return Response(response.json(), status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "External API error", "details": response.text},
                status=response.status_code
            )
    except requests.exceptions.RequestException as e:
        return Response(
            {"error": "Failed to contact external Product Registration API", "details": str(e)},
            status=status.HTTP_502_BAD_GATEWAY
        )

def preprocess_request_data(data):
    return {
        'user': {
            'username': data.get('CustomerUsername'),
            'password': data.get('CustomerPassword'),
        },
        'customer_name': data.get('CustomerName'),
        'phone_number': data.get('PhoneNumber'),
        'customer_email': data.get('CustomerEmail'),
        'gst_number': data.get('GSTNumber'),
        'customer_contact_person': data.get('CustomerContactPerson'),
        'customer_contact': data.get('CustomerContact'),
        'customer_address': data.get('CustomerAddress'),
        'customer_address2': data.get('CustomerAddress2'),
        'customer_state': data.get('CustomerState'),
        'customer_city': data.get('CustomerCity'),
        # New fields
        'authentication_status': data.get('Authenticationstatus'),
        'product_registration_id': data.get('ProductRegistrationId'),
        'unique_identifier': data.get('UniqueIDentifier'),
        'customer_id': data.get('CustomerId'),
        'product_from_date': data.get('ProductFromDate'),
        'product_to_date': data.get('ProductToDate'),
        'total_count': data.get('TotalCount'),
        'project_code': data.get('ProjectCode'),
        'web_login_count': data.get('WebLoginCount'),
        'android_tv_count': data.get('AndroidTvCount'),
        'android_apk_count': data.get('AndroidApkCount'),
        'keypad_device_count': data.get('KeypadDeviceCount'),
        'led_display_count': data.get('LedDisplayCount'),
        'outlet_count': data.get('OutletCount'),
        'locations': json.loads(data.get('Locations', '[]')),
    }

@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def register_company(request):
    logger.info("Company registration initiated. Incoming request data.")
    logger.debug("Registration payload: %s", dict(request.data))
    
    data = preprocess_request_data(request.data)
    # Duplicate check for company name and email
    if AdminOutlet.objects.filter(
        customer_name=data.get('customer_name'),
        customer_email=data.get('customer_email')
    ).exists():
        logger.warning("Registration failed: Company with name '%s' and email '%s' already exists.", 
                       data.get('customer_name'), data.get('customer_email'))
        return Response(
            {"error": "A company with the same name and email already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )
    # Duplicate check for username in User model
    username = data.get('user', {}).get('username')
    if username and AdminOutlet.objects.filter(user__username=username).exists():
        logger.warning("Registration failed: Username '%s' already exists.", username)
        return Response(
            {"error": "Username already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = AdminOutletSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        logger.info("Company registered successfully: %s (User: %s)", 
                    data.get('customer_name'), username)
        return Response({
            "status": "success",
            "message": "Company registered successfully"
            }, status=status.HTTP_201_CREATED)

    logger.warning("Registration validation failed: %s", serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def company_lists(request):
    """
    GET /api/company_lists/
    Query params:
      - page (pagination)
      - page_size (optional, if you want variable page size and enabled)
      - all=true  -> returns all records (no pagination)
    """
    logger.info("Fetching company lists (API). User: %s, Params: %s", request.user, request.query_params)
    qs = AdminOutlet.objects.all().order_by('-created_at')

    # if client explicitly requests all, return non-paginated list
    if request.query_params.get('all') in ('1', 'true', 'True'):
        serializer = AdminOutletSerializer(qs, many=True, context={'request': request})
        logger.debug("Returning all companies (unpaginated). Count: %d", qs.count())
        return Response(serializer.data, status=status.HTTP_200_OK)

    # otherwise paginate
    paginator = PageNumberPagination()
    paginator.page_size = 25  # default page size; change or read from settings
    page = paginator.paginate_queryset(qs, request)
    serializer = AdminOutletSerializer(page, many=True, context={'request': request})
    logger.debug("Returning paginated company list. Count: %d", len(page) if page else 0)
    return paginator.get_paginated_response(serializer.data)

@api_view(['PUT'])
@authentication_classes([])
@permission_classes([AllowAny]) 
def update_company_id(request,id):
    if not id:
        return Response({"error": "customer_id is required."},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        admin_outlet = AdminOutlet.objects.get(id=id)
    except AdminOutlet.DoesNotExist:
        return Response({"error": "AdminOutlet not found for this id."},
                        status=status.HTTP_404_NOT_FOUND)
    serializer = AdminOutletSerializer(admin_outlet, data=request.data, partial=True)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT'])
@authentication_classes([])
@permission_classes([AllowAny]) 
def update_company(request):
    customer_id = request.data.get('customer_id')
    if not customer_id:
        return Response({"error": "customer_id is required."},
                        status=status.HTTP_400_BAD_REQUEST)

    try:
        admin_outlet = AdminOutlet.objects.get(customer_id=customer_id)
    except AdminOutlet.DoesNotExist:
        return Response({"error": "AdminOutlet not found for this customer_id."},
                        status=status.HTTP_404_NOT_FOUND)

    # Ensure username is NOT changed, so remove user data or ignore it
    data = request.data.copy()
    if 'user' in data:
        data.pop('user')

    serializer = AdminOutletSerializer(admin_outlet, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def product_authentication(request):
    product_authentication_url = getattr(settings, "LICENSE_PORTAL_URL")
    external_url = product_authentication_url + "api/ProductAuthentication"
    try:
        # Forward the received JSON payload to the external API
        response = requests.post(
            external_url,
            json=request.data,  # e.g., { "CustomerId": "1234" }
            timeout=10
        )

        if response.status_code == 200:
            return Response(response.json(), status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": "External API error", "details": response.text},
                status=response.status_code
            )
    except requests.exceptions.RequestException as e:
        return Response(
            {"error": "Failed to contact external Product Authentication API", "details": str(e)},
            status=status.HTTP_502_BAD_GATEWAY
        )

@login_required
@never_cache
def dashboard(request):
    # Superadmin check - not linked to AdminOutlet or Vendor
    is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
    is_vendor = Vendor.objects.filter(user=request.user).exists()
    if is_admin_outlet or is_vendor:
        return redirect(base)

    context = {
        'user': request.user,
        'admin_outlets': AdminOutlet.objects.all(),
        'vendors': Vendor.objects.all(),
    }
    return render(request, 'companyadmin/dashboard.html', context)
    
@login_required
def create_utility(request):
    # Superadmin check - not linked to AdminOutlet or Vendor
    is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
    is_vendor = Vendor.objects.filter(user=request.user).exists()
    if is_admin_outlet or is_vendor:
        return redirect(base)

    return render(request, 'companyadmin/create_utility.html')

@login_required
def manage_utilities(request):
    # Superadmin check
    is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
    is_vendor = Vendor.objects.filter(user=request.user).exists()
    if is_admin_outlet or is_vendor:
        return redirect(base)

    return render(request, 'companyadmin/manage_utilities.html')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_utilities(request):
    """
    Returns all utilities for Super Admin with search and filtering.
    """
    try:
        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        is_vendor = Vendor.objects.filter(user=request.user).exists()
        if is_admin_outlet or is_vendor:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        search_query = request.GET.get('search', '')
        vendor_id = request.GET.get('vendor_id', '')
        status_filter = request.GET.get('status', '')

        utilities = Utility.objects.all().select_related('vendor', 'vendor__admin_outlet')

        if search_query:
            utilities = utilities.filter(
                Q(utility_name__icontains=search_query) |
                Q(display_name__icontains=search_query) |
                Q(display_code__icontains=search_query)
            )

        if vendor_id:
            utilities = utilities.filter(vendor__vendor_id=vendor_id)

        if status_filter:
            is_active = status_filter.lower() == 'active'
            utilities = utilities.filter(is_active=is_active)

        utilities_list = []
        for util in utilities:
            options = util.options.all()
            options_list = [{
                'id': opt.id,
                'name': opt.name,
                'is_active': opt.is_active
            } for opt in options]
            
            utilities_list.append({
                'id': util.id,
                'utility_name': util.utility_name,
                'display_name': util.display_name,
                'display_code': util.display_code,
                'token_mode': util.token_mode,
                'prefix': util.prefix,
                'is_active': util.is_active,
                'vendor_id': util.vendor.vendor_id,
                'vendor_name': util.vendor.name,
                'vendor_location': util.vendor.location,
                'company_name': util.vendor.admin_outlet.customer_name if util.vendor.admin_outlet else 'N/A',
                'options': options_list
            })

        return Response({
            "success": True,
            "utilities": utilities_list,
            "count": len(utilities_list)
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@login_required
def utility_user_mapping(request):
    # Superadmin check
    is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
    is_vendor = Vendor.objects.filter(user=request.user).exists()
    if is_admin_outlet or is_vendor:
        return redirect(base)

    if PROJECT_NAME == "dine_flash_buffet":
        return render(request, 'companyadmin/utility_user_mapping_buffet.html')

    return render(request, 'companyadmin/utility_user_mapping.html')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_users(request):
    """
    API to fetch all users for Super Admin.
    """
    try:
        if PROJECT_NAME == "dine_flash_buffet":
            utility_profiles = UserProfile.objects.filter(
                role='utility_user'
            ).select_related('user', 'admin_outlet', 'vendor').prefetch_related('assigned_utilities')

            users_data = []
            for profile in utility_profiles:
                user_inst = profile.user
                users_data.append({
                    'id': profile.id,
                    'username': user_inst.username,
                    'name': profile.name or f"{user_inst.first_name} {user_inst.last_name}".strip() or user_inst.username,
                    'email': user_inst.email,
                    'roles': ['utility_user'],
                    'assigned_utilities': [
                        {
                            'id': util.id,
                            'display_name': util.display_name,
                            'utility_name': util.utility_name
                        }
                        for util in profile.assigned_utilities.all()
                    ]
                })

            return Response({
                'message': 'Users retrieved successfully.',
                'users': users_data
            }, status=status.HTTP_200_OK)

        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        is_vendor = Vendor.objects.filter(user=request.user).exists()
        if is_admin_outlet or is_vendor:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        users = UserProfile.objects.all().select_related('user', 'admin_outlet', 'vendor')

        # Group users by user.id and aggregate roles
        grouped_users = {}
        
        for u in users:
            uid = u.user.id
            if uid not in grouped_users:
                grouped_users[uid] = {
                    'instance': u,
                    'roles': set(),
                    'assigned_utilities': []
                }
            
            grouped_users[uid]['roles'].add(u.role)
            
            # Add assigned utilities if any
            if u.assigned_utilities.exists():
                for util in u.assigned_utilities.all():
                    # Avoid duplicates in assigned_utilities list
                    if not any(item['id'] == util.id for item in grouped_users[uid]['assigned_utilities']):
                        grouped_users[uid]['assigned_utilities'].append({
                            'id': util.id, 
                            'name': util.display_name or util.utility_name
                        })

        serialized_data = []
        for uid, data in grouped_users.items():
            user_inst = data['instance'].user
            serialized_data.append({
                'id': uid,
                'username': user_inst.username,
                'name': f"{user_inst.first_name} {user_inst.last_name}",
                'email': user_inst.email,
                'roles': list(data['roles']),
                'assigned_utilities': data['assigned_utilities']
            })

        return Response({
            'message': 'Users retrieved successfully.',
            'users': serialized_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_utilities_sa(request):
    """
    Super Admin API to update a user's assigned utilities.
    """
    try:
        if PROJECT_NAME == "dine_flash_buffet":
            user_id = request.data.get('user_id')
            assigned_utilities = request.data.get('assigned_utilities', [])

            if not user_id:
                return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user_profile = UserProfile.objects.get(id=user_id)
            except UserProfile.DoesNotExist:
                return Response({"error": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)

            if user_profile.role != 'utility_user':
                return Response({"error": "User is not a utility_user."}, status=status.HTTP_400_BAD_REQUEST)

            if not user_profile.vendor:
                return Response({"error": "User does not belong to a vendor."}, status=status.HTTP_400_BAD_REQUEST)

            utilities = Utility.objects.filter(id__in=assigned_utilities, vendor=user_profile.vendor)
            if utilities.count() != len(set(assigned_utilities)):
                return Response({"error": "Some utilities are invalid or do not belong to this vendor."}, status=status.HTTP_400_BAD_REQUEST)

            user_profile.assigned_utilities.set(utilities)
            return Response({"message": "Assigned utilities updated successfully."}, status=status.HTTP_200_OK)

        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        is_vendor = Vendor.objects.filter(user=request.user).exists()
        if is_admin_outlet or is_vendor:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get('user_id')
        assigned_utilities = request.data.get('assigned_utilities', [])

        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Update all UserProfile instances for this user
        # (Since roles are stored in UserProfile, and mapping relates to the user)
        # Assuming Utility mapping is global for the User across all their profiles?
        # Actually, let's update ALL profiles for this user.
        profiles = UserProfile.objects.filter(user_id=user_id)
        if not profiles.exists():
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        utilities = Utility.objects.filter(id__in=assigned_utilities)
        
        for profile in profiles:
            profile.assigned_utilities.set(utilities)

        return Response({"message": "Mapping updated successfully"}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def get_outlet_creation_data(request,customer_id):
    """
    GET /api/get_outlet_creation_data/
    """
    logger.info("Fetching outlet creation data for customer_id: %s (User: %s)", customer_id, request.user)
    admin_outlet = AdminOutlet.objects.filter(customer_id=customer_id).first()
    if not admin_outlet:
        logger.error("AdminOutlet not found for customer_id: %s", customer_id)
        return Response(
            {'error': 'AdminOutlet not found'}
            , status=status.HTTP_404_NOT_FOUND)

    # Parse locations from JSONField safely.
    # Local DB may already return list/dict, while some environments store JSON as string.
    raw_locations = admin_outlet.locations
    if raw_locations in (None, ""):
        locations_data = []
    elif isinstance(raw_locations, str):
        try:
            locations_data = json.loads(raw_locations)
        except json.JSONDecodeError:
            return Response(
                {'error': 'Invalid locations JSON'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    elif isinstance(raw_locations, list):
        locations_data = raw_locations
    elif isinstance(raw_locations, dict):
        locations_data = [raw_locations]
    else:
        locations_data = []
    # All locations
    locations = []
    for location in locations_data:
        if not isinstance(location, dict):
            continue
        for name, code in location.items():
            locations.append({'key': str(name), 'value': str(code)})

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
    
    # ✅ Add all timezone regions
    timezone_regions = [{'key': tz, 'value': tz} for tz in pytz.all_timezones]

    return Response({
        'locations': locations,
        'keypad_devices': list(available_keypads),
        'android_tvs': list(available_android_tvs),
        'tv_communication_modes': tv_comm_choices,
        'mqtt_modes': mqtt_mode_choices,
        'timezones': timezone_regions,
    }, status=status.HTTP_200_OK)

def generate_unique_vendor_id():
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
@authentication_classes([SessionAuthentication])
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
def update_utility_status_sa(request):
    """
    Super Admin API to update utility status (activate/deactivate).
    """
    try:
        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        if is_admin_outlet:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        utility_id = request.data.get('utility_id')
        is_active = request.data.get('is_active')

        utility = Utility.objects.get(id=utility_id)
        utility.is_active = is_active
        utility.save()

        return Response({"message": "Status updated successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_utility_sa(request):
    """
    Super Admin API to update utility details.
    """
    try:
        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        if is_admin_outlet:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        utility_id = request.data.get('utility_id')
        utility = Utility.objects.get(id=utility_id)

        utility.utility_name = request.data.get('utility_name', utility.utility_name)
        utility.display_name = request.data.get('display_name', utility.display_name)
        utility.display_code = request.data.get('display_code', utility.display_code)
        utility.token_mode = request.data.get('token_mode', utility.token_mode)
        utility.prefix = request.data.get('prefix', utility.prefix)
        
        utility.save()
        return Response({"message": "Utility updated successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_utility_option_sa(request, utility_id):
    """
    Super Admin API to create utility option.
    """
    try:
        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        if is_admin_outlet:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        utility = Utility.objects.get(id=utility_id)
        name = request.data.get("name")
        
        if UtilityOption.objects.filter(utility=utility, name__iexact=name).exists():
            return Response({"error": "Option already exists"}, status=status.HTTP_400_BAD_REQUEST)
            
        option = UtilityOption.objects.create(utility=utility, name=name)
        return Response({"message": "Option created", "option": {"id": option.id, "name": option.name, "is_active": option.is_active}}, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_utility_option_sa(request, option_id):
    """
    Super Admin API to update utility option.
    """
    try:
        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        if is_admin_outlet:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        option = UtilityOption.objects.get(id=option_id)
        name = request.data.get("name")
        is_active = request.data.get("is_active")
        
        if name:
            option.name = name
        if is_active is not None:
            if isinstance(is_active, str):
                is_active = is_active.lower() == 'true'
            option.is_active = is_active
            
        option.save()
        return Response({"message": "Option updated", "option": {"id": option.id, "name": option.name, "is_active": option.is_active}}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_utility_option_sa(request, option_id):
    """
    Super Admin API to delete utility option.
    """
    try:
        # Superadmin check
        is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
        if is_admin_outlet:
             return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        option = UtilityOption.objects.get(id=option_id)
        option.delete()
        return Response({"message": "Option deleted"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def all_outlets(request):
    """
    Return all vendors (outlets) with their associated company info.
    """
    vendors = Vendor.objects.select_related('admin_outlet').order_by('name')
    serializer = VendorListSerializer(vendors, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)
