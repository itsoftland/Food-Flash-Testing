from vendors.models import Vendor,Order
from .utils import (get_vendor_business_day_range,
                    get_vendor_current_date)

import logging
logger = logging.getLogger(__name__)

def get_vendor(vendor_id):
    return Vendor.objects.get(vendor_id=vendor_id)
    
def get_order(token_no, vendor):
    start_dt, end_dt = get_vendor_business_day_range(vendor)
    order = Order.objects.filter(
        token_no=token_no,
        vendor=vendor,
        created_at__range=(start_dt, end_dt)
    ).first()
    return order

def get_airline_data(sequence_code, vendor):
    order = Order.objects.filter(
        sequence_code=sequence_code,
        vendor=vendor,
    ).first()
    return order

def get_booking(booking_id, vendor):
    start_dt, end_dt = get_vendor_business_day_range(vendor)
    order = Order.objects.filter(
        id=booking_id,
        vendor=vendor,
        created_at__range=(start_dt, end_dt)
    ).first()
    return order



def update_existing_order_by_manager(token_no, vendor, device, status,manager):
    order = get_order(token_no, vendor)
    if order:
        order.status = status
        order.updated_by = "manager"
        order.device = device
        order.user_profile = manager
        order.save()
    if not order:
        order = Order.objects.create(
            token_no=token_no,
            vendor=vendor,
            status=status,  
            device=device,
            user_profile=manager,
            updated_by="manager"
        )
    return order
def update_existing_status_by_airlinemanager(sequence_code, vendor, device, status,manager):
    order = get_airline_data(sequence_code, vendor)
    if order:
        order.status = status
        order.updated_by = "manager"
        order.device = device
        order.user_profile = manager
        order.save()
    if not order:
        order = Order.objects.create(
            sequence_code=sequence_code,
            vendor=vendor,
            status=status,  
            device=device,
            user_profile=manager,
            updated_by="manager"
        )
    return order

def update_booking_status_by_dinemanager(booking,status,manager):
    booking.status = status
    booking.updated_by = "manager"
    booking.user_profile = manager
    booking.save()
    return booking


def update_patient_status_by_hospital_manager(booking, status, manager):
    booking.status = status
    booking.updated_by = "manager"
    booking.user_profile = manager
    booking.save()
    return booking

def update_existing_status_by_airlinemanager_bulk(sequence_code=None, vendor=None, device=None, status=None, manager=None, orders_queryset=None):
    """
    Updates one or multiple passenger orders (Airline Manager).

    Args:
        sequence_code (str): Single passenger sequence code.
        vendor (Vendor): Vendor instance.
        device: Device used for update (optional).
        status (str): New status to set.
        manager (UserProfile): Manager performing the update.
        orders_queryset (QuerySet): Optional queryset of multiple orders to bulk update.

    Returns:
        int or Order: Number of updated records (for bulk) or the updated Order instance (for single).
    """
    # === Case 1: Bulk update (flight or zone) ===
    if orders_queryset is not None and orders_queryset.exists():
        logger.info(f"🛫 Bulk updating {orders_queryset.count()} passengers to status '{status}'")

        updated_count = orders_queryset.update(
            status=status,
            updated_by="manager",
            device=device,
            user_profile=manager,
        )
        return updated_count

    # === Case 2: Single passenger (sequence_code) ===
    order = get_airline_data(sequence_code, vendor)
    if order:
        order.status = status
        order.updated_by = "manager"
        order.device = device
        order.user_profile = manager
        order.save(update_fields=["status", "updated_by", "device", "user_profile", "updated_at"])
        return order

    # === Case 3: If not found, create a new record ===
    order = Order.objects.create(
        sequence_code=sequence_code,
        vendor=vendor,
        status=status,
        device=device,
        user_profile=manager,
        updated_by="manager"
    )
    return order


