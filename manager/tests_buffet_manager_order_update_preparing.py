"""
Focused tests: Dine Flash Buffet order-level ``preparing`` in manager_order_update.

Order-level preparing must update Order.status, web-push with buffet_item_preparing,
and must not create ChatMessage or invoke TV/MQTT paths.
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate


def _vendor(tv_mode="MQTT", mqtt_mode=True, pk=1, vendor_id=960001):
    return SimpleNamespace(
        id=pk,
        name="Test Outlet",
        alias_name="Alias",
        vendor_id=vendor_id,
        location_id="L1",
        config=SimpleNamespace(
            vibration_pattern=None,
            vibration_duration=None,
            tv_communication_mode=tv_mode,
            mqtt_mode=mqtt_mode,
            timezone="UTC",
            business_day_start_hour=datetime.strptime("00:00:00", "%H:%M:%S").time(),
        ),
    )


def _manager_user(vendor):
    user = MagicMock()
    user.username = "mgr"
    profile = MagicMock()
    profile.role = "outlet_manager"
    profile.name = "Manager"
    profile.vendor = vendor
    qs = MagicMock()
    qs.exists.return_value = True
    qs.first.return_value = profile
    user.profile_roles = qs
    return user


def _order(vendor, token_no=42, order_id=100, order_status="created"):
    order = MagicMock()
    order.id = order_id
    order.token_no = token_no
    order.table_booking_no = "T-1"
    order.counter_no = 1
    order.status = order_status
    order.vendor = vendor
    order.created_at = timezone.now()
    order.notified_at = None
    order.refresh_from_db = MagicMock()
    order.save = MagicMock()
    return order


def _call_preparing(
    project_name="dine_flash_buffet",
    *,
    action="preparing",
    status="preparing",
    tv_mode="MQTT",
    push_errors=None,
):
    from manager import views as manager_views

    push_errors = [] if push_errors is None else push_errors
    vendor = _vendor(tv_mode=tv_mode)
    user = _manager_user(vendor)
    order = _order(vendor, order_status="created")
    factory = APIRequestFactory()
    request = factory.patch(
        "/manager/api/manager_order_update/",
        {"token_no": 42, "action": action, "status": status},
        format="json",
    )
    force_authenticate(request, user=user)

    updated = MagicMock()
    updated.token_no = order.token_no
    updated.status = "preparing"

    def _apply_update(token_no, vend, device, new_status, mgr):
        order.status = new_status
        return updated

    patches = dict(
        project=patch.object(manager_views, "project_name", project_name),
        day_range=patch(
            "manager.views.get_vendor_business_day_range",
            return_value=(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
        ),
        order_filter=patch("manager.views.Order.objects.filter"),
        logo=patch("manager.views.VendorLogoSerializer"),
        order_update=patch("manager.views.update_existing_order_by_manager"),
        push=patch("manager.views.notify_web_push", return_value=push_errors),
        tv=patch("manager.views.notify_android_tv"),
        mqtt=patch("manager.views.send_order_update"),
        azure=patch("manager.views.get_azure_devices"),
        chat=patch("manager.views.ChatMessage.objects.create"),
    )
    with patches["project"], patches["day_range"], patches["order_filter"] as mock_filter, patches[
        "logo"
    ] as mock_logo, patches["order_update"] as mock_update, patches["push"] as mock_push, patches[
        "tv"
    ] as mock_tv, patches["mqtt"] as mock_mqtt, patches["azure"] as mock_azure, patches[
        "chat"
    ] as mock_chat:
        mock_filter.return_value.first.return_value = order
        mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
        mock_update.side_effect = _apply_update
        response = manager_views.manager_order_update(request)
        return {
            "response": response,
            "order": order,
            "mock_update": mock_update,
            "mock_push": mock_push,
            "mock_tv": mock_tv,
            "mock_mqtt": mock_mqtt,
            "mock_azure": mock_azure,
            "mock_chat": mock_chat,
        }


@override_settings(PROJECT_NAME="dine_flash_buffet", PUSH_COOLDOWN_SECONDS=1)
class BuffetManagerOrderUpdatePreparingTests(SimpleTestCase):
    def test_buffet_preparing_updates_order_and_web_pushes(self):
        ctx = _call_preparing()
        response = ctx["response"]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(ctx["order"].status, "preparing")
        ctx["mock_update"].assert_called_once()
        self.assertEqual(ctx["mock_update"].call_args.args[0], 42)
        self.assertEqual(ctx["mock_update"].call_args.args[3], "preparing")
        ctx["mock_push"].assert_called_once()
        payload = ctx["mock_push"].call_args.args[2]
        self.assertEqual(payload["type"], "buffet_item_preparing")
        self.assertEqual(payload["status"], "preparing")
        self.assertEqual(payload["token_no"], 42)
        self.assertEqual(payload["booking_id"], ctx["order"].id)
        self.assertEqual(payload["title"], "Order Preparing")
        self.assertIn("Preparing", payload["body"])
        self.assertNotIn("item_id", payload)
        self.assertNotIn("item_name", payload)
        self.assertEqual(payload["message"], "Your order 42 is now preparing.")
        self.assertEqual(payload["name"], "Test Outlet")
        self.assertEqual(payload["alias_name"], "Alias")

    def test_buffet_preparing_skips_tv_mqtt_azure_and_chat(self):
        ctx = _call_preparing(tv_mode="Firebase")
        self.assertEqual(ctx["response"].status_code, status.HTTP_200_OK)
        ctx["mock_tv"].assert_not_called()
        ctx["mock_mqtt"].assert_not_called()
        ctx["mock_azure"].assert_not_called()
        ctx["mock_chat"].assert_not_called()
        self.assertIsNone(ctx["response"].data["mqtt"])

    def test_buffet_preparing_push_failure_still_returns_200(self):
        ctx = _call_preparing(push_errors=["No push subscription"])
        response = ctx["response"]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(ctx["order"].status, "preparing")
        self.assertFalse(response.data["web_push"])
        self.assertEqual(response.data["web_push_info"], ["No push subscription"])

    def test_buffet_preparing_db_failure_returns_500_no_push(self):
        from manager import views as manager_views

        vendor = _vendor()
        user = _manager_user(vendor)
        order = _order(vendor)
        factory = APIRequestFactory()
        request = factory.patch(
            "/manager/api/manager_order_update/",
            {"token_no": 42, "action": "preparing", "status": "preparing"},
            format="json",
        )
        force_authenticate(request, user=user)
        with patch.object(manager_views, "project_name", "dine_flash_buffet"), patch(
            "manager.views.get_vendor_business_day_range",
            return_value=(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
        ), patch("manager.views.Order.objects.filter") as mock_filter, patch(
            "manager.views.VendorLogoSerializer"
        ) as mock_logo, patch(
            "manager.views.update_existing_order_by_manager",
            return_value=None,
        ) as mock_update, patch(
            "manager.views.notify_web_push"
        ) as mock_push:
            mock_filter.return_value.first.return_value = order
            mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
            response = manager_views.manager_order_update(request)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        mock_push.assert_not_called()

    def test_mismatched_status_rejects_without_update_or_push(self):
        from manager import views as manager_views

        vendor = _vendor()
        user = _manager_user(vendor)
        order = _order(vendor)
        factory = APIRequestFactory()
        request = factory.patch(
            "/manager/api/manager_order_update/",
            {"token_no": 42, "action": "preparing", "status": "ready"},
            format="json",
        )
        force_authenticate(request, user=user)
        with patch.object(manager_views, "project_name", "dine_flash_buffet"), patch(
            "manager.views.get_vendor_business_day_range",
            return_value=(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
        ), patch("manager.views.Order.objects.filter") as mock_filter, patch(
            "manager.views.VendorLogoSerializer"
        ) as mock_logo, patch(
            "manager.views.update_existing_order_by_manager"
        ) as mock_update, patch(
            "manager.views.notify_web_push"
        ) as mock_push:
            mock_filter.return_value.first.return_value = order
            mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
            response = manager_views.manager_order_update(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(order.status, "created")
        mock_update.assert_not_called()
        mock_push.assert_not_called()


@override_settings(PROJECT_NAME="food_flash", PUSH_COOLDOWN_SECONDS=1)
class FoodFlashPreparingActionRejectionTests(SimpleTestCase):
    def test_food_flash_rejects_preparing_action(self):
        from manager import views as manager_views

        vendor = _vendor()
        user = _manager_user(vendor)
        factory = APIRequestFactory()
        request = factory.patch(
            "/manager/api/manager_order_update/",
            {"token_no": 42, "action": "preparing", "status": "preparing"},
            format="json",
        )
        force_authenticate(request, user=user)
        with patch.object(manager_views, "project_name", "food_flash"):
            response = manager_views.manager_order_update(request)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid action", response.data["message"])