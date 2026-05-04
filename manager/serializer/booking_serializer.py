from rest_framework import serializers
from django.urls import reverse
from vendors.models import Order, ChatMessage
from django.conf import settings
project_name = getattr(settings, "PROJECT_NAME", "food_flash")


class BookingSerializer(serializers.ModelSerializer):
    booked_time = serializers.DateTimeField(source="created_at", read_only=True)
    new_notifications = serializers.SerializerMethodField()
    utility_name = serializers.SerializerMethodField()

    tracking_url = serializers.SerializerMethodField()

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
            raw_seat = instance.seat_no
            seat = (
                raw_seat.strip()
                if isinstance(raw_seat, str)
                else (str(raw_seat).strip() if raw_seat is not None else "")
            )
            data["table_no"] = instance.seat_no
            # Explicit keys for TV / clients that expect seat_no or a single display string.
            data["seat_no"] = instance.seat_no
            booking_no = (instance.table_booking_no or "").strip() if instance.table_booking_no else ""
            if booking_no and seat:
                data["table_booking_no_display"] = f"{booking_no} [{seat}]"
            elif booking_no:
                data["table_booking_no_display"] = booking_no
            elif seat:
                data["table_booking_no_display"] = f"[{seat}]"
            else:
                data["table_booking_no_display"] = booking_no or None
            # Show assigned table in the booking ref (URLs/notifications still use raw table_booking_no on the model).
            if seat:
                data["table_booking_no"] = f"{booking_no}[{seat}]" if booking_no else f"[{seat}]"
        return data

    def get_utility_name(self, obj):
        return obj.utility.display_name if obj.utility else None

    def get_tracking_url(self, obj):
        request = self.context.get("request")
        if not request:
            return None

        vendor = obj.vendor
        project_name = getattr(settings, "PROJECT_NAME", "").lower()

        try:
            tracking_path = reverse("orders:home")
            url = request.build_absolute_uri(
                f"{tracking_path}?location_id={vendor.location_id}"
                f"&vendor_id={vendor.vendor_id}&booking_no={obj.table_booking_no}"
                f"&booking_id={obj.id}"
            )
        except Exception:
            url = request.build_absolute_uri(
                f"/{project_name}/home/?location_id={vendor.location_id}"
                f"&vendor_id={vendor.vendor_id}&booking_no={obj.table_booking_no}"
                f"&booking_id={obj.id}"
            )

        return url
    
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
