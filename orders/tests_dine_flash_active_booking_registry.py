"""Dine Flash Active Booking Registry helper tests."""
from django.test import TestCase

from orders.dine_flash.active_booking_registry import (
    is_dine_flash_booking_registry_active,
    list_selectable_dine_flash_active_bookings,
    register_dine_flash_active_booking,
    sync_dine_flash_active_booking_lifecycle,
)
from vendors.models import AdminOutlet, DineFlashActiveBooking, Order, Vendor


class DineFlashActiveBookingRegistryHelperTests(TestCase):
    def setUp(self):
        self.outlet = AdminOutlet.objects.create(
            customer_name="Dine Active Registry Co",
            customer_id=93001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Dine Registry Outlet",
            alias_name="DRO",
            location="City",
            place_id="place-dine-act-1",
            vendor_id=930001,
            location_id="LOC-DA1",
            menus="[]",
        )

    def _order(self, token_no, booking_no, status="waiting"):
        return Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            table_booking_no=booking_no,
            counter_no=1,
            updated_by="customer",
            status=status,
            customer_name="guest",
        )

    def test_register_skips_invalid_lookup_id(self):
        order = self._order(1, "B-1")
        self.assertIsNone(
            register_dine_flash_active_booking(order_lookup_id=None, order=order)
        )
        self.assertEqual(DineFlashActiveBooking.objects.count(), 0)

    def test_active_status_matrix(self):
        for st in ("created", "waiting", "allocated", "occupied"):
            order = self._order(1, f"A-{st}", status=st)
            self.assertTrue(is_dine_flash_booking_registry_active(order))
        for st in ("booking_cancelled", "operation_closed"):
            order = self._order(2, f"T-{st}", status=st)
            self.assertFalse(is_dine_flash_booking_registry_active(order))

    def test_lifecycle_removes_terminal_booking(self):
        key = "registry-key"
        order = self._order(3, "B-3", status="waiting")
        register_dine_flash_active_booking(order_lookup_id=key, order=order)
        order.status = "booking_cancelled"
        order.save(update_fields=["status"])
        self.assertTrue(sync_dine_flash_active_booking_lifecycle(order=order))
        self.assertFalse(DineFlashActiveBooking.objects.filter(order=order).exists())

    def test_list_selectable_returns_active_rows(self):
        key = "list-key"
        o1 = self._order(4, "B-4")
        o2 = self._order(5, "B-5")
        register_dine_flash_active_booking(order_lookup_id=key, order=o1)
        register_dine_flash_active_booking(order_lookup_id=key, order=o2)
        rows = list_selectable_dine_flash_active_bookings(order_lookup_id=key)
        self.assertEqual(len(rows), 2)
