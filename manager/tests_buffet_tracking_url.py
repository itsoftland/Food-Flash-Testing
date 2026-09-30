"""
Dine Flash Buffet manager tracking_url tests.

Additive response field only — existing Buffet customer tracking contract:
/dine_flash_buffet/home/?token_no=<token_no>&vendor_id=<vendor_id>
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from django.test import SimpleTestCase, override_settings
from django.urls import NoReverseMatch
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.buffet.api_helpers import build_buffet_tracking_url
from orders.buffet.order_create import BuffetOrderCreateStatus


def _manager_vendor(vendor_id="800706"):
    return SimpleNamespace(
        id=1,
        vendor_id=vendor_id,
        name="Buffet Outlet",
        location_id="LOC1",
    )


EXPECTED_TRACKING_URL = (
    "https://example.test/dine_flash_buffet/home/?token_no=42&vendor_id=800706"
)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuildBuffetTrackingUrlTests(SimpleTestCase):
    def test_builds_absolute_url_with_token_no_and_vendor_id_only(self):
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f"https://example.test{path}"
        )
        vendor = _manager_vendor("800706")

        with patch(
            "orders.buffet.api_helpers.reverse",
            return_value="/dine_flash_buffet/home/",
        ):
            url = build_buffet_tracking_url(request, vendor, 42)

        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "example.test")
        self.assertEqual(parsed.path, "/dine_flash_buffet/home/")
        qs = parse_qs(parsed.query)
        self.assertEqual(qs, {"token_no": ["42"], "vendor_id": ["800706"]})
        self.assertNotIn("location_id", qs)
        self.assertNotIn("booking_id", qs)

    def test_fallback_path_when_reverse_fails(self):
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f"https://example.test{path}"
        )
        vendor = _manager_vendor("800706")

        with patch(
            "orders.buffet.api_helpers.reverse",
            side_effect=NoReverseMatch("no reverse"),
        ):
            url = build_buffet_tracking_url(request, vendor, 7)

        self.assertTrue(
            url.startswith("https://example.test/dine_flash_buffet/home/?")
        )
        qs = parse_qs(urlparse(url).query)
        self.assertEqual(qs["token_no"], ["7"])
        self.assertEqual(qs["vendor_id"], ["800706"])


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetCreateOrderTrackingUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_success_includes_tracking_url_and_keeps_existing_fields(self):
        from manager import buffet_views
        from manager.buffet_views import buffet_create_order

        vendor = _manager_vendor()
        user = MagicMock()
        profile = MagicMock()
        profile.id = 10
        profiles = MagicMock()
        profiles.order_by.return_value.first.return_value = profile
        user.profile_roles = profiles
        user.username = "mgr"

        request = self.factory.post(
            "/dine_flash_buffet/manager/api/buffet_create_order/",
            {
                "items": [{"utility_id": 1, "quantity": 1}],
                "table_number": "5",
            },
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
        ) as mock_create, patch(
            "manager.buffet_views.build_buffet_tracking_url",
            return_value=EXPECTED_TRACKING_URL,
        ) as mock_build:
            response = buffet_create_order(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data
        self.assertEqual(data["message"], "Order created successfully by manager.")
        self.assertEqual(data["order_id"], 99)
        self.assertEqual(data["token_no"], 42)
        self.assertEqual(data["table_number"], "5")
        self.assertEqual(data["items_count"], 2)
        self.assertEqual(data["tracking_url"], EXPECTED_TRACKING_URL)
        mock_create.assert_called_once()
        args, _kwargs = mock_build.call_args
        self.assertIs(args[1], vendor)
        self.assertEqual(args[2], 42)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetUtilitiesOrdersSummaryTrackingUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_orders_include_per_order_tracking_url(self):
        from manager import buffet_views
        from manager.buffet_views import buffet_utilities_orders_summary

        vendor = _manager_vendor()
        user = MagicMock()
        user.username = "util"

        profile = MagicMock()
        profile.role = "outlet_manager"
        profile.vendor = vendor

        request = self.factory.get(
            "/dine_flash_buffet/manager/api/buffet_utilities_orders_summary/"
        )
        force_authenticate(request, user=user)

        orders_payload = [
            {
                "token_no": 42,
                "booking_id": 123,
                "table_no": "5",
                "submitted_at": "2026-09-29T10:00:00",
                "tracking_url": EXPECTED_TRACKING_URL,
                "unread_message_count": 0,
                "utilities": [{"id": 1, "name": "Grill", "lines": []}],
            }
        ]

        with patch.object(buffet_views, "project_name", "dine_flash_buffet"), patch(
            "manager.buffet_views.get_manager_vendor", return_value=vendor
        ), patch(
            "manager.buffet_views.UserProfile.objects"
        ) as mock_profiles, patch(
            "manager.buffet_views._buffet_all_assigned_tokens_response",
            return_value=orders_payload,
        ) as mock_summary:
            mock_profiles.select_related.return_value.prefetch_related.return_value.filter.return_value.order_by.return_value.first.return_value = (
                profile
            )
            response = buffet_utilities_orders_summary(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["orders"], orders_payload)
        self.assertEqual(
            response.data["orders"][0]["tracking_url"],
            EXPECTED_TRACKING_URL,
        )
        mock_summary.assert_called_once()
        self.assertEqual(len(mock_summary.call_args.args), 4)

    def test_helper_used_when_building_order_rows(self):
        from manager.buffet_views import _buffet_all_assigned_tokens_response

        vendor = _manager_vendor()
        profile = MagicMock()
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f"https://example.test{path}"
        )
        order = SimpleNamespace(
            id=123,
            token_no=42,
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
            return_value=EXPECTED_TRACKING_URL,
        ) as mock_build, patch(
            "manager.views._build_unread_notifications_map",
            return_value={123: 2},
        ) as mock_unread:
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
        self.assertEqual(row["token_no"], 42)
        self.assertEqual(row["booking_id"], 123)
        self.assertEqual(row["table_no"], "5")
        self.assertEqual(row["submitted_at"], "2026-09-29T10:00:00")
        self.assertEqual(row["tracking_url"], EXPECTED_TRACKING_URL)
        self.assertEqual(row["unread_message_count"], 2)
        self.assertEqual(
            row["utilities"],
            [{"id": 1, "name": "Grill", "lines": [{"id": 9}]}],
        )
        mock_build.assert_called_once_with(request, vendor, 42)
        mock_unread.assert_called_once_with(vendor, [123])
