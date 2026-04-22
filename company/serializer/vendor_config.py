# company/serializers/vendor_config.py

from rest_framework import serializers
from vendors.models import VendorConfig

ALLOWED_DURATIONS = [5, 10, 30, 9999]   # 9999 = infinite until OK pressed
ALLOWED_PATTERNS = [
    "short_buzz",
    "long_buzz",
    "alert_strong",
    "heartbeat",
    "rapid_alert"
]


class VendorVibrationConfigSerializer(serializers.ModelSerializer):

    class Meta:
        model = VendorConfig
        fields = [
            "vibration_enabled",
            "vibration_pattern",
            "vibration_duration"
        ]

    # Duration validation
    def validate_vibration_duration(self, value):
        if value not in ALLOWED_DURATIONS:
            raise serializers.ValidationError(
                "Invalid duration. Allowed values: 5, 10, 30, or 9999 (infinite)."
            )
        return value

    # Pattern validation
    def validate_vibration_pattern(self, value):
        if value not in ALLOWED_PATTERNS:
            raise serializers.ValidationError(
                f"Invalid vibration pattern. Allowed: {ALLOWED_PATTERNS}"
            )
        return value

# class VendorConfigUpdateSerializer(serializers.Serializer):
#     vendor_ids = serializers.ListField(
#         child=serializers.IntegerField(),
#         allow_empty=False
#     )

#     # Optional configuration fields (ONLY those allowed to be updated)
#     phone_number_enabled = serializers.BooleanField(required=False)
#     use_utilities = serializers.BooleanField(required=False)

#     # Future fields can be added safely without breaking API
#     # auto_delete_hours = serializers.IntegerField(required=False, allow_null=True)
#     # timezone = serializers.CharField(required=False)

class VendorConfigUpdateSerializer(serializers.Serializer):
    vendor_id = serializers.IntegerField()

    # Optional configuration fields (ONLY those allowed to be updated)
    phone_number_enabled = serializers.BooleanField(required=False)
    use_utilities = serializers.BooleanField(required=False)
    qr_expiry_minutes = serializers.IntegerField(required=False, min_value=1, max_value=1440)

    # Future fields can be added safely without breaking API
    # auto_delete_hours = serializers.IntegerField(required=False, allow_null=True)
    # timezone = serializers.CharField(required=False)