import threading
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from orders.scheduler import _archive_and_delete_eligible_order, auto_clear_orders
from vendors.models import (
    AdminOutlet,
    ArchivedOrder,
    ArchivedOrderStatusHistory,
    Order,
    OrderStatusHistory,
    PushSubscription,
    Vendor,
    VendorConfig,
)
from vendors.utils import archive_order, idempotent_auto_clear_archival_enabled

PROTECTED_AUTO_CLEAR_FLAVOURS = (
    "dine_flash",
    "dine_flash_buffet",
    "hospital_flash",
)
LEGACY_AUTO_CLEAR_FLAVOURS = (
    "food_flash",
    "airline_flash",
)


def _database_is_mysql():
    engine = settings.DATABASES["default"]["ENGINE"]
    return "mysql" in engine.lower()


class AutoClearOrdersTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sched_admin", password="pass1234")
        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Sched Co",
            customer_id=200,
            locations=[{"CityA": "C1"}],
            authentication_status="Approve",
            product_to_date=timezone.now() + timedelta(days=30),
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Sched Outlet",
            alias_name="SO",
            location="CityA",
            place_id="place-sched",
            vendor_id=654321,
            location_id="L-sched",
            menus="[]",
        )
        self.config = VendorConfig.objects.create(
            vendor=self.vendor,
            auto_delete_hours=2,
        )
        self.client = APIClient()
        self.client.login(username="sched_admin", password="pass1234")

    def _create_stale_order(self, token_no=42, with_history=False):
        order = Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            status="preparing",
        )
        stale_at = timezone.now() - timedelta(hours=5)
        Order.objects.filter(pk=order.pk).update(
            created_at=stale_at,
            updated_at=stale_at,
        )
        order.refresh_from_db()
        if with_history:
            OrderStatusHistory.objects.create(
                order=order,
                previous_status="preparing",
                new_status="ready",
                changed_by="manager",
            )
        return order

    def _seed_archived_order_primary_key(self):
        """
        Reserve an ArchivedOrder primary key so post-archive timeline tests do not
        accidentally pass when ArchivedOrder.pk equals the former Order.pk.
        """
        ArchivedOrder.objects.create(
            original_order_id=-1,
            vendor=self.vendor,
            device=None,
            user_profile=None,
            token_no=9998,
            status="preparing",
            counter_no=1,
            shown_on_tv=False,
            notified_at=None,
            updated_by="manager",
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )


class IdempotentAutoClearFlavourGateTests(TestCase):
    def test_gate_enabled_for_protected_flavours(self):
        for flavour in PROTECTED_AUTO_CLEAR_FLAVOURS:
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                self.assertTrue(idempotent_auto_clear_archival_enabled())

    def test_gate_disabled_for_legacy_flavours(self):
        for flavour in LEGACY_AUTO_CLEAR_FLAVOURS:
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                self.assertFalse(idempotent_auto_clear_archival_enabled())


@override_settings(PROJECT_NAME="dine_flash")
class ArchiveOrderUtilsTests(AutoClearOrdersTestBase):
    def test_archive_order_creates_snapshot_and_history(self):
        order = self._create_stale_order(with_history=True)
        expected_history_count = order.status_history.count()
        with transaction.atomic():
            archived = archive_order(order)
        self.assertEqual(archived.original_order_id, order.id)
        self.assertEqual(
            ArchivedOrderStatusHistory.objects.filter(archived_order=archived).count(),
            expected_history_count,
        )

    def test_archive_order_reuses_existing_without_duplicating_history(self):
        order = self._create_stale_order(with_history=True)
        expected_history_count = order.status_history.count()
        with transaction.atomic():
            first = archive_order(order)
        with transaction.atomic():
            second = archive_order(order)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 1)
        self.assertEqual(
            ArchivedOrderStatusHistory.objects.filter(archived_order=first).count(),
            expected_history_count,
        )


