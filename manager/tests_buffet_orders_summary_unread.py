"""
Dine Flash Buffet: unread_message_count on buffet_utilities_orders_summary GET.

Verifies per-order unread customer chat counts via the shared unread map helper,
without changing chat_history, is_read, FCM, or the legacy POST notify path.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate


def _manager_vendor(vendor_id="800706"):
    return SimpleNamespace(
        id=1,
        vendor_id=vendor_id,
        name="Buffet Outlet",
        location_id="LOC1",
    )


def _order_row(
    order_id,
    token_no,
    table_no="5",
    submitted_at="2026-09-29T10:00:00",
    customer_name="Guest",
    phone_number="9876543210",
):
    return SimpleNamespace(
        id=order_id,
        token_no=token_no,
        customer_name=customer_name,
        phone_number=phone_number,
        table_booking_no=table_no,
        created_at=SimpleNamespace(isoformat=lambda: submitted_at),
    )


UTILITIES = [{"id": 1, "name": "Grill", "lines": [{"status": "preparing", "quantity": 1}]}]
TRACKING = "https://example.test/dine_flash_buffet/home/?token_no=42&vendor_id=800706"


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetOrdersSummaryUnreadCountTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.vendor = _manager_vendor()
        self.profile = MagicMock()
        self.profile.role = "outlet_manager"
        self.request = SimpleNamespace(
            build_absolute_uri=lambda path: f"https://example.test{path}"
        )

    def _run_helper(self, orders, unread_map, hide_delivered=False):
        from manager.buffet_views import _buffet_all_assigned_tokens_response

        order_ids = [o.id for o in orders]
        with patch(
            "manager.buffet_views.get_vendor_business_day_range",
            return_value=("start", "end"),
        ), patch(
            "manager.buffet_views._buffet_assigned_items_queryset"
        ) as mock_qs, patch(
            "manager.buffet_views.Order.objects"
        ) as mock_orders, patch(
            "manager.buffet_views._group_buffet_lines_by_utility",
            return_value=UTILITIES,
        ), patch(
            "manager.buffet_views.build_buffet_tracking_url",
            return_value=TRACKING,
        ), patch(
            "manager.views._build_unread_notifications_map",
            return_value=unread_map,
        ) as mock_unread:
            base_qs = MagicMock()
            base_qs.values_list.return_value.distinct.return_value = order_ids
            filtered = MagicMock()
            filtered.order_by.return_value = filtered
            base_qs.filter.return_value = filtered
            mock_qs.return_value = base_qs
            mock_orders.filter.return_value.order_by.return_value = orders

            payload = _buffet_all_assigned_tokens_response(
                self.vendor,
                self.profile,
                hide_delivered=hide_delivered,
                request=self.request,
            )

        return payload, mock_unread

    def test_unread_count_for_order_with_messages(self):
        order = _order_row(123, 42)
        payload, mock_unread = self._run_helper([order], {123: 3})

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["unread_message_count"], 3)
        self.assertEqual(payload[0]["booking_id"], 123)
        mock_unread.assert_called_once_with(self.vendor, [123])

    def test_zero_when_no_unread_messages(self):
        order = _order_row(123, 42)
        payload, mock_unread = self._run_helper([order], {})

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["unread_message_count"], 0)
        mock_unread.assert_called_once_with(self.vendor, [123])

    def test_independent_counts_for_multiple_orders(self):
        orders = [
            _order_row(10, 1, customer_name="Alice"),
            _order_row(20, 2, customer_name="Bob"),
            _order_row(30, 3, customer_name="Carol"),
        ]
        payload, mock_unread = self._run_helper(
            orders, {10: 2, 20: 0, 30: 5}
        )

        self.assertEqual(len(payload), 3)
        by_id = {row["booking_id"]: row["unread_message_count"] for row in payload}
        self.assertEqual(by_id, {10: 2, 20: 0, 30: 5})
        by_name = {row["booking_id"]: row["customer_name"] for row in payload}
        self.assertEqual(by_name, {10: "Alice", 20: "Bob", 30: "Carol"})
        # Single bulk aggregation — not one call per order
        mock_unread.assert_called_once_with(self.vendor, [10, 20, 30])

    def test_customer_name_none_and_empty_preserved(self):
        orders = [
            _order_row(10, 1, customer_name=None),
            _order_row(20, 2, customer_name=""),
            _order_row(30, 3, customer_name="Dana"),
        ]
        payload, mock_unread = self._run_helper(orders, {30: 1})

        self.assertEqual(len(payload), 3)
        self.assertIsNone(payload[0]["customer_name"])
        self.assertEqual(payload[1]["customer_name"], "")
        self.assertEqual(payload[2]["customer_name"], "Dana")
        self.assertEqual(payload[0]["unread_message_count"], 0)
        self.assertEqual(payload[2]["unread_message_count"], 1)
        mock_unread.assert_called_once_with(self.vendor, [10, 20, 30])

    def test_phone_number_none_and_empty_preserved(self):
        orders = [
            _order_row(10, 1, phone_number=None),
            _order_row(20, 2, phone_number=""),
            _order_row(30, 3, phone_number="9876543210"),
        ]
        payload, mock_unread = self._run_helper(orders, {30: 1})

        self.assertEqual(len(payload), 3)
        self.assertIsNone(payload[0]["phone_number"])
        self.assertEqual(payload[1]["phone_number"], "")
        self.assertEqual(payload[2]["phone_number"], "9876543210")
        self.assertEqual(payload[0]["unread_message_count"], 0)
        self.assertEqual(payload[2]["unread_message_count"], 1)
        mock_unread.assert_called_once_with(self.vendor, [10, 20, 30])

    def test_existing_response_fields_preserved(self):
        order = _order_row(
            123,
            42,
            table_no="7",
            submitted_at="2026-09-29T11:00:00",
            customer_name="John",
            phone_number="9876543210",
        )
        payload, _ = self._run_helper([order], {123: 1})

        row = payload[0]
        self.assertEqual(
            set(row.keys()),
            {
                "token_no",
                "booking_id",
                "customer_name",
                "phone_number",
                "table_no",
                "submitted_at",
                "tracking_url",
                "unread_message_count",
                "utilities",
            },
        )
        self.assertEqual(row["token_no"], 42)
        self.assertEqual(row["booking_id"], 123)
        self.assertEqual(row["customer_name"], "John")
        self.assertEqual(row["phone_number"], "9876543210")
        self.assertEqual(row["table_no"], "7")
        self.assertEqual(row["submitted_at"], "2026-09-29T11:00:00")
        self.assertEqual(row["tracking_url"], TRACKING)
        self.assertEqual(row["utilities"], UTILITIES)
        self.assertEqual(row["unread_message_count"], 1)

    def test_summary_get_returns_orders_with_unread_field(self):
        from manager import buffet_views
        from manager.buffet_views import buffet_utilities_orders_summary

        user = MagicMock()
        user.username = "mgr"
        profile = MagicMock()
        profile.role = "outlet_manager"

        request = self.factory.get(
            "/dine_flash_buffet/manager/api/buffet_utilities_orders_summary/"
        )
        force_authenticate(request, user=user)

        orders_payload = [
            {
                "token_no": 42,
                "booking_id": 123,
                "customer_name": "John",
                "phone_number": "9876543210",
                "table_no": "5",
                "submitted_at": "2026-09-29T10:00:00",
                "tracking_url": TRACKING,
                "unread_message_count": 2,
                "utilities": UTILITIES,
            }
        ]

        with patch.object(buffet_views, "project_name", "dine_flash_buffet"), patch(
            "manager.buffet_views.get_manager_vendor", return_value=self.vendor
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
        self.assertEqual(response.data["message"], "Buffet utilities summary.")
        self.assertEqual(response.data["orders"], orders_payload)
        self.assertEqual(response.data["orders"][0]["unread_message_count"], 2)
        self.assertEqual(response.data["orders"][0]["customer_name"], "John")
        self.assertEqual(response.data["orders"][0]["phone_number"], "9876543210")
        mock_summary.assert_called_once()

    def test_legacy_post_notify_path_unaffected(self):
        """POST with utility_ids + token_no must not go through summary builder."""
        from manager import buffet_views
        from manager.buffet_views import buffet_utilities_orders_summary

        user = MagicMock()
        user.username = "mgr"
        profile = MagicMock()
        profile.role = "outlet_manager"
        profile.assigned_utilities = MagicMock()
        profile.assigned_utilities.all.return_value = []

        order = MagicMock()
        order.id = 99
        order.token_no = 42
        order.table_booking_no = "5"

        request = self.factory.post(
            "/dine_flash_buffet/manager/api/buffet_utilities_orders_summary/",
            {"utility_ids": [1], "token_no": 42},
            format="json",
        )
        force_authenticate(request, user=user)

        utilities_payload = [
            {"id": 1, "name": "Grill", "lines": [{"status": "ready", "quantity": 1}]}
        ]

        with patch.object(buffet_views, "project_name", "dine_flash_buffet"), patch(
            "manager.buffet_views.get_manager_vendor", return_value=self.vendor
        ), patch(
            "manager.buffet_views.UserProfile.objects"
        ) as mock_profiles, patch(
            "manager.buffet_views._buffet_all_assigned_tokens_response"
        ) as mock_summary, patch(
            "manager.buffet_views.get_vendor_business_day_range",
            return_value=("start", "end"),
        ), patch(
            "manager.buffet_views.Order.objects"
        ) as mock_orders, patch(
            "manager.buffet_views.Utility.objects"
        ) as mock_utils, patch(
            "manager.buffet_views._buffet_selected_utilities_status_payload",
            return_value=(utilities_payload, None),
        ), patch(
            "manager.buffet_views._human_buffet_status_message",
            return_value="Your Order 42 — Grill: ready",
        ), patch(
            "manager.buffet_views._buffet_vendor_chat_alias",
            return_value="Buffet",
        ), patch(
            "manager.buffet_views.ChatMessage.objects.create"
        ), patch(
            "manager.buffet_views.send_order_update"
        ), patch(
            "manager.buffet_views.notify_web_push"
        ):
            mock_profiles.select_related.return_value.prefetch_related.return_value.filter.return_value.order_by.return_value.first.return_value = (
                profile
            )
            mock_utils.filter.return_value.values_list.return_value = [1]
            mock_orders.filter.return_value.first.return_value = order

            response = buffet_utilities_orders_summary(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Station notification sent.")
        self.assertEqual(response.data["token_no"], 42)
        self.assertEqual(response.data["booking_id"], 99)
        self.assertEqual(response.data["utilities"], utilities_payload)
        self.assertNotIn("orders", response.data)
        self.assertNotIn("unread_message_count", response.data)
        self.assertNotIn("customer_name", response.data)
        mock_summary.assert_not_called()
