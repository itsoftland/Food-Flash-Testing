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
