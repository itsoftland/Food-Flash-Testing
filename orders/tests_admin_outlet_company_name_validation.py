"""
Flavour-scoped AdminOutlet Company Name validation.

Strict rule (non-empty + at least one alphabetic character) applies only to:
  dine_flash, dine_flash_buffet, hospital_flash

Legacy unrestricted behaviour must remain for:
  food_flash, airline_flash
"""
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from companyadmin.views import register_company
from orders.serializers import (
    AdminOutletSerializer,
    normalize_and_validate_company_name,
    normalize_and_validate_state_or_city,
    validate_simplified_gst_number,
    _COMPANY_NAME_FORMAT_ERROR,
    _COMPANY_NAME_MAX_LENGTH,
    _GST_FORMAT_ERROR,
)
from vendors.models import AdminOutlet

TARGET_FLAVOURS = ("dine_flash", "dine_flash_buffet", "hospital_flash")
VALID_GST = "22AAAAA0000A1Z5"

VALID_NAMES = (
    "ABC",
    "ABC Restaurant",
    "ABC123",
    "123ABC",
    "ABC-123",
    "ABC@123",
    "ABC & Restaurant",
    "കെഎഫ്‌സി",
)

INVALID_NAMES = (
    "",
    "   ",
    "\t",
    "12345",
    "123456789",
    "@#$%",
    "---",
    "___",
    "...",
    "!!!",
)


class NormalizeCompanyNameHelperTests(SimpleTestCase):
    def test_valid_examples(self):
        for value in VALID_NAMES:
            with self.subTest(value=value):
                self.assertEqual(normalize_and_validate_company_name(value), value)

    def test_strips_whitespace(self):
        self.assertEqual(normalize_and_validate_company_name("  ABC  "), "ABC")
        self.assertEqual(
            normalize_and_validate_company_name("  ABC Restaurant  "),
            "ABC Restaurant",
        )

    def test_rejects_invalid_examples(self):
        for value in INVALID_NAMES + (None,):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as ctx:
                    normalize_and_validate_company_name(value)
                self.assertIn(_COMPANY_NAME_FORMAT_ERROR, str(ctx.exception.detail))

    def test_max_length_boundary(self):
        exactly_255 = "A" * _COMPANY_NAME_MAX_LENGTH
        self.assertEqual(normalize_and_validate_company_name(exactly_255), exactly_255)
        with self.assertRaises(ValidationError):
            normalize_and_validate_company_name("A" * (_COMPANY_NAME_MAX_LENGTH + 1))


class _CompanyNameSerializerMixin:
    def _ser(self, instance=None):
        return AdminOutletSerializer(instance=instance)

    def assert_name_accepted(self, raw, expected=None):
        result = self._ser().validate_customer_name(raw)
        self.assertEqual(result, raw if expected is None else expected)

    def assert_name_rejected(self, raw, message_fragment=None):
        with self.assertRaises(ValidationError) as ctx:
            self._ser().validate_customer_name(raw)
        if message_fragment:
            self.assertIn(message_fragment, str(ctx.exception.detail))


