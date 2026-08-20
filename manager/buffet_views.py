import logging
import json
from collections import OrderedDict

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from rest_framework.exceptions import NotFound

from vendors.models import BuffetOrderItem, Order, ChatMessage, UserProfile, Utility
from manager.utils.utils import get_manager_vendor
from manager.buffet_pre_announcement import process_buffet_pre_announcements
from vendors.services.order_service import send_order_update
from vendors.utils import notify_web_push, buffet_utility_image_payload
from static.utils.functions.utils import get_vendor_business_day_range
from orders.buffet.order_create import (
    BuffetOrderCreateStatus,
    create_buffet_order,
)

logger = logging.getLogger(__name__)
project_name = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()


def _sync_buffet_registry_after_lifecycle(order):
    """
    Dine Flash Buffet only: drop inactive orders from Active Order Registry.
    Uses transaction.on_commit so removal runs after the status write commits.
    Never touches BuffetOrderLookup / recovery.
    """
    if project_name != "dine_flash_buffet":
        return
    if order is None or getattr(order, "pk", None) is None:
        return
    order_id = order.pk

    def _run():
        try:
            from orders.buffet.active_order_registry import (
                sync_buffet_active_order_lifecycle,
            )
            from vendors.models import Order as OrderModel

            fresh = (
                OrderModel.objects.filter(pk=order_id)
                .prefetch_related("buffet_items")
                .first()
            )
            if fresh is None:
                return
            removed = sync_buffet_active_order_lifecycle(order=fresh)
            if removed:
                logger.info(
                    "[buffet] registry lifecycle removed order_id=%s token_no=%s status=%s",
                    fresh.pk,
                    fresh.token_no,
                    fresh.status,
                )
        except Exception:
            logger.exception(
                "[buffet] registry lifecycle sync failed order_id=%s",
                order_id,
            )

    transaction.on_commit(_run)

def _buffet_vendor_chat_alias(vendor):
    """
    Header label for Dine Flash Buffet customer chat / push payloads.
    Aligns with CHECK_STATUS: vendor.alias_name when set; otherwise outlet name, then vendor.name.
    """
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


# BuffetOrderItem.status values (see core.config.status_choices "dine_flash_buffet")
_BUFFET_LINE_STATUSES = frozenset(
    {"created", "preparing", "ready", "delivered", "cancelled", "operation_closed"}
)

# Allowed targets for POST api/buffet_update_item_status/ (manager kitchen)
_BUFFET_ITEM_STATUS_UPDATE_ACTIONS = frozenset(
    {"preparing", "ready", "cancelled", "delivered", "operation_closed"}
)


def _buffet_line_details(item):
    """Normalized customizations list and remarks for customer-facing payloads."""
    raw_cust = item.customizations
    if isinstance(raw_cust, list):
        customizations = [str(c).strip() for c in raw_cust if c is not None and str(c).strip()]
    else:
        customizations = []
    remarks = (item.remarks or "").strip() if item.remarks else ""
    return customizations, remarks


def _buffet_line_detail_suffix(item):
    """Human-readable suffix when the same utility appears on multiple lines."""
    parts = []
    customizations, remarks = _buffet_line_details(item)
    if customizations:
        parts.append(", ".join(customizations))
    if remarks:
        parts.append(f"Note: {remarks}")
    return f" ({'; '.join(parts)})" if parts else ""


