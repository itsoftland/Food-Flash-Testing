import json
import requests

from django.core.cache import cache
from django.shortcuts import render, redirect
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings

from rest_framework.decorators import api_view,permission_classes 
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from orders.serializers import AdminOutletSerializer
from vendors.models import Vendor,AdminOutlet

@login_required
def registration(request):
    # Clear only cache entries relevant to this view
    cache.delete_many([
        'registration_page_data',
    ])
    return render(request, 'companyadmin/registration.html')

@login_required
def order_update(request):
    # Clear only cache entries relevant to this view
    cache.delete_many([
        'update_order_page_data',
    ])
    return render(request, 'companyadmin/update_order.html')

@api_view(['POST'])
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
@permission_classes([AllowAny])
def register_company(request):
    data = preprocess_request_data(request.data)
    # Duplicate check for company name and email
    if AdminOutlet.objects.filter(
        customer_name=data.get('customer_name'),
        customer_email=data.get('customer_email')
    ).exists():
        return Response(
            {"error": "A company with the same name and email already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )
    # Duplicate check for username in User model
    username = data.get('user', {}).get('username')
    if username and AdminOutlet.objects.filter(user__username=username).exists():
        return Response(
            {"error": "Username already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = AdminOutletSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Company registered successfully"}, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
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
def dashboard(request):
    # Superadmin check - not linked to AdminOutlet or Vendor
    is_admin_outlet = AdminOutlet.objects.filter(user=request.user).exists()
    is_vendor = Vendor.objects.filter(user=request.user).exists()
    if is_admin_outlet or is_vendor:
        return redirect('/login')

    context = {
        'user': request.user,
        'admin_outlets': AdminOutlet.objects.all(),
        'vendors': Vendor.objects.all(),
    }
    return render(request, 'companyadmin/dashboard.html', context)