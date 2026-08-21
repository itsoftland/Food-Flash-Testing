"""
Dine Flash Buffet only: per-utility station-queue pre-announcement notifications.

When a BuffetOrderItem transitions to ready, notify the next
pre_announcement_count eligible (non-terminal, non-ready) items behind that
anchor in the same vendor/utility business-day queue.

Optional ETA: approximate_service_time * eligible distance (minutes).
Service time does not affect recipient selection. Service time 0 omits ETA.
No MQTT. Web Push + ChatMessage only.
Hospital Flash pre-announcement remains entirely separate.
"""

import json
import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from vendors.models import BuffetOrderItem, ChatMessage
from vendors.utils import notify_web_push

logger = logging.getLogger(__name__)
project_name = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()

# Ready + terminal statuses do not receive pre-announcements and do not
# consume a slot in the pre_announcement_count window.
_BUFFET_PRE_ANNOUNCEMENT_EXCLUDED_STATUSES = frozenset(
    {"ready", "delivered", "cancelled", "operation_closed"}
)


def is_dine_flash_buffet():
    return project_name == "dine_flash_buffet"


def is_eligible_for_buffet_pre_announcement(status):
    """Non-terminal items that have not yet reached ready are eligible."""
    return (status or "").strip().lower() not in _BUFFET_PRE_ANNOUNCEMENT_EXCLUDED_STATUSES


def _buffet_vendor_chat_alias(vendor):
    if not vendor:
        return ""
    alias = (getattr(vendor, "alias_name", None) or "").strip()
    if alias:
        return alias
    ao = getattr(vendor, "admin_outlet", None)
    if ao is not None:
        cn = (getattr(ao, "customer_name", None) or "").strip()
        if cn:
            return cn
    return (getattr(vendor, "name", None) or "").strip()


def get_utility_queue_items(vendor, utility, start_dt, end_dt):
    """
    Buffet station queue for the current business day.

    Same vendor + utility; day scoped via parent Order.created_at (existing
    Buffet business-day handling). Ordered by item created_at, id.
    """
    return list(
        BuffetOrderItem.objects.filter(
            order__vendor=vendor,
            utility=utility,
            order__created_at__range=(start_dt, end_dt),
        )
        .select_related("utility", "order", "order__vendor")
        .order_by("created_at", "id")
    )


def select_buffet_pre_announcement_recipients(queue_items, anchor_item_id, pre_count):
    """
    Return [(item, distance), ...] for the next ``pre_count`` eligible items
    after the ready anchor. Ready/terminal rows are skipped and do not consume
    the count. The anchor itself is never selected.
    """
    if pre_count <= 0 or not queue_items:
        return []

    anchor_idx = None
    for index, item in enumerate(queue_items):
        if item.pk == anchor_item_id or item.id == anchor_item_id:
            anchor_idx = index
            break
    if anchor_idx is None:
        return []

    recipients = []
    distance = 0
    for item in queue_items[anchor_idx + 1 :]:
        if not is_eligible_for_buffet_pre_announcement(item.status):
            continue
        distance += 1
        if distance > pre_count:
            break
        recipients.append((item, distance))
    return recipients


def build_buffet_pre_announcement_payload(
    item, *, distance, queue_position, alias_name, eta_minutes=None
):
    order = item.order
    vendor = order.vendor
    item_name = item.utility.display_name if item.utility else "your item"
    utility_name = item_name
    token_no = order.token_no

    title = "Almost Your Turn"
    if eta_minutes is not None and eta_minutes > 0:
        body = (
            f"Your Order {token_no} for {item_name} is approaching its turn "
            f"(approximately {eta_minutes} minute(s) away)."
        )
    else:
        body = (
            f"Your Order {token_no} for {item_name} is approaching its turn "
            f"(about {distance} ahead in the {utility_name} queue)."
        )

    payload = {
        "title": title,
        "body": body,
        "message": body,
        "type": "buffet_pre_announcement",
        "vendor_id": vendor.vendor_id,
        "token_no": token_no,
        "booking_id": order.id,
        "item_id": item.id,
        "item_name": item_name,
        "utility_name": utility_name,
        "status": (item.status or "").strip().lower(),
        "alias_name": alias_name,
        "queue_position": queue_position,
        "distance_from_ready": distance,
        "name": getattr(vendor, "name", "") or "",
    }
    if eta_minutes is not None and eta_minutes > 0:
        payload["eta_minutes"] = eta_minutes
    return payload


