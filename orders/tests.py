import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from orders.utils import (
    dine_flash_manager_fcm_data_extra,
    dine_flash_manager_fcm_event_name,
    dine_flash_manager_fcm_payload,
    send_to_managers,
)
from orders.views import (
    _build_dine_flash_booking_created_manager_payload,
    _schedule_dine_flash_booking_created_fcm,
    book_table,
    check_status,
)
from vendors.models import Order

_DINE_FLASH_STATUS_CHOICES = [
    ("created", "Request Created"),
    ("waiting", "Allocation Pending"),
    ("allocated", "Allocated"),
    ("occupied", "Occupied"),
    ("booking_cancelled", "Booking Cancelled"),
    ("operation_closed", "Close Operation"),
]


class BuffetCheckStatusTests(SimpleTestCase):
    @patch("orders.views.project_name", "dine_flash_buffet")
    @patch.object(Order.objects, "get")
    def test_unknown_token_returns_400_without_auto_create(self, mock_get):
        mock_get.side_effect = Order.DoesNotExist

        factory = APIRequestFactory()
        request = factory.post(
            "/check-status/",
            {"token_no": 400, "vendor_id": 1},
            format="json",
        )

        with patch("orders.views.OrdersSerializer") as mock_serializer:
            response = check_status(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid token", response.data["error"])
        mock_serializer.assert_not_called()


class DineFlashBookingCreatedFcmUtilsTests(SimpleTestCase):
    def test_event_name_booking_created(self):
        self.assertEqual(
            dine_flash_manager_fcm_event_name({"action": "booking_created"}),
            "booking_created",
        )

    def test_event_name_customer_chat(self):
        self.assertEqual(
            dine_flash_manager_fcm_event_name({"type": "user_reply"}),
            "customer_chat",
        )

    def test_payload_booking_created_strips_updated_by(self):
        result = dine_flash_manager_fcm_payload(
            {
                "action": "booking_created",
                "type": "dinestatus",
                "updated_by": "customer",
            }
        )
        self.assertEqual(result["type"], "dinestatus")
        self.assertNotIn("updated_by", result)

    def test_data_extra_booking_created(self):
        extra = dine_flash_manager_fcm_data_extra(
            {
                "action": "booking_created",
                "booking_id": 9,
                "booking_no": "VIP-3",
                "type": "dinestatus",
            }
        )
        self.assertEqual(extra["event"], "booking_created")
        self.assertEqual(extra["project"], "dine_flash")
        self.assertEqual(extra["booking_id"], 9)
        self.assertEqual(extra["booking_no"], "VIP-3")

    @override_settings(PROJECT_NAME="dine_flash")
    @patch("orders.utils.send_fcm_multicast")
    @patch("orders.utils.collect_manager_fcm_tokens", return_value=["token-a"])
    def test_send_to_managers_booking_created_high_priority(
        self, mock_collect, mock_multicast
    ):
        vendor = SimpleNamespace(vendor_id=1, name="Outlet")
        data = {
            "action": "booking_created",
            "booking_id": 5,
            "booking_no": "A-1",
            "type": "dinestatus",
        }
        send_to_managers(vendor, data, "New Table Booking", "Guest — 2 guests (A-1)")

        mock_multicast.assert_called_once()
        kwargs = mock_multicast.call_args.kwargs
        self.assertTrue(kwargs["android_high_priority"])
        self.assertEqual(kwargs["fcm_data_extra"]["event"], "booking_created")

    @override_settings(PROJECT_NAME="food_flash")
    @patch("orders.utils.send_fcm_multicast")
    @patch("orders.utils.collect_manager_fcm_tokens", return_value=["token-a"])
    def test_send_to_managers_booking_created_skipped_outside_dine_flash(
        self, mock_collect, mock_multicast
    ):
        vendor = SimpleNamespace(vendor_id=1, name="Outlet")
        data = {"action": "booking_created", "type": "dinestatus"}
        send_to_managers(vendor, data, "New Table Booking", "body")

        kwargs = mock_multicast.call_args.kwargs
        self.assertIsNone(kwargs["fcm_data_extra"])
        self.assertFalse(kwargs["android_high_priority"])


class DineFlashBookTableFcmTests(SimpleTestCase):
    def _booking_request(self, factory):
        return factory.post(
            "/api/book_table/",
            {
                "vendor_id": 100,
                "customer_name": "Jane Doe",
                "no_of_guests": 2,
                "qr_session": "qr-test-token",
            },
            format="json",
        )

    @patch.object(Order, "STATUS_CHOICES", _DINE_FLASH_STATUS_CHOICES)
    @patch("orders.views.project_name", "dine_flash")
    @patch("orders.views._schedule_dine_flash_booking_created_fcm")
    @patch("orders.views.VendorLogoSerializer")
    @patch("orders.views.OrdersSerializer")
    @patch("orders.views.reset_counters_if_new_business_day")
    @patch("orders.views._validate_dine_flash_qr_session", return_value=(True, None))
    @patch("orders.views.transaction.atomic")
    def test_customer_book_table_schedules_manager_fcm(
        self,
        mock_atomic,
        mock_qr,
        mock_reset,
        mock_serializer_cls,
        mock_logo_serializer,
        mock_schedule,
    ):
        mock_atomic.return_value.__enter__ = lambda self: self
        mock_atomic.return_value.__exit__ = lambda *args: False

        vendor = SimpleNamespace(
            id=1,
            vendor_id=100,
            name="Test Vendor",
            alias_name="",
            location_id="LOC1",
            config=SimpleNamespace(use_utilities=False),
        )
        booking = SimpleNamespace(
            id=42,
            token_no=1,
            table_booking_no="1",
            status="waiting",
            customer_name="Jane Doe",
            no_of_packs=2,
            remarks="",
            counter_no=1,
        )
        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.save.return_value = booking
        serializer.data = {"id": 42, "token_no": 1}
        mock_serializer_cls.return_value = serializer

        mock_logo_serializer.return_value.data = {"logo_url": "http://logo"}

        with patch.object(Order.objects, "filter") as mock_filter:
            mock_filter.return_value.aggregate.return_value = {"m": None}
            with patch(
                "orders.views.Vendor.objects.select_related"
            ) as mock_vendor_qs:
                mock_vendor_qs.return_value.filter.return_value.first.return_value = (
                    vendor
                )
                factory = APIRequestFactory()
                request = self._booking_request(factory)
                request.user = AnonymousUser()

                response = book_table(request)

        self.assertEqual(response.status_code, 201)
        mock_schedule.assert_called_once()
        args = mock_schedule.call_args[0]
        payload = args[1]
        self.assertEqual(payload["action"], "booking_created")
        self.assertEqual(payload["type"], "dinestatus")
        self.assertEqual(args[2], "New Table Booking")

    @patch.object(Order, "STATUS_CHOICES", _DINE_FLASH_STATUS_CHOICES)
    @patch("orders.views.project_name", "dine_flash")
    @patch("orders.views._schedule_dine_flash_booking_created_fcm")
    @patch("orders.views.OrdersSerializer")
    @patch("orders.views.reset_counters_if_new_business_day")
    @patch("orders.views._validate_dine_flash_qr_session", return_value=(True, None))
    @patch("orders.views.transaction.atomic")
    def test_manager_created_book_table_skips_manager_fcm(
        self,
        mock_atomic,
        mock_qr,
        mock_reset,
        mock_serializer_cls,
        mock_schedule,
    ):
        mock_atomic.return_value.__enter__ = lambda self: self
        mock_atomic.return_value.__exit__ = lambda *args: False

        vendor = SimpleNamespace(
            id=1,
            vendor_id=100,
            name="Test Vendor",
            alias_name="",
            location_id="LOC1",
            config=SimpleNamespace(use_utilities=False),
        )
        manager_profile = SimpleNamespace(id=7, vendor=vendor)
        booking = SimpleNamespace(
            id=43,
            token_no=2,
            table_booking_no="2",
            status="waiting",
            customer_name="Jane Doe",
            no_of_packs=2,
            remarks="",
            counter_no=1,
        )
        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.save.return_value = booking
        serializer.data = {"id": 43}
        mock_serializer_cls.return_value = serializer

        user = MagicMock()
        user.is_authenticated = True
        user.profile_roles.select_related.return_value.order_by.return_value.first.return_value = (
            manager_profile
        )

        with patch.object(Order.objects, "filter") as mock_filter:
            mock_filter.return_value.aggregate.return_value = {"m": 1}
            factory = APIRequestFactory()
            request = factory.post(
                "/api/book_table/",
                {
                    "customer_name": "Jane Doe",
                    "no_of_guests": 2,
                },
                format="json",
            )
            request.user = user

            response = book_table(request)

        self.assertEqual(response.status_code, 201)
        mock_schedule.assert_not_called()

    @patch("orders.views.project_name", "food_flash")
    @patch("orders.views._schedule_dine_flash_booking_created_fcm")
    @patch("orders.views.OrdersSerializer")
    @patch("orders.views.reset_counters_if_new_business_day")
    @patch("orders.views.transaction.atomic")
    def test_food_flash_book_table_skips_dine_flash_fcm(
        self,
        mock_atomic,
        mock_reset,
        mock_serializer_cls,
        mock_schedule,
    ):
        mock_atomic.return_value.__enter__ = lambda self: self
        mock_atomic.return_value.__exit__ = lambda *args: False

        vendor = SimpleNamespace(
            id=1,
            vendor_id=100,
            name="Food Vendor",
            alias_name="",
            location_id="LOC1",
            config=SimpleNamespace(use_utilities=False),
        )
        booking = SimpleNamespace(
            id=44,
            token_no=3,
            table_booking_no="3",
            status="preparing",
            customer_name="Jane Doe",
            no_of_packs=2,
            remarks="",
            counter_no=1,
        )
        serializer = MagicMock()
        serializer.is_valid.return_value = True
        serializer.save.return_value = booking
        serializer.data = {"id": 44}
        mock_serializer_cls.return_value = serializer

        with patch.object(Order.objects, "filter") as mock_filter:
            mock_filter.return_value.aggregate.return_value = {"m": None}
            with patch(
                "orders.views.Vendor.objects.select_related"
            ) as mock_vendor_qs:
                mock_vendor_qs.return_value.filter.return_value.first.return_value = (
                    vendor
                )
                factory = APIRequestFactory()
                request = factory.post(
                    "/api/book_table/",
                    {
                        "vendor_id": 100,
                        "customer_name": "Jane Doe",
                        "no_of_guests": 2,
                        "status": "preparing",
                    },
                    format="json",
                )
                request.user = AnonymousUser()

                response = book_table(request)

        self.assertEqual(response.status_code, 201)
        mock_schedule.assert_not_called()

    @patch("orders.views.threading.Thread")
    @patch("orders.views._send_to_managers_async")
    @patch("orders.views.transaction.on_commit")
    def test_schedule_registers_on_commit_and_async_send(
        self, mock_on_commit, mock_send_async, mock_thread
    ):
        vendor = SimpleNamespace(vendor_id=1)
        payload = {"action": "booking_created"}
        mock_on_commit.side_effect = lambda fn: fn()

        _schedule_dine_flash_booking_created_fcm(
            vendor, payload, "New Table Booking", "body"
        )

        mock_on_commit.assert_called_once()
        mock_thread.assert_called_once()
        thread_kwargs = mock_thread.call_args.kwargs
        self.assertTrue(thread_kwargs["daemon"])
        thread_kwargs["target"](*thread_kwargs["args"])
        mock_send_async.assert_called_once_with(
            vendor, payload, "New Table Booking", "body"
        )

    @patch("orders.views.VendorLogoSerializer")
    def test_build_booking_created_payload_shape(self, mock_logo_serializer):
        mock_logo_serializer.return_value.data = {"logo_url": "http://example/logo.png"}
        vendor = SimpleNamespace(
            vendor_id=10,
            name="Vendor",
            alias_name="Alias",
            location_id="L1",
        )
        utility = SimpleNamespace(display_name="Patio")
        booking = SimpleNamespace(
            id=99,
            table_booking_no="P-5",
            token_no=5,
            status="waiting",
            customer_name="Sam",
            no_of_packs=3,
            remarks="window",
            counter_no=1,
        )
        factory = APIRequestFactory()
        request = factory.post("/")

        payload = _build_dine_flash_booking_created_manager_payload(
            booking, vendor, utility, request
        )

        self.assertEqual(payload["action"], "booking_created")
        self.assertEqual(payload["type"], "dinestatus")
        self.assertEqual(payload["booking_id"], 99)
        self.assertEqual(payload["utility_name"], "Patio")
        self.assertNotIn("updated_by", payload)


class BuffetTableQrTokenTests(SimpleTestCase):
    def test_sign_and_unsign_round_trip(self):
        from orders.buffet_table_qr import sign_buffet_table_qr, unsign_buffet_table_qr

        token = sign_buffet_table_qr(800706, 12)
        payload = unsign_buffet_table_qr(token)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["vendor_id"], "800706")
        self.assertEqual(payload["table_no"], "12")

    def test_tampered_token_rejected(self):
        from orders.buffet_table_qr import sign_buffet_table_qr, unsign_buffet_table_qr

        token = sign_buffet_table_qr(800706, 25)
        tampered = token[:-4] + "xxxx"
        self.assertIsNone(unsign_buffet_table_qr(tampered))

    def test_zero_table_number_invalid(self):
        from orders.buffet_table_qr import is_valid_buffet_table_no, sign_buffet_table_qr

        self.assertFalse(is_valid_buffet_table_no(0))
        self.assertFalse(is_valid_buffet_table_no("0"))
        with self.assertRaises(ValueError):
            sign_buffet_table_qr(800706, 0)

    def test_positive_integer_validation(self):
        from orders.buffet_table_qr import is_valid_buffet_table_no

        self.assertTrue(is_valid_buffet_table_no(1))
        self.assertTrue(is_valid_buffet_table_no("42"))
        self.assertFalse(is_valid_buffet_table_no(-1))
        self.assertFalse(is_valid_buffet_table_no("abc"))
        self.assertFalse(is_valid_buffet_table_no(""))


