"""
Flavour-scoped AdminOutlet State/City validation.

Strict alphabetic+spaces rule applies only to:
  dine_flash, dine_flash_buffet, hospital_flash

Legacy unrestricted behaviour must remain for:
  food_flash, airline_flash
"""
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from orders.serializers import (
    AdminOutletSerializer,
    normalize_and_validate_state_or_city,
)


class NormalizeStateCityHelperTests(SimpleTestCase):
    def test_valid_values(self):
        self.assertEqual(normalize_and_validate_state_or_city("Kerala"), "Kerala")
        self.assertEqual(normalize_and_validate_state_or_city("Tamil Nadu"), "Tamil Nadu")
        self.assertEqual(normalize_and_validate_state_or_city("New Delhi"), "New Delhi")

    def test_trims_and_collapses_spaces(self):
        self.assertEqual(
            normalize_and_validate_state_or_city("  Tamil   Nadu  "),
            "Tamil Nadu",
        )
        self.assertEqual(
            normalize_and_validate_state_or_city("New  Delhi"),
            "New Delhi",
        )

    def test_rejects_invalid_values(self):
        invalid = [
            "123",
            "Kerala123",
            "123Kerala",
            "Kerala@123",
            "@Kerala",
            "Kochi#",
            "Tamil-Nadu",
            "Kerala.",
            "   ",
            "\t",
            "",
            None,
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalize_and_validate_state_or_city(value)


class _StateCitySerializerMixin:
    def _ser(self):
        return AdminOutletSerializer()

    def assert_state_accepted(self, raw, expected=None):
        result = self._ser().validate_customer_state(raw)
        self.assertEqual(result, raw if expected is None else expected)

    def assert_city_accepted(self, raw, expected=None):
        result = self._ser().validate_customer_city(raw)
        self.assertEqual(result, raw if expected is None else expected)

    def assert_state_rejected(self, raw):
        with self.assertRaises(ValidationError):
            self._ser().validate_customer_state(raw)

    def assert_city_rejected(self, raw):
        with self.assertRaises(ValidationError):
            self._ser().validate_customer_city(raw)


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashStateCityValidationTests(_StateCitySerializerMixin, SimpleTestCase):
    def test_valid_examples(self):
        self.assert_state_accepted("Kerala", "Kerala")
        self.assert_state_accepted("Tamil Nadu", "Tamil Nadu")
        self.assert_city_accepted("New Delhi", "New Delhi")

    def test_normalization(self):
        self.assert_state_accepted("  Kerala  ", "Kerala")
        self.assert_city_accepted("New  Delhi", "New Delhi")

    def test_invalid_examples(self):
        for value in (
            "123",
            "Kerala123",
            "Kerala@123",
            "@Kerala",
            "Kerala.",
            "Tamil-Nadu",
            "   ",
            "\t",
        ):
            with self.subTest(value=value):
                self.assert_state_rejected(value)
                self.assert_city_rejected(value)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetStateCityValidationTests(_StateCitySerializerMixin, SimpleTestCase):
    def test_valid_and_invalid(self):
        self.assert_state_accepted("Uttar Pradesh", "Uttar Pradesh")
        self.assert_city_accepted("Kochi", "Kochi")
        self.assert_state_rejected("123")
        self.assert_city_rejected("Kerala123")
        self.assert_state_accepted("  Tamil  Nadu ", "Tamil Nadu")


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalFlashStateCityValidationTests(_StateCitySerializerMixin, SimpleTestCase):
    def test_valid_and_invalid(self):
        self.assert_state_accepted("Himachal Pradesh", "Himachal Pradesh")
        self.assert_city_accepted("Thiruvananthapuram", "Thiruvananthapuram")
        self.assert_state_rejected("@@@")
        self.assert_city_rejected("   ")
        self.assert_city_accepted("  New Delhi  ", "New Delhi")


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashStateCityLegacyBehaviourTests(_StateCitySerializerMixin, SimpleTestCase):
    """food_flash must retain unrestricted State/City behaviour."""

    def test_legacy_values_still_accepted_unchanged(self):
        for value in (
            "123",
            "Kerala123",
            "Kerala@123",
            "@Kerala",
            "Kerala.",
            "Tamil-Nadu",
            "   ",
            "\t",
            "Kerala",
            "Tamil Nadu",
        ):
            with self.subTest(value=value):
                self.assert_state_accepted(value)
                self.assert_city_accepted(value)

    def test_does_not_trim_or_normalize(self):
        raw = "  New  Delhi  "
        self.assert_state_accepted(raw)
        self.assert_city_accepted(raw)


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashStateCityLegacyBehaviourTests(_StateCitySerializerMixin, SimpleTestCase):
    """airline_flash must retain unrestricted State/City behaviour."""

    def test_legacy_values_still_accepted_unchanged(self):
        for value in (
            "123",
            "Kerala123",
            "Kerala@123",
            "@Kerala",
            "Kerala.",
            "Tamil-Nadu",
            "   ",
            "\t",
            "Kerala",
            "New Delhi",
        ):
            with self.subTest(value=value):
                self.assert_state_accepted(value)
                self.assert_city_accepted(value)

    def test_does_not_trim_or_normalize(self):
        raw = "  Tamil  Nadu  "
        self.assert_state_accepted(raw)
        self.assert_city_accepted(raw)
