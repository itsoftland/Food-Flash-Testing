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
        return ChatMessage.objects.filter(
            vendor=obj.vendor,
            booking_no=obj.table_booking_no,
            created_date=obj.created_at.date(),
            sender='user',
            is_read=False
        ).count()
