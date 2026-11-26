"""
Dine Flash Buffet — Parent ↔ Item Status Synchronization Tests.

Covers:
  A. Item → Parent aggregation (_aggregate_buffet_parent_status)
  B. Manager Parent → Item synchronization (_buffet_manager_sync_items_to_status,
     manager_order_update integration)
  C. Lifecycle and regression
"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status as drf_status
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from vendors.models import (
    AdminOutlet,
    BuffetOrderItem,
    Order,
    OrderStatusHistory,
    UserProfile,
    Utility,
    Vendor,
    VendorConfig,
)


# ---------------------------------------------------------------------------
# Shared DB helpers (reuse pattern from tests_get_today_orders_buffet_items)
# ---------------------------------------------------------------------------

def _create_vendor(suffix, customer_id, vendor_id):
    company = User.objects.create_user(username=f"co_bss_{suffix}", password="pass")
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


def _create_manager(outlet, vendor, username, role="outlet_manager", utilities=None):
    user = User.objects.create_user(username=username, password="secret123")
    profile = UserProfile.objects.create(
        user=user,
        name=username,
        role=role,
        admin_outlet=outlet,
        vendor=vendor,
    )
    if utilities:
        profile.assigned_utilities.set(utilities)
    return user, profile


def _today_order(vendor, token_no, *, order_status="created"):
    order = Order.objects.create(
        vendor=vendor,
        token_no=token_no,
        status=order_status,
        table_booking_no=str(token_no),
        customer_name="Guest",
        updated_by="customer",
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now())
    order.refresh_from_db()
    return order


def _add_item(order, utility, item_status="created"):
    return BuffetOrderItem.objects.create(order=order, utility=utility, status=item_status)


def _business_day_patch(views_module="manager.buffet_views"):
    return patch(
        f"{views_module}.get_vendor_business_day_range",
        return_value=(
            timezone.now() - timedelta(hours=12),
            timezone.now() + timedelta(hours=12),
        ),
    )


# ===========================================================================
# A. Item → Parent Aggregation (_aggregate_buffet_parent_status) — DB tests
# ===========================================================================

@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetParentAggregationTests(TestCase):
    """Real-DB tests for _aggregate_buffet_parent_status."""

    def setUp(self):
        self.outlet, self.vendor = _create_vendor("agg", 88101, 881001)
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Station A",
            display_name="Sta A",
            display_code="SA",
        )
        self.utility_b = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Station B",
            display_name="Sta B",
            display_code="SB",
        )

    def _fresh_order(self, token_no, order_status="created"):
        return _today_order(self.vendor, token_no, order_status=order_status)

    def _aggregate(self, order):
        from manager.buffet_views import _aggregate_buffet_parent_status
        order.refresh_from_db()
        return _aggregate_buffet_parent_status(order)

    # Test 1: All active items preparing → parent preparing
    def test_all_preparing_returns_preparing(self):
        order = self._fresh_order(1001)
        _add_item(order, self.utility, "preparing")
        _add_item(order, self.utility_b, "preparing")
        self.assertEqual(self._aggregate(order), "preparing")

    # Test 2: All active items ready → parent ready
    def test_all_ready_returns_ready(self):
        order = self._fresh_order(1002)
        _add_item(order, self.utility, "ready")
        _add_item(order, self.utility_b, "ready")
        self.assertEqual(self._aggregate(order), "ready")

    # Test 3: All active items delivered → parent delivered
    def test_all_delivered_returns_delivered(self):
        order = self._fresh_order(1003)
        _add_item(order, self.utility, "delivered")
        _add_item(order, self.utility_b, "delivered")
        self.assertEqual(self._aggregate(order), "delivered")

    # Test 4: Mixed active statuses → no change (None)
    def test_mixed_active_statuses_returns_none(self):
        order = self._fresh_order(1004)
        _add_item(order, self.utility, "preparing")
        _add_item(order, self.utility_b, "ready")
        self.assertIsNone(self._aggregate(order))

    # Test 5: Cancelled items ignored when non-cancelled items exist
    def test_cancelled_ignored_with_non_cancelled(self):
        order = self._fresh_order(1005)
        _add_item(order, self.utility, "ready")
        _add_item(order, self.utility_b, "cancelled")
        # Only ready remains; should return ready
        self.assertEqual(self._aggregate(order), "ready")

    def test_preparing_and_cancelled_returns_preparing(self):
        order = self._fresh_order(1006)
        _add_item(order, self.utility, "preparing")
        _add_item(order, self.utility_b, "preparing")
        _add_item(order, self.utility_b, "cancelled")
        self.assertEqual(self._aggregate(order), "preparing")

    # Test 6: All items cancelled → parent cancelled
    def test_all_cancelled_returns_cancelled(self):
        order = self._fresh_order(1007)
        _add_item(order, self.utility, "cancelled")
        _add_item(order, self.utility_b, "cancelled")
        self.assertEqual(self._aggregate(order), "cancelled")

    # Test 7: Cancelled item reactivated → participates in aggregation
    def test_reactivated_item_participates_in_aggregation(self):
        order = self._fresh_order(1008)
        item = _add_item(order, self.utility, "cancelled")
        # Reactivate: set to ready
        item.status = "ready"
        item.save(update_fields=["status"])
        # Now: ready item + no other items → should return ready
        self.assertEqual(self._aggregate(order), "ready")

    # Test 8: Empty order → no change (None)
    def test_empty_order_returns_none(self):
        order = self._fresh_order(1009)
        self.assertIsNone(self._aggregate(order))

    # Test 9: Parent status changes → OrderStatusHistory entry created
    def test_parent_status_change_creates_history(self):
        order = self._fresh_order(1010, order_status="created")
        _add_item(order, self.utility, "preparing")
        history_before = OrderStatusHistory.objects.filter(order=order).count()
        order.status = "preparing"
        order.save(update_fields=["status"])
        history_after = OrderStatusHistory.objects.filter(order=order).count()
        # pre_save signal fires and creates a new history entry
        self.assertGreater(history_after, history_before)

    # Test 10: Parent status unchanged → no unnecessary history entry
    def test_parent_status_unchanged_no_history(self):
        order = self._fresh_order(1011, order_status="preparing")
        _add_item(order, self.utility, "preparing")
        from manager.buffet_views import _aggregate_buffet_parent_status
        order.refresh_from_db()
        computed = _aggregate_buffet_parent_status(order)
        # Computed is "preparing", same as current
        history_before = OrderStatusHistory.objects.filter(order=order).count()
        # Simulate: only save when different
        if computed is not None and order.status != computed:
            order.status = computed
            order.save(update_fields=["status"])
        history_after = OrderStatusHistory.objects.filter(order=order).count()
        # No save happened, so no new history
        self.assertEqual(history_before, history_after)

    # Test 11: operation_closed participates as a non-cancelled status
    def test_operation_closed_is_non_cancelled(self):
        order = self._fresh_order(1012)
        _add_item(order, self.utility, "operation_closed")
        _add_item(order, self.utility_b, "operation_closed")
        # All items have the same status (operation_closed) → aggregate returns it
        self.assertEqual(self._aggregate(order), "operation_closed")

    def test_operation_closed_mixed_does_not_aggregate(self):
        order = self._fresh_order(1013)
        _add_item(order, self.utility, "operation_closed")
        _add_item(order, self.utility_b, "ready")
        # Mixed → no change
        self.assertIsNone(self._aggregate(order))


# ===========================================================================
# B. Item → Parent via buffet_update_item_status pathway (DB integration)
# ===========================================================================

@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetUpdateItemStatusAggregationTests(TestCase):
    """
    DB integration tests: when buffet_update_item_status changes an item,
    the parent Order.status is aggregated correctly.
    """

    def setUp(self):
        self.outlet, self.vendor = _create_vendor("itmagg", 88201, 882001)
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Station C",
            display_name="Sta C",
            display_code="SC",
        )
        self.utility_b = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Station D",
            display_name="Sta D",
            display_code="SD",
        )
        self.mgr_user, self.mgr_profile = _create_manager(self.outlet, self.vendor, "itmagg_mgr")
        self.client = APIClient()
        self.client.force_authenticate(user=self.mgr_user)

    def _post_item_status(self, item_id, new_status):
        url = reverse("manager:buffet_update_item_status")
        with _business_day_patch():
            return self.client.post(
                url,
                {"item_id": item_id, "status": new_status},
                format="json",
            )

    def test_all_items_preparing_aggregates_parent_to_preparing(self):
        order = _today_order(self.vendor, 2001)
        item1 = _add_item(order, self.utility, "created")
        item2 = _add_item(order, self.utility_b, "preparing")
        resp = self._post_item_status(item1.id, "preparing")
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "preparing")

    def test_all_items_ready_aggregates_parent_to_ready(self):
        order = _today_order(self.vendor, 2002)
        item1 = _add_item(order, self.utility, "ready")
        item2 = _add_item(order, self.utility_b, "created")
        resp = self._post_item_status(item2.id, "ready")
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "ready")

    def test_all_items_delivered_aggregates_parent_to_delivered(self):
        order = _today_order(self.vendor, 2003)
        item1 = _add_item(order, self.utility, "delivered")
        item2 = _add_item(order, self.utility_b, "ready")
        resp = self._post_item_status(item2.id, "delivered")
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "delivered")

    def test_mixed_statuses_do_not_change_parent(self):
        order = _today_order(self.vendor, 2004, order_status="created")
        item1 = _add_item(order, self.utility, "preparing")
        item2 = _add_item(order, self.utility_b, "created")
        # Set item2 to ready → now preparing + ready = mixed
        resp = self._post_item_status(item2.id, "ready")
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        order.refresh_from_db()
        # Parent stays at its current status (unchanged)
        self.assertEqual(order.status, "created")

    def test_cancelled_item_ignored_non_cancelled_items_exist(self):
        order = _today_order(self.vendor, 2005)
        item1 = _add_item(order, self.utility, "cancelled")
        item2 = _add_item(order, self.utility_b, "created")
        # Set item2 to ready → non-cancelled = only ready
        resp = self._post_item_status(item2.id, "ready")
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "ready")

    def test_all_items_cancelled_aggregates_parent_to_cancelled(self):
        order = _today_order(self.vendor, 2006)
        item1 = _add_item(order, self.utility, "cancelled")
        item2 = _add_item(order, self.utility_b, "ready")
        resp = self._post_item_status(item2.id, "cancelled")
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

    def test_reactivated_item_participates_in_aggregation(self):
        order = _today_order(self.vendor, 2007)
        item1 = _add_item(order, self.utility, "cancelled")
        # Reactivate item1 to ready
        resp = self._post_item_status(item1.id, "ready")
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, "ready")

    def test_updated_by_not_changed_on_aggregation(self):
        """Aggregation must not alter the existing updated_by value."""
        order = _today_order(self.vendor, 2008)
        Order.objects.filter(pk=order.pk).update(updated_by="customer")
        order.refresh_from_db()
        item1 = _add_item(order, self.utility, "created")
        self._post_item_status(item1.id, "preparing")
        order.refresh_from_db()
        # Aggregation set parent status but must not have changed updated_by
        self.assertEqual(order.updated_by, "customer")

    def test_aggregation_creates_order_status_history_entry(self):
        order = _today_order(self.vendor, 2009, order_status="created")
        item1 = _add_item(order, self.utility, "created")
        history_before = OrderStatusHistory.objects.filter(order=order).count()
        # This should aggregate parent from 'created' → 'preparing'
        self._post_item_status(item1.id, "preparing")
        history_after = OrderStatusHistory.objects.filter(order=order).count()
        order.refresh_from_db()
        self.assertEqual(order.status, "preparing")
        self.assertGreater(history_after, history_before)


# ===========================================================================
# C. Manager → Item Sync (_buffet_manager_sync_items_to_status) — DB tests
# ===========================================================================

@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetManagerItemSyncTests(TestCase):
    """Real-DB tests for _buffet_manager_sync_items_to_status."""

    def setUp(self):
        self.outlet, self.vendor = _create_vendor("msync", 88301, 883001)
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Station E",
            display_name="Sta E",
            display_code="SE",
        )
        self.utility_b = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Station F",
            display_name="Sta F",
            display_code="SF",
        )

    def _sync(self, order, target_status):
        from manager.buffet_views import _buffet_manager_sync_items_to_status
        return _buffet_manager_sync_items_to_status(order, target_status)

    # Test 12: Manager sets preparing → all non-cancelled items become preparing
    def test_manager_preparing_syncs_non_cancelled(self):
        order = _today_order(self.vendor, 3001)
        item1 = _add_item(order, self.utility, "created")
        item2 = _add_item(order, self.utility_b, "ready")
        item3 = _add_item(order, self.utility_b, "cancelled")
        changed = self._sync(order, "preparing")
        self.assertEqual(changed, 2)
        item1.refresh_from_db()
        item2.refresh_from_db()
        item3.refresh_from_db()
        self.assertEqual(item1.status, "preparing")
        self.assertEqual(item2.status, "preparing")
        self.assertEqual(item3.status, "cancelled")  # preserved

    # Test 13: Manager sets ready → all non-cancelled items become ready
    def test_manager_ready_syncs_non_cancelled(self):
        order = _today_order(self.vendor, 3002)
        item1 = _add_item(order, self.utility, "created")
        item2 = _add_item(order, self.utility_b, "preparing")
        item3 = _add_item(order, self.utility, "cancelled")
        changed = self._sync(order, "ready")
        self.assertEqual(changed, 2)
        item1.refresh_from_db()
        item2.refresh_from_db()
        item3.refresh_from_db()
        self.assertEqual(item1.status, "ready")
        self.assertEqual(item2.status, "ready")
        self.assertEqual(item3.status, "cancelled")

    # Test 14: Manager sets delivered → all non-cancelled items become delivered
    def test_manager_delivered_syncs_non_cancelled(self):
        order = _today_order(self.vendor, 3003)
        item1 = _add_item(order, self.utility, "ready")
        item2 = _add_item(order, self.utility_b, "preparing")
        item3 = _add_item(order, self.utility, "cancelled")
        changed = self._sync(order, "delivered")
        self.assertEqual(changed, 2)
        item1.refresh_from_db()
        item2.refresh_from_db()
        item3.refresh_from_db()
        self.assertEqual(item1.status, "delivered")
        self.assertEqual(item2.status, "delivered")
        self.assertEqual(item3.status, "cancelled")

    # Test 15: Manager sets cancelled → all non-cancelled items become cancelled
    def test_manager_cancelled_syncs_all_to_cancelled(self):
        order = _today_order(self.vendor, 3004)
        item1 = _add_item(order, self.utility, "ready")
        item2 = _add_item(order, self.utility_b, "preparing")
        item3 = _add_item(order, self.utility, "cancelled")  # already cancelled
        changed = self._sync(order, "cancelled")
        self.assertEqual(changed, 2)
        item1.refresh_from_db()
        item2.refresh_from_db()
        item3.refresh_from_db()
        self.assertEqual(item1.status, "cancelled")
        self.assertEqual(item2.status, "cancelled")
        self.assertEqual(item3.status, "cancelled")

    # Test 16: Existing cancelled items remain cancelled during non-cancellation updates
    def test_already_cancelled_preserved_during_non_cancel_sync(self):
        order = _today_order(self.vendor, 3005)
        item1 = _add_item(order, self.utility, "cancelled")
        item2 = _add_item(order, self.utility_b, "cancelled")
        # Sync to ready: nothing should change
        changed = self._sync(order, "ready")
        self.assertEqual(changed, 0)
        item1.refresh_from_db()
        item2.refresh_from_db()
        self.assertEqual(item1.status, "cancelled")
        self.assertEqual(item2.status, "cancelled")

    # Test 17: Manager cancellation handles already-cancelled items correctly
    def test_manager_cancel_does_not_double_cancel(self):
        order = _today_order(self.vendor, 3006)
        item1 = _add_item(order, self.utility, "cancelled")
        item2 = _add_item(order, self.utility_b, "ready")
        changed = self._sync(order, "cancelled")
        self.assertEqual(changed, 1)  # only item2 changed
        item1.refresh_from_db()
        item2.refresh_from_db()
        self.assertEqual(item1.status, "cancelled")
        self.assertEqual(item2.status, "cancelled")

    # Test 18: Subsequent item-level status changes after manager override still work
    def test_subsequent_item_changes_work_after_manager_sync(self):
        order = _today_order(self.vendor, 3007)
        item1 = _add_item(order, self.utility, "created")
        item2 = _add_item(order, self.utility_b, "created")
        # Manager syncs to ready
        self._sync(order, "ready")
        item1.refresh_from_db()
        item2.refresh_from_db()
        self.assertEqual(item1.status, "ready")
        self.assertEqual(item2.status, "ready")
        # Then item1 is updated individually to delivered
        item1.status = "delivered"
        item1.save(update_fields=["status"])
        # Aggregation should now be: delivered + ready = mixed → no change
        from manager.buffet_views import _aggregate_buffet_parent_status
        order.refresh_from_db()
        computed = _aggregate_buffet_parent_status(order)
        self.assertIsNone(computed)

    # Test 19: Mixed item statuses after subsequent updates leave parent unchanged
    def test_mixed_statuses_after_subsequent_updates(self):
        order = _today_order(self.vendor, 3008, order_status="preparing")
        item1 = _add_item(order, self.utility, "preparing")
        item2 = _add_item(order, self.utility_b, "ready")
        from manager.buffet_views import _aggregate_buffet_parent_status
        order.refresh_from_db()
        computed = _aggregate_buffet_parent_status(order)
        self.assertIsNone(computed)

    # Test 20: Reactivated items participate in subsequent aggregation
    def test_reactivated_items_participate_in_subsequent_aggregation(self):
        order = _today_order(self.vendor, 3009)
        item1 = _add_item(order, self.utility, "cancelled")
        item2 = _add_item(order, self.utility_b, "cancelled")
        # Manager cancels all — from aggregation standpoint all cancelled → parent = cancelled
        from manager.buffet_views import _aggregate_buffet_parent_status
        order.refresh_from_db()
        self.assertEqual(_aggregate_buffet_parent_status(order), "cancelled")
        # Now reactivate item1 to ready
        item1.status = "ready"
        item1.save(update_fields=["status"])
        # item2 is still cancelled, item1 is ready → non-cancelled = ready → parent = ready
        order.refresh_from_db()
        self.assertEqual(_aggregate_buffet_parent_status(order), "ready")


# ===========================================================================
# D. Manager → Item via manager_order_update (mocked — unit tests)
# ===========================================================================

def _mock_vendor(tv_mode="MQTT", mqtt_mode=True, pk=1, vendor_id=990001):
    return SimpleNamespace(
        id=pk,
        name="Buffet Outlet",
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


def _mock_manager_user(vendor):
    user = MagicMock()
    user.username = "bmgr"
    profile = MagicMock()
    profile.role = "outlet_manager"
    profile.name = "BManager"
    profile.vendor = vendor
    qs = MagicMock()
    qs.exists.return_value = True
    qs.first.return_value = profile
    user.profile_roles = qs
    return user


def _mock_order(vendor, token_no=42, order_id=200, order_status="created"):
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


def _call_manager_order_update(action, vendor=None, mock_sync=True):
    """
    Call manager_order_update for Buffet with common mocks.
    Returns (response, mock_buffet_update, mock_push, mock_update).
    """
    from manager import views as manager_views

    if vendor is None:
        vendor = _mock_vendor()
    user = _mock_manager_user(vendor)
    order = _mock_order(vendor)
    factory = APIRequestFactory()
    request = factory.patch(
        "/manager/api/manager_order_update/",
        {"token_no": 42, "action": action, "status": action},
        format="json",
    )
    force_authenticate(request, user=user)

    updated = MagicMock()
    updated.token_no = order.token_no
    updated.status = action

    with patch.object(manager_views, "project_name", "dine_flash_buffet"), \
         patch("manager.views.get_vendor_business_day_range",
               return_value=(timezone.now() - timedelta(hours=1),
                             timezone.now() + timedelta(hours=1))), \
         patch("manager.views.Order.objects.filter") as mock_filter, \
         patch("manager.views.VendorLogoSerializer") as mock_logo, \
         patch("manager.views.update_existing_order_by_manager",
               return_value=updated) as mock_update, \
         patch("manager.buffet_views._buffet_manager_update_order_and_sync_items",
               return_value=updated) as mock_buffet_update, \
         patch("manager.views.notify_web_push", return_value=[]) as mock_push, \
         patch("manager.views.notify_android_tv", return_value=(True, "ok")), \
         patch("manager.views.send_order_update", return_value=True):
        mock_filter.return_value.first.return_value = order
        mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
        response = manager_views.manager_order_update(request)
        return response, mock_buffet_update, mock_push, mock_update


@override_settings(PROJECT_NAME="dine_flash_buffet", PUSH_COOLDOWN_SECONDS=1)
class BuffetManagerOrderUpdateItemSyncUnitTests(SimpleTestCase):
    """
    Unit tests (mocked) verifying manager_order_update calls item sync for Buffet.
    Does not generate individual item notifications.
    """

    def _assert_sync_called(self, action, expected_target):
        response, mock_buffet_update, mock_push, mock_update = \
            _call_manager_order_update(action)
        self.assertEqual(response.status_code, drf_status.HTTP_200_OK,
                         response.data)
        # Buffet manager update wrapper must be invoked with token, vendor, None, action, manager
        mock_buffet_update.assert_called_once()
        call_args = mock_buffet_update.call_args
        self.assertEqual(call_args.args[0], 42)
        self.assertEqual(call_args.args[3], expected_target)
        return response, mock_push

    def test_ready_action_syncs_items_to_ready(self):
        self._assert_sync_called("ready", "ready")

    def test_preparing_action_syncs_items_to_preparing(self):
        self._assert_sync_called("preparing", "preparing")

    def test_delivered_action_syncs_items_to_delivered(self):
        self._assert_sync_called("delivered", "delivered")

    def test_cancelled_action_syncs_items_to_cancelled(self):
        self._assert_sync_called("cancelled", "cancelled")

    def test_manager_level_web_push_still_fires(self):
        """Existing manager-level web push behaviour is preserved."""
        _, _, mock_push, _ = _call_manager_order_update("ready")
        # Web push fires exactly once at the manager order level
        mock_push.assert_called_once()

    def test_no_individual_item_chat_messages(self):
        """
        Manager bulk sync must not create individual item ChatMessages.
        _notify_item_update is on the item pathway; it must NOT be called here.
        """
        from manager import views as manager_views
        vendor = _mock_vendor()
        user = _mock_manager_user(vendor)
        order = _mock_order(vendor)
        factory = APIRequestFactory()
        request = factory.patch(
            "/manager/api/manager_order_update/",
            {"token_no": 42, "action": "ready", "status": "ready"},
            format="json",
        )
        force_authenticate(request, user=user)
        updated = MagicMock()
        updated.token_no = 42
        updated.status = "ready"
        with patch.object(manager_views, "project_name", "dine_flash_buffet"), \
             patch("manager.views.get_vendor_business_day_range",
                   return_value=(timezone.now() - timedelta(hours=1),
                                 timezone.now() + timedelta(hours=1))), \
             patch("manager.views.Order.objects.filter") as mock_filter, \
             patch("manager.views.VendorLogoSerializer") as mock_logo, \
             patch("manager.buffet_views._buffet_manager_update_order_and_sync_items",
                   return_value=updated), \
             patch("manager.views.notify_web_push", return_value=[]), \
             patch("manager.buffet_views._notify_item_update") as mock_notify_item:
            mock_filter.return_value.first.return_value = order
            mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
            manager_views.manager_order_update(request)
        # _notify_item_update (which creates ChatMessages) must NOT be called
        mock_notify_item.assert_not_called()

    def test_manager_update_enclosed_in_atomic_with_parent_lock_first(self):
        """
        Verify that _buffet_manager_update_order_and_sync_items:
        1. Opens transaction.atomic()
        2. Locks parent Order using select_for_update() BEFORE updating parent or items
        3. Calls update_existing_order_by_manager
        4. Bulk syncs items and schedules registry lifecycle on commit
        """
        from manager.buffet_views import _buffet_manager_update_order_and_sync_items
        vendor = _mock_vendor()
        manager = MagicMock(name="manager")
        order_mock = MagicMock()
        order_mock.pk = 100
        order_mock.token_no = 42

        call_log = []

        class MockAtomic:
            def __enter__(self):
                call_log.append("atomic_enter")
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                call_log.append("atomic_exit")

        mock_qs = MagicMock()
        mock_qs.first.return_value = order_mock

        def fake_select_for_update(*args, **kwargs):
            call_log.append("parent_select_for_update")
            return mock_qs

        def fake_update_parent(token, vend, dev, action, mgr):
            call_log.append("update_parent")
            return order_mock

        def fake_sync_items(order, action):
            call_log.append(f"sync_items_{action}")

        with patch("django.db.transaction.atomic", side_effect=MockAtomic), \
             patch("manager.buffet_views.get_vendor_business_day_range",
                   return_value=(timezone.now() - timedelta(hours=1),
                                 timezone.now() + timedelta(hours=1))), \
             patch("manager.buffet_views.Order.objects.select_for_update",
                   side_effect=fake_select_for_update), \
             patch("static.utils.functions.queries.update_existing_order_by_manager",
                   side_effect=fake_update_parent), \
             patch("manager.buffet_views._buffet_sync_manager_items_and_registry",
                   side_effect=fake_sync_items):
            res = _buffet_manager_update_order_and_sync_items(42, vendor, None, "ready", manager)

        self.assertEqual(res, order_mock)
        self.assertEqual(call_log, [
            "atomic_enter",
            "parent_select_for_update",
            "update_parent",
            "sync_items_ready",
            "atomic_exit",
        ])


# ===========================================================================
# E. Lifecycle and Regression
# ===========================================================================

@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetLifecycleRegressionTests(TestCase):
    """
    DB tests for registry cleanup and cross-flavour isolation.
    """

    def setUp(self):
        self.outlet, self.vendor = _create_vendor("lifecycle", 88401, 884001)
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Station G",
            display_name="Sta G",
            display_code="SG",
        )

    def test_non_buffet_flavour_aggregate_not_called(self):
        """
        _aggregate_buffet_parent_status is a pure function that works on any Order,
        but _update_buffet_item_status is gated to dine_flash_buffet only.
        Confirm the gate exists in buffet_update_item_status view.
        """
        from manager.buffet_views import buffet_update_item_status
        factory = APIRequestFactory()
        request = factory.post(
            "/manager/api/buffet_update_item_status/",
            {"item_id": 1, "status": "ready"},
            format="json",
        )
        from django.contrib.auth.models import User as DjangoUser
        user = MagicMock()
        user.username = "food_mgr"
        force_authenticate(request, user=user)
        with patch("manager.buffet_views.project_name", "food_flash"):
            response = buffet_update_item_status(request)
        self.assertEqual(response.status_code, drf_status.HTTP_404_NOT_FOUND)

    # Test 21: Registry cleanup after delivered lifecycle
    def test_registry_lifecycle_scheduled_on_delivered_aggregation(self):
        """
        When all items become delivered, registry lifecycle sync is scheduled
        (via transaction.on_commit). Verifies _sync_buffet_registry_after_lifecycle
        is invoked from the item pathway.
        """
        order = _today_order(self.vendor, 4001, order_status="preparing")
        item = _add_item(order, self.utility, "preparing")
        mgr_user, _ = _create_manager(self.outlet, self.vendor, "reg_del_mgr")
        client = APIClient()
        client.force_authenticate(user=mgr_user)
        url = reverse("manager:buffet_update_item_status")
        with _business_day_patch(), \
             patch("manager.buffet_views._sync_buffet_registry_after_lifecycle") as mock_reg:
            resp = client.post(
                url,
                {"item_id": item.id, "status": "delivered"},
                format="json",
            )
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        mock_reg.assert_called_once()

    # Test 22: Registry cleanup when all items are cancelled
    def test_registry_lifecycle_scheduled_on_all_cancelled(self):
        order = _today_order(self.vendor, 4002, order_status="preparing")
        item = _add_item(order, self.utility, "preparing")
        mgr_user, _ = _create_manager(self.outlet, self.vendor, "reg_cancel_mgr")
        client = APIClient()
        client.force_authenticate(user=mgr_user)
        url = reverse("manager:buffet_update_item_status")
        with _business_day_patch(), \
             patch("manager.buffet_views._sync_buffet_registry_after_lifecycle") as mock_reg:
            resp = client.post(
                url,
                {"item_id": item.id, "status": "cancelled"},
                format="json",
            )
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        mock_reg.assert_called_once()

    # Test 25: Non-Buffet flavour behaviour is unaffected
    def test_food_flash_manager_order_update_unaffected(self):
        """
        manager_order_update with food_flash should not call buffet item sync.
        """
        from manager import views as manager_views

        vendor = _mock_vendor(tv_mode="Firebase")
        user = _mock_manager_user(vendor)
        order = _mock_order(vendor)
        factory = APIRequestFactory()
        request = factory.patch(
            "/manager/api/manager_order_update/",
            {"token_no": 42, "action": "ready", "status": "ready"},
            format="json",
        )
        force_authenticate(request, user=user)
        updated = MagicMock()
        updated.token_no = 42
        updated.status = "ready"
        with patch.object(manager_views, "project_name", "food_flash"), \
             patch("manager.views.get_vendor_business_day_range",
                   return_value=(timezone.now() - timedelta(hours=1),
                                 timezone.now() + timedelta(hours=1))), \
             patch("manager.views.Order.objects.filter") as mock_filter, \
             patch("manager.views.VendorLogoSerializer") as mock_logo, \
             patch("manager.views.update_existing_order_by_manager",
                   return_value=updated) as mock_update, \
             patch("manager.views.notify_web_push", return_value=[]) as mock_push, \
             patch("manager.views.notify_android_tv", return_value=(True, "ok")) as mock_tv:
            mock_filter.return_value.first.return_value = order
            mock_logo.return_value.data = {"logo_url": "https://example.test/logo.png"}
            response = manager_views.manager_order_update(request)
        # Must succeed
        self.assertEqual(response.status_code, drf_status.HTTP_200_OK)
        # Android TV should be called (non-buffet Firebase path)
        mock_tv.assert_called_once()
        # update_existing_order_by_manager called once
        mock_update.assert_called_once()


# ===========================================================================
# F. Pure-unit tests for _aggregate_buffet_parent_status (no DB)
# ===========================================================================

class BuffetAggregateUnitTests(SimpleTestCase):
    """Unit tests using mock order objects — no DB required."""

    def _run(self, statuses):
        from manager.buffet_views import _aggregate_buffet_parent_status
        order = MagicMock()
        items = [MagicMock(status=s) for s in statuses]
        order.buffet_items.all.return_value = items
        return _aggregate_buffet_parent_status(order)

    def test_no_items_returns_none(self):
        self.assertIsNone(self._run([]))

    def test_all_preparing(self):
        self.assertEqual(self._run(["preparing", "preparing"]), "preparing")

    def test_all_ready(self):
        self.assertEqual(self._run(["ready", "ready"]), "ready")

    def test_all_delivered(self):
        self.assertEqual(self._run(["delivered", "delivered"]), "delivered")

    def test_mixed_active(self):
        self.assertIsNone(self._run(["preparing", "ready"]))

    def test_ready_and_cancelled(self):
        self.assertEqual(self._run(["ready", "cancelled"]), "ready")

    def test_preparing_preparing_cancelled(self):
        self.assertEqual(self._run(["preparing", "preparing", "cancelled"]), "preparing")

    def test_all_cancelled(self):
        self.assertEqual(self._run(["cancelled", "cancelled"]), "cancelled")

    def test_operation_closed_non_cancelled(self):
        self.assertEqual(self._run(["operation_closed", "operation_closed"]), "operation_closed")

    def test_operation_closed_mixed_with_ready(self):
        self.assertIsNone(self._run(["operation_closed", "ready"]))

    def test_single_item_ready(self):
        self.assertEqual(self._run(["ready"]), "ready")

    def test_single_item_cancelled(self):
        self.assertEqual(self._run(["cancelled"]), "cancelled")
