import logging
from django.conf import settings
from django.db import transaction
from django.shortcuts import render
from django.http import HttpResponseBadRequest
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from vendors.models import Vendor, Order, Utility, BuffetOrderItem
from manager.utils.utils import reset_counters_if_new_business_day

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def buffet_submit_order(request):
    data = request.data or {}

    vendor_id = data.get("vendor_id")
    table_number = data.get("table_number")
    customer_name = data.get("customer_name")
    phone_number = data.get("phone_number")
    items_data = data.get("items", [])

    if not vendor_id or not items_data:
        return Response({"error": "vendor_id and items are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        vendor_id_int = int(vendor_id)
    except (ValueError, TypeError):
        return Response({"error": "Invalid vendor_id"}, status=status.HTTP_400_BAD_REQUEST)

    vendor = Vendor.objects.filter(vendor_id=vendor_id_int).first()
    if not vendor:
        return Response({"error": "Vendor not found."}, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        reset_counters_if_new_business_day(vendor, None)
        
        last_booking = Order.objects.filter(vendor=vendor).order_by("-token_no").first()
        token_no = (last_booking.token_no + 1) if last_booking else 1

        order = Order.objects.create(
            vendor=vendor,
            token_no=token_no,
            table_booking_no=table_number, # Store table number here
            counter_no=1,
            updated_by='customer',
            status='created',
            customer_name=customer_name,
            phone_number=phone_number,
        )

        created_items = []
        for item in items_data:
            utility_id = item.get("utility_id")
            utility = Utility.objects.filter(id=utility_id, vendor=vendor).first()
            if not utility:
                logger.warning(f"Utility {utility_id} not found for vendor {vendor_id_int}")
                continue
            
            customizations = item.get("customizations", [])
            item_remarks = item.get("remarks", "")
            is_grouped = item.get("is_grouped", False)
            quantity = int(item.get("quantity", 1))

            buffet_item = BuffetOrderItem.objects.create(
                order=order,
                utility=utility,
                status='created',
                customizations=customizations,
                remarks=item_remarks,
                is_grouped=is_grouped,
                quantity=quantity
            )
            created_items.append(buffet_item.id)
            
        if not created_items:
            # If no items were created (e.g. due to invalid utilities), rollback.
            transaction.set_rollback(True)
            return Response({"error": "No valid items found in order."}, status=status.HTTP_400_BAD_REQUEST)

    # Note: For DineFlash Buffet, we may need to trigger a web socket / mqtt message to the Kitchen View here.
    # The kitchen view will poll or rely on mqtt. We can add MQTT publishing later if required.

    return Response({
        "message": "Order placed successfully.",
        "order_id": order.id,
        "token_no": order.token_no,
        "table_number": table_number,
        "items_count": len(created_items)
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_table_booking(request):
    vendor_id = request.GET.get("vendor_id") or request.COOKIES.get("vendor_id")
    
    utilities_enabled = False
    phone_number_enabled = False

    if vendor_id:
        vendor = Vendor.objects.filter(vendor_id=vendor_id).first()
        if vendor and hasattr(vendor, "config"):
            utilities_enabled = vendor.config.use_utilities
            phone_number_enabled = vendor.config.phone_number_enabled

    context = {
        "vendor_id": vendor_id,
        "UTILITIES_ENABLED": utilities_enabled,
        "PHONE_NUMBER_ENABLED": phone_number_enabled,
    }

    return render(request, 'orders/buffet/table_booking.html', context)

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_utility_selection(request):
    return render(request, 'orders/buffet/utility_selection.html')

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_combined_options(request):
    return render(request, 'orders/buffet/combined_options.html')

@api_view(['GET'])
@permission_classes([AllowAny])
def buffet_order_confirmation(request):
    return render(request, 'orders/buffet/order_confirmation.html')
