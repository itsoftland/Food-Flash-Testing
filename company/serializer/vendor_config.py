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
    mr_number_enabled = serializers.BooleanField(required=False)
    bill_number_enabled = serializers.BooleanField(required=False)
    use_utilities = serializers.BooleanField(required=False)
    qr_expiry_minutes = serializers.IntegerField(required=False, min_value=1, max_value=1440)
    announcement_templates = serializers.JSONField(required=False)
    called_chat_template = serializers.CharField(required=False, allow_blank=True)

    def validate_called_chat_template(self, value):
        from django.conf import settings

        current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        if current_project != "hospital_flash":
            return ""
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        if "{department}" not in text:
            raise serializers.ValidationError(
                "Called chat template must include the {department} placeholder."
            )
        return text

    def validate_announcement_templates(self, value):
        from django.conf import settings
        from vendors.hospital_announcement_templates import normalize_announcement_templates

        current_project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        # Other flavours: ignore silently (view also strips before save).
        if current_project != "hospital_flash":
            return {}
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("announcement_templates must be an object.")
        return normalize_announcement_templates(value)

    # Future fields can be added safely without breaking API
    # auto_delete_hours = serializers.IntegerField(required=False, allow_null=True)
    # timezone = serializers.CharField(required=False)