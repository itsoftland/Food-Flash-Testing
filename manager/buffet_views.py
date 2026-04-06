import logging
import json
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from vendors.models import BuffetOrderItem, Order, ChatMessage
from manager.utils.utils import get_manager_vendor
from vendors.services.order_service import send_order_update
from vendors.utils import notify_web_push
from static.utils.functions.utils import get_vendor_business_day_range

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_buffet_kitchen_items(request):
    try:
        vendor = get_manager_vendor(request.user)
        if not vendor:
            return Response({"error": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

        start_dt, end_dt = get_vendor_business_day_range(vendor)
        
        user_profile = request.user.profile_roles.first()
        if not user_profile:
             return Response({"error": "User profile not found"}, status=status.HTTP_403_FORBIDDEN)
        
        assigned_utilities = user_profile.assigned_utilities.all()
        
        items = BuffetOrderItem.objects.filter(
            order__vendor=vendor,
            order__created_at__range=(start_dt, end_dt),
            status__in=['created', 'preparing'] # Only show active items
        )
        
        # Filter by assigned utilities if they have any, else they might be a global manager
        if assigned_utilities.exists():
            items = items.filter(utility__in=assigned_utilities)
            
        items = items.select_related('order', 'utility').order_by('created_at')
        
        data = []
        for item in items:
            data.append({
                "id": item.id,
                "order_id": item.order.id,
                "token_no": item.order.token_no,
                "table_number": item.order.table_booking_no,
                "customer_name": item.order.customer_name,
                "utility_name": item.utility.display_name if item.utility else "Unknown",
                "status": item.status,
                "quantity": item.quantity,
                "remarks": item.remarks,
                "customizations": item.customizations,
                "is_grouped": item.is_grouped,
                "created_at": item.created_at
            })
            
        return Response({"items": data}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("[get_buffet_kitchen_items] Error: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def _notify_item_update(vendor, item, status_text):
    """Helper to create ChatMessage and send real-time notification."""
    order = item.order
    # Create ChatMessage for customer history
    ChatMessage.objects.create(
        vendor=vendor,
        token_no=order.token_no,
        booking_no=order.table_booking_no,
        booking_id=order.id,
        created_date=timezone.now().date(),
        sender='system',
        is_send=True,
        message_text=json.dumps({
            "item_id": item.id,
            "item_name": item.utility.display_name if item.utility else "Unknown",
            "status": status_text,
            "type": "buffet_item_update"
        })
    )
    
    # Send MQTT/Push notification
    # Buffest flavour: provide verbose, multi-line message body similar to statusMessages.js
    item_name = item.utility.display_name if item.utility else "your item"
    
    if status_text == "ready":
        verb = "ready"
        suffix = "Please collect it."
    elif status_text == "preparing":
        verb = "preparing"
        suffix = "Please wait while we finish it."
    elif status_text == "cancelled":
        verb = "cancelled"
        suffix = "Please contact staff for assistance."
    elif status_text == "delivered":
        verb = "delivered"
        suffix = "Thank you for choosing us!"
    else:
        verb = status_text
        suffix = ""

    message_body = f"Your Order {order.token_no} for {item_name} is now {verb}. {suffix}".strip()

    push_payload = {
        "type": f"item_{status_text}",
        "vendor_id": vendor.vendor_id,
        "token_no": order.token_no,
        "booking_id": order.id,
        "item_id": item.id,
        "item_name": item_name,
        "status": status_text,
        "title": f"Order {status_text.capitalize()}",
        "body": message_body,
        "message": message_body
    }
    
    send_order_update(vendor, push_payload)
    notify_web_push(order, vendor, push_payload)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_buffet_item_preparing(request):
    return _update_buffet_item_status(request, 'preparing')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_buffet_item_ready(request):
    return _update_buffet_item_status(request, 'ready')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_buffet_item_cancelled(request):
    return _update_buffet_item_status(request, 'cancelled')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_buffet_item_delivered(request):
    return _update_buffet_item_status(request, 'delivered')

def _update_buffet_item_status(request, new_status):
    try:
        item_id = request.data.get("item_id")
        if not item_id:
            return Response({"error": "item_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        vendor = get_manager_vendor(request.user)
        user_profile = request.user.profile_roles.first()
        
        if not user_profile:
             return Response({"error": "User profile not found"}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            item = BuffetOrderItem.objects.select_for_update().filter(id=item_id, order__vendor=vendor).first()
            if not item:
                return Response({"error": "Buffet item not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Responsibility check: Utility User must be assigned to the item's utility
            assigned_utilities = user_profile.assigned_utilities.all()
            if assigned_utilities.exists() and item.utility not in assigned_utilities:
                return Response({"error": "You are not authorized to update this item"}, status=status.HTTP_403_FORBIDDEN)

            # Idempotency check: Don't send duplicate notifications
            if item.status == new_status:
                return Response({"message": f"Item is already {new_status}"}, status=status.HTTP_200_OK)
                
            item.status = new_status
            item.save(update_fields=['status'])
            
            _notify_item_update(vendor, item, new_status)
                
        return Response({"message": f"Item marked as {new_status} successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception(f"[_update_buffet_item_status] Error: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_booking_delivered(request):
    try:
        booking_id = request.data.get("booking_id")
        if not booking_id:
            return Response({"error": "booking_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        vendor = get_manager_vendor(request.user)
        logger.info(f"[mark_booking_delivered] Processing delivery for booking_id={booking_id}, vendor={vendor.id}")

        with transaction.atomic():
            # Try lookup by primary key first
            order = Order.objects.select_for_update().filter(id=booking_id, vendor=vendor).first()
            
            # Fallback: Try lookup by token_no for today's business day if id lookup failed
            if not order:
                logger.debug(f"[mark_booking_delivered] Order ID {booking_id} not found. Trying token_no fallback.")
                start_dt, end_dt = get_vendor_business_day_range(vendor)
                order = Order.objects.select_for_update().filter(
                    token_no=booking_id, 
                    vendor=vendor, 
                    created_at__range=(start_dt, end_dt)
                ).first()

            if not order:
                # Check if the ID exists but for a different vendor for debugging
                exists_elsewhere = Order.objects.filter(id=booking_id).exists()
                logger.warning(f"[mark_booking_delivered] Booking {booking_id} not found (exists_elsewhere={exists_elsewhere})")
                return Response({"error": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Validation: All non-cancelled items must be ready or delivered
            pending_items = order.buffet_items.exclude(status__in=['ready', 'cancelled', 'delivered']).exists()
            if pending_items:
                logger.warning(f"[mark_booking_delivered] Cannot deliver Order {order.id}: pending items exist.")
                return Response({"error": "Cannot deliver: some items are still pending"}, status=status.HTTP_400_BAD_REQUEST)
            
            if order.status == 'delivered':
                 return Response({"message": "Booking is already delivered"}, status=status.HTTP_200_OK)

            order.status = 'delivered'
            order.updated_by = 'manager'
            order.save(update_fields=['status', 'updated_by'])
            
            # Note: No item-level chat message as per requirement
            push_payload = {
                "type": "order_delivered",
                "vendor_id": vendor.vendor_id,
                "token_no": order.token_no,
                "booking_id": order.id,
                "message": "Your order has been delivered. Thank you!"
            }
            send_order_update(vendor, push_payload)
            notify_web_push(order, vendor, push_payload)
                
        return Response({"message": "Booking marked as delivered successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("[mark_booking_delivered] Error: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
