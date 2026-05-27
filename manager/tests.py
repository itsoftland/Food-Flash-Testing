from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from manager.serializer.booking_serializer import serialize_dine_flash_manager_bookings
from manager.utils.dine_flash_manager_cache import (
    clear_all as clear_vendor_cache,
    get_cached_manager_vendor,
    is_enabled as vendor_cache_enabled,
)
from manager.utils.utility_cache import (
    clear_all as clear_utility_cache,
    get_cached_utilities,
    is_enabled as utility_cache_enabled,
)


class DineFlashManagerPerfTests(SimpleTestCase):
    def test_serialize_dine_flash_manager_bookings_shape(self):
        utility = SimpleNamespace(display_name="Patio")
        order = SimpleNamespace(
            id=7,
            table_booking_no="A-3",
            customer_name="Sam",
            phone_number="999",
            no_of_packs=2,
            remarks="",
            status="waiting",
            created_at=None,
            seat_no="T12",
            utility=utility,
        )
        rows = serialize_dine_flash_manager_bookings([order], {7: 2})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["new_notifications"], 2)
        self.assertEqual(row["utility_name"], "Patio")
        self.assertEqual(row["table_booking_no_display"], "A-3 [T12]")
        self.assertIsNone(row["tracking_url"])

    @override_settings(PROJECT_NAME="dine_flash")
    def test_utility_cache_enabled_for_dine_flash(self):
        clear_utility_cache()
        self.assertTrue(utility_cache_enabled())

    @override_settings(PROJECT_NAME="food_flash")
    def test_utility_cache_disabled_outside_dine_flash(self):
        clear_utility_cache()
        self.assertFalse(utility_cache_enabled())
        self.assertIsNone(get_cached_utilities(1))

    @override_settings(PROJECT_NAME="dine_flash")
    def test_vendor_cache_disabled_for_other_flavours(self):
        clear_vendor_cache()
        self.assertTrue(vendor_cache_enabled())

    @override_settings(PROJECT_NAME="food_flash")
    def test_vendor_cache_not_enabled_for_food_flash(self):
        self.assertFalse(vendor_cache_enabled())
        user = SimpleNamespace(pk=1)
        with patch(
            "manager.utils.dine_flash_manager_cache.get_manager_vendor_dine_flash",
            return_value="vendor",
        ) as lookup:
            vendor = get_cached_manager_vendor(user)
            self.assertEqual(vendor, "vendor")
            lookup.assert_called_once_with(user)