def _serialize_buffet_utility(request, utility):
    payload = {
        "id": utility.id,
        "utility_name": utility.utility_name,
        "display_name": utility.display_name,
        "display_code": utility.display_code,
        "token_mode": utility.token_mode,
        "prefix": utility.prefix,
        "options": [
            {
                "id": option.id,
                "name": option.name,
                "is_active": option.is_active,
            }
            for option in utility.options.all()
            if option.is_active
        ],
    }
    payload.update(buffet_utility_image_payload(request, utility))
    return payload


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buffet_create_order(request):
    """
    Dine Flash Buffet: Outlet Manager creates a customer Buffet order.

    Uses the shared Buffet create core (same as customer buffet_submit_order).
    Vendor is resolved from the authenticated manager profile — request vendor_id
    is never trusted alone.
    """
    if project_name != "dine_flash_buffet":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    logger.info(
        "[buffet_create_order] Started | remote_addr=%s | user=%s",
        request.META.get("REMOTE_ADDR"),
        getattr(request.user, "username", None),
    )

    vendor = get_manager_vendor(request.user)
    data = request.data or {}

    # Optional: if client sends vendor_id, it must match the manager's outlet.
    request_vendor_id = data.get("vendor_id")
    if request_vendor_id is not None and str(request_vendor_id).strip() != "":
        if str(request_vendor_id) != str(vendor.vendor_id):
            logger.warning(
                "[buffet_create_order] vendor_id mismatch | request=%s | manager=%s",
                request_vendor_id,
                vendor.vendor_id,
            )
            return Response(
                {"error": "vendor_id does not match manager vendor."},
                status=status.HTTP_403_FORBIDDEN,
            )

    items_data = data.get("items", [])
    if not items_data:
        logger.warning(
            "[buffet_create_order] Missing items | user=%s",
            getattr(request.user, "username", None),
        )
        return Response(
            {"error": "items are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    table_number = data.get("table_number")
    customer_name = data.get("customer_name")
    phone_number = data.get("phone_number") or None

    manager_profile = (
        request.user.profile_roles.order_by("id").first()
        if hasattr(request.user, "profile_roles")
        else None
    )

    result = create_buffet_order(
        vendor=vendor,
        items_data=items_data,
        updated_by="manager",
        user_profile=manager_profile,
        table_number=table_number,
        customer_name=customer_name,
        phone_number=phone_number,
        log_prefix="[buffet_create_order]",
    )

    if result.status == BuffetOrderCreateStatus.REMARKS_TOO_LONG:
        return Response(
            {"error": result.error_message},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if result.status == BuffetOrderCreateStatus.NO_VALID_ITEMS:
        return Response(
            {"error": result.error_message},
            status=status.HTTP_400_BAD_REQUEST,
        )

    order = result.order
    created_items = result.created_item_ids or []

    logger.info(
        "[buffet_create_order] Order created | vendor_id=%s | order_id=%s | token_no=%s | "
        "table_number=%s | items_count=%s | manager_id=%s",
        vendor.vendor_id,
        order.id,
        order.token_no,
        table_number,
        len(created_items),
        manager_profile.id if manager_profile else None,
    )

    return Response(
        {
            "message": "Order created successfully by manager.",
            "order_id": order.id,
            "token_no": order.token_no,
            "table_number": table_number,
            "items_count": len(created_items),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_assigned_buffet_utilities(request):
    """
    Returns active buffet utilities assigned to the logged-in utility user.
    """
    if project_name != "dine_flash_buffet":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        utility_profile = (
            UserProfile.objects.select_related("vendor", "admin_outlet")
            .prefetch_related(
                "assigned_utilities__options",
                "assigned_utilities__buffet_images",
            )
            .filter(user=request.user, role="utility_user")
            .order_by("id")
            .first()
        )

        if not utility_profile:
            return Response(
                {"error": "Utility user profile not found."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not utility_profile.vendor_id:
            return Response(
                {"error": "Utility user is not mapped to any vendor."},
                status=status.HTTP_403_FORBIDDEN,
            )

        utilities = sorted(
            (
                utility
                for utility in utility_profile.assigned_utilities.all()
                if utility.vendor_id == utility_profile.vendor_id and utility.is_active
            ),
            key=lambda utility: utility.id,
        )
        data = [_serialize_buffet_utility(request, utility) for utility in utilities]

        return Response(
            {
                "utilities": data,
                "count": len(data),
                "utility_mapped": bool(data),
                "user": {
                    "manager_id": utility_profile.id,
                    "manager_name": utility_profile.name,
                    "vendor_id": utility_profile.vendor.vendor_id,
                    "customer_id": utility_profile.vendor.admin_outlet.customer_id,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("[get_assigned_buffet_utilities] Error: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
                "item_id": item.id,
                "utility_id": item.utility_id,
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
    customizations, remarks = _buffet_line_details(item)
    detail_suffix = _buffet_line_detail_suffix(item)
    item_name = item.utility.display_name if item.utility else "Unknown"

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
            "item_name": item_name,
            "status": status_text,
            "type": "buffet_item_update",
            "alias_name": _buffet_vendor_chat_alias(vendor),
            "customizations": customizations,
            "remarks": remarks,
            "token_no": order.token_no,
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
    elif status_text == "operation_closed":
        verb = "closed for this service"
        suffix = "Thank you for choosing us today."
    else:
        verb = status_text.replace("_", " ")
        suffix = ""

    message_body = (
        f"Your Order {order.token_no} for {item_name}{detail_suffix} is now {verb}. {suffix}"
    ).strip()

    if status_text == "operation_closed":
        push_title = "Close operation"
    else:
        push_title = f"Order {status_text.capitalize()}"

    push_payload = {
        "type": f"item_{status_text}",
        "vendor_id": vendor.vendor_id,
        "token_no": order.token_no,
        "booking_id": order.id,
        "item_id": item.id,
        "item_name": item_name,
        "status": status_text,
        "title": push_title,
        "body": message_body,
        "message": message_body,
        "alias_name": _buffet_vendor_chat_alias(vendor),
        "customizations": customizations,
        "remarks": remarks,
    }
    
    send_order_update(vendor, push_payload)
    notify_web_push(order, vendor, push_payload)


def _group_buffet_lines_by_utility(queryset):
    """Build [{id, name, lines: [{status, quantity, item_id, customizations, remarks}]}] preserving utility order."""
    groups = OrderedDict()
    for row in queryset:
        if not row.utility_id or not row.utility:
            continue
        uid = row.utility_id
        if uid not in groups:
            groups[uid] = {
                "id": row.utility.id,
                "name": row.utility.display_name or row.utility.utility_name,
                "lines": [],
            }
        groups[uid]["lines"].append(
            {
                "status": row.status,
                "quantity": row.quantity,
                "item_id": row.id,
                "customizations": row.customizations,
                "remarks": row.remarks,
            }
        )
    return list(groups.values())


def _buffet_selected_utilities_status_payload(order, utility_ids, statuses_filter):
    """
    Returns (utilities list | None, error str | None).
    utilities: [{id, name, lines: [{status, quantity, item_id, customizations, remarks}]}, ...]

    statuses_filter: None → all line statuses; non-empty list → only those statuses.
    """
    if not utility_ids:
        return None, "No utility ids."

    qs = (
        BuffetOrderItem.objects.filter(order=order, utility_id__in=utility_ids)
        .select_related("utility")
        .order_by("utility_id", "id")
    )

    if statuses_filter is not None:
        if len(statuses_filter) == 0:
            return None, "statuses, when provided, must be a non-empty list of status strings."
        unknown = [s for s in statuses_filter if s not in _BUFFET_LINE_STATUSES]
        if unknown:
            return None, f"Invalid status value(s): {unknown}"
        qs = qs.filter(status__in=list(statuses_filter))

    utilities = _group_buffet_lines_by_utility(qs)
    if not utilities:
        return None, "No buffet items match the selected utilities and status filter."
    return utilities, None


def _strip_delivered_lines_from_utilities(utilities):
    """Return a deep copy of utilities blocks with `delivered` lines removed; drop empty blocks."""
    out = []
    for block in utilities or []:
        lines = [ln for ln in (block.get("lines") or []) if (ln.get("status") or "").lower() != "delivered"]
        if not lines:
            continue
        out.append({**block, "lines": lines})
    return out


def _buffet_assigned_items_queryset(vendor, start_dt, end_dt, user_profile):
    """
    BuffetOrderItem rows for the vendor business day, scoped by role / assigned_utilities
    (same idea as get_buffet_kitchen_items).
    """
    qs = BuffetOrderItem.objects.filter(
        order__vendor=vendor,
        order__created_at__range=(start_dt, end_dt),
    ).select_related("order", "utility")

    assigned = list(user_profile.assigned_utilities.all())
    if user_profile.role == "utility_user":
        allowed = [u for u in assigned if u.vendor_id == vendor.id]
        if not allowed:
            return qs.none()
        return qs.filter(utility_id__in=[u.id for u in allowed])

    if assigned:
        return qs.filter(utility__in=assigned)
    return qs


def _buffet_all_assigned_tokens_response(vendor, user_profile, hide_delivered):
    """
    Build [{token_no, booking_id, submitted_at, utilities: [...]}, ...] for today's orders
    that still have at least one visible line after optional delivered stripping.
    """
    start_dt, end_dt = get_vendor_business_day_range(vendor)
    base_qs = _buffet_assigned_items_queryset(vendor, start_dt, end_dt, user_profile)
    order_ids = base_qs.values_list("order_id", flat=True).distinct()
    if not order_ids:
        return []

    orders_payload = []
    for order in (
        Order.objects.filter(id__in=order_ids, vendor=vendor)
        .order_by("token_no", "id")
    ):
        qs = base_qs.filter(order_id=order.id).order_by("utility_id", "id")
        utilities = _group_buffet_lines_by_utility(qs)
        if hide_delivered:
            utilities = _strip_delivered_lines_from_utilities(utilities)
        if not utilities:
            continue
        orders_payload.append(
            {
                "token_no": order.token_no,
                "booking_id": order.id,
                "submitted_at": order.created_at.isoformat(),
                "utilities": utilities,
            }
        )
    return orders_payload


def _human_buffet_line_status_bit(line):
    """Status + qty + optional customizations/remarks for push/chat plain text."""
    st = line.get("status") or "unknown"
    qty = line.get("quantity")
    try:
        q = int(qty)
    except (TypeError, ValueError):
        q = 1
    bit = f"{st}" + (f" ×{q}" if q and q != 1 else "")
    detail_parts = []
    raw_cust = line.get("customizations")
    if isinstance(raw_cust, list):
        detail_parts.extend(
            str(c).strip() for c in raw_cust if c is not None and str(c).strip()
        )
    remarks = (line.get("remarks") or "").strip() if line.get("remarks") else ""
    if remarks:
        detail_parts.append(f"Note: {remarks}")
    if detail_parts:
        bit = f"{bit} ({'; '.join(detail_parts)})"
    return bit


def _human_buffet_status_message(order, utilities_payload):
    """Single paragraph for push body / chat."""
    parts = []
    for block in utilities_payload:
        name = block.get("name") or "Station"
        line_bits = [_human_buffet_line_status_bit(ln) for ln in block.get("lines") or []]
        parts.append(f"{name}: {', '.join(line_bits)}" if line_bits else name)
    return f"Your Order {order.token_no} — " + "; ".join(parts)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def buffet_utilities_orders_summary(request):
    """
    Dine Flash Buffet — utilities / kitchen orders summary API.

    - GET, or POST with no `utility_ids` / `token_no`: returns all tokens (orders)
      for the business day assigned to the caller. Utility users do not see lines
      with status ``delivered``. Outlet / admin managers see every line status.
      No body or query parameters are required.

    - POST with ``utility_ids`` (non-empty list) and ``token_no``: legacy behaviour —
      sends web push and chat for that order and utilities. Optional ``statuses``
      filters which line statuses are included in the notification.
    """
    if project_name != "dine_flash_buffet":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        vendor = get_manager_vendor(request.user)
    except NotFound:
        return Response({"error": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)

    user_profile = (
        UserProfile.objects.select_related("vendor")
        .prefetch_related("assigned_utilities")
        .filter(user=request.user, vendor=vendor)
        .order_by("id")
        .first()
    )
    if not user_profile:
        return Response({"error": "User profile not found"}, status=status.HTTP_403_FORBIDDEN)

    raw_ids = request.data.get("utility_ids")
    token_no = request.data.get("token_no")
    legacy_notify = isinstance(raw_ids, list) and len(raw_ids) > 0 and token_no is not None

    if not legacy_notify:
        if user_profile.role == "utility_user":
            hide_delivered = True
        elif user_profile.role in ("outlet_manager", "admin_manager"):
            hide_delivered = False
        else:
            return Response(
                {"error": "This summary is only available for utility users or outlet managers."},
                status=status.HTTP_403_FORBIDDEN,
            )
        orders_payload = _buffet_all_assigned_tokens_response(vendor, user_profile, hide_delivered)
        return Response(
            {
                "message": "Buffet utilities summary.",
                "orders": orders_payload,
            },
            status=status.HTTP_200_OK,
        )

    try:
        utility_ids = sorted({int(x) for x in raw_ids})
    except (TypeError, ValueError):
        return Response(
            {"error": "utility_ids must contain integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        token_no = int(token_no)
    except (TypeError, ValueError):
        return Response({"error": "token_no must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

    assigned = list(user_profile.assigned_utilities.all())
    if assigned:
        allowed = {u.id for u in assigned if u.vendor_id == vendor.id}
        bad = [uid for uid in utility_ids if uid not in allowed]
        if bad:
            return Response(
                {"error": "You are not authorized for one or more utilities.", "invalid_utility_ids": bad},
                status=status.HTTP_403_FORBIDDEN,
            )
    else:
        existing = set(
            Utility.objects.filter(vendor=vendor, id__in=utility_ids).values_list("id", flat=True)
        )
        if existing != set(utility_ids):
            return Response(
                {"error": "One or more utilities are invalid for this vendor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    start_dt, end_dt = get_vendor_business_day_range(vendor)
    order = (
        Order.objects.filter(
            vendor=vendor,
            token_no=token_no,
            created_at__range=(start_dt, end_dt),
        )
        .first()
    )
    if not order:
        return Response({"error": "Order not found for this token today."}, status=status.HTTP_404_NOT_FOUND)

    raw_statuses = request.data.get("statuses", None)
    statuses_filter = None
    if raw_statuses is not None:
        if not isinstance(raw_statuses, list):
            return Response(
                {"error": "statuses must be an array of status strings, or omitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            statuses_filter = [str(s).strip().lower() for s in raw_statuses if str(s).strip()]
        except TypeError:
            statuses_filter = []

    utilities_payload, err_msg = _buffet_selected_utilities_status_payload(
        order, utility_ids, statuses_filter
    )
    if err_msg:
        return Response(
            {"error": err_msg, "utility_ids": utility_ids},
            status=status.HTTP_400_BAD_REQUEST,
        )

    message_body = _human_buffet_status_message(order, utilities_payload)

    chat_alias = _buffet_vendor_chat_alias(vendor)
    chat_payload = {
        "type": "buffet_utilities_status",
        "utilities": utilities_payload,
        "token_no": order.token_no,
        "booking_id": order.id,
        "alias_name": chat_alias,
    }

    push_payload = {
        "type": "buffet_utilities_status",
        "vendor_id": vendor.vendor_id,
        "token_no": order.token_no,
        "booking_id": order.id,
        "utilities": utilities_payload,
        "title": "Buffet station update",
        "body": message_body,
        "message": message_body,
        "alias_name": chat_alias,
    }

    try:
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
        send_order_update(vendor, push_payload)
        notify_web_push(order, vendor, push_payload)
    except Exception as e:
        logger.exception("[buffet_utilities_orders_summary] Error: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response(
        {
            "message": "Station notification sent.",
            "utilities": utilities_payload,
            "token_no": order.token_no,
            "booking_id": order.id,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def buffet_update_item_status(request):
    """
    Dine Flash Buffet: set a single BuffetOrderItem line status.

    Preferred body:
      - {"item_id": <int>, "status": ...}
      Optional disambiguation / validation on the same request:
      - {"token_no": <int>, "item_id": <int>, "status": ...}
      - {"token_no": <int>, "utility_id": <int>, "item_id": <int>, "status": ...}

    Legacy (only when exactly one line exists for that token + utility today):
      - {"token_no": <int>, "utility_id": <int>, "status": ...}
        If multiple lines share the same utility on that order, the API returns 400 and
        lists ``item_ids`` so the client must send ``item_id``.
    """
    if project_name != "dine_flash_buffet":
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    raw = request.data.get("status")
    new_status = (raw or "").strip().lower() if isinstance(raw, str) else ""
    if new_status not in _BUFFET_ITEM_STATUS_UPDATE_ACTIONS:
        logger.warning(
            "[buffet_update_item_status] Invalid or missing status | status=%s | remote_addr=%s",
            raw,
            request.META.get("REMOTE_ADDR"),
        )
        return Response(
            {
                "error": "Invalid or missing status.",
                "allowed": sorted(_BUFFET_ITEM_STATUS_UPDATE_ACTIONS),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return _update_buffet_item_status(request, new_status)


def _update_buffet_item_status(request, new_status):
    logger.info(
        "[buffet_update_item_status] Started | remote_addr=%s | status=%s | item_id=%s | "
        "token_no=%s | utility_id=%s",
        request.META.get("REMOTE_ADDR"),
        new_status,
        request.data.get("item_id"),
        request.data.get("token_no"),
        request.data.get("utility_id"),
    )
    try:
        item_id = request.data.get("item_id")
        token_no = request.data.get("token_no")
        utility_id = request.data.get("utility_id")

        has_item_id = item_id not in (None, "")
        has_token = token_no not in (None, "")
        has_utility = utility_id not in (None, "")
        has_token_utility_pair = has_token and has_utility

        if not has_item_id and not has_token_utility_pair:
            return Response(
                {
                    "error": (
                        "Send item_id (recommended), or both token_no and utility_id "
                        "only when a single buffet line exists for that pair."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        vendor = get_manager_vendor(request.user)
        user_profile = request.user.profile_roles.first()

        if not user_profile:
            return Response({"error": "User profile not found"}, status=status.HTTP_403_FORBIDDEN)

        start_dt, end_dt = get_vendor_business_day_range(vendor)

        with transaction.atomic():
            if has_item_id:
                try:
                    item_id_int = int(item_id)
                except (ValueError, TypeError):
                    return Response({"error": "item_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
                items = list(
                    BuffetOrderItem.objects.select_for_update()
                    .select_related("utility", "order")
                    .filter(id=item_id_int, order__vendor=vendor)
                )
                if not items:
                    return Response({"error": "Buffet item not found"}, status=status.HTTP_404_NOT_FOUND)
                ref_item = items[0]
                if not (start_dt <= ref_item.order.created_at <= end_dt):
                    return Response(
                        {"error": "Buffet item not found for the current business day."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if has_token:
                    try:
                        token_no_int = int(token_no)
                    except (ValueError, TypeError):
                        return Response(
                            {"error": "token_no must be an integer"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if ref_item.order.token_no != token_no_int:
                        return Response(
                            {"error": "token_no does not match this buffet line."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                if has_utility:
                    try:
                        utility_id_int = int(utility_id)
                    except (ValueError, TypeError):
                        return Response(
                            {"error": "utility_id must be an integer"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    if ref_item.utility_id != utility_id_int:
                        return Response(
                            {"error": "utility_id does not match this buffet line."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                items = [ref_item]
            else:
                try:
                    token_no_int = int(token_no)
                    utility_id_int = int(utility_id)
                except (ValueError, TypeError):
                    return Response(
                        {"error": "token_no and utility_id must be integers"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                order = (
                    Order.objects.select_for_update()
                    .filter(
                        token_no=token_no_int,
                        vendor=vendor,
                        created_at__range=(start_dt, end_dt),
                    )
                    .first()
                )
                if not order:
                    return Response({"error": "Buffet item not found"}, status=status.HTTP_404_NOT_FOUND)
                items = list(
                    BuffetOrderItem.objects.select_for_update()
                    .select_related("utility", "order")
                    .filter(order=order, utility_id=utility_id_int)
                )
                if len(items) > 1:
                    return Response(
                        {
                            "error": (
                                "Multiple buffet lines share this token and utility. "
                                "Include item_id in the request to update exactly one line."
                            ),
                            "item_ids": [row.id for row in items],
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if not items:
                return Response({"error": "Buffet item not found"}, status=status.HTTP_404_NOT_FOUND)

            assigned_utilities = user_profile.assigned_utilities.all()
            for item in items:
                if assigned_utilities.exists() and item.utility not in assigned_utilities:
                    return Response(
                        {"error": "You are not authorized to update this item"},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            updated_any = False
            touched_order = None
            for item in items:
                if item.status == new_status:
                    continue
                previous_status = item.status
                item.status = new_status
                item.save(update_fields=["status"])
                # Existing item_* notifications first; pre-announcement is additive.
                _notify_item_update(vendor, item, new_status)
                if new_status == "ready" and item.utility_id:
                    process_buffet_pre_announcements(
                        vendor,
                        item.utility,
                        item,
                        start_dt,
                        end_dt,
                    )
                updated_any = True
                touched_order = item.order
                logger.info(
                    "[buffet_update_item_status] Status updated | vendor_id=%s | token_no=%s | "
                    "item_id=%s | utility_id=%s | %s -> %s",
                    vendor.vendor_id,
                    item.order.token_no,
                    item.id,
                    item.utility_id,
                    previous_status,
                    new_status,
                )

            if updated_any and touched_order is not None:
                _sync_buffet_registry_after_lifecycle(touched_order)

            if not updated_any:
                ref = items[0]
                logger.info(
                    "[buffet_update_item_status] No change | vendor_id=%s | token_no=%s | "
                    "item_id=%s | utility_id=%s | status=%s",
                    vendor.vendor_id,
                    ref.order.token_no,
                    ref.id,
                    ref.utility_id,
                    new_status,
                )
                return Response(
                    {
                        "message": f"Item is already {new_status}",
                        "item_id": ref.id,
                        "utility_id": ref.utility_id,
                        "token_no": ref.order.token_no,
                    },
                    status=status.HTTP_200_OK,
                )

        ref = items[0]
        return Response(
            {
                "message": f"Item marked as {new_status} successfully",
                "item_id": ref.id,
                "utility_id": ref.utility_id,
                "token_no": ref.order.token_no,
            },
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.exception("[buffet_update_item_status] Error: %s", e)
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
            
            # Lines in terminal states (incl. operation_closed) do not block whole-booking delivery
            pending_items = order.buffet_items.exclude(
                status__in=['ready', 'cancelled', 'delivered', 'operation_closed']
            ).exists()
            if pending_items:
                logger.warning(f"[mark_booking_delivered] Cannot deliver Order {order.id}: pending items exist.")
                return Response({"error": "Cannot deliver: some items are still pending"}, status=status.HTTP_400_BAD_REQUEST)
            
            if order.status == 'delivered':
                 return Response({"message": "Booking is already delivered"}, status=status.HTTP_200_OK)

            order.status = 'delivered'
            order.updated_by = 'manager'
            order.save(update_fields=['status', 'updated_by'])

            # Phase 7: booking completed → leave Active Order Registry.
            _sync_buffet_registry_after_lifecycle(order)
            
            # Note: No item-level chat message as per requirement
            push_payload = {
                "type": "order_delivered",
                "vendor_id": vendor.vendor_id,
                "token_no": order.token_no,
                "booking_id": order.id,
                "message": "Your order has been delivered. Thank you!",
            }
            if project_name == "dine_flash_buffet":
                push_payload["alias_name"] = _buffet_vendor_chat_alias(vendor)
            send_order_update(vendor, push_payload)
            notify_web_push(order, vendor, push_payload)
                
        return Response({"message": "Booking marked as delivered successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("[mark_booking_delivered] Error: %s", e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