@override_settings(PROJECT_NAME="dine_flash")
class AutoClearOrdersWorkflowTests(AutoClearOrdersTestBase):
    def test_successful_archival_and_deletion(self):
        order = self._create_stale_order(token_no=10, with_history=True)
        sub = PushSubscription.objects.create(
            browser_id="b1",
            endpoint="https://example.com/push/1",
            p256dh="k",
            auth="a",
        )
        sub.tokens.add(order)

        auto_clear_orders()

        self.assertFalse(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 1)
        archived = ArchivedOrder.objects.get(original_order_id=order.id)
        self.assertGreaterEqual(
            ArchivedOrderStatusHistory.objects.filter(archived_order=archived).count(),
            1,
        )
        # Orphan push subscription cleanup runs after the order is removed.
        self.assertFalse(PushSubscription.objects.filter(pk=sub.pk).exists())

    def test_repeated_auto_clear_does_not_duplicate_archive(self):
        order = self._create_stale_order(token_no=11)
        delete_threshold = timezone.now() - timedelta(hours=2)

        with transaction.atomic():
            _archive_and_delete_eligible_order(order.pk, self.vendor, delete_threshold)

        self.assertFalse(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 1)

        auto_clear_orders()
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 1)

    def test_existing_archive_reused_on_retry_without_extra_history(self):
        order = self._create_stale_order(token_no=12, with_history=True)
        archived = ArchivedOrder.objects.create(
            original_order_id=order.id,
            vendor=self.vendor,
            device=None,
            user_profile=None,
            token_no=order.token_no,
            status=order.status,
            counter_no=order.counter_no,
            shown_on_tv=order.shown_on_tv,
            notified_at=order.notified_at,
            updated_by=order.updated_by,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )
        ArchivedOrderStatusHistory.objects.create(
            archived_order=archived,
            previous_status=None,
            new_status="preparing",
            changed_by="manager",
            changed_at=timezone.now(),
        )

        delete_threshold = timezone.now() - timedelta(hours=2)
        with transaction.atomic():
            _archive_and_delete_eligible_order(order.pk, self.vendor, delete_threshold)

        self.assertFalse(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 1)
        self.assertEqual(
            ArchivedOrderStatusHistory.objects.filter(archived_order=archived).count(),
            1,
        )

    @patch("vendors.utils.ArchivedOrder.objects.create")
    def test_archive_creation_failure_preserves_active_order(self, mock_create):
        mock_create.side_effect = RuntimeError("archive create failed")
        order = self._create_stale_order(token_no=13)
        delete_threshold = timezone.now() - timedelta(hours=2)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                _archive_and_delete_eligible_order(order.pk, self.vendor, delete_threshold)

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 0)

    @patch("vendors.utils.ArchivedOrderStatusHistory.objects.bulk_create")
    def test_status_history_copy_failure_rolls_back(self, mock_bulk_create):
        mock_bulk_create.side_effect = RuntimeError("history copy failed")
        order = self._create_stale_order(token_no=14, with_history=True)
        delete_threshold = timezone.now() - timedelta(hours=2)

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                _archive_and_delete_eligible_order(order.pk, self.vendor, delete_threshold)

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 0)
        self.assertEqual(
            ArchivedOrderStatusHistory.objects.filter(
                archived_order__original_order_id=order.id
            ).count(),
            0,
        )

    def test_subscription_cleanup_failure_preserves_active_order(self):
        order = self._create_stale_order(token_no=15)
        sub = PushSubscription.objects.create(
            browser_id="b2",
            endpoint="https://example.com/push/2",
            p256dh="k2",
            auth="a2",
        )
        sub.tokens.add(order)
        delete_threshold = timezone.now() - timedelta(hours=2)

        with patch.object(
            sub.tokens.__class__,
            "remove",
            side_effect=RuntimeError("subscription cleanup failed"),
        ):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    _archive_and_delete_eligible_order(
                        order.pk, self.vendor, delete_threshold
                    )

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 0)

    def test_deletion_failure_preserves_active_order(self):
        order = self._create_stale_order(token_no=16)
        delete_threshold = timezone.now() - timedelta(hours=2)

        with patch.object(Order, "delete", side_effect=RuntimeError("delete failed")):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    _archive_and_delete_eligible_order(
                        order.pk, self.vendor, delete_threshold
                    )

        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 0)

    def test_per_order_failure_does_not_block_other_orders(self):
        first = self._create_stale_order(token_no=17)
        second = self._create_stale_order(token_no=18)
        real_process = _archive_and_delete_eligible_order

        def side_effect(order_id, vendor, delete_threshold):
            if order_id == first.pk:
                raise RuntimeError("first order failed")
            return real_process(order_id, vendor, delete_threshold)

        with patch(
            "orders.scheduler._archive_and_delete_eligible_order",
            side_effect=side_effect,
        ):
            auto_clear_orders()

        self.assertTrue(Order.objects.filter(pk=first.pk).exists())
        self.assertFalse(Order.objects.filter(pk=second.pk).exists())


