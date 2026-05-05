from rest_framework import serializers
from vendors.models import Order, UserProfile, ChatMessage
from django.conf import settings
project_name = getattr(settings, "PROJECT_NAME", "food_flash")

class OrdersSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    manager_id = serializers.PrimaryKeyRelatedField(
        source='user_profile',
        queryset=UserProfile.objects.all(),
        required=False,
    )
    manager_name = serializers.CharField(source='user_profile.name', read_only=True)
    new_notifications = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = '__all__'
        extra_fields = ['vendor_name', 'manager_id', 'manager_name', 'new_notifications']

    def get_fields(self):
        fields = super().get_fields()

        # -----------------------------
        # ✔ Hide Airline fields
        # -----------------------------
        airline_fields = [
            "sequence_code",
            "flight_no",
            "pnr_no",
            "seat_no",
            "zone",
            "passenger_name"
        ]

        is_airline = project_name == "airline_flash"
        if not is_airline:
            for f in airline_fields:
                fields.pop(f, None)

        # -----------------------------
        # ✔ Hide Dine Flash fields
        # -----------------------------
        dine_fields = [
            "customer_name",
            "no_of_packs",
            "remarks",
            "table_booking_no",
            "utility",
            "current_utility"
        ]

        is_dine = project_name in ["dine_flash", "dine_flash_buffet"]
        if not is_dine:
            for f in dine_fields:
                fields.pop(f, None)

        return fields
    def get_new_notifications(self, obj):
        unread_by_booking = self.context.get("unread_notifications_map")
        if unread_by_booking is not None:
            return unread_by_booking.get(obj.id, 0)

        unread_by_sequence = self.context.get("unread_notifications_map_by_sequence")
        if unread_by_sequence is not None:
            return unread_by_sequence.get(obj.sequence_code, 0)

        if project_name == "airline_flash":
            return ChatMessage.objects.filter(
                vendor=obj.vendor,
                sequence_code = obj.sequence_code,
                sender='user',
                is_read=False
            ).count()
        return ChatMessage.objects.filter(
            vendor=obj.vendor,
            token_no=obj.token_no,
            created_date=obj.created_at.date(),
            sender='user',
            is_read=False
        ).count()

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        rep['name'] = instance.vendor.name
        rep.pop('user_profile', None)
        
        return rep
