"""
Flavour-scoped AdminOutlet GST Number validation.

Simplified rules (not full GSTIN) apply only to:
  dine_flash, dine_flash_buffet, hospital_flash

Legacy unrestricted behaviour must remain for:
  food_flash, airline_flash

Duplicate GST checks are application-level and deployment-scoped
(one PROJECT_NAME per database). No model unique=True / DB constraint.
"""
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ValidationError

from orders.serializers import (
    AdminOutletSerializer,
    validate_simplified_gst_number,
    _GST_FORMAT_ERROR,
    _GST_DUPLICATE_ERROR,
)
from vendors.models import AdminOutlet

VALID_GST = "22AAAAA0000A1Z5"
VALID_GST_ALT = "ABCDEFGHIJKLM1N"
VALID_GST_MIXED = "A12345678901234"

TARGET_FLAVOURS = ("dine_flash", "dine_flash_buffet", "hospital_flash")


class ValidateSimplifiedGstHelperTests(SimpleTestCase):
    def test_valid_examples(self):
        for value in (VALID_GST, VALID_GST_ALT, VALID_GST_MIXED, "abcde1234567890"):
            with self.subTest(value=value):
                self.assertEqual(validate_simplified_gst_number(value), value)

    def test_rejects_invalid_examples(self):
        invalid = [
            "123456789012345",  # digits only
            "ABCDEFGHIJKLMNO",  # letters only
            "12345ABCDE",  # too short
            "22AAAAA0000A1Z56",  # too long
            " 22AAAAA0000A1Z5",  # leading space
            "22AAAAA0000A1Z5 ",  # trailing space
            "22AAAAA0000A Z5",  # internal space
            "22AAAAA0000A1@5",  # special
            "22AAAAA0000A1-Z5",  # special
            "22AAAAA0000A1.Z5",  # special
            "22AAAAA0000A1@$5",  # multiple specials
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as ctx:
                    validate_simplified_gst_number(value)
                self.assertIn(_GST_FORMAT_ERROR, str(ctx.exception.detail))


class _GstSerializerMixin:
    def _ser(self, instance=None):
        return AdminOutletSerializer(instance=instance)

    def assert_gst_accepted(self, raw, expected=None, instance=None):
        result = self._ser(instance=instance).validate_gst_number(raw)
        self.assertEqual(result, raw if expected is None else expected)

    def assert_gst_rejected(self, raw, instance=None, message_fragment=None):
        with self.assertRaises(ValidationError) as ctx:
            self._ser(instance=instance).validate_gst_number(raw)
        if message_fragment:
            self.assertIn(message_fragment, str(ctx.exception.detail))


def _create_outlet(username, gst_number=None, **extra):
    user = User.objects.create_user(username=username, password="pass12345")
    return AdminOutlet.objects.create(
        user=user,
        customer_name=extra.get("customer_name", username),
        customer_email=extra.get("customer_email", f"{username}@example.com"),
        gst_number=gst_number,
    )


class _StrictGstFormatTests(_GstSerializerMixin):
    """Shared format / requiredness cases for each target flavour."""

    def test_valid_gst_accepted(self):
        self.assert_gst_accepted(VALID_GST)
        self.assert_gst_accepted(VALID_GST_ALT)
        self.assert_gst_accepted(VALID_GST_MIXED)

    def test_rejects_wrong_length(self):
        self.assert_gst_rejected("12345ABCDE", message_fragment=_GST_FORMAT_ERROR)
        self.assert_gst_rejected("22AAAAA0000A1Z56", message_fragment=_GST_FORMAT_ERROR)

    def test_rejects_digits_only(self):
        self.assert_gst_rejected("123456789012345", message_fragment=_GST_FORMAT_ERROR)

    def test_rejects_letters_only(self):
        self.assert_gst_rejected("ABCDEFGHIJKLMNO", message_fragment=_GST_FORMAT_ERROR)

    def test_rejects_spaces(self):
        self.assert_gst_rejected(" 22AAAAA0000A1Z5", message_fragment=_GST_FORMAT_ERROR)
        self.assert_gst_rejected("22AAAAA0000A1Z5 ", message_fragment=_GST_FORMAT_ERROR)
        self.assert_gst_rejected("22AAAAA0000A Z5", message_fragment=_GST_FORMAT_ERROR)

    def test_rejects_special_characters(self):
        self.assert_gst_rejected("22AAAAA0000A1@5", message_fragment=_GST_FORMAT_ERROR)
        self.assert_gst_rejected("22AAAAA0000A1-Z5", message_fragment=_GST_FORMAT_ERROR)
        self.assert_gst_rejected("22AAAAA0000A1.Z5", message_fragment=_GST_FORMAT_ERROR)
        self.assert_gst_rejected("22AAAAA0000A1@$5", message_fragment=_GST_FORMAT_ERROR)

    def test_empty_and_none_remain_optional_on_serializer(self):
        """Backend gst_number stays blank/null-optional; empty is not format-validated."""
        self.assert_gst_accepted(None)
        self.assert_gst_accepted("")

    def test_whitespace_only_rejected_when_supplied(self):
        self.assert_gst_rejected("               ", message_fragment=_GST_FORMAT_ERROR)
        self.assert_gst_rejected("   ", message_fragment=_GST_FORMAT_ERROR)

    def test_does_not_normalize_value(self):
        # Lowercase valid GST must be returned unchanged (no forced uppercasing).
        raw = "a12345678901234"
        self.assert_gst_accepted(raw)


class _StrictGstDuplicateTests(_GstSerializerMixin, TestCase):
    """Duplicate GST tests (DB) for a single target flavour class."""

    def test_same_flavour_duplicate_rejected(self):
        _create_outlet("co1", gst_number=VALID_GST)
        self.assert_gst_rejected(VALID_GST, message_fragment=_GST_DUPLICATE_ERROR)
        # Case-insensitive duplicate bypass must fail
        self.assert_gst_rejected(VALID_GST.lower(), message_fragment=_GST_DUPLICATE_ERROR)

    def test_update_retaining_own_gst_allowed(self):
        outlet = _create_outlet("co_keep", gst_number=VALID_GST)
        self.assert_gst_accepted(VALID_GST, instance=outlet)

    def test_update_other_to_existing_gst_rejected(self):
        _create_outlet("co_owner", gst_number=VALID_GST)
        other = _create_outlet("co_other", gst_number=VALID_GST_ALT)
        self.assert_gst_rejected(
            VALID_GST, instance=other, message_fragment=_GST_DUPLICATE_ERROR
        )

    def test_partial_update_omitting_gst_allowed(self):
        """Missing gst_number on partial update must not fail for GST absence."""
        outlet = _create_outlet("co_partial", gst_number=VALID_GST)
        ser = AdminOutletSerializer(
            outlet,
            data={"customer_name": "Updated Name"},
            partial=True,
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        self.assertEqual(ser.validated_data["customer_name"], "Updated Name")
        self.assertNotIn("gst_number", ser.validated_data)


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashGstFormatTests(_StrictGstFormatTests, TestCase):
    pass


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetGstFormatTests(_StrictGstFormatTests, TestCase):
    pass


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalFlashGstFormatTests(_StrictGstFormatTests, TestCase):
    pass


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashGstDuplicateTests(_StrictGstDuplicateTests):
    pass


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetGstDuplicateTests(_StrictGstDuplicateTests):
    pass


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalFlashGstDuplicateTests(_StrictGstDuplicateTests):
    pass


class CrossFlavourGstDuplicateTests(TestCase):
    """
    Target flavours are separate deployments (separate DBs). Uniqueness is
    enforced only while PROJECT_NAME is a target flavour, against that
    deployment's AdminOutlet rows. Same GST may exist in another flavour's
    deployment because those databases are separate — no global unique=True.
    """

    def test_model_field_is_not_globally_unique(self):
        field = AdminOutlet._meta.get_field("gst_number")
        self.assertFalse(field.unique)

    def test_orm_allows_same_gst_on_multiple_rows(self):
        """DB has no unique constraint; separate deployments can store the same GST."""
        _create_outlet("orm1", gst_number=VALID_GST)
        _create_outlet("orm2", gst_number=VALID_GST)
        self.assertEqual(
            AdminOutlet.objects.filter(gst_number__iexact=VALID_GST).count(), 2
        )

    @override_settings(PROJECT_NAME="food_flash")
    def test_food_flash_allows_duplicate_of_existing_gst(self):
        _create_outlet("ff_existing", gst_number=VALID_GST)
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_gst_number(VALID_GST), VALID_GST)

    @override_settings(PROJECT_NAME="airline_flash")
    def test_airline_flash_allows_duplicate_of_existing_gst(self):
        _create_outlet("af_existing", gst_number=VALID_GST)
        ser = AdminOutletSerializer()
        self.assertEqual(ser.validate_gst_number(VALID_GST), VALID_GST)

    def test_each_target_flavour_enforces_duplicate_in_its_context(self):
        _create_outlet("shared_gst_owner", gst_number=VALID_GST)
        for flavour in TARGET_FLAVOURS:
            with self.subTest(flavour=flavour):
                with override_settings(PROJECT_NAME=flavour):
                    with self.assertRaises(ValidationError) as ctx:
                        AdminOutletSerializer().validate_gst_number(VALID_GST)
                    self.assertIn(_GST_DUPLICATE_ERROR, str(ctx.exception.detail))


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashGstLegacyBehaviourTests(_GstSerializerMixin, SimpleTestCase):
    def test_legacy_values_still_accepted_unchanged(self):
        for value in (
            "123456789012345",
            "ABCDEFGHIJKLMNO",
            "short",
            " 22AAAAA0000A1Z5",
            "22AAAAA0000A1@5",
            "22AAAAA0000A1-Z5",
            "   ",
            VALID_GST,
            None,
            "",
        ):
            with self.subTest(value=value):
                self.assert_gst_accepted(value)

    def test_does_not_normalize(self):
        raw = "  abcd  "
        self.assert_gst_accepted(raw)


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashGstLegacyBehaviourTests(_GstSerializerMixin, SimpleTestCase):
    def test_legacy_values_still_accepted_unchanged(self):
        for value in (
            "123456789012345",
            "ABCDEFGHIJKLMNO",
            "short",
            " 22AAAAA0000A1Z5",
            "22AAAAA0000A1@5",
            "22AAAAA0000A1-Z5",
            "   ",
            VALID_GST,
            None,
            "",
        ):
            with self.subTest(value=value):
                self.assert_gst_accepted(value)

    def test_does_not_normalize(self):
        raw = "tax-id-123"
        self.assert_gst_accepted(raw)