class _StrictCompanyNameTests(_CompanyNameSerializerMixin):
    """Shared Company Name cases for each target flavour."""

    def test_empty_rejected(self):
        self.assert_name_rejected("", message_fragment=_COMPANY_NAME_FORMAT_ERROR)
        self.assert_name_rejected(None, message_fragment=_COMPANY_NAME_FORMAT_ERROR)

    def test_whitespace_only_rejected(self):
        self.assert_name_rejected("   ", message_fragment=_COMPANY_NAME_FORMAT_ERROR)
        self.assert_name_rejected("\t\n", message_fragment=_COMPANY_NAME_FORMAT_ERROR)

    def test_numeric_only_rejected(self):
        self.assert_name_rejected("12345", message_fragment=_COMPANY_NAME_FORMAT_ERROR)
        self.assert_name_rejected("123456789", message_fragment=_COMPANY_NAME_FORMAT_ERROR)

    def test_special_character_only_rejected(self):
        for value in ("@#$%", "---", "___", "...", "!!!"):
            with self.subTest(value=value):
                self.assert_name_rejected(
                    value, message_fragment=_COMPANY_NAME_FORMAT_ERROR
                )

    def test_alphabetic_only_accepted(self):
        self.assert_name_accepted("ABC", "ABC")

    def test_alphabetic_plus_numeric_accepted(self):
        self.assert_name_accepted("ABC123", "ABC123")
        self.assert_name_accepted("123ABC", "123ABC")

    def test_alphabetic_plus_special_accepted(self):
        self.assert_name_accepted("ABC-123", "ABC-123")
        self.assert_name_accepted("ABC@123", "ABC@123")
        self.assert_name_accepted("ABC & Restaurant", "ABC & Restaurant")

    def test_mixed_letters_numbers_special_accepted(self):
        self.assert_name_accepted("ABC@123", "ABC@123")
        self.assert_name_accepted("ABC Restaurant", "ABC Restaurant")

    def test_unicode_alphabetic_accepted(self):
        self.assert_name_accepted("കെഎഫ്‌സി", "കെഎഫ്‌സി")

    def test_strips_leading_trailing_whitespace(self):
        self.assert_name_accepted("  ABC  ", "ABC")

    def test_255_character_valid_name_accepted(self):
        name = "A" * _COMPANY_NAME_MAX_LENGTH
        self.assert_name_accepted(name, name)

    def test_over_255_characters_rejected(self):
        name = "A" * (_COMPANY_NAME_MAX_LENGTH + 1)
        self.assert_name_rejected(name)


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashCompanyNameValidationTests(_StrictCompanyNameTests, SimpleTestCase):
    pass


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetCompanyNameValidationTests(_StrictCompanyNameTests, SimpleTestCase):
    pass


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalFlashCompanyNameValidationTests(_StrictCompanyNameTests, SimpleTestCase):
    pass


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashCompanyNameLegacyBehaviourTests(_CompanyNameSerializerMixin, SimpleTestCase):
    """food_flash must retain unrestricted Company Name behaviour."""

    def test_legacy_values_still_accepted_unchanged(self):
        for value in INVALID_NAMES + VALID_NAMES:
            with self.subTest(value=value):
                self.assert_name_accepted(value)

    def test_does_not_trim_or_normalize(self):
        raw = "  ABC  "
        self.assert_name_accepted(raw)

    def test_none_still_accepted(self):
        self.assert_name_accepted(None)


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashCompanyNameLegacyBehaviourTests(
    _CompanyNameSerializerMixin, SimpleTestCase
):
    """airline_flash must retain unrestricted Company Name behaviour."""

    def test_legacy_values_still_accepted_unchanged(self):
        for value in INVALID_NAMES + VALID_NAMES:
            with self.subTest(value=value):
                self.assert_name_accepted(value)

    def test_does_not_trim_or_normalize(self):
        raw = "  ABC  "
        self.assert_name_accepted(raw)

    def test_none_still_accepted(self):
        self.assert_name_accepted(None)


class CompanyNameMaxLengthModelFieldTests(SimpleTestCase):
    """Existing model max_length=255 must remain in place."""

    def test_model_field_max_length_is_255(self):
        field = AdminOutlet._meta.get_field("customer_name")
        self.assertEqual(field.max_length, 255)


