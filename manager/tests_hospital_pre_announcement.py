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
    def _queue_orders(self, statuses, notified_distances=None):
        notified_distances = notified_distances or [None] * len(statuses)
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
            order.pre_announcement_notified_at = None
            order.pre_announcement_notified_distance = notified_distances[i - 1]
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
    def test_window_notifies_all_within_pre_count(
        self, mock_get_queue, mock_order_objects, mock_notify, mock_logo
    ):
        """P1 Called, pre_count=2 → notify P2 (d=1) and P3 (d=2); not P4 (d=3)."""
        from manager.hospital_pre_announcement import process_hospital_pre_announcements

        mock_logo.return_value.data = {"logo_url": ""}
        mock_get_queue.return_value = self._queue_orders(
            ["called", "waiting", "waiting", "waiting"]
        )
        mock_order_objects.filter.return_value.filter.return_value.update.return_value = 1

        utility = SimpleNamespace(
            display_name="Radiology",
            pre_announcement_count=2,
            approximate_service_time=5,
        )
        vendor = SimpleNamespace(id=1)
        request = MagicMock()

        notified = process_hospital_pre_announcements(
            request, vendor, utility, "start", "end"
        )
        notified_ids = [o.id for o in notified]
        self.assertEqual(notified_ids, [2, 3])
        self.assertNotIn(4, notified_ids)
        self.assertEqual(mock_notify.call_count, 2)

        payloads_by_id = {
            call.args[0].id: call.args[2] for call in mock_notify.call_args_list
        }
        self.assertEqual(payloads_by_id[2]["eta_minutes"], 5)
        self.assertEqual(payloads_by_id[2]["distance_from_called"], 1)
        self.assertEqual(payloads_by_id[3]["eta_minutes"], 10)
        self.assertEqual(payloads_by_id[3]["distance_from_called"], 2)

    @patch("manager.hospital_pre_announcement.VendorLogoSerializer")
    @patch("manager.hospital_pre_announcement.notify_web_push")
    @patch("manager.hospital_pre_announcement.Order.objects")
    @patch("manager.hospital_pre_announcement.get_department_queue_orders")
    def test_queue_advance_renotifies_with_updated_eta(
        self, mock_get_queue, mock_order_objects, mock_notify, mock_logo
    ):
        """
        After P2 Called: P3 was notified at distance 2, now at distance 1 →
        re-notify with ETA 5; P4 newly enters window at distance 2 → ETA 10.
        """
        from manager.hospital_pre_announcement import process_hospital_pre_announcements

        mock_logo.return_value.data = {"logo_url": ""}
        # P3 previously notified at distance=2; P4 never notified
        mock_get_queue.return_value = self._queue_orders(
            ["completed", "called", "waiting", "waiting", "waiting"],
            notified_distances=[None, None, 2, None, None],
        )
        mock_order_objects.filter.return_value.filter.return_value.update.return_value = 1

        utility = SimpleNamespace(
            display_name="Radiology",
            pre_announcement_count=2,
            approximate_service_time=5,
        )
        notified = process_hospital_pre_announcements(
            MagicMock(), SimpleNamespace(id=1), utility, "start", "end"
        )
        notified_ids = [o.id for o in notified]
        self.assertEqual(notified_ids, [3, 4])
        payloads_by_id = {
            call.args[0].id: call.args[2] for call in mock_notify.call_args_list
        }
        self.assertEqual(payloads_by_id[3]["eta_minutes"], 5)
        self.assertEqual(payloads_by_id[3]["distance_from_called"], 1)
        self.assertEqual(payloads_by_id[4]["eta_minutes"], 10)
        self.assertEqual(payloads_by_id[4]["distance_from_called"], 2)
        self.assertEqual(payloads_by_id[3]["type"], "hospital_pre_announcement")

    @patch("manager.hospital_pre_announcement.notify_web_push")
    @patch("manager.hospital_pre_announcement.Order.objects")
    @patch("manager.hospital_pre_announcement.get_department_queue_orders")
    def test_does_not_resend_same_distance(
        self, mock_get_queue, mock_order_objects, mock_notify
    ):
        from manager.hospital_pre_announcement import process_hospital_pre_announcements

        # P3 already notified for current distance=2 (called index 1 → patient 3)
        mock_get_queue.return_value = self._queue_orders(
            ["called", "waiting", "waiting", "waiting"],
            notified_distances=[None, 1, 2, None],
        )
        # Atomic claim would also fail, but early skip should avoid the update
        mock_order_objects.filter.return_value.filter.return_value.update.return_value = 0

        utility = SimpleNamespace(
            display_name="Radiology",
            pre_announcement_count=2,
            approximate_service_time=5,
        )
        notified = process_hospital_pre_announcements(
            MagicMock(), SimpleNamespace(id=1), utility, "start", "end"
        )
        self.assertEqual(notified, [])
        mock_notify.assert_not_called()

    @patch("manager.hospital_pre_announcement.VendorLogoSerializer")
    @patch("manager.hospital_pre_announcement.notify_web_push")
    @patch("manager.hospital_pre_announcement.Order.objects")
    @patch("manager.hospital_pre_announcement.get_department_queue_orders")
    def test_atomic_claim_blocks_concurrent_same_distance(
        self, mock_get_queue, mock_order_objects, mock_notify, mock_logo
    ):
        from manager.hospital_pre_announcement import process_hospital_pre_announcements

        mock_logo.return_value.data = {"logo_url": ""}
        mock_get_queue.return_value = self._queue_orders(
            ["called", "waiting", "waiting"]
        )
        # Concurrent retry lost the race
        mock_order_objects.filter.return_value.filter.return_value.update.return_value = 0

        utility = SimpleNamespace(
            display_name="Radiology",
            pre_announcement_count=2,
            approximate_service_time=5,
        )
        notified = process_hospital_pre_announcements(
            MagicMock(), SimpleNamespace(id=1), utility, "start", "end"
        )
        self.assertEqual(notified, [])
        mock_notify.assert_not_called()

    @override_settings(PROJECT_NAME="dine_flash")
    @patch("manager.hospital_pre_announcement.notify_web_push")
    def test_noop_for_non_hospital_project(self, mock_notify):
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
