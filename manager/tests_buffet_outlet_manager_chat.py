"""
Dine Flash Buffet Outlet Manager chat backend tests.

Covers existing chat APIs used by the external Buffet OM Android client:
login (smoke), register_android_apk profile link, manager_order_update message,
chat_history by token_no, customer reply ChatMessage + FCM targeting, unread,
cross-vendor isolation, and Buffet-specific FCM role filtering.

Does not introduce new chat APIs or models.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from orders.utils import collect_manager_fcm_tokens, send_to_managers
from vendors.models import (
    AdminOutlet,
    AndroidAPK,
    ChatMessage,
    Order,
    UserProfile,
    Vendor,
    VendorConfig,
)


def _buffet_vendor(pk=1, vendor_id=960001, name="Buffet Outlet"):
    return SimpleNamespace(
        id=pk,
        name=name,
        alias_name="Buffet",
        vendor_id=vendor_id,
        location_id="BA1",
        config=SimpleNamespace(
            vibration_pattern=None,
            vibration_duration=None,
            tv_communication_mode="MQTT",
            mqtt_mode=True,
        ),
    )


def _manager_user(vendor, role="outlet_manager"):
    user = MagicMock()
    user.username = "outlet_mgr"
    profile = MagicMock()
    profile.role = role
    profile.name = "Outlet Manager"
    profile.vendor = vendor
    profile.id = 42
    qs = MagicMock()
    qs.exists.return_value = True
    qs.first.return_value = profile
    user.profile_roles = qs
    return user, profile


def _order(vendor, token_no=42, order_id=100):
    order = MagicMock()
    order.id = order_id
    order.pk = order_id
    order.token_no = token_no
    order.table_booking_no = "T-1"
    order.counter_no = 1
    order.status = "created"
    order.vendor = vendor
    order.notified_at = None
    order.customer_name = "Guest"
    order.phone_number = None
    order.device = None
    order.user_profile = None
    order.updated_by = "customer"
    order.buffet_items = MagicMock()
    order.buffet_items.exclude.return_value = []
    order.buffet_items.select_related.return_value.all.return_value.order_by.return_value = []
    return order


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetManagerOrderUpdateMessageTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.vendor = _buffet_vendor()
        self.user, self.profile = _manager_user(self.vendor)
        self.order = _order(self.vendor)

    def _call(self, body, logo_url=""):
        from manager import views as manager_views

        request = self.factory.patch(
            "/manager/api/manager_order_update/",
            body,
            format="json",
        )
        force_authenticate(request, user=self.user)
        with patch.object(manager_views, "project_name", "dine_flash_buffet"), patch(
            "manager.views.get_vendor_business_day_range",
            return_value=(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
        ), patch(
            "manager.views.Order.objects.filter"
        ) as mock_filter, patch(
            "manager.views.VendorLogoSerializer"
        ) as mock_logo, patch(
            "manager.views.get_vendor_current_time",
            return_value=timezone.now(),
        ), patch(
            "manager.views.ChatMessage.objects.create"
        ) as mock_create, patch(
            "manager.views.notify_web_push",
            return_value=[],
        ) as mock_push:
            mock_filter.return_value.first.return_value = self.order
            mock_logo.return_value.data = {"logo_url": logo_url}
            chat = MagicMock()
            chat.id = 555
            mock_create.return_value = chat
            response = manager_views.manager_order_update(request)
            return response, mock_create, mock_push

    def test_outlet_manager_can_send_message_without_logo(self):
        """Buffet message path must not 404 when vendor logo is missing."""
        response, mock_create, mock_push = self._call(
            {"token_no": 42, "action": "message", "status": "Your table is ready"},
            logo_url="",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["sender"], "manager")
        self.assertEqual(kwargs["message_text"], "Your table is ready")
        self.assertEqual(kwargs["token_no"], 42)
        self.assertEqual(kwargs["booking_id"], self.order.id)
        self.assertEqual(kwargs["booking_no"], "T-1")
        mock_push.assert_called_once()
        push_payload = mock_push.call_args.args[2]
        self.assertEqual(push_payload["type"], "buffet_manager")

    def test_message_still_rejects_when_order_missing_for_vendor(self):
        from manager import views as manager_views

        request = self.factory.patch(
            "/manager/api/manager_order_update/",
            {"token_no": 99, "action": "message", "status": "Hello"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        with patch.object(manager_views, "project_name", "dine_flash_buffet"), patch(
            "manager.views.get_vendor_business_day_range",
            return_value=(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
        ), patch(
            "manager.views.Order.objects.filter"
        ) as mock_filter, patch(
            "manager.views.VendorLogoSerializer"
        ) as mock_logo:
            mock_filter.return_value.first.return_value = None
            mock_logo.return_value.data = {"logo_url": "https://x/logo.png"}
            response = manager_views.manager_order_update(request)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetChatHistoryTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.vendor = _buffet_vendor()
        self.user, _ = _manager_user(self.vendor)

    def test_chat_history_uses_token_no_and_marks_user_messages_read(self):
        from manager import views as manager_views

        request = self.factory.get(
            "/manager/api/chat_history/",
            {"token_no": "42"},
        )
        force_authenticate(request, user=self.user)

        fake_qs = MagicMock()
        fake_qs.update.return_value = 2
        fake_qs.only.return_value.order_by.return_value = []

        with patch.object(manager_views, "project_name", "dine_flash_buffet"), patch(
            "manager.views._resolve_vendor_for_manager",
            return_value=self.vendor,
        ), patch(
            "manager.views.get_vendor_current_date",
            return_value=date(2026, 9, 29),
        ), patch(
            "manager.views.ChatMessage.objects.filter",
            return_value=fake_qs,
        ) as mock_filter, patch(
            "manager.views.ChatMessageSerializer"
        ) as mock_ser:
            mock_ser.return_value.data = [
                {
                    "message_id": "m1",
                    "sender": "user",
                    "message_text": "Hi",
                    "audio_file": None,
                    "reply_to": None,
                    "created_at": "2026-09-29T10:00:00Z",
                }
            ]
            response = manager_views.chat_history(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["messages"]), 1)
        # First filter call marks unread user messages read with token_no + vendor date
        first_kwargs = mock_filter.call_args_list[0].kwargs
        self.assertEqual(first_kwargs["vendor"], self.vendor)
        self.assertEqual(first_kwargs["token_no"], 42)
        self.assertEqual(first_kwargs["sender"], "user")
        self.assertEqual(first_kwargs["is_read"], False)
        self.assertEqual(first_kwargs["created_date"], date(2026, 9, 29))
        fake_qs.update.assert_called_with(is_read=True)

    def test_chat_history_requires_token_no_for_buffet(self):
        from manager import views as manager_views

        request = self.factory.get("/manager/api/chat_history/")
        force_authenticate(request, user=self.user)
        with patch.object(manager_views, "project_name", "dine_flash_buffet"):
            response = manager_views.chat_history(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token_no", response.data["error"])


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetCustomerReplyCreatedDateTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.vendor = _buffet_vendor()
        self.order = _order(self.vendor)

    @patch("orders.views._send_to_managers_async")
    @patch("orders.views.VendorLogoSerializer")
    @patch("orders.views.ChatMessage.objects.create")
    @patch("orders.views.get_vendor_current_time")
    @patch("orders.views.Order.objects.get")
    def test_customer_reply_uses_vendor_local_created_date(
        self, mock_get, mock_vendor_time, mock_create, mock_logo, mock_fcm
    ):
        from orders import views as order_views

        mock_get.return_value = self.order
        mock_vendor_time.return_value = datetime(2026, 9, 29, 23, 30, 0)
        mock_logo.return_value.data = {"logo_url": ""}
        chat = MagicMock()
        chat.id = 9
        mock_create.return_value = chat

        request = self.factory.post(
            "/check-status/",
            {
                "token_no": 42,
                "vendor_id": self.vendor.vendor_id,
                "reply_text": "On my way",
            },
            format="json",
        )
        with patch.object(order_views, "project_name", "dine_flash_buffet"):
            response = order_views.check_status(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "user_reply")
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["sender"], "user")
        self.assertEqual(kwargs["message_text"], "On my way")
        self.assertEqual(kwargs["token_no"], 42)
        self.assertEqual(kwargs["booking_id"], self.order.id)
        self.assertEqual(kwargs["created_date"], date(2026, 9, 29))
        mock_vendor_time.assert_called()
        mock_fcm.assert_called_once()


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetFcmRoleFilterTests(SimpleTestCase):
    @patch("orders.utils.send_fcm_multicast")
    @patch("orders.utils.collect_manager_fcm_tokens")
    def test_user_reply_collects_manager_roles_only(self, mock_collect, mock_multicast):
        vendor = _buffet_vendor()
        mock_collect.return_value = ["om-token"]
        mock_multicast.return_value = (True, {})

        data = {"type": "user_reply", "token_no": 42, "reply_status": "Hi"}
        send_to_managers(vendor, data, "Customer Message Received", "body")

        mock_collect.assert_called_once()
        _, kwargs = mock_collect.call_args
        self.assertIn("roles", kwargs)
        self.assertIn("outlet_manager", kwargs["roles"])
        self.assertNotIn("utility_user", kwargs["roles"])
        # Payload type unchanged (not remapped like Dine Flash)
        mock_multicast.assert_called_once()
        fcm_payload = mock_multicast.call_args.args[1]
        self.assertEqual(fcm_payload["type"], "user_reply")

    @patch("orders.utils.send_fcm_multicast")
    @patch("orders.utils.collect_manager_fcm_tokens")
    def test_buffet_status_push_keeps_vendor_wide_tokens(self, mock_collect, mock_multicast):
        vendor = _buffet_vendor()
        mock_collect.return_value = ["om-token", "kitchen-token"]
        mock_multicast.return_value = (True, {})

        send_to_managers(vendor, {"type": "buffetstatus", "token_no": 42}, "t", "b")

        mock_collect.assert_called_once_with(vendor)
        self.assertNotIn("roles", mock_collect.call_args.kwargs)

    @override_settings(PROJECT_NAME="food_flash")
    @patch("orders.utils.send_fcm_multicast")
    @patch("orders.utils.collect_manager_fcm_tokens")
    def test_food_flash_user_reply_unchanged(self, mock_collect, mock_multicast):
        vendor = _buffet_vendor()
        mock_collect.return_value = ["token-a"]
        mock_multicast.return_value = (True, {})

        send_to_managers(vendor, {"type": "user_reply", "token_no": 1}, "t", "b")

        mock_collect.assert_called_once_with(vendor)
        self.assertNotIn("roles", mock_collect.call_args.kwargs)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetOutletManagerChatIntegrationTests(TestCase):
    """DB-backed coverage for registration, send, history, unread, isolation."""

    def setUp(self):
        self.client = APIClient()

        company = User.objects.create_user(username="buffet_co_chat", password="pass")
        self.admin_outlet = AdminOutlet.objects.create(
            user=company,
            customer_name="Buffet Chat Co",
            customer_id=97001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Chat Outlet",
            alias_name="CO",
            location="L1",
            vendor_id=970001,
            location_id="C1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)

        other_company = User.objects.create_user(username="buffet_co_other", password="pass")
        self.other_outlet = AdminOutlet.objects.create(
            user=other_company,
            customer_name="Other Co",
            customer_id=97002,
            authentication_status="Approve",
        )
        self.other_vendor = Vendor.objects.create(
            admin_outlet=self.other_outlet,
            name="Other Outlet",
            alias_name="OO",
            location="L2",
            vendor_id=970002,
            location_id="C2",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.other_vendor)

        self.manager_user = User.objects.create_user(
            username="buffet_om_chat", password="secret123"
        )
        self.manager_profile = UserProfile.objects.create(
            user=self.manager_user,
            name="OM Chat",
            role="outlet_manager",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
        )
        self.utility_user = User.objects.create_user(
            username="buffet_kitchen_chat", password="secret123"
        )
        self.utility_profile = UserProfile.objects.create(
            user=self.utility_user,
            name="Kitchen",
            role="utility_user",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
        )
        other_mgr_user = User.objects.create_user(
            username="buffet_om_other", password="secret123"
        )
        self.other_manager = UserProfile.objects.create(
            user=other_mgr_user,
            name="Other OM",
            role="outlet_manager",
            admin_outlet=self.other_outlet,
            vendor=self.other_vendor,
        )

        today = timezone.now().date()
        self.order = Order.objects.create(
            vendor=self.vendor,
            token_no=42,
            status="created",
            table_booking_no="B-42",
            updated_by="customer",
        )
        # Ensure created_at is within a typical business-day window used by APIs
        Order.objects.filter(pk=self.order.pk).update(created_at=timezone.now())
        self.order.refresh_from_db()

        self.other_order = Order.objects.create(
            vendor=self.other_vendor,
            token_no=42,
            status="created",
            table_booking_no="X-42",
            updated_by="customer",
        )
        Order.objects.filter(pk=self.other_order.pk).update(created_at=timezone.now())

        self.client.force_authenticate(user=self.manager_user)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_outlet_manager_login_succeeds(self):
        self.client.force_authenticate(user=None)
        url = reverse("buffet_outlet_manager_login")
        resp = self.client.post(
            url,
            {
                "username": "buffet_om_chat",
                "password": "secret123",
                "customer_id": self.admin_outlet.customer_id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["user"]["manager_id"], self.manager_profile.id)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_register_android_apk_links_outlet_manager_profile(self):
        self.client.force_authenticate(user=None)
        url = reverse("vendors:register-android-apk")
        with patch("vendors.views.build_vendor_config_payload", return_value={}):
            resp = self.client.post(
                url,
                {
                    "token": "fcm-om-token-1",
                    "customer_id": self.admin_outlet.customer_id,
                    "mac_address": "AA:BB:CC:DD:EE:01",
                    "apk_version": "1.0.0",
                    "manager_id": self.manager_profile.id,
                },
                format="json",
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["mapped"])
        device = AndroidAPK.objects.get(mac_address="AA:BB:CC:DD:EE:01")
        self.assertEqual(device.user_profile_id, self.manager_profile.id)
        self.assertEqual(device.user_profile.vendor_id, self.vendor.id)
        self.assertEqual(device.token, "fcm-om-token-1")

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_collect_fcm_tokens_roles_excludes_utility_user(self):
        AndroidAPK.objects.create(
            token="om-fcm",
            mac_address="AA:BB:CC:DD:EE:10",
            apk_version="1.0.0",
            admin_outlet=self.admin_outlet,
            user_profile=self.manager_profile,
        )
        AndroidAPK.objects.create(
            token="kitchen-fcm",
            mac_address="AA:BB:CC:DD:EE:11",
            apk_version="1.0.0",
            admin_outlet=self.admin_outlet,
            user_profile=self.utility_profile,
        )
        all_tokens = set(collect_manager_fcm_tokens(self.vendor))
        self.assertEqual(all_tokens, {"om-fcm", "kitchen-fcm"})

        from orders.utils import _BUFFET_MANAGER_CHAT_ROLES

        chat_tokens = set(
            collect_manager_fcm_tokens(self.vendor, roles=_BUFFET_MANAGER_CHAT_ROLES)
        )
        self.assertEqual(chat_tokens, {"om-fcm"})
        self.assertNotIn("kitchen-fcm", chat_tokens)

    @patch("manager.views.project_name", "dine_flash_buffet")
    @patch("manager.views.notify_web_push", return_value=[])
    @patch("manager.views.VendorLogoSerializer")
    @patch(
        "manager.views.get_vendor_business_day_range",
    )
    @patch("manager.views.get_vendor_current_time")
    @patch("manager.views.get_vendor_current_date")
    def test_manager_can_send_message_and_history_returns_it(
        self, mock_cur_date, mock_cur_time, mock_day_range, mock_logo, mock_push
    ):
        now = timezone.now()
        mock_day_range.return_value = (now - timedelta(hours=12), now + timedelta(hours=12))
        mock_cur_time.return_value = now
        mock_cur_date.return_value = now.date()
        mock_logo.return_value.data = {"logo_url": ""}
        url = reverse("manager:manager_order_update")
        resp = self.client.patch(
            url,
            {"token_no": 42, "action": "message", "status": "Food is ready"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        msg = ChatMessage.objects.get(vendor=self.vendor, token_no=42, sender="manager")
        self.assertEqual(msg.message_text, "Food is ready")
        self.assertEqual(msg.booking_id, self.order.id)

        history_url = reverse("manager:chat_history")
        hist = self.client.get(history_url, {"token_no": 42})
        self.assertEqual(hist.status_code, status.HTTP_200_OK)
        texts = [m["message_text"] for m in hist.data["messages"]]
        self.assertIn("Food is ready", texts)

    @patch("manager.views.project_name", "dine_flash_buffet")
    def test_customer_reply_unread_then_cleared_by_chat_history(self):
        ChatMessage.objects.create(
            vendor=self.vendor,
            token_no=42,
            booking_id=self.order.id,
            booking_no="B-42",
            created_date=timezone.now().date(),
            sender="user",
            is_send=True,
            is_read=False,
            message_text="Where is my order?",
        )
        orders_url = reverse("manager:get_today_orders")
        with patch("manager.views.project_name", "dine_flash_buffet"), patch(
            "manager.views.get_vendor_business_day_range",
            return_value=(
                timezone.now() - timedelta(hours=12),
                timezone.now() + timedelta(hours=12),
            ),
        ):
            listing = self.client.get(orders_url)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        data = listing.data
        rows = data.get("detail") or []
        matching = [r for r in rows if int(r.get("token_no", -1)) == 42]
        self.assertTrue(matching)
        self.assertGreaterEqual(matching[0].get("new_notifications", 0), 1)
        self.assertGreaterEqual(data.get("unread", 0), 1)

        with patch("manager.views.project_name", "dine_flash_buffet"), patch(
            "manager.views.get_vendor_current_date",
            return_value=timezone.now().date(),
        ):
            hist = self.client.get(reverse("manager:chat_history"), {"token_no": 42})
        self.assertEqual(hist.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ChatMessage.objects.filter(
                vendor=self.vendor, token_no=42, sender="user", is_read=False
            ).exists()
        )

    @patch("manager.views.project_name", "dine_flash_buffet")
    def test_manager_cannot_see_other_vendor_conversation(self):
        ChatMessage.objects.create(
            vendor=self.other_vendor,
            token_no=42,
            booking_id=self.other_order.id,
            created_date=timezone.now().date(),
            sender="user",
            is_send=True,
            is_read=False,
            message_text="Secret other vendor",
        )
        with patch(
            "manager.views.get_vendor_current_date",
            return_value=timezone.now().date(),
        ):
            hist = self.client.get(reverse("manager:chat_history"), {"token_no": 42})
        self.assertEqual(hist.status_code, status.HTTP_200_OK)
        texts = [m["message_text"] for m in hist.data["messages"]]
        self.assertNotIn("Secret other vendor", texts)
