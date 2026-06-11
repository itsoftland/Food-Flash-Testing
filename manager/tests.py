from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from manager.serializer.booking_serializer import serialize_dine_flash_manager_bookings
from orders.dine_flash_tracking_token import unsign_dine_flash_tracking_token
from manager.views import _dine_flash_requested_utility_filter
from manager.utils.dine_flash_request_perf import (
    should_trace_manager_request,
    ensure_request_trace,
    record_handler_timing,
)
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
            call_count=3,
        )
        rows = serialize_dine_flash_manager_bookings([order], {7: 2})
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["new_notifications"], 2)
        self.assertEqual(row["utility_name"], "Patio")
        self.assertEqual(row["table_booking_no_display"], "A-3 [T12]")
        self.assertEqual(row["call_count"], 3)
        self.assertIsNone(row["tracking_url"])
        self.assertIsNone(row["encrypted_tracking_url"])

    @override_settings(PROJECT_NAME="dine_flash")
    def test_serialize_dine_flash_manager_bookings_encrypted_tracking_url(self):
        utility = SimpleNamespace(display_name="Patio")
        vendor = SimpleNamespace(vendor_id="108029", location_id="KZ01")
        order = SimpleNamespace(
            id=213,
            table_booking_no="147",
            customer_name="Sam",
            phone_number="999",
            no_of_packs=2,
            remarks="",
            status="waiting",
            created_at=None,
            seat_no="T12",
            utility=utility,
            call_count=0,
        )
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f"http://testhost{path}"
        )
        with patch(
            "manager.serializer.booking_serializer.reverse",
            return_value="/dine_flash/home/",
        ):
            rows = serialize_dine_flash_manager_bookings(
                [order], {213: 0}, vendor=vendor, request=request
            )

        row = rows[0]
        self.assertEqual(
            row["tracking_url"],
            "http://testhost/dine_flash/home/?location_id=KZ01&vendor_id=108029&"
            "booking_no=147&booking_id=213",
        )
        self.assertIn("encrypted_tracking_url", row)
        self.assertTrue(row["encrypted_tracking_url"].startswith(
            "http://testhost/dine_flash/home/?t="
        ))
        token = row["encrypted_tracking_url"].split("?t=", 1)[1]
        payload = unsign_dine_flash_tracking_token(token)
        self.assertEqual(
            payload,
            {
                "vendor_id": "108029",
                "location_id": "KZ01",
                "booking_id": "213",
                "booking_no": "147",
            },
        )

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

    def test_parse_dine_flash_utility_filter_prefers_id(self):
        request = SimpleNamespace(
            query_params={"utility_id": "42", "utility_code": "VIP"}
        )
        utility_id, utility_code = _dine_flash_requested_utility_filter(request)
        self.assertEqual(utility_id, 42)
        self.assertEqual(utility_code, "VIP")

    def test_parse_dine_flash_utility_filter_code_only(self):
        request = SimpleNamespace(query_params={"display_code": " ac "})
        utility_id, utility_code = _dine_flash_requested_utility_filter(request)
        self.assertIsNone(utility_id)
        self.assertEqual(utility_code, "ac")

    def test_parse_dine_flash_utility_filter_invalid_id(self):
        request = SimpleNamespace(query_params={"utility_id": "abc"})
        with self.assertRaises(ValueError):
            _dine_flash_requested_utility_filter(request)

    @override_settings(PROJECT_NAME="dine_flash")
    def test_should_trace_dine_flash_manager_api(self):
        request = SimpleNamespace(path="/dine_flash/manager/api/utility_list/")
        self.assertTrue(should_trace_manager_request(request))

    @override_settings(PROJECT_NAME="food_flash")
    def test_should_not_trace_other_flavours(self):
        request = SimpleNamespace(path="/food_flash/manager/api/utility_list/")
        self.assertFalse(should_trace_manager_request(request))

    @override_settings(PROJECT_NAME="dine_flash")
    def test_ensure_request_trace_sets_trace_id(self):
        request = SimpleNamespace(
            path="/dine_flash/manager/api/utility_list/",
            method="GET",
            user=None,
        )
        trace = ensure_request_trace(request)
        self.assertIsNotNone(trace)
        self.assertEqual(len(trace["trace_id"]), 12)

    @override_settings(PROJECT_NAME="dine_flash")
    def test_record_handler_timing_stores_handler_ms(self):
        import time

        request = SimpleNamespace(
            path="/dine_flash/manager/api/utility_list/",
            method="GET",
            user=None,
        )
        ensure_request_trace(request)
        started = time.perf_counter()
        record_handler_timing(
            request,
            "manager_utility_list",
            started,
            vendor=1.0,
            query=2.0,
            cache="miss",
            count=3,
        )
        trace = getattr(request, "_dine_flash_perf")
        self.assertIn("handler_ms", trace)
        self.assertEqual(trace["segments"].get("cache"), "miss")
