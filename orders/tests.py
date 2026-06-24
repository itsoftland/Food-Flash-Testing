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


def _encrypt_qr_payload_for_test(params, *, iv=None, secret=None):
    import base64

    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    from orders.dine_flash.qr_crypto import _derive_aes_key, canonical_query_string

    plain = canonical_query_string(params)
    key = _derive_aes_key(secret)
    iv_bytes = iv or (b"\x11" * 16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv_bytes))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    raw = iv_bytes + ciphertext
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class QrCryptoTests(SimpleTestCase):
    def test_legacy_hash_resolve_with_vendor_hint(self):
        from datetime import datetime

        from orders.dine_flash.qr_crypto import build_qr_hash, resolve_legacy_hashed_qr_data

        fixed_now = datetime(2026, 6, 11, 18, 13, 37)
        params = {
            "vendor_id": "101",
            "qr_date": "2026-06-11",
            "qr_time": "18:13:37",
            "qr_expiry_minutes": "1",
        }
        data = build_qr_hash(params)

        resolved = resolve_legacy_hashed_qr_data(
            data,
            vendor_id_hint=101,
            qr_expiry_minutes_hint=1,
            now=fixed_now,
            clock_skew_seconds=90,
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.vendor_id, 101)
        self.assertEqual(resolved.qr_date, "2026-06-11")
        self.assertEqual(resolved.qr_time, "18:13:37")

    def test_decrypt_qr_data_encrypted_round_trip(self):
        from datetime import datetime

        from orders.dine_flash.qr_crypto import decrypt_qr_data, extract_data_param

        fixed_now = datetime(2026, 6, 11, 18, 13, 37)
        params = {
            "vendor_id": "101",
            "qr_date": "2026-06-11",
            "qr_time": "18:13:37",
            "qr_expiry_minutes": "5",
        }
        encrypted = _encrypt_qr_payload_for_test(params)
        resolved = decrypt_qr_data(encrypted, now=fixed_now)

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.vendor_id, 101)
        self.assertEqual(resolved.qr_expiry_minutes, 5)

        url = f"https://example.com/dine_flash/table_booking/?data={encrypted}"
        self.assertEqual(extract_data_param(url), encrypted)

    def test_decrypt_qr_data_legacy_auto_detect(self):
        from datetime import datetime

        from orders.dine_flash.qr_crypto import build_qr_hash, decrypt_qr_data

        fixed_now = datetime(2026, 6, 11, 18, 13, 37)
        params = {
            "qr_date": "2026-06-11",
            "qr_time": "18:13:37",
            "qr_expiry_minutes": "1",
        }
        data = build_qr_hash(params)
        resolved = decrypt_qr_data(data, now=fixed_now)

        self.assertIsNotNone(resolved)
        self.assertIsNone(resolved.vendor_id)

    def test_decrypt_qr_data_returns_none_for_empty_or_invalid(self):
        from datetime import datetime

        from orders.dine_flash.qr_crypto import decrypt_qr_data

        self.assertIsNone(decrypt_qr_data("", now=datetime(2026, 6, 11, 18, 13, 37)))
        self.assertIsNone(decrypt_qr_data("not-valid-base64", now=datetime(2026, 6, 11, 18, 13, 37)))
        self.assertIsNone(decrypt_qr_data("a" * 64, now=datetime(2026, 6, 11, 18, 13, 37)))

    def test_decrypt_qr_data_returns_none_when_expired(self):
        from datetime import datetime, timedelta

        from orders.dine_flash.qr_crypto import decrypt_qr_data

        fixed_now = datetime(2026, 6, 11, 18, 0, 0)
        params = {
            "vendor_id": "101",
            "qr_date": fixed_now.strftime("%Y-%m-%d"),
            "qr_time": fixed_now.strftime("%H:%M:%S"),
            "qr_expiry_minutes": "1",
        }
        encrypted = _encrypt_qr_payload_for_test(params)
        now = fixed_now + timedelta(minutes=4, seconds=1)

        self.assertIsNone(decrypt_qr_data(encrypted, now=now))

    def test_decrypt_qr_data_allows_boundary_grace_period(self):
        from datetime import datetime, timedelta

        from orders.dine_flash.qr_crypto import decrypt_qr_data

        issued_at = datetime(2026, 6, 11, 13, 0, 0)
        params_5min = {
            "vendor_id": "101",
            "qr_date": issued_at.strftime("%Y-%m-%d"),
            "qr_time": issued_at.strftime("%H:%M:%S"),
            "qr_expiry_minutes": "5",
        }
        encrypted_5min = _encrypt_qr_payload_for_test(params_5min)

        for now in (
            issued_at + timedelta(minutes=7, seconds=59),
            issued_at + timedelta(minutes=8),
        ):
            with self.subTest(expiry_minutes=5, now=now):
                self.assertIsNotNone(decrypt_qr_data(encrypted_5min, now=now))

        self.assertIsNone(
            decrypt_qr_data(
                encrypted_5min, now=issued_at + timedelta(minutes=8, seconds=1)
            )
        )

        params_1min = {**params_5min, "qr_expiry_minutes": "1"}
        encrypted_1min = _encrypt_qr_payload_for_test(params_1min)

        for now in (
            issued_at + timedelta(minutes=3, seconds=59),
            issued_at + timedelta(minutes=4),
        ):
            with self.subTest(expiry_minutes=1, now=now):
                self.assertIsNotNone(decrypt_qr_data(encrypted_1min, now=now))

        self.assertIsNone(
            decrypt_qr_data(
                encrypted_1min, now=issued_at + timedelta(minutes=4, seconds=1)
            )
        )


