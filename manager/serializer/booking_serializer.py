from rest_framework import serializers
from django.urls import reverse
from vendors.models import Order, ChatMessage
from django.conf import settings
project_name = getattr(settings, "PROJECT_NAME", "food_flash")


def _dine_flash_seat_display_parts(order):
    raw_seat = order.seat_no
    seat = (
        raw_seat.strip()
        if isinstance(raw_seat, str)
        else (str(raw_seat).strip() if raw_seat is not None else "")
    )
    booking_no = (order.table_booking_no or "").strip() if order.table_booking_no else ""
    if booking_no and seat:
        display = f"{booking_no} [{seat}]"
    elif booking_no:
        display = booking_no
    elif seat:
        display = f"[{seat}]"
    else:
        display = booking_no or None
    return seat, display


def _dine_flash_tracking_base(vendor, request):
    """
    Build the shared prefix of the Dine Flash customer tracking/chat URL.

    All bookings in a manager list belong to the same vendor, so the
    location_id/vendor_id portion is computed once and the per-booking
    booking_no/booking_id are appended later. Returns None when the URL
    cannot be built (e.g. no request available), preserving the legacy
    ``tracking_url: None`` behaviour for callers that opt out.
    """
    if vendor is None or request is None:
        return None

    project = getattr(settings, "PROJECT_NAME", "").lower()
    try:
        tracking_path = reverse("orders:home")
        return request.build_absolute_uri(
            f"{tracking_path}?location_id={vendor.location_id}"
            f"&vendor_id={vendor.vendor_id}&"
        )
    except Exception:
        return request.build_absolute_uri(
            f"/{project}/home/?location_id={vendor.location_id}"
            f"&vendor_id={vendor.vendor_id}&"
        )


def serialize_dine_flash_manager_bookings(booking_list, unread_map, vendor=None, request=None):
    """
    Build manager APK booking rows without DRF (Dine Flash list endpoints only).
    Response shape matches BookingSerializer + dine_flash to_representation extras.

    When both ``vendor`` and ``request`` are supplied, ``tracking_url`` is
    populated with the customer tracking/chat URL for each booking. Callers
    that omit them keep the legacy ``tracking_url: None`` behaviour.
    """
    tracking_base = _dine_flash_tracking_base(vendor, request)
    rows = []
    for order in booking_list:
        utility = order.utility
        _, display = _dine_flash_seat_display_parts(order)
        if tracking_base:
            booking_no = order.table_booking_no or ""
            tracking_url = f"{tracking_base}booking_no={booking_no}&booking_id={order.id}"
        else:
            tracking_url = None
        rows.append(
            {
                "id": order.id,
                "table_booking_no": order.table_booking_no,
                "customer_name": order.customer_name,
                "phone_number": order.phone_number,
                "no_of_packs": order.no_of_packs,
                "remarks": order.remarks,
                "status": order.status,
                "booked_time": order.created_at,
                "new_notifications": unread_map.get(order.id, 0),
                "utility_name": utility.display_name if utility else None,
                "tracking_url": tracking_url,
                "table_no": order.seat_no,
                "seat_no": order.seat_no,
                "table_booking_no_display": display,
                "call_count": getattr(order, "call_count", 0) or 0,
            }
        )
    return rows


class BookingSerializer(serializers.ModelSerializer):
    booked_time = serializers.DateTimeField(source="created_at", read_only=True)
    new_notifications = serializers.SerializerMethodField()
    utility_name = serializers.SerializerMethodField()

    tracking_url = serializers.SerializerMethodField()

    def _manager_list_mode(self):
        """Manager APK list endpoints omit tracking URLs (large lists, unused in app)."""
        return bool(self.context.get("manager_list"))

    class Meta:
        model = Order
        fields = [
            "id",
            "table_booking_no",
            "customer_name",
            "phone_number",
            "no_of_packs",
            "remarks",
            "status",
            "booked_time",
            "new_notifications",
            "utility_name",
            "tracking_url",   # ➜ Added here
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if getattr(settings, "PROJECT_NAME", "").lower() == "dine_flash":
            data["table_no"] = instance.seat_no
            data["seat_no"] = instance.seat_no
            _, data["table_booking_no_display"] = _dine_flash_seat_display_parts(instance)
        return data

    def get_utility_name(self, obj):
        return obj.utility.display_name if obj.utility else None

    def get_tracking_url(self, obj):
        if self._manager_list_mode():
            return None

        request = self.context.get("request")
        if not request:
            return None

        vendor = obj.vendor
        cache_key = "_manager_tracking_base"
        base = self.context.get(cache_key)
        if base is None:
            project_name = getattr(settings, "PROJECT_NAME", "").lower()
            try:
                tracking_path = reverse("orders:home")
                base = request.build_absolute_uri(
                    f"{tracking_path}?location_id={vendor.location_id}"
                    f"&vendor_id={vendor.vendor_id}&"
                )
            except Exception:
                base = request.build_absolute_uri(
                    f"/{project_name}/home/?location_id={vendor.location_id}"
                    f"&vendor_id={vendor.vendor_id}&"
                )
            self.context[cache_key] = base

        booking_no = obj.table_booking_no or ""
        return f"{base}booking_no={booking_no}&booking_id={obj.id}"
    
    def get_new_notifications(self, obj):
        unread_map = self.context.get("unread_notifications_map")
        if unread_map is not None:
            return unread_map.get(obj.id, 0)

        return ChatMessage.objects.filter(
            vendor=obj.vendor,
            booking_no=obj.table_booking_no,
            created_date=obj.created_at.date(),
            sender='user',
            is_read=False
        ).count()
