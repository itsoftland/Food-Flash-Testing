"""
Buffet Active Order Registry — Phase 1 helper tests.

Does not touch BuffetOrderLookup recovery, PushSubscription, or Chat.
"""
from django.test import TestCase

from orders.buffet.active_order_registry import (
    count_buffet_active_orders,
    list_buffet_active_orders,
    register_buffet_active_order,
    remove_buffet_active_order,
    serialize_buffet_active_order,
)
from orders.buffet.order_lookup import upsert_buffet_order_lookup
from vendors.models import AdminOutlet, BuffetActiveOrder, BuffetOrderLookup, Order, Vendor


class BuffetActiveOrderRegistryHelperTests(TestCase):
    def setUp(self):
        self.outlet = AdminOutlet.objects.create(
            customer_name="Registry Test Co",
            customer_id=92001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Buffet Registry Outlet",
            alias_name="BRO",
            location="City",
            place_id="place-registry-1",
            vendor_id=920001,
            location_id="LOC-R1",
            menus="[]",
        )

    def _make_order(self, token_no):
        return Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            counter_no=1,
            updated_by="customer",
            status="created",
            customer_name="registry_test",
        )

    def test_register_absent_lookup_id_is_noop(self):
        order = self._make_order(1)
        self.assertIsNone(register_buffet_active_order(order_lookup_id=None, order=order))
        self.assertIsNone(register_buffet_active_order(order_lookup_id="", order=order))
        self.assertEqual(BuffetActiveOrder.objects.count(), 0)

    def test_register_multiple_orders_same_lookup_id(self):
        key = "customer-registry-key"
        o1 = self._make_order(1)
        o2 = self._make_order(2)
        register_buffet_active_order(order_lookup_id=key, order=o1)
        register_buffet_active_order(order_lookup_id=key, order=o2)
        self.assertEqual(count_buffet_active_orders(order_lookup_id=key), 2)
        tokens = set(
            list_buffet_active_orders(order_lookup_id=key).values_list("token_no", flat=True)
        )
        self.assertEqual(tokens, {1, 2})

    def test_register_idempotent_for_same_order(self):
        key = "same-order-key"
        order = self._make_order(5)
        register_buffet_active_order(order_lookup_id=key, order=order)
        register_buffet_active_order(order_lookup_id=key, order=order)
        self.assertEqual(BuffetActiveOrder.objects.filter(order=order).count(), 1)
        self.assertEqual(count_buffet_active_orders(order_lookup_id=key), 1)

    def test_remove_registry_entry(self):
        key = "remove-key"
        order = self._make_order(9)
        register_buffet_active_order(order_lookup_id=key, order=order)
        self.assertTrue(remove_buffet_active_order(order=order))
        self.assertEqual(count_buffet_active_orders(order_lookup_id=key), 0)
        self.assertFalse(remove_buffet_active_order(order=order))

    def test_order_delete_cascades_registry_row(self):
        key = "cascade-key"
        order = self._make_order(3)
        register_buffet_active_order(order_lookup_id=key, order=order)
        order_id = order.id
        order.delete()
        self.assertFalse(BuffetActiveOrder.objects.filter(order_id=order_id).exists())

    def test_registry_does_not_replace_buffet_order_lookup(self):
        """Latest Order Wins lookup remains independent of registry multi-row list."""
        key = "lookup-independence"
        o1 = self._make_order(1)
        o2 = self._make_order(2)
        upsert_buffet_order_lookup(order_lookup_id=key, order=o1)
        register_buffet_active_order(order_lookup_id=key, order=o1)
        upsert_buffet_order_lookup(order_lookup_id=key, order=o2)
        register_buffet_active_order(order_lookup_id=key, order=o2)

        self.assertEqual(BuffetOrderLookup.objects.filter(order_lookup_id=key).count(), 1)
        self.assertEqual(
            BuffetOrderLookup.objects.get(order_lookup_id=key).order_id,
            o2.id,
        )
        self.assertEqual(count_buffet_active_orders(order_lookup_id=key), 2)

    def test_serialize_shape(self):
        key = "serialize-key"
        order = self._make_order(11)
        entry = register_buffet_active_order(order_lookup_id=key, order=order)
        data = serialize_buffet_active_order(entry)
        self.assertEqual(data["token_no"], 11)
        self.assertEqual(data["vendor_id"], self.vendor.vendor_id)
        self.assertEqual(data["booking_id"], order.id)
        self.assertEqual(data["order_lookup_id"], key)
        self.assertEqual(data["order_status"], "created")
        self.assertIsNotNone(data["created_at"])