class ExistingStateCityGstRegressionTests(SimpleTestCase):
    """Company Name changes must not alter State/City/GST helpers."""

    def test_state_city_helper_unchanged(self):
        self.assertEqual(normalize_and_validate_state_or_city("Kerala"), "Kerala")
        with self.assertRaises(ValidationError):
            normalize_and_validate_state_or_city("123")

    def test_gst_helper_unchanged(self):
        self.assertEqual(validate_simplified_gst_number(VALID_GST), VALID_GST)
        with self.assertRaises(ValidationError) as ctx:
            validate_simplified_gst_number("123456789012345")
        self.assertIn(_GST_FORMAT_ERROR, str(ctx.exception.detail))


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashStateCityStillStrictAfterCompanyNameChangeTests(SimpleTestCase):
    def test_state_city_still_enforced(self):
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_customer_state("Kerala"), "Kerala")
        with self.assertRaises(ValidationError):
            ser.validate_customer_state("123")
        with self.assertRaises(ValidationError):
            ser.validate_customer_city("@@@")


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashGstStillStrictAfterCompanyNameChangeTests(TestCase):
    def test_gst_still_enforced(self):
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_gst_number(VALID_GST), VALID_GST)
        with self.assertRaises(ValidationError):
            ser.validate_gst_number("123456789012345")


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashStateCityGstLegacyUnchangedTests(SimpleTestCase):
    def test_state_city_gst_remain_unrestricted(self):
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_customer_state("123"), "123")
        self.assertEqual(ser.validate_customer_city("@@@"), "@@@")
        self.assertEqual(ser.validate_gst_number("short"), "short")


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashStateCityGstLegacyUnchangedTests(SimpleTestCase):
    def test_state_city_gst_remain_unrestricted(self):
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_customer_state("123"), "123")
        self.assertEqual(ser.validate_customer_city("@@@"), "@@@")
        self.assertEqual(ser.validate_gst_number("short"), "short")


def _create_outlet(username, **extra):
    user = User.objects.create_user(username=username, password="pass12345")
    return AdminOutlet.objects.create(
        user=user,
        customer_name=extra.get("customer_name", username),
        customer_email=extra.get("customer_email", f"{username}@example.com"),
        gst_number=extra.get("gst_number"),
    )


class DuplicateCompanyNameEmailRegressionTests(TestCase):
    """Existing duplicate name+email check in register_company must remain."""

    def setUp(self):
        self.factory = APIRequestFactory()
        _create_outlet(
            "dup_user",
            customer_name="Acme Corp",
            customer_email="acme@example.com",
        )

    def _post(self, payload):
        request = self.factory.post(
            "/companyadmin/api/register-company/",
            payload,
            format="json",
        )
        return register_company(request)

    def test_duplicate_name_and_email_rejected(self):
        response = self._post(
            {
                "CustomerName": "Acme Corp",
                "CustomerEmail": "acme@example.com",
                "CustomerUsername": "new_user_dup",
                "CustomerPassword": "pass12345",
                "PhoneNumber": "9876543210",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", str(response.data.get("error", "")))


@override_settings(PROJECT_NAME="dine_flash")
class RegisterCompanyApiCompanyNameEnforcementTests(TestCase):
    """Backend must reject invalid Company Names even via direct API."""

    def setUp(self):
        self.factory = APIRequestFactory()

    def _post(self, customer_name):
        request = self.factory.post(
            "/companyadmin/api/register-company/",
            {
                "CustomerName": customer_name,
                "CustomerEmail": "newco@example.com",
                "CustomerUsername": "api_name_user",
                "CustomerPassword": "pass12345",
                "PhoneNumber": "9876543210",
                "CustomerState": "Kerala",
                "CustomerCity": "Kochi",
                "GSTNumber": VALID_GST,
            },
            format="json",
        )
        return register_company(request)

    def test_numeric_only_rejected_via_api(self):
        response = self._post("12345")
        self.assertEqual(response.status_code, 400)
        self.assertIn("customer_name", response.data)

    def test_special_only_rejected_via_api(self):
        response = self._post("@@@")
        self.assertEqual(response.status_code, 400)
        self.assertIn("customer_name", response.data)

    def test_valid_name_passes_company_name_validation(self):
        """Valid name must not fail on customer_name (may fail on other fields)."""
        response = self._post("ABC Restaurant")
        if response.status_code == 400:
            self.assertNotIn("customer_name", response.data)
        else:
            self.assertEqual(response.status_code, 201)


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashRegisterCompanyApiLegacyNameTests(TestCase):
    """food_flash must still accept numeric-only Company Name at serializer layer."""

    def test_numeric_only_accepted_by_serializer(self):
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_customer_name("12345"), "12345")


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashRegisterCompanyApiLegacyNameTests(TestCase):
    """airline_flash must still accept numeric-only Company Name at serializer layer."""

    def test_numeric_only_accepted_by_serializer(self):
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_customer_name("12345"), "12345")
