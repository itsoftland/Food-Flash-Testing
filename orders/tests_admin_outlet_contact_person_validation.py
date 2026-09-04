"""
Flavour-scoped AdminOutlet Contact Person validation.

Strict rule (alphabetic characters and spaces only) applies only to:
  dine_flash, dine_flash_buffet, hospital_flash

Legacy unrestricted behaviour must remain for:
  food_flash, airline_flash
"""
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ValidationError

from orders.serializers import (
    AdminOutletSerializer,
    normalize_and_validate_contact_person,
    _CONTACT_PERSON_FORMAT_ERROR,
    _CONTACT_PERSON_MAX_LENGTH,
)
from vendors.models import AdminOutlet

TARGET_FLAVOURS = ("dine_flash", "dine_flash_buffet", "hospital_flash")

VALID_NAMES = (
    "John",
    "John Doe",
    "Mary Ann",
)

INVALID_NAMES = (
    "John123",
    "John@Doe",
    "John-Doe",
    "John_Doe",
    "12345",
    "@#$%",
    "   ",
    "\t",
)


class NormalizeContactPersonHelperTests(SimpleTestCase):
    def test_valid_examples(self):
        for value in VALID_NAMES:
            with self.subTest(value=value):
                self.assertEqual(normalize_and_validate_contact_person(value), value)

    def test_strips_and_collapses_whitespace(self):
        self.assertEqual(normalize_and_validate_contact_person("  John  "), "John")
        self.assertEqual(
            normalize_and_validate_contact_person("  John   Doe  "),
            "John Doe",
        )

    def test_rejects_invalid_examples(self):
        for value in INVALID_NAMES:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as ctx:
                    normalize_and_validate_contact_person(value)
                self.assertIn(_CONTACT_PERSON_FORMAT_ERROR, str(ctx.exception.detail))

    def test_max_length_boundary(self):
        exactly_255 = "A" * _CONTACT_PERSON_MAX_LENGTH
        self.assertEqual(
            normalize_and_validate_contact_person(exactly_255), exactly_255
        )
        with self.assertRaises(ValidationError):
            normalize_and_validate_contact_person(
                "A" * (_CONTACT_PERSON_MAX_LENGTH + 1)
            )


class _ContactPersonSerializerMixin:
    def _ser(self, instance=None):
        return AdminOutletSerializer(instance=instance)

    def assert_contact_accepted(self, raw, expected=None, instance=None):
        result = self._ser(instance=instance).validate_customer_contact_person(raw)
        self.assertEqual(result, raw if expected is None else expected)

    def assert_contact_rejected(self, raw, message_fragment=None, instance=None):
        with self.assertRaises(ValidationError) as ctx:
            self._ser(instance=instance).validate_customer_contact_person(raw)
        if message_fragment:
            self.assertIn(message_fragment, str(ctx.exception.detail))


class _StrictContactPersonTests(_ContactPersonSerializerMixin):
    """Shared Contact Person cases for each target flavour."""

    def test_valid_alphabetic_name_accepted(self):
        self.assert_contact_accepted("John", "John")

    def test_valid_multi_word_name_accepted(self):
        self.assert_contact_accepted("John Doe", "John Doe")
        self.assert_contact_accepted("Mary Ann", "Mary Ann")

    def test_numeric_value_rejected(self):
        self.assert_contact_rejected(
            "12345", message_fragment=_CONTACT_PERSON_FORMAT_ERROR
        )

    def test_name_containing_numbers_rejected(self):
        self.assert_contact_rejected(
            "John123", message_fragment=_CONTACT_PERSON_FORMAT_ERROR
        )

    def test_special_character_rejected(self):
        self.assert_contact_rejected(
            "@#$%", message_fragment=_CONTACT_PERSON_FORMAT_ERROR
        )

    def test_name_containing_special_characters_rejected(self):
        for value in ("John@Doe", "John-Doe", "John_Doe"):
            with self.subTest(value=value):
                self.assert_contact_rejected(
                    value, message_fragment=_CONTACT_PERSON_FORMAT_ERROR
                )

    def test_whitespace_only_rejected(self):
        self.assert_contact_rejected(
            "   ", message_fragment=_CONTACT_PERSON_FORMAT_ERROR
        )
        self.assert_contact_rejected(
            "\t\n", message_fragment=_CONTACT_PERSON_FORMAT_ERROR
        )

    def test_empty_and_none_remain_optional_on_serializer(self):
        """Backend customer_contact_person stays blank/null-optional."""
        self.assert_contact_accepted(None)
        self.assert_contact_accepted("")

    def test_255_character_valid_name_accepted(self):
        name = "A" * _CONTACT_PERSON_MAX_LENGTH
        self.assert_contact_accepted(name, name)

    def test_over_255_characters_rejected(self):
        name = "A" * (_CONTACT_PERSON_MAX_LENGTH + 1)
        self.assert_contact_rejected(name)

    def test_strips_leading_trailing_whitespace(self):
        self.assert_contact_accepted("  John Doe  ", "John Doe")


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashContactPersonValidationTests(_StrictContactPersonTests, SimpleTestCase):
    pass


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetContactPersonValidationTests(
    _StrictContactPersonTests, SimpleTestCase
):
    pass


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalFlashContactPersonValidationTests(
    _StrictContactPersonTests, SimpleTestCase
):
    pass


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashContactPersonLegacyBehaviourTests(
    _ContactPersonSerializerMixin, SimpleTestCase
):
    """food_flash must retain unrestricted Contact Person behaviour."""

    def test_legacy_values_still_accepted_unchanged(self):
        for value in INVALID_NAMES + VALID_NAMES:
            with self.subTest(value=value):
                self.assert_contact_accepted(value)

    def test_does_not_trim_or_normalize(self):
        raw = "  John  "
        self.assert_contact_accepted(raw)

    def test_none_still_accepted(self):
        self.assert_contact_accepted(None)


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashContactPersonLegacyBehaviourTests(
    _ContactPersonSerializerMixin, SimpleTestCase
):
    """airline_flash must retain unrestricted Contact Person behaviour."""

    def test_legacy_values_still_accepted_unchanged(self):
        for value in INVALID_NAMES + VALID_NAMES:
            with self.subTest(value=value):
                self.assert_contact_accepted(value)

    def test_does_not_trim_or_normalize(self):
        raw = "  John  "
        self.assert_contact_accepted(raw)

    def test_none_still_accepted(self):
        self.assert_contact_accepted(None)


