"""
Hospital Flash patient reply routing tests for _hospital_check_status.

Scenarios:
1. booking_id reply → one ChatMessage on that Order (not orders[0]).
2. registration_batch_id reply → one ChatMessage per Order; one notify.
3. Single-order batch → one ChatMessage.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory


def _vendor():
    return SimpleNamespace(
        id=1,
        name="City Hospital",
        alias_name="City Hospital",
        vendor_id=101,
        location_id="L1",
        config=SimpleNamespace(vibration_pattern=None, vibration_duration=None),
    )


def _order(vendor, order_id, booking_no, token_no, batch_id, utility_name="Dept"):
    utility = SimpleNamespace(id=order_id, display_name=utility_name, display_code="D")
    order = MagicMock()
    order.id = order_id
    order.pk = order_id
    order.token_no = token_no
    order.table_booking_no = booking_no
    order.customer_name = "Patient A"
    order.counter_no = 1
    order.status = "waiting"
    order.registration_batch_id = batch_id
    order.utility = utility
    order.remarks = None
    order.updated_by = "customer"
    order.device = None
    order.user_profile = None
    order.vendor = vendor
    return order


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalCheckStatusReplyTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.vendor = _vendor()
        self.batch_id = uuid4()

    def _call(self, body):
        from orders import views as order_views

        request = self.factory.post(
            "/hospital_flash/check-status/",
            body,
            format="json",
        )
        with patch.object(order_views, "project_name", "hospital_flash"):
            return order_views.check_status(request)

    def _orders(self):
        return [
            _order(self.vendor, 10, "A-1", 1, self.batch_id, "Cardiology"),
            _order(self.vendor, 20, "B-2", 2, self.batch_id, "Radiology"),
            _order(self.vendor, 30, "C-3", 3, self.batch_id, "Laboratory"),
        ]

    @patch("orders.views._send_to_managers_async")
    @patch("orders.views.ChatMessage.objects.create")
    @patch("orders.views._hospital_resolve_orders")
    @patch("orders.views.VendorLogoSerializer")
    def test_scenario_1_booking_id_creates_one_message_on_matched_order(
        self,
        mock_logo,
        mock_resolve,
        mock_chat_create,
        mock_notify,
    ):
        orders = self._orders()
        mock_resolve.return_value = (orders, orders[0])
        mock_logo.return_value.data = {"logo_url": ""}
        mock_chat_create.return_value = SimpleNamespace(id=1)

        response = self._call(
            {
                "vendor_id": 101,
                "booking_id": 20,
                "reply_text": "I'll arrive in 10 minutes.",
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_chat_create.call_count, 1)
        kwargs = mock_chat_create.call_args.kwargs
        self.assertEqual(kwargs["booking_id"], 20)
        self.assertEqual(kwargs["booking_no"], "B-2")
        self.assertEqual(kwargs["message_text"], "I'll arrive in 10 minutes.")
        self.assertEqual(kwargs["sender"], "user")
        mock_notify.assert_called_once()

    @patch("orders.views._send_to_managers_async")
    @patch("orders.views.ChatMessage.objects.create")
    @patch("orders.views._hospital_resolve_orders")
    @patch("orders.views.VendorLogoSerializer")
    def test_scenario_2_batch_reply_duplicates_and_notifies_once(
        self,
        mock_logo,
        mock_resolve,
        mock_chat_create,
        mock_notify,
    ):
        orders = self._orders()
        mock_resolve.return_value = (orders, orders[0])
        mock_logo.return_value.data = {"logo_url": ""}
        mock_chat_create.return_value = SimpleNamespace(id=1)

        response = self._call(
            {
                "vendor_id": 101,
                "registration_batch_id": str(self.batch_id),
                "reply_text": "I'll arrive in 10 minutes.",
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_chat_create.call_count, 3)
        booking_ids = [
            call.kwargs["booking_id"] for call in mock_chat_create.call_args_list
        ]
        self.assertEqual(booking_ids, [10, 20, 30])
        for call in mock_chat_create.call_args_list:
            self.assertEqual(
                call.kwargs["message_text"], "I'll arrive in 10 minutes."
            )
        mock_notify.assert_called_once()
        notify_args = mock_notify.call_args.args
        self.assertEqual(notify_args[2], "Patient Message Received")
        self.assertIn("A-1", notify_args[3])

    @patch("orders.views._send_to_managers_async")
    @patch("orders.views.ChatMessage.objects.create")
    @patch("orders.views._hospital_resolve_orders")
    @patch("orders.views.VendorLogoSerializer")
    def test_scenario_3_single_order_one_message(
        self,
        mock_logo,
        mock_resolve,
        mock_chat_create,
        mock_notify,
    ):
        single = [
            _order(self.vendor, 99, "S-1", 9, self.batch_id, "Cardiology"),
        ]
        mock_resolve.return_value = (single, single[0])
        mock_logo.return_value.data = {"logo_url": ""}
        mock_chat_create.return_value = SimpleNamespace(id=1)

        response = self._call(
            {
                "vendor_id": 101,
                "registration_batch_id": str(self.batch_id),
                "reply_text": "On my way.",
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_chat_create.call_count, 1)
        self.assertEqual(mock_chat_create.call_args.kwargs["booking_id"], 99)
        mock_notify.assert_called_once()

    def test_chat_target_helper_prefers_booking_id_over_batch(self):
        from orders.views import _hospital_chat_target_orders

        orders = self._orders()
        targets = _hospital_chat_target_orders(
            orders,
            orders[0],
            registration_batch_id=str(self.batch_id),
            parsed_booking_id=30,
        )
        self.assertEqual([o.id for o in targets], [30])
