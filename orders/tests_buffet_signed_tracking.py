"""
Dine Flash Buffet tracking token unit tests.

Covers:
- Signing and unsigning round trips
- Tampered tokens rejected
- Malformed payloads rejected
- Missing identifiers rejected
- Dedicated Buffet salt used (isolation from Dine Flash)
- URL builder
- Home view resolution with ?t=
- API responses include encrypted_tracking_url alongside tracking_url
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import AnonymousUser
from django.core import signing
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.buffet.buffet_tracking_token import (
    BUFFET_TRACKING_TOKEN_SALT,
    build_buffet_encrypted_tracking_url,
    sign_buffet_tracking_token,
    unsign_buffet_tracking_token,
)
from orders.buffet.order_create import BuffetOrderCreateStatus
from orders.dine_flash_tracking_token import (
    sign_dine_flash_tracking_token,
    unsign_dine_flash_tracking_token,
)


class BuffetTrackingTokenTests(SimpleTestCase):
    def test_sign_and_unsign_round_trip(self):
        token = sign_buffet_tracking_token(vendor_id="800706", token_no=42)
        payload = unsign_buffet_tracking_token(token)
        self.assertEqual(
            payload,
            {
                "vendor_id": "800706",
                "token_no": "42",
            },
        )

    def test_tampered_token_rejected(self):
        token = sign_buffet_tracking_token(vendor_id="800706", token_no=42)
        self.assertIsNone(unsign_buffet_tracking_token(token[:-4] + "xxxx"))

    def test_malformed_payload_rejected(self):
        # Non-dict payload
        token = signing.dumps("raw_string", salt=BUFFET_TRACKING_TOKEN_SALT)
        self.assertIsNone(unsign_buffet_tracking_token(token))

        # Dict missing token_no
        token_missing = signing.dumps({"vendor_id": "800706"}, salt=BUFFET_TRACKING_TOKEN_SALT)
        self.assertIsNone(unsign_buffet_tracking_token(token_missing))

        # Dict missing vendor_id
        token_missing_v = signing.dumps({"token_no": "42"}, salt=BUFFET_TRACKING_TOKEN_SALT)
        self.assertIsNone(unsign_buffet_tracking_token(token_missing_v))

    def test_empty_or_none_rejected(self):
        self.assertIsNone(unsign_buffet_tracking_token(""))
        self.assertIsNone(unsign_buffet_tracking_token(None))
        self.assertIsNone(unsign_buffet_tracking_token("   "))

    def test_salt_isolation_from_dine_flash(self):
        buffet_token = sign_buffet_tracking_token(vendor_id="800706", token_no="42")
        self.assertIsNone(unsign_dine_flash_tracking_token(buffet_token))

        dine_token = sign_dine_flash_tracking_token(
            vendor_id="800706", location_id="LOC1", booking_id="1", booking_no="42"
        )
        self.assertIsNone(unsign_buffet_tracking_token(dine_token))

    def test_build_buffet_encrypted_tracking_url(self):
        vendor = SimpleNamespace(vendor_id="800706")
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f"https://example.test{path}"
        )
        with patch("orders.buffet.buffet_tracking_token.reverse", return_value="/dine_flash_buffet/home/"):
            url = build_buffet_encrypted_tracking_url(request, vendor, 42)

        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "example.test")
        self.assertEqual(parsed.path, "/dine_flash_buffet/home/")
        qs = parse_qs(parsed.query)
        self.assertIn("t", qs)
        self.assertNotIn("vendor_id", qs)
        self.assertNotIn("token_no", qs)
        token = qs["t"][0]
        payload = unsign_buffet_tracking_token(token)
        self.assertEqual(payload, {"vendor_id": "800706", "token_no": "42"})


class DineFlashBuffetHomeTrackingTokenTests(SimpleTestCase):
    @override_settings(PROJECT_NAME="dine_flash_buffet")
    @patch("orders.views.project_name", "dine_flash_buffet")
    @patch("orders.views._buffet_order_tracking_exists", return_value=True)
    @patch("orders.views.get_vendor")
    def test_home_accepts_valid_signed_buffet_token(
        self, mock_get_vendor, mock_tracking_exists
    ):
        from orders.views import home

        mock_get_vendor.return_value = SimpleNamespace(vendor_id="800706")
        token = sign_buffet_tracking_token(vendor_id="800706", token_no="42")
        request = RequestFactory().get(f"/dine_flash_buffet/home/?t={token}")
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 200)
        mock_get_vendor.assert_called_once_with("800706")
        mock_tracking_exists.assert_called_once_with("800706", "42")
        content = response.content.decode()
        self.assertIn("window.BUFFET_TRACKING_BOOTSTRAP", content)
        self.assertIn('"vendor_id": "800706"', content)
        self.assertIn('"token_no": "42"', content)
        self.assertNotIn("window.DINE_FLASH_TRACKING_BOOTSTRAP", content)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    @patch("orders.views.project_name", "dine_flash_buffet")
    def test_home_rejects_invalid_signed_buffet_token(self):
        from orders.views import home

        request = RequestFactory().get("/dine_flash_buffet/home/?t=invalid-token")
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid tracking link", response.content)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    @patch("orders.views.project_name", "dine_flash_buffet")
    def test_home_rejects_empty_signed_buffet_token(self):
        from orders.views import home

        request = RequestFactory().get("/dine_flash_buffet/home/?t=")
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid tracking link", response.content)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    @patch("orders.views.project_name", "dine_flash_buffet")
    @patch("orders.views.get_vendor", side_effect=Exception("Vendor not found"))
    def test_home_rejects_nonexistent_vendor(self, mock_get_vendor):
        from orders.views import home

        token = sign_buffet_tracking_token(vendor_id="999999", token_no="42")
        request = RequestFactory().get(f"/dine_flash_buffet/home/?t={token}")
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid tracking link", response.content)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    @patch("orders.views.project_name", "dine_flash_buffet")
    @patch("orders.views.get_vendor")
    @patch("orders.views._buffet_order_tracking_exists", return_value=False)
    def test_home_rejects_nonexistent_order_or_other_vendor(
        self, mock_tracking_exists, mock_get_vendor
    ):
        from orders.views import home

        mock_get_vendor.return_value = SimpleNamespace(vendor_id="800706")
        token = sign_buffet_tracking_token(vendor_id="800706", token_no="999")
        request = RequestFactory().get(f"/dine_flash_buffet/home/?t={token}")
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid tracking link", response.content)
        mock_tracking_exists.assert_called_once_with("800706", "999")

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    @patch("orders.views.project_name", "dine_flash_buffet")
    def test_normal_buffet_query_params_unaffected(self):
        from orders.views import home

        request = RequestFactory().get(
            "/dine_flash_buffet/home/?token_no=42&vendor_id=800706"
        )
        request.user = AnonymousUser()

        response = home(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("window.BUFFET_TRACKING_BOOTSTRAP", content)
        self.assertNotIn("window.DINE_FLASH_TRACKING_BOOTSTRAP", content)


class BuffetApiEncryptedTrackingUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_buffet_create_order_adds_encrypted_tracking_url(self):
        from manager import buffet_views
        from manager.buffet_views import buffet_create_order

        vendor = SimpleNamespace(id=1, vendor_id="800706", name="Buffet", location_id="LOC1")
        user = MagicMock()
        profile = MagicMock()
        profile.id = 10
        profiles = MagicMock()
        profiles.order_by.return_value.first.return_value = profile
        user.profile_roles = profiles
        user.username = "mgr"

        request = self.factory.post(
            "/dine_flash_buffet/manager/api/buffet_create_order/",
            {"items": [{"utility_id": 1, "quantity": 1}], "table_number": "5"},
            format="json",
        )
        force_authenticate(request, user=user)

        order = SimpleNamespace(id=99, token_no=42)
        with patch.object(buffet_views, "project_name", "dine_flash_buffet"), patch(
            "manager.buffet_views.get_manager_vendor", return_value=vendor
        ), patch(
            "manager.buffet_views.create_buffet_order",
            return_value=SimpleNamespace(
                status=BuffetOrderCreateStatus.CREATED,
                order=order,
                created_item_ids=[1, 2],
                error_message=None,
            ),
        ), patch(
            "manager.buffet_views.build_buffet_tracking_url",
            return_value="https://example.test/normal_track",
        ), patch(
            "manager.buffet_views.build_buffet_encrypted_tracking_url",
            return_value="https://example.test/dine_flash_buffet/home/?t=mocktoken",
        ) as mock_encrypted:
            response = buffet_create_order(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data
        self.assertEqual(data["tracking_url"], "https://example.test/normal_track")
        self.assertEqual(
            data["encrypted_tracking_url"],
            "https://example.test/dine_flash_buffet/home/?t=mocktoken",
        )
        mock_encrypted.assert_called_once()
        call_args = mock_encrypted.call_args[0]
        self.assertIs(call_args[1], vendor)
        self.assertEqual(call_args[2], 42)

    def test_buffet_all_assigned_tokens_response_adds_encrypted_tracking_url(self):
        from manager.buffet_views import _buffet_all_assigned_tokens_response

        vendor = SimpleNamespace(id=1, vendor_id="800706")
        profile = MagicMock()
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f"https://example.test{path}"
        )
        order = SimpleNamespace(
            id=123,
            token_no=42,
            customer_name="John",
            phone_number="9876543210",
            table_booking_no="5",
            created_at=SimpleNamespace(isoformat=lambda: "2026-09-29T10:00:00"),
        )

        with patch(
            "manager.buffet_views.get_vendor_business_day_range",
            return_value=("start", "end"),
        ), patch(
            "manager.buffet_views._buffet_assigned_items_queryset"
        ) as mock_qs, patch(
            "manager.buffet_views.Order.objects"
        ) as mock_orders, patch(
            "manager.buffet_views._group_buffet_lines_by_utility",
            return_value=[{"id": 1, "name": "Grill", "lines": [{"id": 9}]}],
        ), patch(
            "manager.buffet_views.build_buffet_tracking_url",
            return_value="https://example.test/normal_track",
        ) as mock_build, patch(
            "manager.buffet_views.build_buffet_encrypted_tracking_url",
            return_value="https://example.test/signed_track",
        ) as mock_build_enc, patch(
            "manager.views._build_unread_notifications_map",
            return_value={123: 2},
        ):
            base_qs = MagicMock()
            base_qs.values_list.return_value.distinct.return_value = [123]
            filtered = MagicMock()
            filtered.order_by.return_value = filtered
            base_qs.filter.return_value = filtered
            mock_qs.return_value = base_qs
            mock_orders.filter.return_value.order_by.return_value = [order]

            payload = _buffet_all_assigned_tokens_response(
                vendor, profile, hide_delivered=False, request=request
            )

        self.assertEqual(len(payload), 1)
        row = payload[0]
        self.assertEqual(row["tracking_url"], "https://example.test/normal_track")
        self.assertEqual(row["encrypted_tracking_url"], "https://example.test/signed_track")
        mock_build.assert_called_once_with(request, vendor, 42)
        mock_build_enc.assert_called_once_with(request, vendor, 42)