class DineFlashQrTimeValidationTests(SimpleTestCase):
    def test_validate_dine_flash_qr_time_allows_boundary_grace_period(self):
        from datetime import datetime, timedelta

        from django.utils import timezone

        from orders.views import _validate_dine_flash_qr_time

        tz = timezone.get_current_timezone()
        issued_at = timezone.make_aware(datetime(2026, 6, 11, 13, 0, 0), tz)

        with patch("orders.views.timezone.localtime") as mock_localtime, patch(
            "orders.views.timezone.now", return_value=issued_at
        ):
            for offset_seconds in (479, 480):
                with self.subTest(offset_seconds=offset_seconds):
                    mock_localtime.return_value = issued_at + timedelta(seconds=offset_seconds)
                    ok, msg = _validate_dine_flash_qr_time(
                        "2026-06-11",
                        "13:00:00",
                        "101",
                        expiry_minutes=5,
                    )
                    self.assertTrue(ok, msg)

            mock_localtime.return_value = issued_at + timedelta(minutes=8, seconds=1)
            ok, msg = _validate_dine_flash_qr_time(
                "2026-06-11",
                "13:00:00",
                "101",
                expiry_minutes=5,
            )
            self.assertFalse(ok)
            self.assertIn("QR expired", msg)


class DineFlashHashedQrTableBookingTests(SimpleTestCase):
    def _vendor(self, vendor_id=101):
        return SimpleNamespace(
            vendor_id=vendor_id,
            name="Test Vendor",
            alias_name="",
            logo=None,
            config=SimpleNamespace(
                qr_expiry_minutes=1,
                use_utilities=False,
                phone_number_enabled=False,
            ),
        )

    @override_settings(PROJECT_NAME="dine_flash")
    @patch("orders.views.render")
    @patch("orders.views._validate_dine_flash_qr_time")
    @patch("orders.views.Vendor.objects")
    @patch("orders.views.project_name", "dine_flash")
    def test_table_booking_accepts_encrypted_qr(
        self,
        mock_vendor_objects,
        mock_validate_qr_time,
        mock_render,
    ):
        from datetime import datetime

        from django.http import HttpResponse
        from django.test import RequestFactory

        from orders.views import table_booking

        mock_validate_qr_time.return_value = (True, None)

        fixed_now = datetime(2026, 6, 11, 18, 13, 37)
        params = {
            "vendor_id": "101",
            "qr_date": "2026-06-11",
            "qr_time": "18:13:37",
            "qr_expiry_minutes": "1",
        }
        encrypted = _encrypt_qr_payload_for_test(params)

        vendor = self._vendor(101)
        mock_vendor_objects.select_related.return_value.filter.return_value.first.return_value = (
            vendor
        )
        mock_render.return_value = HttpResponse("ok")

        with patch("orders.views.timezone.localtime", return_value=fixed_now):
            request = RequestFactory().get(f"/dine_flash/table_booking/?data={encrypted}")
            response = table_booking(request)

        self.assertEqual(response.status_code, 200)
        mock_render.assert_called_once()
        context = mock_render.call_args[0][2]
        self.assertEqual(context["vendor_id"], "101")
        self.assertEqual(context["QR_DATE"], "2026-06-11")
        self.assertEqual(context["QR_TIME"], "18:13:37")

    @patch("orders.views.project_name", "dine_flash")
    def test_table_booking_rejects_invalid_hash(self):
        from django.test import RequestFactory

        from orders.views import table_booking

        invalid_hash = "b" * 64
        request = RequestFactory().get(f"/dine_flash/table_booking/?data={invalid_hash}")
        response = table_booking(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"QR expired", response.content)

    @patch("orders.views.project_name", "dine_flash")
    def test_table_booking_rejects_unreadable_data(self):
        from django.test import RequestFactory

        from orders.views import table_booking

        request = RequestFactory().get("/dine_flash/table_booking/?data=abc123")
        response = table_booking(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"QR expired", response.content)

    @patch("orders.views.render")
    @patch("orders.views.project_name", "food_flash")
    def test_table_booking_ignores_hash_on_non_dine_flash(self, mock_render):
        from django.http import HttpResponse
        from django.test import RequestFactory

        from orders.views import table_booking

        mock_render.return_value = HttpResponse("ok")

        params = {
            "vendor_id": "101",
            "qr_date": "2026-06-11",
            "qr_time": "18:13:37",
            "qr_expiry_minutes": "1",
        }
        encrypted = _encrypt_qr_payload_for_test(params)
        request = RequestFactory().get(f"/food_flash/table_booking/?data={encrypted}")
        response = table_booking(request)

        self.assertEqual(response.status_code, 200)
        mock_render.assert_called_once()