@override_settings(PROJECT_NAME="dine_flash")
class AutoClearOrdersConcurrentTests(TransactionTestCase):
    """
    Row-level locking concurrency requires real commits between threads.

    Uses TransactionTestCase (not TestCase) so MySQL ``SELECT ... FOR UPDATE``
    blocks across separate connections. Skipped when the default DB is not MySQL.
    """

    def setUp(self):
        if not _database_is_mysql():
            return
        self.user = User.objects.create_user(username="conc_admin", password="pass1234")
        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Conc Co",
            customer_id=201,
            locations=[{"CityA": "C1"}],
            authentication_status="Approve",
            product_to_date=timezone.now() + timedelta(days=30),
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Conc Outlet",
            alias_name="CO",
            location="CityA",
            place_id="place-conc",
            vendor_id=654322,
            location_id="L-conc",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor, auto_delete_hours=2)

    def _create_stale_order_with_history(self):
        order = Order.objects.create(
            vendor=self.vendor,
            token_no=99,
            status="preparing",
        )
        stale_at = timezone.now() - timedelta(hours=5)
        Order.objects.filter(pk=order.pk).update(
            created_at=stale_at,
            updated_at=stale_at,
        )
        order.refresh_from_db()
        OrderStatusHistory.objects.create(
            order=order,
            previous_status="preparing",
            new_status="ready",
            changed_by="manager",
        )
        expected_history_count = order.status_history.count()
        return order.pk, expected_history_count

    def _run_concurrent_workers(self, worker_fn, worker_count=2):
        if not _database_is_mysql():
            self.skipTest("MySQL is required for SELECT FOR UPDATE concurrency tests")

        barrier = threading.Barrier(worker_count)
        errors = []
        lock = threading.Lock()

        def worker():
            connection.close()
            try:
                barrier.wait(timeout=10)
                worker_fn()
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(worker_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            self.assertFalse(
                thread.is_alive(),
                "Concurrent worker thread did not finish within the timeout",
            )
        return errors

    def _assert_single_archive_outcome(self, original_order_id, expected_history_count):
        self.assertFalse(
            Order.objects.filter(pk=original_order_id).exists(),
            "Active order should be deleted only after a successful archive workflow",
        )
        archives = list(
            ArchivedOrder.objects.filter(original_order_id=original_order_id)
        )
        self.assertEqual(
            len(archives),
            1,
            "Exactly one ArchivedOrder should exist for the original order id",
        )
        archived = archives[0]
        history_count = ArchivedOrderStatusHistory.objects.filter(
            archived_order=archived
        ).count()
        self.assertEqual(
            history_count,
            expected_history_count,
            "Archived status history should be copied once, not duplicated",
        )

    def test_concurrent_auto_clear_orders_creates_single_archive(self):
        """
        Production entry point: two threads call auto_clear_orders() concurrently.

        Proves the scheduler's per-order transaction + row lock prevents duplicate
        archives when both workers select the same stale order.
        """
        if not _database_is_mysql():
            self.skipTest("MySQL is required for SELECT FOR UPDATE concurrency tests")

        original_order_id, expected_history_count = self._create_stale_order_with_history()

        errors = self._run_concurrent_workers(auto_clear_orders)

        self.assertEqual(errors, [], f"Unexpected worker exceptions: {errors!r}")
        self._assert_single_archive_outcome(original_order_id, expected_history_count)

    def test_concurrent_helper_clear_creates_single_archive(self):
        """
        Same row-lock path as production, invoked directly (supplemental).

        Does not exercise vendor iteration, order-id collection, or orphan
        subscription cleanup inside auto_clear_orders().
        """
        if not _database_is_mysql():
            self.skipTest("MySQL is required for SELECT FOR UPDATE concurrency tests")

        original_order_id, expected_history_count = self._create_stale_order_with_history()
        delete_threshold = timezone.now() - timedelta(hours=2)
        vendor_id = self.vendor.pk

        def run_helper():
            vendor = Vendor.objects.get(pk=vendor_id)
            with transaction.atomic():
                _archive_and_delete_eligible_order(
                    original_order_id, vendor, delete_threshold
                )

        errors = self._run_concurrent_workers(run_helper)

        self.assertEqual(errors, [], f"Unexpected worker exceptions: {errors!r}")
        self._assert_single_archive_outcome(original_order_id, expected_history_count)


@override_settings(PROJECT_NAME="dine_flash")
class AutoClearOrdersApiCompatibilityTests(AutoClearOrdersTestBase):
    def test_order_status_timeline_after_auto_clear_uses_archived_pk(self):
        """
        order_status_timeline resolves archived rows by ArchivedOrder.pk (URL param),
        not by the former active Order.pk / original_order_id alone.
        """
        self._seed_archived_order_primary_key()
        order = self._create_stale_order(token_no=20, with_history=True)
        original_order_id = order.pk
        expected_new_statuses = set(
            order.status_history.values_list("new_status", flat=True)
        )

        auto_clear_orders()

        self.assertFalse(Order.objects.filter(pk=original_order_id).exists())
        archived = ArchivedOrder.objects.get(original_order_id=original_order_id)
        self.assertNotEqual(
            archived.pk,
            original_order_id,
            "Test must not rely on ArchivedOrder.pk coincidentally matching Order.pk",
        )

        url = reverse("company:order_status_timeline", args=[archived.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        timeline = resp.json()
        returned_new_statuses = {entry["new_status"] for entry in timeline}
        self.assertTrue(
            expected_new_statuses.issubset(returned_new_statuses),
            msg=(
                "Timeline should include archived status history entries; "
                f"expected {expected_new_statuses}, got {returned_new_statuses}"
            ),
        )

    def test_order_status_timeline_does_not_resolve_by_original_order_id(self):
        """
        Documents current API behaviour: after archival, the former Order.pk is not
        accepted unless it happens to equal ArchivedOrder.pk.
        """
        self._seed_archived_order_primary_key()
        order = self._create_stale_order(token_no=22, with_history=True)
        original_order_id = order.pk

        auto_clear_orders()

        archived = ArchivedOrder.objects.get(original_order_id=original_order_id)
        self.assertNotEqual(archived.pk, original_order_id)

        url = reverse("company:order_status_timeline", args=[original_order_id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("Order not found", resp.json().get("detail", ""))

    def test_order_counts_summary_after_auto_clear(self):
        self._create_stale_order(token_no=21)
        auto_clear_orders()
        url = reverse("company:order_counts_summary")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertGreaterEqual(data.get("orders_today", 0), 1)


class ProtectedFlavourAutoClearSmokeTests(AutoClearOrdersTestBase):
    def test_auto_clear_uses_stage_a_path_for_each_protected_flavour(self):
        for index, flavour in enumerate(PROTECTED_AUTO_CLEAR_FLAVOURS):
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                order = self._create_stale_order(token_no=100 + index, with_history=True)
                auto_clear_orders()
                self.assertFalse(Order.objects.filter(pk=order.pk).exists())
                self.assertEqual(
                    ArchivedOrder.objects.filter(original_order_id=order.id).count(),
                    1,
                )


class LegacyFlavourAutoClearTests(AutoClearOrdersTestBase):
    @patch("vendors.utils.ArchivedOrder.objects.create")
    def test_legacy_archive_order_swallows_create_failure(self, mock_create):
        mock_create.side_effect = RuntimeError("archive create failed")
        order = self._create_stale_order(token_no=30)
        for flavour in LEGACY_AUTO_CLEAR_FLAVOURS:
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                archive_order(order)
        self.assertEqual(ArchivedOrder.objects.filter(original_order_id=order.id).count(), 0)

    def test_legacy_archive_order_does_not_reuse_existing_row(self):
        order = self._create_stale_order(token_no=31, with_history=True)
        for flavour in LEGACY_AUTO_CLEAR_FLAVOURS:
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                archive_order(order)
                archive_order(order)
                self.assertEqual(
                    ArchivedOrder.objects.filter(original_order_id=order.id).count(),
                    2,
                )
                ArchivedOrder.objects.filter(original_order_id=order.id).delete()

    @patch("vendors.utils.ArchivedOrder.objects.create")
    def test_legacy_auto_clear_deletes_order_when_archive_fails(self, mock_create):
        mock_create.side_effect = RuntimeError("archive create failed")
        for index, flavour in enumerate(LEGACY_AUTO_CLEAR_FLAVOURS):
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                order = self._create_stale_order(token_no=40 + index)
                auto_clear_orders()
                self.assertFalse(Order.objects.filter(pk=order.pk).exists())
                self.assertEqual(
                    ArchivedOrder.objects.filter(original_order_id=order.id).count(),
                    0,
                )
