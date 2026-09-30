"""
Dine Flash Buffet: buffet_conversation_orders GET API.

Additive OM conversation-list coverage. Does not change chat_history,
order-summary, tracking helpers, unread helper, or ChatMessage writes.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from vendors.models import (
    AdminOutlet,
    ChatMessage,
    Order,
    UserProfile,
    Vendor,
    VendorConfig,
)


def _create_buffet_vendor(suffix, customer_id, vendor_id):
    company = User.objects.create_user(username=f"co_{suffix}", password="pass")
    outlet = AdminOutlet.objects.create(
        user=company,
        customer_name=f"Co {suffix}",
        customer_id=customer_id,
        authentication_status="Approve",
    )
    vendor = Vendor.objects.create(
        admin_outlet=outlet,
        name=f"Outlet {suffix}",
        alias_name=suffix[:8],
        location="L1",
        vendor_id=vendor_id,
        location_id=suffix[:4].upper(),
        menus="[]",
    )
    VendorConfig.objects.create(vendor=vendor)
    return outlet, vendor


def _create_manager(outlet, vendor, username, role="outlet_manager"):
    user = User.objects.create_user(username=username, password="secret123")
    profile = UserProfile.objects.create(
        user=user,
        name=username,
        role=role,
        admin_outlet=outlet,
        vendor=vendor,
    )
    return user, profile


def _create_order(vendor, token_no, table_no="5", customer_name="John"):
    order = Order.objects.create(
        vendor=vendor,
        token_no=token_no,
        status="created",
        table_booking_no=table_no,
        customer_name=customer_name,
        updated_by="customer",
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now())
    order.refresh_from_db()
    return order


def _chat(
    vendor,
    order,
    sender,
    text,
    created_date=None,
    is_read=False,
    booking_id=None,
    token_no=None,
):
    return ChatMessage.objects.create(
        vendor=vendor,
        token_no=token_no if token_no is not None else order.token_no,
        booking_id=order.id if booking_id is None and order is not None else booking_id,
        booking_no=order.table_booking_no if order is not None else None,
        created_date=created_date or timezone.now().date(),
        sender=sender,
        is_send=True,
        is_read=is_read,
        message_text=text,
    )


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetConversationOrdersTests(TestCase):
    def setUp(self):
        # Module-level project_name is bound at import; patch like other Buffet view tests.
        self._project_patcher = patch(
            "manager.buffet_views.project_name", "dine_flash_buffet"
        )
        self._project_patcher.start()
        self.addCleanup(self._project_patcher.stop)

        self.client = APIClient()
        self.outlet, self.vendor = _create_buffet_vendor("conv", 98001, 980001)
        self.other_outlet, self.other_vendor = _create_buffet_vendor(
            "other", 98002, 980002
        )
        self.manager_user, _ = _create_manager(
            self.outlet, self.vendor, "om_conv"
        )
        self.other_manager, _ = _create_manager(
            self.other_outlet, self.other_vendor, "om_other_conv"
        )
        self.order = _create_order(self.vendor, 882, table_no="5", customer_name="John")
        self.order_b = _create_order(
            self.vendor, 883, table_no="7", customer_name="Alice"
        )
        self.other_order = _create_order(
            self.other_vendor, 882, table_no="9", customer_name="Other"
        )
        self.url = reverse("manager:buffet_conversation_orders")
        self.client.force_authenticate(user=self.manager_user)
        self.today = timezone.now().date()

    def test_authenticated_manager_can_call(self):
        _chat(self.vendor, self.order, "user", "Hello", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["message"], "Conversation orders retrieved successfully.")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(len(resp.data["orders"]), 1)

    @override_settings(PROJECT_NAME="dine_flash")
    def test_non_buffet_flavour_gated(self):
        with patch("manager.buffet_views.project_name", "dine_flash"):
            factory = APIRequestFactory()
            request = factory.get("/manager/api/buffet_conversation_orders/")
            force_authenticate(request, user=self.manager_user)
            from manager import buffet_views

            resp = buffet_views.buffet_conversation_orders(request)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_vendor_isolation(self):
        _chat(self.vendor, self.order, "user", "Mine", created_date=self.today)
        _chat(self.other_vendor, self.other_order, "user", "Secret", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        texts = [r["latest_message"] for r in resp.data["orders"]]
        self.assertIn("Mine", texts)
        self.assertNotIn("Secret", texts)
        for row in resp.data["orders"]:
            self.assertEqual(row["booking_id"], self.order.id)

    def test_uses_chat_created_date_not_business_day_range(self):
        """Regression: conversation list follows chat_history date convention."""
        _chat(self.vendor, self.order, "user", "Today", created_date=self.today)
        with patch(
            "manager.buffet_views.get_vendor_current_date",
            return_value=self.today,
        ) as mock_chat_date, patch(
            "manager.buffet_views.get_vendor_business_day_range"
        ) as mock_biz:
            resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        mock_chat_date.assert_called()
        mock_biz.assert_not_called()

    def test_previous_day_conversations_excluded(self):
        yesterday = self.today - timedelta(days=1)
        _chat(self.vendor, self.order, "user", "Old", created_date=yesterday)
        _chat(self.vendor, self.order_b, "manager", "New", created_date=self.today)
        with patch(
            "manager.buffet_views.get_vendor_current_date", return_value=self.today
        ):
            resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["orders"][0]["booking_id"], self.order_b.id)
        self.assertEqual(resp.data["orders"][0]["latest_message"], "New")

    def test_historical_conversations_excluded(self):
        old = self.today - timedelta(days=30)
        _chat(self.vendor, self.order, "user", "Ancient", created_date=old)
        with patch(
            "manager.buffet_views.get_vendor_current_date", return_value=self.today
        ):
            resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 0)
        self.assertEqual(resp.data["orders"], [])

    def test_customer_only_included(self):
        _chat(self.vendor, self.order, "user", "Hello", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["orders"][0]["latest_message_sender"], "user")

    def test_manager_only_included(self):
        _chat(self.vendor, self.order, "manager", "Hi", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["orders"][0]["latest_message_sender"], "manager")

    def test_customer_and_manager_included(self):
        _chat(self.vendor, self.order, "user", "Hello", created_date=self.today)
        _chat(self.vendor, self.order, "manager", "Hi", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["orders"][0]["booking_id"], self.order.id)

    def test_system_only_excluded(self):
        _chat(self.vendor, self.order, "system", '{"type":"buffet_item_update"}', created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 0)

    def test_system_plus_human_included(self):
        _chat(self.vendor, self.order, "system", '{"type":"buffet_item_update"}', created_date=self.today)
        _chat(self.vendor, self.order, "user", "Where is it?", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["orders"][0]["latest_message"], "Where is it?")
        self.assertEqual(resp.data["orders"][0]["latest_message_sender"], "user")

    def test_multiple_messages_one_order_entry(self):
        _chat(self.vendor, self.order, "user", "One", created_date=self.today)
        _chat(self.vendor, self.order, "user", "Two", created_date=self.today)
        _chat(self.vendor, self.order, "manager", "Three", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(len(resp.data["orders"]), 1)

    def test_multiple_orders_separate_entries(self):
        _chat(self.vendor, self.order, "user", "A", created_date=self.today)
        _chat(self.vendor, self.order_b, "manager", "B", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 2)
        ids = {r["booking_id"] for r in resp.data["orders"]}
        self.assertEqual(ids, {self.order.id, self.order_b.id})

    def test_booking_id_token_customer_table_fields(self):
        _chat(self.vendor, self.order, "user", "Hi", created_date=self.today)
        resp = self.client.get(self.url)
        row = resp.data["orders"][0]
        self.assertEqual(row["booking_id"], self.order.id)
        self.assertEqual(row["token_no"], 882)
        self.assertEqual(row["customer_name"], "John")
        self.assertEqual(row["table_no"], "5")

    def test_null_and_empty_customer_name(self):
        null_order = _create_order(self.vendor, 100, customer_name=None)
        empty_order = _create_order(self.vendor, 101, customer_name="")
        _chat(self.vendor, null_order, "user", "n", created_date=self.today)
        _chat(self.vendor, empty_order, "user", "e", created_date=self.today)
        resp = self.client.get(self.url)
        by_token = {r["token_no"]: r for r in resp.data["orders"]}
        self.assertIsNone(by_token[100]["customer_name"])
        self.assertEqual(by_token[101]["customer_name"], "")

    def test_fully_read_still_included(self):
        _chat(
            self.vendor,
            self.order,
            "user",
            "Read me",
            created_date=self.today,
            is_read=True,
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["orders"][0]["unread_message_count"], 0)

    def test_unread_message_count(self):
        _chat(self.vendor, self.order, "user", "U1", created_date=self.today, is_read=False)
        _chat(self.vendor, self.order, "user", "U2", created_date=self.today, is_read=False)
        _chat(self.vendor, self.order, "manager", "M", created_date=self.today)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["orders"][0]["unread_message_count"], 2)

    def test_latest_human_message_not_system(self):
        older = timezone.now() - timedelta(minutes=5)
        newer_system = timezone.now() - timedelta(minutes=1)
        human = _chat(self.vendor, self.order, "user", "Human latest", created_date=self.today)
        ChatMessage.objects.filter(pk=human.pk).update(created_at=older)
        system = _chat(
            self.vendor,
            self.order,
            "system",
            '{"type":"buffet_item_update"}',
            created_date=self.today,
        )
        ChatMessage.objects.filter(pk=system.pk).update(created_at=newer_system)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["orders"][0]["latest_message"], "Human latest")
        self.assertEqual(resp.data["orders"][0]["latest_message_sender"], "user")

    def test_ordered_by_latest_human_descending(self):
        older = timezone.now() - timedelta(minutes=10)
        newer = timezone.now()
        m1 = _chat(self.vendor, self.order, "user", "Older conv", created_date=self.today)
        m2 = _chat(self.vendor, self.order_b, "user", "Newer conv", created_date=self.today)
        ChatMessage.objects.filter(pk=m1.pk).update(created_at=older)
        ChatMessage.objects.filter(pk=m2.pk).update(created_at=newer)
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["orders"][0]["booking_id"], self.order_b.id)
        self.assertEqual(resp.data["orders"][1]["booking_id"], self.order.id)

    def test_null_booking_id_ignored(self):
        ChatMessage.objects.create(
            vendor=self.vendor,
            token_no=999,
            booking_id=None,
            created_date=self.today,
            sender="user",
            is_send=True,
            message_text="No booking",
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 0)

    def test_orphan_booking_id_ignored(self):
        ChatMessage.objects.create(
            vendor=self.vendor,
            token_no=999,
            booking_id=999999,
            created_date=self.today,
            sender="user",
            is_send=True,
            message_text="Orphan",
        )
        resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 0)

    def test_same_token_other_day_not_mixed(self):
        yesterday = self.today - timedelta(days=1)
        old_order = _create_order(self.vendor, 882, table_no="old", customer_name="Yday")
        _chat(self.vendor, old_order, "user", "Yesterday", created_date=yesterday)
        _chat(self.vendor, self.order, "user", "Today", created_date=self.today)
        with patch(
            "manager.buffet_views.get_vendor_current_date", return_value=self.today
        ):
            resp = self.client.get(self.url)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["orders"][0]["booking_id"], self.order.id)
        self.assertEqual(resp.data["orders"][0]["latest_message"], "Today")

    def test_tracking_url_present(self):
        _chat(self.vendor, self.order, "user", "Hi", created_date=self.today)
        with patch(
            "manager.buffet_views.build_buffet_tracking_url",
            return_value="https://example.test/track",
        ) as mock_track:
            resp = self.client.get(self.url)
        self.assertEqual(resp.data["orders"][0]["tracking_url"], "https://example.test/track")
        mock_track.assert_called_once()

    def test_empty_result(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 0)
        self.assertEqual(resp.data["orders"], [])

    def test_chat_history_unchanged(self):
        _chat(self.vendor, self.order, "user", "Keep", created_date=self.today, is_read=False)
        with patch(
            "manager.views.get_vendor_current_date", return_value=self.today
        ), patch("manager.views.project_name", "dine_flash_buffet"):
            hist = self.client.get(
                reverse("manager:chat_history"), {"token_no": self.order.token_no}
            )
        self.assertEqual(hist.status_code, status.HTTP_200_OK)
        self.assertTrue(any(m["message_text"] == "Keep" for m in hist.data["messages"]))
        self.assertFalse(
            ChatMessage.objects.filter(
                vendor=self.vendor,
                token_no=self.order.token_no,
                sender="user",
                is_read=False,
            ).exists()
        )

    def test_order_summary_still_uses_business_day_helper(self):
        """Existing summary path still depends on business-day range (unchanged)."""
        from manager.buffet_views import _buffet_all_assigned_tokens_response
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        profile = MagicMock()
        profile.role = "outlet_manager"
        request = SimpleNamespace(
            build_absolute_uri=lambda path: f"https://example.test{path}"
        )
        with patch(
            "manager.buffet_views.get_vendor_business_day_range",
            return_value=(timezone.now(), timezone.now()),
        ) as mock_biz, patch(
            "manager.buffet_views._buffet_assigned_items_queryset"
        ) as mock_qs, patch(
            "manager.views._build_unread_notifications_map", return_value={}
        ):
            qs = MagicMock()
            qs.values_list.return_value.distinct.return_value = []
            mock_qs.return_value = qs
            payload = _buffet_all_assigned_tokens_response(
                self.vendor, profile, False, request
            )
        self.assertEqual(payload, [])
        mock_biz.assert_called_once()


@override_settings(PROJECT_NAME="food_flash")
class BuffetConversationOrdersCrossFlavourTests(TestCase):
    def test_food_flash_returns_not_found(self):
        outlet, vendor = _create_buffet_vendor("ff", 98101, 981001)
        user, _ = _create_manager(outlet, vendor, "ff_mgr")
        factory = APIRequestFactory()
        request = factory.get("/manager/api/buffet_conversation_orders/")
        force_authenticate(request, user=user)
        with patch("manager.buffet_views.project_name", "food_flash"):
            from manager import buffet_views

            resp = buffet_views.buffet_conversation_orders(request)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
