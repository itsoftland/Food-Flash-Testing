"""
Focused tests: Dine Flash Buffet order-level ``ready`` in manager_order_update.

Buffet must skip TV/MQTT/Azure and still web-push the customer browser.
Food Flash and Dine Flash ready behaviour must remain unchanged.
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


def _order(vendor, token_no=42, order_id=100):
    order = MagicMock()
    order.id = order_id
    order.token_no = token_no
    order.table_booking_no = "T-1"
    order.counter_no = 1
    order.status = "preparing"
    order.vendor = vendor
    order.created_at = timezone.now()
    order.notified_at = None
    order.refresh_from_db = MagicMock()
    order.save = MagicMock()
    return order


def _call_ready(
    project_name,
    tv_mode="MQTT",
    mqtt_mode=True,
    push_errors=None,
    mqtt_return=False,
):
    """Invoke manager_order_update ready with common mocks; return response and mocks."""
    from manager import views as manager_views

    push_errors = [] if push_errors is None else push_errors
    vendor = _vendor(tv_mode=tv_mode, mqtt_mode=mqtt_mode)
    user = _manager_user(vendor)
    order = _order(vendor)
    factory = APIRequestFactory()
    body = {"token_no": 42, "action": "ready", "status": "ready", "counter_no": 1}
    request = factory.patch(
        "/manager/api/manager_order_update/",
        body,
        format="json",
    )
    force_authenticate(request, user=user)

    updated = MagicMock()
    updated.token_no = order.token_no
    updated.status = "ready"

    with patch.object(manager_views, "project_name", project_name), patch(
        "manager.views.get_vendor_business_day_range",
        return_value=(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
    ), patch("manager.views.Order.objects.filter") as mock_filter, patch(
        "manager.views.VendorLogoSerializer"
    ) as mock_logo, patch(
        "manager.views.update_existing_order_by_manager",
        return_value=updated,
    ) as mock_update, patch(
        "manager.views.notify_web_push",
        return_value=push_errors,
    ) as mock_push, patch(
        "manager.views.notify_android_tv",
        return_value=(True, "ok"),
    ) as mock_tv, patch(
        "manager.views.send_order_update",
        return_value=mqtt_return,
    ) as mock_mqtt, patch(
        "manager.views.get_azure_devices",
        return_value={"sent": True},
    ) as mock_azure:
        mock_filter.return_value.first.return_value = order
        mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
        response = manager_views.manager_order_update(request)
        return {
            "response": response,
            "order": order,
            "mock_update": mock_update,
            "mock_push": mock_push,
            "mock_tv": mock_tv,
            "mock_mqtt": mock_mqtt,
            "mock_azure": mock_azure,
        }


def _call_status_action(project_name, action):
    from manager import views as manager_views

    vendor = _vendor(tv_mode="MQTT", mqtt_mode=True)
    user = _manager_user(vendor)
    order = _order(vendor)
    factory = APIRequestFactory()
    request = factory.patch(
        "/manager/api/manager_order_update/",
        {"token_no": 42, "action": action, "status": action},
        format="json",
    )
    force_authenticate(request, user=user)
    updated = MagicMock()
    updated.token_no = order.token_no

    with patch.object(manager_views, "project_name", project_name), patch(
        "manager.views.get_vendor_business_day_range",
        return_value=(timezone.now() - timedelta(hours=1), timezone.now() + timedelta(hours=1)),
    ), patch("manager.views.Order.objects.filter") as mock_filter, patch(
        "manager.views.VendorLogoSerializer"
    ) as mock_logo, patch(
        "manager.views.update_existing_order_by_manager",
        return_value=updated,
    ) as mock_update, patch(
        "manager.views.notify_web_push",
        return_value=[],
    ) as mock_push, patch(
        "manager.views.send_order_update"
    ) as mock_mqtt:
        mock_filter.return_value.first.return_value = order
        mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
        response = manager_views.manager_order_update(request)
        return response, mock_update, mock_push, mock_mqtt


@override_settings(PROJECT_NAME="dine_flash_buffet", PUSH_COOLDOWN_SECONDS=1)
class BuffetManagerOrderUpdateReadyTests(SimpleTestCase):
    def test_buffet_ready_mqtt_skips_tv_and_mqtt_still_web_pushes(self):
        ctx = _call_ready("dine_flash_buffet", tv_mode="MQTT", mqtt_return=False)
        response = ctx["response"]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        ctx["mock_update"].assert_called_once()
        self.assertEqual(ctx["mock_update"].call_args.args[3], "ready")
        ctx["mock_mqtt"].assert_not_called()
        ctx["mock_tv"].assert_not_called()
        ctx["mock_push"].assert_called_once()
        payload = ctx["mock_push"].call_args.args[2]
        self.assertEqual(payload["type"], "buffet_item_ready")
        self.assertEqual(payload["booking_id"], ctx["order"].id)
        self.assertIsNone(response.data["mqtt"])

    def test_buffet_ready_payload_has_token_message_and_keeps_outlet_fields(self):
        ctx = _call_ready("dine_flash_buffet", tv_mode="MQTT")
        payload = ctx["mock_push"].call_args.args[2]
        self.assertEqual(payload["message"], "Your order 42 is now ready.")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["token_no"], 42)
        self.assertEqual(payload["name"], "Test Outlet")
        self.assertEqual(payload["alias_name"], "Alias")
        self.assertEqual(payload["title"], "Order Update by Manager")
        self.assertEqual(payload["body"], "Your order 42 status: Ready")
        self.assertNotIn("item_name", payload)

    def test_buffet_ready_firebase_skips_tv_web_push_called(self):
        ctx = _call_ready("dine_flash_buffet", tv_mode="Firebase")
        self.assertEqual(ctx["response"].status_code, status.HTTP_200_OK)
        ctx["mock_tv"].assert_not_called()
        ctx["mock_push"].assert_called_once()

    def test_buffet_ready_azure_skips_iot_web_push_called(self):
        ctx = _call_ready("dine_flash_buffet", tv_mode="AZURE_IOT")
        self.assertEqual(ctx["response"].status_code, status.HTTP_200_OK)
        ctx["mock_azure"].assert_not_called()
        ctx["mock_push"].assert_called_once()

    def test_buffet_ready_without_subscription_still_succeeds(self):
        ctx = _call_ready(
            "dine_flash_buffet",
            tv_mode="MQTT",
            push_errors=["No push subscription for customer"],
        )
        response = ctx["response"]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertFalse(response.data["web_push"])
        self.assertEqual(
            response.data["web_push_info"],
            ["No push subscription for customer"],
        )
        ctx["mock_update"].assert_called_once()

    def test_buffet_delivered_and_cancelled_unchanged(self):
        for action in ("delivered", "cancelled"):
            with self.subTest(action=action):
                response, mock_update, mock_push, mock_mqtt = _call_status_action(
                    "dine_flash_buffet", action
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertTrue(response.data["success"])
                mock_update.assert_called_once()
                mock_push.assert_called_once()
                mock_mqtt.assert_not_called()
                self.assertIsNone(response.data["mqtt"])
                payload = mock_push.call_args.args[2]
                self.assertEqual(payload["type"], "buffet_item_ready")
                self.assertEqual(payload["status"], action)
                self.assertEqual(payload["message"], f"Your order 42 is now {action}.")
                self.assertEqual(payload["name"], "Test Outlet")
                self.assertEqual(payload["alias_name"], "Alias")
                self.assertEqual(payload["title"], f"Order {action.capitalize()}")


@override_settings(PROJECT_NAME="food_flash", PUSH_COOLDOWN_SECONDS=1)
class FoodFlashManagerOrderUpdateReadyRegressionTests(SimpleTestCase):
    def test_food_flash_ready_mqtt_failure_still_returns_500(self):
        ctx = _call_ready("food_flash", tv_mode="MQTT", mqtt_return=False)
        self.assertEqual(ctx["response"].status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        ctx["mock_mqtt"].assert_called_once()
        ctx["mock_push"].assert_not_called()

    def test_food_flash_ready_payload_has_no_buffet_message(self):
        ctx = _call_ready("food_flash", tv_mode="Firebase", mqtt_return=True)
        self.assertEqual(ctx["response"].status_code, status.HTTP_200_OK)
        payload = ctx["mock_push"].call_args.args[2]
        self.assertEqual(payload["type"], "foodstatus")
        self.assertNotIn("message", payload)
        self.assertNotIn("booking_id", payload)

    def test_food_flash_delivered_and_cancelled_have_no_buffet_message(self):
        for action in ("delivered", "cancelled"):
            with self.subTest(action=action):
                response, _mock_update, mock_push, _mock_mqtt = _call_status_action(
                    "food_flash", action
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                payload = mock_push.call_args.args[2]
                self.assertEqual(payload["type"], "foodstatus")
                self.assertNotIn("message", payload)


@override_settings(PROJECT_NAME="dine_flash", PUSH_COOLDOWN_SECONDS=1)
class DineFlashManagerOrderUpdateReadyRegressionTests(SimpleTestCase):
    def test_dine_flash_ready_firebase_still_notifies_tv(self):
        ctx = _call_ready("dine_flash", tv_mode="Firebase", mqtt_return=True)
        self.assertEqual(ctx["response"].status_code, status.HTTP_200_OK)
        ctx["mock_tv"].assert_called_once()
        ctx["mock_mqtt"].assert_not_called()
        ctx["mock_push"].assert_called_once()
        payload = ctx["mock_push"].call_args.args[2]
        self.assertEqual(payload["type"], "foodstatus")
        self.assertNotIn("message", payload)