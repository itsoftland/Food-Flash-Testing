from rest_framework import serializers
from django.urls import reverse
from vendors.models import Order
from django.conf import settings


class BookingSerializer(serializers.ModelSerializer):
    booked_time = serializers.DateTimeField(source="created_at", read_only=True)
    new_notifications = serializers.IntegerField(default=0, read_only=True)
    utility_id = serializers.IntegerField(source="utility.id", read_only=True)

    tracking_url = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "table_booking_no",
            "token_no",
            "customer_name",
            "phone_number",
            "no_of_packs",
            "remarks",
            "status",
            "booked_time",
            "new_notifications",
            "utility_id",
            "tracking_url",   # ➜ Added here
        ]
        read_only_fields = fields

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