def process_buffet_pre_announcements(vendor, utility, ready_item, start_dt, end_dt):
    """
    After a BuffetOrderItem becomes ready, notify the next eligible items
    in that utility's business-day queue.

    Dine Flash Buffet only. Safe no-op for other flavours / missing config.
    Does not send MQTT and does not alter existing item_* notifications.
    """
    if not is_dine_flash_buffet():
        return []
    if not vendor or not utility or ready_item is None or not start_dt or not end_dt:
        return []

    pre_count = int(getattr(utility, "pre_announcement_count", 0) or 0)
    if pre_count <= 0:
        return []

    # Buffet-only read of shared Utility.approximate_service_time.
    # Does not affect recipient selection; 0 means omit ETA (not disable notify).
    service_time = int(getattr(utility, "approximate_service_time", 0) or 0)

    queue_items = get_utility_queue_items(vendor, utility, start_dt, end_dt)
    if not queue_items:
        return []

    recipients = select_buffet_pre_announcement_recipients(
        queue_items, ready_item.pk, pre_count
    )
    if not recipients:
        return []

    alias_name = _buffet_vendor_chat_alias(vendor)
    notified_items = []

    for item, distance in recipients:
        if item.pre_announcement_notified_distance == distance:
            continue

        # Atomic per-(item, distance) claim: first update wins; retries /
        # concurrent processing for the same distance are skipped.
        claimed = (
            BuffetOrderItem.objects.filter(pk=item.pk)
            .filter(
                ~Q(status__in=list(_BUFFET_PRE_ANNOUNCEMENT_EXCLUDED_STATUSES))
            )
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

        item.pre_announcement_notified_at = timezone.now()
        item.pre_announcement_notified_distance = distance

        # 1-based index in the full station queue (stable registration order).
        queue_position = next(
            (idx for idx, row in enumerate(queue_items, start=1) if row.pk == item.pk),
            distance,
        )
        eta_minutes = service_time * distance if service_time > 0 else None
        payload = build_buffet_pre_announcement_payload(
            item,
            distance=distance,
            queue_position=queue_position,
            alias_name=alias_name,
            eta_minutes=eta_minutes,
        )

        # Chat persistence (Buffet pattern) — no MQTT for pre-announcement.
        order = item.order
        chat_payload = {
            "item_id": item.id,
            "item_name": payload["item_name"],
            "status": payload["status"],
            "type": "buffet_pre_announcement",
            "alias_name": alias_name,
            "token_no": order.token_no,
            "distance_from_ready": distance,
            "queue_position": queue_position,
            "body": payload["body"],
            "message": payload["message"],
        }
        if "eta_minutes" in payload:
            chat_payload["eta_minutes"] = payload["eta_minutes"]
        ChatMessage.objects.create(
            vendor=vendor,
            token_no=order.token_no,
            booking_no=order.table_booking_no,
            booking_id=order.id,
            created_date=timezone.now().date(),
            sender="system",
            is_send=True,
            message_text=json.dumps(chat_payload),
        )
        notify_web_push(order, vendor, payload)
        notified_items.append(item)
        logger.info(
            "[buffet_pre_announcement] item_id=%s order_id=%s token_no=%s "
            "utility=%s distance=%s eta_minutes=%s ready_anchor_id=%s",
            item.id,
            order.id,
            order.token_no,
            getattr(utility, "display_name", None) or utility.id,
            distance,
            payload.get("eta_minutes"),
            ready_item.pk,
        )

    return notified_items
