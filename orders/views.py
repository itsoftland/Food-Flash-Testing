import json

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from vendors.models import (Order, Vendor, AdminOutlet,
                            AdvertisementProfileAssignment,
                            UserProfile,ChatMessage)
from vendors.serializers import OrdersSerializer

from .utils import send_to_managers
from static.utils.functions.queries import get_vendor



from .serializers import (
    AdminOutletSerializer,
    VendorLogoSerializer,
    VendorAdsSerializer,
    FeedbackSerializer,
    VendorMenuSerializer
)
import logging

logger = logging.getLogger(__name__)

def outlet_selection(request):
    location_id = request.GET.get("location_id")
    context = {}

    response = render(request, "orders/landing_page.html", context)

    if location_id:
        response.set_cookie(
            "activeLocation",
            location_id,
            max_age=30 * 24 * 60 * 60,  # 30 days
            samesite="Lax",            # Helps prevent CSRF
            secure=request.is_secure() # Only for HTTPS
        )

    return response


def home(request):
    cache.clear()
    return render(request, 'orders/index.html')

# def token_display(request):
#     cache.clear()
#     return render(request, 'orders/token_display.html')

@api_view(['POST'])
@permission_classes([AllowAny])
def check_status(request):
    token_no = request.data.get('token_no')
    vendor_id = request.data.get('vendor_id')
    reply_text = request.data.get('reply_text')  # Optional

    logger.info("check_status called with token_no: %s, vendor_id: %s", token_no, vendor_id)

    # ───── Validations ─────
    if not token_no:
        return Response({'error': 'Token number is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if not vendor_id:
        return Response({'error': 'Vendor ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token_no = int(token_no)
        vendor_id = int(vendor_id)
        if token_no <= 0:
            return Response({'error': 'Token number must be a positive integer.'}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError:
        return Response({'error': 'Token number and Vendor ID must be integers.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # ───── Existing Order ─────
        order = Order.objects.get(token_no=token_no, vendor__vendor_id=vendor_id, created_date=timezone.now().date())

        if order.status == 'created':
            order.status = 'preparing'
            order.updated_by = 'customer'
            order.save()

        vendor_serializer = VendorLogoSerializer(order.vendor, context={'request': request})
        logo_url = vendor_serializer.data.get('logo_url', '')

        data = {
            'name': order.vendor.name,
            'vendor': order.vendor.id,
            'token_no': order.token_no,
            'status': order.status,
            'counter_no': order.counter_no or 1,
            'device_id': order.device.id if order.device else None,
            'device_serial_no': order.device.serial_no if order.device else None,
            'manager_id': order.user_profile.id if order.user_profile else None,
            'manager_name': order.user_profile.name if order.user_profile else None,
            'vendor_id': order.vendor.vendor_id,
            'location_id': order.vendor.location_id,
            'logo_url': logo_url,
            'type': 'foodstatus',
            'updated_by': order.updated_by,
            'message': 'Order retrieved successfully.',
            'reply_status': ''
        }

        if reply_text:
            data['message'] = "Reply message sent to managers."
            data['type'] = 'user_reply'
            data['reply_status'] = reply_text
            MAX_MESSAGE_LENGTH = 200

            if reply_text and len(reply_text) > MAX_MESSAGE_LENGTH:
                return Response(
                    {"error": f"Message too long. Limit is {MAX_MESSAGE_LENGTH} characters."},
                    status=400
                )
            
            try:
                ChatMessage.objects.create(
                    vendor=order.vendor,
                    token_no=order.token_no,
                    created_date=timezone.now().date(),
                    sender='user',
                    message_text=reply_text
                )
            except Exception as e:
                logger.exception("Failed to store user chat message")

        send_to_managers(order.vendor, data)
        return Response(data, status=status.HTTP_200_OK)

    except Order.DoesNotExist:
        # ───── New Order ─────
        try:
            vendor = Vendor.objects.get(vendor_id=vendor_id)
            vendor_serializer = VendorLogoSerializer(vendor, context={'request': request})
            logo_url = vendor_serializer.data.get('logo_url', '')

            new_order_data = {
                'name': vendor.name,
                'token_no': token_no,
                'vendor': vendor.id,
                'location_id': vendor.location_id,
                'counter_no': 1,
                'device': None,
                'status': 'preparing',
                'updated_by': 'customer',
                'type': 'foodstatus',
            }

            serializer = OrdersSerializer(data=new_order_data)
            if serializer.is_valid():
                order = serializer.save()

                data = {
                    'name': vendor.name,
                    'vendor': vendor.id,
                    'token_no': token_no,
                    'status': 'preparing',
                    'counter_no': 1,
                    'device_id': None,
                    'device_serial_no': None,
                    'manager_id': None,
                    'manager_name': None,
                    'vendor_id': vendor.vendor_id,
                    'location_id': vendor.location_id,
                    'logo_url': logo_url,
                    'type': 'foodstatus',
                    'updated_by': 'customer',
                    'message': 'Order created with status preparing.',
                    'reply_status': ''
                }
                send_to_managers(vendor, data)

                return Response(data, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        except Vendor.DoesNotExist:
            return Response({'error': 'Vendor not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception("Unexpected error while creating order.")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.exception("Unexpected error while processing order.")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_outlets(request):
    location_id = request.GET.get('location_id', None)  # Fetch location ID from query params
    
    if not location_id:
        return Response({"error": "Location ID is required"}, status=status.HTTP_400_BAD_REQUEST)
    outlets = Vendor.objects.filter(location_id=location_id)
    
    data = [
        {
            "id": outlet.id,
            "name": outlet.name,
            "logo": f"{settings.MEDIA_URL}{outlet.logo}" if outlet.logo else None,
            "vendor_id":outlet.vendor_id
        }
        for outlet in outlets
    ]

    return Response(data, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def get_vendor_logos(request):
    try:
        vendor_ids = request.data.get("vendor_ids")
        
        # Validate input
        if vendor_ids is None or not isinstance(vendor_ids, list):
            return Response(
                {"error": "vendor_ids must be provided as a list."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ensure each ID is an integer
        if not all(isinstance(v_id, int) for v_id in vendor_ids):
            return Response(
                {"error": "All vendor_ids must be integers."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filter using vendor_id, not id
        vendors = Vendor.objects.filter(vendor_id__in=vendor_ids)

        if not vendors.exists():
            return Response(
                {"error": "No matching vendors found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serialized = VendorLogoSerializer(vendors, many=True, context={'request': request})
        return Response(serialized.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response(
            {"error": "An unexpected error occurred.", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def get_vendor_ads(request):
    try:
        vendor_ids = request.data.get("vendor_ids")

        if not vendor_ids or not isinstance(vendor_ids, list):
            return Response({"error": "vendor_ids must be provided as a list."}, status=400)

        vendors = Vendor.objects.filter(vendor_id__in=vendor_ids)

        # ✅ Use serializer to convert ad paths to full URLs
        serializer = VendorAdsSerializer(vendors, many=True, context={'request': request})
        return Response(serializer.data, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)

@api_view(['POST'])
@permission_classes([AllowAny])
def get_vendor_menus(request):
    try:
        vendor_ids = request.data.get("vendor_ids")

        if not vendor_ids or not isinstance(vendor_ids, list):
            return Response({"error": "vendor_ids must be provided as a list."}, status=400)

        vendors = Vendor.objects.filter(vendor_id__in=vendor_ids)

        serializer = VendorMenuSerializer(vendors, many=True, context={'request': request})
        return Response(serializer.data, status=200)

    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
@api_view(['POST'])
@permission_classes([AllowAny])
def submit_feedback(request):
    vendor_id = request.data.get('vendor_id')

    if not vendor_id:
        return Response({'success': False, 'message': 'Vendor ID is required'}, status=400)

    try:
        vendor = Vendor.objects.get(vendor_id=vendor_id)
    except Vendor.DoesNotExist:
        return Response({'success': False, 'message': 'Vendor not found'}, status=404)

    # Prepare the complete data dictionary
    data = {
        'vendor': vendor.id,  # actual primary key
        'feedback_type': request.data.get('feedback_type'),
        'category': request.data.get('category'),
        'name': request.data.get('name'),
        'comment': request.data.get('comment'),
    }

    serializer = FeedbackSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response({'success': True, 'message': 'Feedback submitted successfully'}, status=201)
    else:
        return Response({'success': False, 'errors': serializer.errors}, status=400)

def login_view(request):
   return render(request, 'orders/login.html')


@api_view(['POST'])
@permission_classes([AllowAny])
def login_api_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    requested_role = request.data.get('role')

    if not username or not password:
        return Response({'error': 'Username and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)

    if not user:
        return Response({'error': 'Invalid username or password.'}, status=status.HTTP_401_UNAUTHORIZED)
    login(request, user)
    refresh = RefreshToken.for_user(user)
    MANAGER_ROLE_MAP = {
        'admin_manager': 'Admin Manager',
        'outlet_manager': 'Outlet Manager',
        'order_manager': 'Order Manager',
        'web_manager': 'Web Manager',
    }
    
    # 1. Manager Login (UserProfile with a specific role)
    if requested_role:
        try:
            profile = UserProfile.objects.get(
                user=user,
                role__in=['outlet_manager', 'admin_manager', 'order_manager']
            )
            role_display = MANAGER_ROLE_MAP.get(profile.role, profile.role)
            return Response({
                'message': 'Login successful',
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'username': user.username,
                    'role': role_display,
                    'vendor_id': profile.vendor.id if profile.vendor else None,
                    'vendor_name': profile.vendor.name if profile.vendor else None,
                    'customer_id': profile.admin_outlet.customer_id if profile.admin_outlet else None,
                    'outlet_name': profile.admin_outlet.customer_name if profile.admin_outlet else None,
                    'manager_id': profile.id,
                    'manager_name': profile.name,
                }
            }, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'error': f"This user does not have the '{requested_role}' role."}, status=status.HTTP_403_FORBIDDEN)

    # 2. Superadmin Login
    if user.is_superuser:
        return Response({
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'username': user.username,
                'role': 'Super Admin',
            }
        }, status=status.HTTP_200_OK)

    # 3. Company Login(AdminOutlet)
    if user.is_staff and hasattr(user, 'admin_outlet'):
        customer_id = user.admin_outlet.customer_id
        request.session['customer_id'] = customer_id
        return Response({
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'username': user.admin_outlet.customer_name,
                'role': 'Company',
                'customer_id': customer_id,
            }
        }, status=status.HTTP_200_OK)

    # 4. Outlet Login (Vendor)
    if Vendor.objects.filter(user=user).exists():
        vendor = Vendor.objects.get(user=user)
        return Response({
            'message': 'Login successful',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'username': vendor.name,
                'role': 'Outlet',
                'vendor_id': vendor.id
            }
        }, status=status.HTTP_200_OK)

    return Response({'error': 'User type not recognized.'}, status=status.HTTP_403_FORBIDDEN)



@login_required
def outlet_dashboard(request):
    try:
        vendor = Vendor.objects.get(user=request.user)
    except Vendor.DoesNotExist:
        return redirect('/login')

    context = {
        'vendor': vendor,
    }
    return render(request, 'orders/outlet/outlet_dashboard.html', context)

def logout_view(request):
    logout(request)
    return redirect('/login')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_api_view(request):
    refresh_token = request.data.get("refresh_token")
    if not refresh_token:
        return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token = RefreshToken(refresh_token)
        token.blacklist()

        # Optional session cleanup (only needed if you use Django session auth)
        logout(request)
        request.session.flush()

        return Response({"detail": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['PUT'])
@permission_classes([IsAuthenticated]) 
def update_admin_outlet(request):
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

@api_view(['GET'])
@permission_classes([AllowAny])
def get_banners(request):
    vendor_ids_param = request.GET.get('vendor_ids')
    if not vendor_ids_param:
        return Response({"error": "vendor_ids is required"}, status=400)

    try:
        vendor_ids = json.loads(vendor_ids_param)
        if not isinstance(vendor_ids, list) or not all(isinstance(v, int) for v in vendor_ids):
            raise ValueError
    except ValueError:
        return Response({
            "error": "Invalid vendor_ids format. Use JSON list of integers, e.g., [101,104]"}, status=400)

    vendors = Vendor.objects.filter(vendor_id__in=vendor_ids)
    result = []

    for vendor in vendors:
        assignments = AdvertisementProfileAssignment.objects.filter(
            vendor=vendor).select_related('profile')

        active_profiles = [
            a.profile for a in assignments
            if a.profile.is_active_today()
        ]
        active_profiles.sort(key=lambda p: p.priority)

        ads = []
        for profile in active_profiles:
            ads.extend([request.build_absolute_uri(img.image.url) for img in profile.images.all()])

        result.append({
            "vendor_id": vendor.vendor_id,
            "ads": ads,
            "name": vendor.name
        })

    return Response(result)
