"""
Buffet Active Order Registry — Phase 7 lifecycle sync tests.

Verifies inactive orders are removed from the Registry on status transitions
without touching BuffetOrderLookup recovery.
"""
from django.test import TestCase

from orders.buffet.active_order_registry import (
    is_buffet_order_registry_active,
    list_selectable_buffet_active_orders,
    register_buffet_active_order,
    sync_buffet_active_order_lifecycle,
)
from vendors.models import (
    AdminOutlet,
    BuffetActiveOrder,
    BuffetOrderItem,
    Order,
    Utility,
    Vendor,
)


class BuffetActiveOrderLifecycleTests(TestCase):
    def setUp(self):
        self.outlet = AdminOutlet.objects.create(
            customer_name="Lifecycle Co",
            customer_id=94001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Buffet Lifecycle Outlet",
            alias_name="BLO",
            location="City",
            place_id="place-lifecycle-1",
            vendor_id=940001,
            location_id="LOC-LC1",
            menus="[]",
        )
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Main Dish",
            display_name="Main Dish",
            display_code="MD",
        )
        self.lookup_id = "lifecycle-customer-key"

    def _make_order(self, token_no, *, item_status="created", order_status="created"):
        order = Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            counter_no=1,
            updated_by="customer",
            status=order_status,
            customer_name="lifecycle_test",
        )
        BuffetOrderItem.objects.create(
            order=order,
            utility=self.utility,
            status=item_status,
            quantity=1,
        )
        register_buffet_active_order(order_lookup_id=self.lookup_id, order=order)
        return order

    def test_active_created_order_stays_in_registry(self):
        order = self._make_order(1, item_status="created")
        self.assertTrue(is_buffet_order_registry_active(order))
        self.assertFalse(sync_buffet_active_order_lifecycle(order=order))
        self.assertTrue(BuffetActiveOrder.objects.filter(order=order).exists())

    def test_ready_order_stays_in_registry(self):
        order = self._make_order(2, item_status="ready")
        self.assertTrue(is_buffet_order_registry_active(order))
        self.assertFalse(sync_buffet_active_order_lifecycle(order=order))
        self.assertTrue(BuffetActiveOrder.objects.filter(order=order).exists())

    def test_fully_cancelled_removes_from_registry(self):
        order = self._make_order(3, item_status="cancelled")
        self.assertFalse(is_buffet_order_registry_active(order))
        self.assertTrue(sync_buffet_active_order_lifecycle(order=order))
        self.assertFalse(BuffetActiveOrder.objects.filter(order=order).exists())
        self.assertEqual(
            list_selectable_buffet_active_orders(order_lookup_id=self.lookup_id),
            [],
        )

    def test_all_items_delivered_removes_from_registry(self):
        order = self._make_order(4, item_status="delivered")
        self.assertTrue(sync_buffet_active_order_lifecycle(order=order))
        self.assertFalse(BuffetActiveOrder.objects.filter(order=order).exists())

    def test_order_status_delivered_removes_from_registry(self):
        order = self._make_order(5, item_status="ready", order_status="delivered")
        self.assertTrue(sync_buffet_active_order_lifecycle(order=order))
        self.assertFalse(BuffetActiveOrder.objects.filter(order=order).exists())

    def test_mixed_ready_and_delivered_stays_active(self):
        order = self._make_order(6, item_status="ready")
        BuffetOrderItem.objects.create(
            order=order,
            utility=self.utility,
            status="delivered",
            quantity=1,
        )
        order.refresh_from_db()
        self.assertTrue(is_buffet_order_registry_active(order))
        self.assertFalse(sync_buffet_active_order_lifecycle(order=order))
        self.assertTrue(BuffetActiveOrder.objects.filter(order=order).exists())

    def test_operation_closed_all_lines_removes(self):
        order = self._make_order(7, item_status="operation_closed")
        self.assertTrue(sync_buffet_active_order_lifecycle(order=order))
        self.assertFalse(BuffetActiveOrder.objects.filter(order=order).exists())