class ContactPersonMaxLengthModelFieldTests(SimpleTestCase):
    """Existing model max_length=255 must remain in place."""

    def test_model_field_max_length_is_255(self):
        field = AdminOutlet._meta.get_field("customer_contact_person")
        self.assertEqual(field.max_length, 255)
        self.assertTrue(field.blank)
        self.assertTrue(field.null)


def _create_outlet(username, **extra):
    user = User.objects.create_user(username=username, password="pass12345")
    return AdminOutlet.objects.create(
        user=user,
        customer_name=extra.get("customer_name", username),
        customer_email=extra.get("customer_email", f"{username}@example.com"),
        customer_contact_person=extra.get("customer_contact_person"),
        gst_number=extra.get("gst_number"),
    )


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashContactPersonUpdateTests(_ContactPersonSerializerMixin, TestCase):
    def test_update_with_valid_contact_person(self):
        outlet = _create_outlet("cp_upd_ok", customer_contact_person="Old Name")
        self.assert_contact_accepted(
            "Jane Doe", expected="Jane Doe", instance=outlet
        )

    def test_update_with_invalid_contact_person(self):
        outlet = _create_outlet("cp_upd_bad", customer_contact_person="Old Name")
        self.assert_contact_rejected(
            "Jane123",
            message_fragment=_CONTACT_PERSON_FORMAT_ERROR,
            instance=outlet,
        )

    def test_partial_update_omitting_contact_person_allowed(self):
        outlet = _create_outlet("cp_partial", customer_contact_person="John Doe")
        serializer = AdminOutletSerializer(
            outlet,
            data={"customer_name": "Updated Co"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn("customer_contact_person", serializer.validated_data)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetContactPersonUpdateTests(_ContactPersonSerializerMixin, TestCase):
    def test_update_with_valid_contact_person(self):
        outlet = _create_outlet("cp_buf_ok", customer_contact_person="Old Name")
        self.assert_contact_accepted(
            "Mary Ann", expected="Mary Ann", instance=outlet
        )

    def test_update_with_invalid_contact_person(self):
        outlet = _create_outlet("cp_buf_bad", customer_contact_person="Old Name")
        self.assert_contact_rejected(
            "John@Doe",
            message_fragment=_CONTACT_PERSON_FORMAT_ERROR,
            instance=outlet,
        )


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalFlashContactPersonUpdateTests(_ContactPersonSerializerMixin, TestCase):
    def test_update_with_valid_contact_person(self):
        outlet = _create_outlet("cp_hos_ok", customer_contact_person="Old Name")
        self.assert_contact_accepted("John", expected="John", instance=outlet)

    def test_update_with_invalid_contact_person(self):
        outlet = _create_outlet("cp_hos_bad", customer_contact_person="Old Name")
        self.assert_contact_rejected(
            "12345",
            message_fragment=_CONTACT_PERSON_FORMAT_ERROR,
            instance=outlet,
        )


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashContactPersonUpdateLegacyTests(_ContactPersonSerializerMixin, TestCase):
    def test_update_accepts_numeric_and_special(self):
        outlet = _create_outlet("cp_ff_upd", customer_contact_person="Old")
        self.assert_contact_accepted("John123", instance=outlet)
        self.assert_contact_accepted("John@Doe", instance=outlet)


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashContactPersonUpdateLegacyTests(
    _ContactPersonSerializerMixin, TestCase
):
    def test_update_accepts_numeric_and_special(self):
        outlet = _create_outlet("cp_af_upd", customer_contact_person="Old")
        self.assert_contact_accepted("John123", instance=outlet)
        self.assert_contact_accepted("John@Doe", instance=outlet)