class DineFlashTrackingTokenTests(SimpleTestCase):
    def test_sign_unsign_roundtrip(self):
        from orders.dine_flash_tracking_token import (
            sign_dine_flash_tracking_token,
            unsign_dine_flash_tracking_token,
        )

        token = sign_dine_flash_tracking_token(
            vendor_id="108029",
            location_id="KZ01",
            booking_id=213,
            booking_no="147",
        )
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

    def test_tampered_tracking_token_rejected(self):
        from orders.dine_flash_tracking_token import (
            sign_dine_flash_tracking_token,
            unsign_dine_flash_tracking_token,
        )

        token = sign_dine_flash_tracking_token(
            vendor_id="108029",
            location_id="KZ01",
            booking_id="213",
            booking_no="147",
        )
        self.assertIsNone(unsign_dine_flash_tracking_token(token[:-4] + "xxxx"))


class DineFlashHomeTrackingTokenTests(SimpleTestCase):
    @override_settings(PROJECT_NAME="dine_flash")
    @patch("orders.views._dine_flash_order_tracking_exists", return_value=True)
    @patch("orders.views._dine_flash_business_day_start_hour", return_value="06:00:00")
    def test_home_accepts_signed_tracking_token(
        self, mock_business_hour, mock_tracking_exists
    ):
        from django.test import RequestFactory

        from orders.dine_flash_tracking_token import sign_dine_flash_tracking_token
        from orders.views import home

        token = sign_dine_flash_tracking_token(
            vendor_id="108029",
            location_id="KZ01",
            booking_id="213",
            booking_no="147",
        )
        request = RequestFactory().get(f"/dine_flash/home/?t={token}")
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 200)
        mock_tracking_exists.assert_called_once_with(
            "108029",
            booking_id="213",
            booking_no="147",
        )
        content = response.content.decode()
        self.assertIn("window.DINE_FLASH_TRACKING_BOOTSTRAP", content)
        self.assertIn('"vendor_id": "108029"', content)
        self.assertIn('"booking_no": "147"', content)

    @override_settings(PROJECT_NAME="dine_flash")
    def test_home_rejects_invalid_signed_tracking_token(self):
        from django.test import RequestFactory

        from orders.views import home

        request = RequestFactory().get("/dine_flash/home/?t=not-a-valid-token")
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid tracking link", response.content)
