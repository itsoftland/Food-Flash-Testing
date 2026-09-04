from rest_framework import serializers
from vendors.models import Vendor, Feedback, Order
from django.conf import settings
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger(__name__)
project_name = getattr(settings, "PROJECT_NAME", "food_flash")
class VendorLogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['id', 'name', 'logo','vendor_id','place_id','alias_name']  # 'logo' should be an ImageField

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')

        def append_cache_buster(url, value):
            """
            Dine Flash only: ensure recently updated outlet logos bypass stale browser cache.
            """
            if not url or value is None:
                return url
            parts = urlsplit(url)
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query["v"] = str(value)
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

        try:
            if request and hasattr(instance.logo, 'url'):
                url = request.build_absolute_uri(instance.logo.url)
                # ✅ Force HTTPS only on non-local environments
                if 'localhost' not in url and '127.0.0.1' not in url:
                    url = url.replace("http://", "https://")
                else:
                    url = url

                if project_name in ("dine_flash", "dine_flash_buffet"):
                    updated_ts = int(instance.updated_at.timestamp()) if getattr(instance, "updated_at", None) else None
                    url = append_cache_buster(url, updated_ts)

                data['logo_url'] = url
            else:
                data['logo_url'] = ''
        except Exception as e:
            logger.warning(f"Error building logo URL: {e}")
            data['logo_url'] = ''
        
        data.pop('logo')  # Optional: remove raw logo field
        return data


class VendorAdsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['vendor_id', 'ads', 'name']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')

        # Process JSON string of ads and convert to full URLs
        ad_paths = instance.get_ads_list()
        full_ad_urls = []

        if request:
            for path in ad_paths:
                if not path.startswith("http"):
                    url = request.build_absolute_uri(f"/media/{path}")
                    # ✅ Force HTTPS only on non-local environments
                    if 'localhost' not in url and '127.0.0.1' not in url:
                        full_ad_urls.append(url.replace("http://", "https://"))
                    else:
                        full_ad_urls.append(url)
                else:
                    full_ad_urls.append(path)

        data['ads'] = full_ad_urls
        return data


class VendorMenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['vendor_id', 'menus', 'name']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')

        # Convert menu paths to full URLs
        menu_paths = instance.menus  # assuming this is a JSONField or TextField storing JSON
        if isinstance(menu_paths, str):
            import json
            menu_paths = json.loads(menu_paths)

        full_menu_urls = []
        start_url = getattr(settings, "PROJECT_NAME")
        if request:
            for path in menu_paths:
                if not path.startswith("http"):
                    url = request.build_absolute_uri(f"/{start_url}/media/{path}")
                    # ✅ Force HTTPS only on non-local environments
                    if 'localhost' not in url and '127.0.0.1' not in url:
                        full_menu_urls.append(url.replace("http://", "https://"))
                    else:
                        full_menu_urls.append(url)
                else:
                    full_menu_urls.append(path)

        data['menus'] = full_menu_urls
        return data


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = [
            'id',
            'vendor',
            'feedback_type',
            'category',
            'name',
            'comment',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

from rest_framework import serializers
from django.contrib.auth.models import User
from vendors.models import AdminOutlet

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password']

    def create(self, validated_data):
        is_staff = self.context.get('is_staff', False)  # default False
        user = User(
            username=validated_data['username'],
            is_staff=is_staff,
            is_active=True
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value


# Flavours that enforce alphabetic State/City (letters + spaces only).
# food_flash / airline_flash intentionally excluded — keep legacy behaviour.
_STATE_CITY_STRICT_PROJECTS = frozenset({
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
})
_STATE_CITY_ALPHA_SPACE_RE = re.compile(r"^[A-Za-z]+(?: [A-Za-z]+)*$")

# Flavours that enforce simplified GST Number rules + same-deployment duplicate check.
# food_flash / airline_flash intentionally excluded — keep legacy behaviour.
_GST_STRICT_PROJECTS = frozenset({
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
})
_GST_SIMPLE_RE = re.compile(r"^[A-Za-z0-9]{15}$")
_GST_HAS_LETTER_RE = re.compile(r"[A-Za-z]")
_GST_HAS_DIGIT_RE = re.compile(r"[0-9]")
_GST_FORMAT_ERROR = (
    "GST Number must be exactly 15 characters, contain only letters and digits "
    "(A-Z, a-z, 0-9), include at least one letter and one digit, and must not "
    "contain spaces or special characters."
)
_GST_DUPLICATE_ERROR = "A company with this GST Number already exists."

# Flavours that require Company Name to contain at least one alphabetic character.
# food_flash / airline_flash intentionally excluded — keep legacy behaviour.
_COMPANY_NAME_STRICT_PROJECTS = frozenset({
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
})
_COMPANY_NAME_FORMAT_ERROR = (
    "Company Name cannot be empty and must contain at least one alphabetic character."
)
_COMPANY_NAME_MAX_LENGTH = 255

# Flavours that require Contact Person to be alphabetic characters and spaces only.
# food_flash / airline_flash intentionally excluded — keep legacy behaviour.
_CONTACT_PERSON_STRICT_PROJECTS = frozenset({
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
})
_CONTACT_PERSON_ALPHA_SPACE_RE = re.compile(r"^[A-Za-z]+(?: [A-Za-z]+)*$")
_CONTACT_PERSON_FORMAT_ERROR = (
    "Contact Person must contain alphabetic characters and spaces only."
)
_CONTACT_PERSON_MAX_LENGTH = 255


def _current_project_name():
    return (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()


def _requires_strict_state_city_validation():
    return _current_project_name() in _STATE_CITY_STRICT_PROJECTS


def _requires_strict_gst_validation():
    return _current_project_name() in _GST_STRICT_PROJECTS


def _requires_strict_company_name_validation():
    return _current_project_name() in _COMPANY_NAME_STRICT_PROJECTS


def _requires_strict_contact_person_validation():
    return _current_project_name() in _CONTACT_PERSON_STRICT_PROJECTS


def normalize_and_validate_state_or_city(value, field_label="This field"):
    """
    Trim, collapse internal spaces, require at least one letter, allow A-Z/a-z and
    single spaces between words only. Used only for strict-project flavours.
    """
    if value is None:
        raise serializers.ValidationError(
            f"{field_label} must contain alphabetic characters and spaces only."
        )
    text = str(value).strip()
    text = " ".join(text.split())
    if not text or not _STATE_CITY_ALPHA_SPACE_RE.match(text):
        raise serializers.ValidationError(
            f"{field_label} must contain alphabetic characters and spaces only."
        )
    if len(text) > 100:
        raise serializers.ValidationError(
            f"{field_label} cannot exceed 100 characters."
        )
    return text


def normalize_and_validate_company_name(value):
    """
    Strip leading/trailing whitespace; require non-empty value with at least one
    alphabetic character (Unicode-aware). Numbers and special characters remain
    allowed when letters are also present. No character whitelist.
    """
    if value is None:
        raise serializers.ValidationError(_COMPANY_NAME_FORMAT_ERROR)
    text = str(value).strip()
    if not text or not any(ch.isalpha() for ch in text):
        raise serializers.ValidationError(_COMPANY_NAME_FORMAT_ERROR)
    if len(text) > _COMPANY_NAME_MAX_LENGTH:
        raise serializers.ValidationError(
            f"Company Name cannot exceed {_COMPANY_NAME_MAX_LENGTH} characters."
        )
    return text


def normalize_and_validate_contact_person(value):
    """
    Trim, collapse internal spaces; require A-Z/a-z and single spaces between
    words only. Rejects numbers, special characters, and whitespace-only input.
    Empty/None are not validated here (caller preserves optional semantics).
    """
    text = str(value).strip()
    text = " ".join(text.split())
    if not text or not _CONTACT_PERSON_ALPHA_SPACE_RE.match(text):
        raise serializers.ValidationError(_CONTACT_PERSON_FORMAT_ERROR)
    if len(text) > _CONTACT_PERSON_MAX_LENGTH:
        raise serializers.ValidationError(
            f"Contact Person cannot exceed {_CONTACT_PERSON_MAX_LENGTH} characters."
        )
    return text


def validate_simplified_gst_number(value):
    """
    Simplified GST rules (not full GSTIN): exactly 15 A-Z/a-z/0-9 chars with at
    least one letter and one digit; no spaces or special characters; no silent
    normalization. Empty/None are not validated here (caller preserves optional).
    """
    text = str(value)
    if (
        not _GST_SIMPLE_RE.fullmatch(text)
        or not _GST_HAS_LETTER_RE.search(text)
        or not _GST_HAS_DIGIT_RE.search(text)
    ):
        raise serializers.ValidationError(_GST_FORMAT_ERROR)
    return text


class AdminOutletSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    authentication_status = serializers.CharField(required=False, allow_null=True,default='Pending')

    class Meta:
        model = AdminOutlet
        fields = '__all__'

    def validate_customer_name(self, value):
        if not _requires_strict_company_name_validation():
            return value
        return normalize_and_validate_company_name(value)

    def validate_customer_state(self, value):
        if not _requires_strict_state_city_validation():
            return value
        return normalize_and_validate_state_or_city(value, field_label="State")

    def validate_customer_city(self, value):
        if not _requires_strict_state_city_validation():
            return value
        return normalize_and_validate_state_or_city(value, field_label="City")

    def validate_customer_contact_person(self, value):
        if not _requires_strict_contact_person_validation():
            return value
        # Preserve existing optional semantics: omit / null / "" stay allowed.
        if value is None or value == "":
            return value
        return normalize_and_validate_contact_person(value)

    def validate_gst_number(self, value):
        if not _requires_strict_gst_validation():
            return value
        # Preserve existing optional semantics: omit / null / "" stay allowed.
        if value is None or value == "":
            return value
        text = validate_simplified_gst_number(value)
        # Duplicate check is deployment-scoped (one PROJECT_NAME per DB).
        # Case-insensitive match so duplicates cannot bypass via letter case.
        qs = AdminOutlet.objects.filter(gst_number__iexact=text)
        if self.instance is not None and getattr(self.instance, "pk", None) is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_GST_DUPLICATE_ERROR)
        return text

    def validate(self, attrs):
        if attrs.get('authentication_status') is None:
            attrs['authentication_status'] = 'Pending'
        return attrs

    def create(self, validated_data):
        user_data = validated_data.pop('user')
        user_serializer = UserSerializer(data=user_data, context={'is_staff': True})
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()
        admin_outlet = AdminOutlet.objects.create(user=user, **validated_data)
        return admin_outlet

# serializers.py
from rest_framework import serializers
from vendors.models import WebChatMessage, Vendor, PushSubscription

# class WebChatMessageSerializer(serializers.ModelSerializer):
#     vendor = serializers.CharField(write_only=True)  # accept vendor_id (not PK)
#     browser_id = serializers.CharField(write_only=True)  # accept browser_id instead of full subscription object

#     class Meta:
#         model = WebChatMessage
#         fields = [
#             "id", "browser_id", "vendor", "token_no",
#             "sender", "type", "text", "timestamp",
#             "is_read", "is_send","sequence_code"
#         ]
class WebChatMessageSerializer(serializers.ModelSerializer):
    vendor = serializers.CharField(write_only=True)
    browser_id = serializers.CharField(write_only=True)
    passenger_name = serializers.SerializerMethodField() 

    class Meta:
        model = WebChatMessage
        fields = [
            "id", "browser_id", "vendor", "token_no",
            "sender", "type", "text", "timestamp",
            "is_read", "is_send", "sequence_code",
            "passenger_name","booking_id","booking_no"  
        ]
    # 🧩 Airline Flash special handling
    def get_passenger_name(self, obj):
        """
        Dynamically returns passenger_name for airline_flash only.
        """
        try:
            from django.conf import settings
            project_name = getattr(settings, "PROJECT_NAME", "").lower()
            
            if project_name == "airline_flash" and obj.sequence_code:
                order = Order.objects.filter(
                    sequence_code=obj.sequence_code, vendor=obj.vendor
                ).first()
                if order and hasattr(order, "passenger_name"):
                    return order.passenger_name
        except Exception:
            pass
        return None  # return null if not airline_flash or not found

    def create(self, validated_data):
        vendor_identifier = validated_data.pop("vendor", None)
        browser_id = validated_data.pop("browser_id", None)

        # 🔹 Vendor lookup
        try:
            vendor = Vendor.objects.get(vendor_id=vendor_identifier)
        except Vendor.DoesNotExist:
            raise serializers.ValidationError({
                "vendor": f"Vendor with vendor_id {vendor_identifier} not found"
            })

        # 🔹 Subscription lookup using browser_id
        if not browser_id:
            raise serializers.ValidationError({
                "browser_id": "Browser ID is required to link subscription."
            })

        try:
            subscription = PushSubscription.objects.get(browser_id=browser_id)
        except PushSubscription.DoesNotExist:
            raise serializers.ValidationError({
                "browser_id": f"No subscription found for browser_id {browser_id}"
            })

        # 🧩 Airline Flash special handling
        if project_name == "airline_flash":
            sequence_code = validated_data.get("sequence_code")
            if sequence_code:
                try:
                    order = Order.objects.get(sequence_code=sequence_code, vendor=vendor)
                    validated_data["token_no"] = order.token_no
                    validated_data["sequence_code"] = sequence_code
                except Order.DoesNotExist:
                    validated_data["token_no"] = None
        if project_name == "dine_flash":
            booking_id = validated_data.get("booking_id")
            if booking_id:
                try:
                    booking = Order.objects.get(id=booking_id, vendor=vendor)
                    validated_data["token_no"] = booking.token_no
                    validated_data["booking_no"] = booking.table_booking_no
                    validated_data['booking_id'] = booking_id
                except Order.DoesNotExist:
                    validated_data["token_no"] = None

        if project_name == "dine_flash_buffet":
            booking_id = validated_data.get("booking_id")
            token_no = validated_data.get("token_no")
            if booking_id:
                try:
                    booking = Order.objects.get(id=booking_id, vendor=vendor)
                    validated_data["token_no"] = booking.token_no
                    validated_data["booking_no"] = booking.table_booking_no
                    validated_data["booking_id"] = booking_id
                except Order.DoesNotExist:
                    validated_data["token_no"] = None
            elif token_no is not None:
                try:
                    booking = Order.objects.get(token_no=token_no, vendor=vendor)
                    validated_data["booking_id"] = booking.id
                    validated_data["booking_no"] = booking.table_booking_no
                except Order.DoesNotExist:
                    pass

        # 🔹 Create WebChatMessage
        return WebChatMessage.objects.create(
            vendor=vendor,
            subscription=subscription,
            **validated_data
        )


