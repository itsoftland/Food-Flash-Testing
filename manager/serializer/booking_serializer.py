# managers/serializers/booking_serializer.py

from rest_framework import serializers
from vendors.models import Order

class BookingSerializer(serializers.ModelSerializer):
    booked_time = serializers.DateTimeField(source="created_at", read_only=True)
    new_notifications = serializers.IntegerField(default=0, read_only=True)

    # Extract only FK ID
    utility_id = serializers.IntegerField(source="utility.id", read_only=True)

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
        ]
        read_only_fields = fields
