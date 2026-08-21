"""
Dine Flash Buffet pre-announcement unit tests.

Cross-flavour guard: these tests only exercise manager.buffet_pre_announcement
helpers and never import Hospital update paths.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings


class BuffetPreAnnouncementEligibilityTests(SimpleTestCase):
    def test_created_and_preparing_are_eligible(self):
        from manager.buffet_pre_announcement import is_eligible_for_buffet_pre_announcement

        self.assertTrue(is_eligible_for_buffet_pre_announcement("created"))
        self.assertTrue(is_eligible_for_buffet_pre_announcement("preparing"))

    def test_ready_and_terminal_are_excluded(self):
        from manager.buffet_pre_announcement import is_eligible_for_buffet_pre_announcement

        for status in ("ready", "delivered", "cancelled", "operation_closed"):
            self.assertFalse(is_eligible_for_buffet_pre_announcement(status))


class BuffetPreAnnouncementRecipientSelectionTests(SimpleTestCase):
    def _items(self, statuses):
        items = []
        for i, status in enumerate(statuses, start=1):
            items.append(SimpleNamespace(id=i, pk=i, status=status))
        return items

    def test_count_zero_selects_nobody(self):
        from manager.buffet_pre_announcement import select_buffet_pre_announcement_recipients

        queue = self._items(["ready", "created", "preparing"])
        self.assertEqual(select_buffet_pre_announcement_recipients(queue, 1, 0), [])

    def test_next_n_eligible_only(self):
        from manager.buffet_pre_announcement import select_buffet_pre_announcement_recipients

        # A ready (anchor), B created, C preparing, D created
        queue = self._items(["ready", "created", "preparing", "created"])
        recipients = select_buffet_pre_announcement_recipients(queue, 1, 2)
        self.assertEqual([(item.id, distance) for item, distance in recipients], [(2, 1), (3, 2)])

    def test_ready_item_itself_not_selected(self):
        from manager.buffet_pre_announcement import select_buffet_pre_announcement_recipients

        queue = self._items(["ready", "created"])
        recipients = select_buffet_pre_announcement_recipients(queue, 1, 5)
        self.assertEqual([item.id for item, _ in recipients], [2])

    def test_terminal_and_ready_do_not_consume_count(self):
        from manager.buffet_pre_announcement import select_buffet_pre_announcement_recipients

        # A ready (anchor), B ready, C created, D preparing, E cancelled, F created
        queue = self._items(
            ["ready", "ready", "created", "preparing", "cancelled", "created"]
        )
        recipients = select_buffet_pre_announcement_recipients(queue, 1, 2)
        self.assertEqual([(item.id, distance) for item, distance in recipients], [(3, 1), (4, 2)])

    def test_rolling_queue_after_later_ready(self):
        from manager.buffet_pre_announcement import select_buffet_pre_announcement_recipients

        # A ready, B ready (new anchor), C preparing, D created
        queue = self._items(["ready", "ready", "preparing", "created"])
        recipients = select_buffet_pre_announcement_recipients(queue, 2, 2)
        self.assertEqual([(item.id, distance) for item, distance in recipients], [(3, 1), (4, 2)])


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetPreAnnouncementProcessTests(SimpleTestCase):
    def setUp(self):
        import manager.buffet_pre_announcement as mod

        self._project_patcher = patch.object(mod, "project_name", "dine_flash_buffet")
        self._project_patcher.start()

    def tearDown(self):
        self._project_patcher.stop()

    def _queue_items(self, statuses, notified_distances=None):
        notified_distances = notified_distances or [None] * len(statuses)
        items = []
        vendor = SimpleNamespace(
            name="Buffet",
            alias_name="Buffet Cafe",
            vendor_id="B1",
            admin_outlet=None,
        )
        for i, status in enumerate(statuses, start=1):
            order = SimpleNamespace(
                id=100 + i,
                token_no=i,
                table_booking_no=f"T-{i}",
                vendor=vendor,
            )
            utility = SimpleNamespace(display_name="Dosa", id=10)
            item = MagicMock()
            item.pk = i
            item.id = i
            item.status = status
            item.pre_announcement_notified_at = None
            item.pre_announcement_notified_distance = notified_distances[i - 1]
            item.utility = utility
            item.order = order
            items.append(item)
        return items

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.BuffetOrderItem.objects")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_window_notifies_next_n_eligible(
        self, mock_get_queue, mock_item_objects, mock_notify, mock_chat
    ):
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        mock_get_queue.return_value = self._queue_items(
            ["ready", "created", "preparing", "created"]
        )
        mock_item_objects.filter.return_value.filter.return_value.filter.return_value.update.return_value = (
            1
        )

        utility = SimpleNamespace(display_name="Dosa", id=10, pre_announcement_count=2)
        vendor = SimpleNamespace(id=1, vendor_id="B1", alias_name="Buffet Cafe", name="Buffet")
        ready_item = mock_get_queue.return_value[0]

        notified = process_buffet_pre_announcements(
            vendor, utility, ready_item, "start", "end"
        )
        notified_ids = [item.id for item in notified]
        self.assertEqual(notified_ids, [2, 3])
        self.assertEqual(mock_notify.call_count, 2)
        self.assertEqual(mock_chat.call_count, 2)

        payloads_by_item = {
            call.args[2]["item_id"]: call.args[2] for call in mock_notify.call_args_list
        }
        self.assertEqual(payloads_by_item[2]["type"], "buffet_pre_announcement")
        self.assertEqual(payloads_by_item[2]["distance_from_ready"], 1)
        self.assertEqual(payloads_by_item[3]["distance_from_ready"], 2)
        # Service time unset/0: no ETA key (distance-only wording).
        self.assertNotIn("eta_minutes", payloads_by_item[2])
        self.assertNotIn("eta_minutes", payloads_by_item[3])
        self.assertNotIn("0 minute", payloads_by_item[2]["body"].lower())

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.BuffetOrderItem.objects")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_service_time_adds_eta_without_changing_recipients(
        self, mock_get_queue, mock_item_objects, mock_notify, mock_chat
    ):
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        mock_get_queue.return_value = self._queue_items(
            ["ready", "created", "preparing", "created"]
        )
        mock_item_objects.filter.return_value.filter.return_value.filter.return_value.update.return_value = (
            1
        )

        utility = SimpleNamespace(
            display_name="Dosa",
            id=10,
            pre_announcement_count=2,
            approximate_service_time=5,
        )
        vendor = SimpleNamespace(id=1, vendor_id="B1", alias_name="Buffet Cafe", name="Buffet")
        ready_item = mock_get_queue.return_value[0]

        notified = process_buffet_pre_announcements(
            vendor, utility, ready_item, "start", "end"
        )
        self.assertEqual([item.id for item in notified], [2, 3])
        payloads = {
            call.args[2]["item_id"]: call.args[2] for call in mock_notify.call_args_list
        }
        self.assertEqual(payloads[2]["distance_from_ready"], 1)
        self.assertEqual(payloads[2]["eta_minutes"], 5)
        self.assertEqual(payloads[3]["distance_from_ready"], 2)
        self.assertEqual(payloads[3]["eta_minutes"], 10)
        self.assertIn("approximately 5 minute", payloads[2]["body"])
        chat_payloads = [
            __import__("json").loads(call.kwargs["message_text"])
            for call in mock_chat.call_args_list
        ]
        by_item = {row["item_id"]: row for row in chat_payloads}
        self.assertEqual(by_item[2]["eta_minutes"], 5)
        self.assertEqual(by_item[3]["eta_minutes"], 10)

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.BuffetOrderItem.objects")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_service_time_zero_still_notifies_without_eta(
        self, mock_get_queue, mock_item_objects, mock_notify, mock_chat
    ):
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        mock_get_queue.return_value = self._queue_items(["ready", "created", "preparing"])
        mock_item_objects.filter.return_value.filter.return_value.filter.return_value.update.return_value = (
            1
        )
        utility = SimpleNamespace(
            display_name="Dosa",
            id=10,
            pre_announcement_count=2,
            approximate_service_time=0,
        )
        notified = process_buffet_pre_announcements(
            SimpleNamespace(id=1, vendor_id="B1", alias_name="Cafe", name="Cafe"),
            utility,
            mock_get_queue.return_value[0],
            "start",
            "end",
        )
        self.assertEqual([item.id for item in notified], [2, 3])
        payloads = {
            call.args[2]["item_id"]: call.args[2] for call in mock_notify.call_args_list
        }
        self.assertNotIn("eta_minutes", payloads[2])
        self.assertNotIn("0 minute", payloads[2]["body"].lower())

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.BuffetOrderItem.objects")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_same_distance_not_renotified_when_service_time_changes(
        self, mock_get_queue, mock_item_objects, mock_notify, mock_chat
    ):
        """Distance dedupe ignores service-time-only changes."""
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        mock_get_queue.return_value = self._queue_items(
            ["ready", "created"],
            notified_distances=[None, 1],
        )
        utility = SimpleNamespace(
            display_name="Dosa",
            id=10,
            pre_announcement_count=2,
            approximate_service_time=7,
        )
        notified = process_buffet_pre_announcements(
            SimpleNamespace(id=1, vendor_id="B1", alias_name="", name=""),
            utility,
            mock_get_queue.return_value[0],
            "start",
            "end",
        )
        self.assertEqual(notified, [])
        mock_notify.assert_not_called()
        mock_item_objects.filter.assert_not_called()

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_count_zero_sends_nothing(self, mock_get_queue, mock_notify, mock_chat):
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        mock_get_queue.return_value = self._queue_items(["ready", "created", "preparing"])
        utility = SimpleNamespace(display_name="Dosa", id=10, pre_announcement_count=0)
        notified = process_buffet_pre_announcements(
            SimpleNamespace(id=1),
            utility,
            mock_get_queue.return_value[0],
            "start",
            "end",
        )
        self.assertEqual(notified, [])
        mock_notify.assert_not_called()
        mock_chat.assert_not_called()
        mock_get_queue.assert_not_called()

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.BuffetOrderItem.objects")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_same_distance_deduped(
        self, mock_get_queue, mock_item_objects, mock_notify, mock_chat
    ):
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        mock_get_queue.return_value = self._queue_items(
            ["ready", "created", "preparing"],
            notified_distances=[None, 1, 2],
        )
        utility = SimpleNamespace(display_name="Dosa", id=10, pre_announcement_count=2)
        notified = process_buffet_pre_announcements(
            SimpleNamespace(id=1, vendor_id="B1", alias_name="", name=""),
            utility,
            mock_get_queue.return_value[0],
            "start",
            "end",
        )
        self.assertEqual(notified, [])
        mock_notify.assert_not_called()
        mock_item_objects.filter.assert_not_called()

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.BuffetOrderItem.objects")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_distance_change_renotifies(
        self, mock_get_queue, mock_item_objects, mock_notify, mock_chat
    ):
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        # After B becomes ready: C was notified at distance 2, now distance 1
        mock_get_queue.return_value = self._queue_items(
            ["ready", "ready", "preparing", "created"],
            notified_distances=[None, None, 2, None],
        )
        mock_item_objects.filter.return_value.filter.return_value.filter.return_value.update.return_value = (
            1
        )
        utility = SimpleNamespace(display_name="Dosa", id=10, pre_announcement_count=2)
        notified = process_buffet_pre_announcements(
            SimpleNamespace(id=1, vendor_id="B1", alias_name="Cafe", name="Cafe"),
            utility,
            mock_get_queue.return_value[1],
            "start",
            "end",
        )
        notified_ids = [item.id for item in notified]
        self.assertEqual(notified_ids, [3, 4])
        payloads = {
            call.args[2]["item_id"]: call.args[2] for call in mock_notify.call_args_list
        }
        self.assertEqual(payloads[3]["distance_from_ready"], 1)
        self.assertEqual(payloads[4]["distance_from_ready"], 2)

    @patch("manager.buffet_pre_announcement.ChatMessage.objects.create")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    @patch("manager.buffet_pre_announcement.BuffetOrderItem.objects")
    @patch("manager.buffet_pre_announcement.get_utility_queue_items")
    def test_atomic_claim_blocks_duplicate(
        self, mock_get_queue, mock_item_objects, mock_notify, mock_chat
    ):
        from manager.buffet_pre_announcement import process_buffet_pre_announcements

        mock_get_queue.return_value = self._queue_items(["ready", "created"])
        mock_item_objects.filter.return_value.filter.return_value.filter.return_value.update.return_value = (
            0
        )
        utility = SimpleNamespace(display_name="Dosa", id=10, pre_announcement_count=2)
        notified = process_buffet_pre_announcements(
            SimpleNamespace(id=1, vendor_id="B1", alias_name="", name=""),
            utility,
            mock_get_queue.return_value[0],
            "start",
            "end",
        )
        self.assertEqual(notified, [])
        mock_notify.assert_not_called()

    @override_settings(PROJECT_NAME="hospital_flash")
    @patch("manager.buffet_pre_announcement.notify_web_push")
    def test_noop_outside_buffet_flavour(self, mock_notify):
        import manager.buffet_pre_announcement as mod

        with patch.object(mod, "project_name", "hospital_flash"):
            result = mod.process_buffet_pre_announcements(
                SimpleNamespace(id=1),
                SimpleNamespace(pre_announcement_count=2),
                SimpleNamespace(pk=1),
                "s",
                "e",
            )
        self.assertEqual(result, [])
        mock_notify.assert_not_called()


class BuffetPreAnnouncementCrossFlavourGuardTests(SimpleTestCase):
    def test_guard_paths_for_all_other_flavours(self):
        import manager.buffet_pre_announcement as mod

        for flavour in ("hospital_flash", "dine_flash", "food_flash", "airline_flash"):
            with patch.object(mod, "project_name", flavour):
                self.assertFalse(mod.is_dine_flash_buffet())
                self.assertEqual(
                    mod.process_buffet_pre_announcements(
                        SimpleNamespace(id=1),
                        SimpleNamespace(pre_announcement_count=2),
                        SimpleNamespace(pk=1),
                        "s",
                        "e",
                    ),
                    [],
                )

    def test_dine_flash_is_not_treated_as_buffet(self):
        import manager.buffet_pre_announcement as mod

        with patch.object(mod, "project_name", "dine_flash"):
            self.assertFalse(mod.is_dine_flash_buffet())
