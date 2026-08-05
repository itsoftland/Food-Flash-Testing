"""
Hospital Flash only: department queue pre-announcement notifications.

Notify every waiting patient whose distance from the current called token
satisfies 0 < distance <= pre_announcement_count.

ETA = approximate_service_time * distance (minutes).

Patients may receive another pre-announcement when the queue advances and
their distance changes (updated ETA). Deduped per (order, distance) so a
single recalculation / concurrent retry cannot double-push the same ETA.
"""

import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from orders.serializers import VendorLogoSerializer
from vendors.models import Order
from vendors.utils import notify_web_push

logger = logging.getLogger(__name__)
project_name = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()


def is_hospital_flash():
    return project_name == "hospital_flash"


def get_department_queue_orders(vendor, utility, start_dt, end_dt):
    """
    Hospital department queue for the business day.

    Ordering matches manager booking list within a department: created_at, id.
    Positions are stable 1-based indices over the full day queue (including
    completed/cancelled) so distance uses registration order, not live renumbering.
    """
    return list(
        Order.objects.filter(
            vendor=vendor,
            utility=utility,
            created_at__range=(start_dt, end_dt),
        )
        .select_related("utility", "vendor", "vendor__config")
        .order_by("created_at", "id")
    )


def find_current_called_index(queue_orders):
    """
    1-based index of the current called patient in the department queue.

    When multiple orders are marked called, the latest (highest index) is used.
    Returns None when nobody is currently called.
    """
    current_idx = None
    for index, order in enumerate(queue_orders, start=1):
        if (order.status or "").strip().lower() == "called":
            current_idx = index
    return current_idx


def compute_queue_distance(patient_index, current_called_index):
    """Distance from the current called token to a patient (same units as example)."""
    if current_called_index is None or patient_index is None:
        return None
    return patient_index - current_called_index


def build_hospital_pre_announcement_payload(
    request,
    order,
    *,
    department_name,
    eta_minutes,
    queue_position,
    distance,
):
    vendor = order.vendor
    vendor_serializer = VendorLogoSerializer(vendor, context={"request": request})
    logo_url = vendor_serializer.data.get("logo_url", "")
    batch_id = order.registration_batch_id
    booking_no = order.table_booking_no

    title = "Almost Your Turn"
    body = (
        f"{department_name}: you are approximately {eta_minutes} minute(s) away "
        f"(position {queue_position})."
    )

    return {
        "title": title,
        "body": body,
        "type": "hospital_pre_announcement",
        "registration_batch_id": str(batch_id) if batch_id else None,
        "booking_id": order.id,
        "booking_no": booking_no,
        "utility_name": department_name,
        "department_name": department_name,
        "customer_name": order.customer_name,
        "status": (order.status or "").strip().lower(),
        "token_no": order.token_no,
        "counter_no": order.counter_no or 1,
        "eta_minutes": eta_minutes,
        "queue_position": queue_position,
        "distance_from_called": distance,
        "name": vendor.name,
        "alias_name": vendor.alias_name,
        "vendor_id": vendor.vendor_id,
        "location_id": vendor.location_id,
        "logo_url": logo_url,
        "vibration_pattern": vendor.config.vibration_pattern,
        "vibration_duration": vendor.config.vibration_duration,
    }


def process_hospital_pre_announcements(request, vendor, utility, start_dt, end_dt):
    """
    Recalculate department queue and notify patients in the pre-announcement window.

    Hospital Flash only. Safe no-op for other flavours / missing config.
    """
    if not is_hospital_flash():
        return []
    if not vendor or not utility or not start_dt or not end_dt:
        return []

    pre_count = int(getattr(utility, "pre_announcement_count", 0) or 0)
    if pre_count <= 0:
        return []

    service_time = int(getattr(utility, "approximate_service_time", 0) or 0)
    department_name = utility.display_name or "-"

    queue_orders = get_department_queue_orders(vendor, utility, start_dt, end_dt)
    if not queue_orders:
        return []

    current_called_index = find_current_called_index(queue_orders)
    if current_called_index is None:
        return []

    notified_orders = []
    for patient_index, order in enumerate(queue_orders, start=1):
        if (order.status or "").strip().lower() != "waiting":
            continue

        distance = compute_queue_distance(patient_index, current_called_index)
        if distance is None or distance <= 0 or distance > pre_count:
            continue
        if order.pre_announcement_notified_distance == distance:
            continue

        # Atomic per-(order, distance) claim: first update wins; retries /
        # concurrent recalculations for the same distance are skipped.
        claimed = (
            Order.objects.filter(pk=order.pk, status="waiting")
            .filter(
                Q(pre_announcement_notified_distance__isnull=True)
                | ~Q(pre_announcement_notified_distance=distance)
            )
            .update(
                pre_announcement_notified_at=timezone.now(),
                pre_announcement_notified_distance=distance,
            )
        )
        if claimed != 1:
            continue

        order.pre_announcement_notified_at = timezone.now()
        order.pre_announcement_notified_distance = distance
        eta_minutes = service_time * distance
        payload = build_hospital_pre_announcement_payload(
            request,
            order,
            department_name=department_name,
            eta_minutes=eta_minutes,
            queue_position=patient_index,
            distance=distance,
        )
        notify_web_push(order, vendor, payload)
        notified_orders.append(order)
        logger.info(
            "[hospital_pre_announcement] booking_id=%s booking_no=%s dept=%s "
            "distance=%s eta_minutes=%s current_called_index=%s",
            order.id,
            order.table_booking_no,
            department_name,
            distance,
            eta_minutes,
            current_called_index,
        )

    return notified_orders
