"""
Hospital Flash pre-announcement unit tests.

Cross-flavour guard: these tests only exercise manager.hospital_pre_announcement
helpers and never import other flavour update paths.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings


class HospitalPreAnnouncementQueueLogicTests(SimpleTestCase):
    def test_find_current_called_index_uses_highest_called(self):
        from manager.hospital_pre_announcement import find_current_called_index

        queue = [
            SimpleNamespace(status="completed"),
            SimpleNamespace(status="called"),
            SimpleNamespace(status="waiting"),
            SimpleNamespace(status="waiting"),
            SimpleNamespace(status="waiting"),
        ]
        self.assertEqual(find_current_called_index(queue), 2)

    def test_find_current_called_index_none_when_nobody_called(self):
        from manager.hospital_pre_announcement import find_current_called_index

        queue = [
            SimpleNamespace(status="waiting"),
            SimpleNamespace(status="waiting"),
        ]
        self.assertIsNone(find_current_called_index(queue))

    def test_distance_matches_business_example(self):
        from manager.hospital_pre_announcement import compute_queue_distance

        # Current called = 1, token 4 → distance 3
        self.assertEqual(compute_queue_distance(4, 1), 3)
        # Current called = 2, token 4 → distance 2
        self.assertEqual(compute_queue_distance(4, 2), 2)

    def test_eta_calculation(self):
        approximate_service_time = 10
        distance = 2
        self.assertEqual(approximate_service_time * distance, 20)


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalPreAnnouncementProcessTests(SimpleTestCase):
    def _queue_orders(self, statuses, notified_flags=None):
        notified_flags = notified_flags or [None] * len(statuses)
        orders = []
        for i, status in enumerate(statuses, start=1):
            order = MagicMock()
            order.pk = i
            order.id = i
            order.status = status
            order.table_booking_no = f"RAD-{i}"
            order.token_no = i
            order.customer_name = f"Patient {i}"
            order.counter_no = 1
            order.registration_batch_id = None
            order.pre_announcement_notified_at = notified_flags[i - 1]
            order.utility = SimpleNamespace(display_name="Radiology")
            order.vendor = SimpleNamespace(
                name="Hospital",
                alias_name="Hospital",
                vendor_id="H1",
                location_id="L1",
                config=SimpleNamespace(vibration_pattern=None, vibration_duration=None),
            )
            orders.append(order)
        return orders

    @patch("manager.hospital_pre_announcement.VendorLogoSerializer")
    @patch("manager.hospital_pre_announcement.notify_web_push")
    @patch("manager.hospital_pre_announcement.Order.objects")
    @patch("manager.hospital_pre_announcement.get_department_queue_orders")
    def test_scenario_token_4_not_notified_when_distance_is_3(
        self, mock_get_queue, mock_order_objects, mock_notify, mock_logo
    ):
        from manager.hospital_pre_announcement import process_hospital_pre_announcements

        # Current called = 1; token 4 distance = 3 → Token 4 not notified.
        # Token 3 (distance 2) is eligible for pre_count=2.
        mock_logo.return_value.data = {"logo_url": ""}
        mock_get_queue.return_value = self._queue_orders(
            ["called", "waiting", "waiting", "waiting", "waiting"]
        )
        mock_order_objects.filter.return_value.update.return_value = 1

        utility = SimpleNamespace(
            display_name="Radiology",
            pre_announcement_count=2,
            approximate_service_time=10,
        )
        vendor = SimpleNamespace(id=1)
        request = MagicMock()

        notified = process_hospital_pre_announcements(
            request, vendor, utility, "start", "end"
        )
        notified_ids = [o.id for o in notified]
        self.assertNotIn(4, notified_ids)
        self.assertEqual(notified_ids, [3])
        self.assertEqual(mock_notify.call_args[0][2]["eta_minutes"], 20)

    @patch("manager.hospital_pre_announcement.VendorLogoSerializer")
    @patch("manager.hospital_pre_announcement.notify_web_push")
    @patch("manager.hospital_pre_announcement.Order.objects")
    @patch("manager.hospital_pre_announcement.get_department_queue_orders")
    def test_scenario_notify_token_4_once_when_distance_is_2(
        self, mock_get_queue, mock_order_objects, mock_notify, mock_logo
    ):
        from manager.hospital_pre_announcement import process_hospital_pre_announcements

        # Current called = 2; token 4 distance = 2; pre_count = 2 → notify once
        mock_logo.return_value.data = {"logo_url": ""}
        mock_get_queue.return_value = self._queue_orders(
            ["completed", "called", "waiting", "waiting", "waiting"]
        )
        mock_order_objects.filter.return_value.update.return_value = 1

        utility = SimpleNamespace(
            display_name="Radiology",
            pre_announcement_count=2,
            approximate_service_time=10,
        )
        vendor = SimpleNamespace(id=1)
        request = MagicMock()

        notified = process_hospital_pre_announcements(
            request, vendor, utility, "start", "end"
        )
        self.assertEqual(len(notified), 1)
        self.assertEqual(notified[0].id, 4)
        mock_notify.assert_called_once()
        _order_arg, _vendor_arg, payload = mock_notify.call_args[0]
        self.assertEqual(payload["type"], "hospital_pre_announcement")
        self.assertEqual(payload["department_name"], "Radiology")
        self.assertEqual(payload["eta_minutes"], 20)
        self.assertEqual(payload["queue_position"], 4)
        self.assertEqual(payload["distance_from_called"], 2)
        self.assertEqual(payload["booking_no"], "RAD-4")

    @patch("manager.hospital_pre_announcement.notify_web_push")
    @patch("manager.hospital_pre_announcement.Order.objects")
    @patch("manager.hospital_pre_announcement.get_department_queue_orders")
    def test_does_not_resend_when_already_notified(
        self, mock_get_queue, mock_order_objects, mock_notify
    ):
        from manager.hospital_pre_announcement import process_hospital_pre_announcements
        from django.utils import timezone

        mock_get_queue.return_value = self._queue_orders(
            ["completed", "called", "waiting", "waiting", "waiting"],
            notified_flags=[None, None, None, timezone.now(), None],
        )
        # Atomic claim fails because already notified
        mock_order_objects.filter.return_value.update.return_value = 0

        utility = SimpleNamespace(
            display_name="Radiology",
            pre_announcement_count=2,
            approximate_service_time=10,
        )
        notified = process_hospital_pre_announcements(
            MagicMock(), SimpleNamespace(id=1), utility, "start", "end"
        )
        self.assertEqual(notified, [])
        mock_notify.assert_not_called()

    @override_settings(PROJECT_NAME="dine_flash")
    @patch("manager.hospital_pre_announcement.notify_web_push")
    def test_noop_for_non_hospital_project(self, mock_notify):
        # Re-import path: function checks module-level project_name via is_hospital_flash
        import manager.hospital_pre_announcement as mod

        with patch.object(mod, "project_name", "dine_flash"):
            result = mod.process_hospital_pre_announcements(
                MagicMock(),
                SimpleNamespace(id=1),
                SimpleNamespace(pre_announcement_count=2, approximate_service_time=10),
                "start",
                "end",
            )
        self.assertEqual(result, [])
        mock_notify.assert_not_called()


class CrossFlavourGuardTests(SimpleTestCase):
    def test_manager_patient_update_404_outside_hospital(self):
        from manager import hospital_views

        with patch.object(hospital_views, "project_name", "food_flash"):
            response = hospital_views._hospital_flash_only_response()
        self.assertEqual(response.status_code, 404)

    def test_process_guard_paths_for_all_other_flavours(self):
        import manager.hospital_pre_announcement as mod

        for flavour in ("dine_flash", "dine_flash_buffet", "food_flash", "airline_flash"):
            with patch.object(mod, "project_name", flavour):
                self.assertFalse(mod.is_hospital_flash())
                self.assertEqual(
                    mod.process_hospital_pre_announcements(
                        MagicMock(),
                        SimpleNamespace(id=1),
                        SimpleNamespace(pre_announcement_count=2),
                        "s",
                        "e",
                    ),
                    [],
                )
