"""Dine Flash GET active_bookings API tests."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory

from orders.dine_flash.active_booking_registry import register_dine_flash_active_booking
from orders.dine_flash.booking_lookup import upsert_dine_flash_booking_lookup
from orders.views import list_active_dine_flash_bookings
from vendors.models import AdminOutlet, Order, Vendor


class DineFlashActiveBookingsApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.lookup_id = "api-lookup-key"
        self.outlet = AdminOutlet.objects.create(
            customer_name="Dine API Co",
            customer_id=93003,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Dine API Outlet",
            alias_name="DAO",
            location="City",
            place_id="place-dine-api-1",
            vendor_id=930003,
            location_id="LOC-DAPI1",
            menus="[]",
        )

    def _order(self, token_no, booking_no):
        return Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            table_booking_no=booking_no,
            counter_no=1,
            updated_by="customer",
            status="waiting",
            customer_name="guest",
        )

    def _get(self, params):
        request = self.factory.get("/api/dine_flash/active_bookings/", params)
        with patch("orders.views.project_name", "dine_flash"):
            return list_active_dine_flash_bookings(request)

    def test_lists_active_bookings_with_is_latest(self):
        o1 = self._order(1, "B-1")
        o2 = self._order(2, "B-2")
        register_dine_flash_active_booking(order_lookup_id=self.lookup_id, order=o1)
        register_dine_flash_active_booking(order_lookup_id=self.lookup_id, order=o2)
        upsert_dine_flash_booking_lookup(order_lookup_id=self.lookup_id, order=o2)

        resp = self._get({"order_lookup_id": self.lookup_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)
        latest = [row for row in resp.data if row.get("is_latest")]
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["booking_id"], o2.id)

    def test_invalid_order_lookup_id_rejected(self):
        resp = self._get({"order_lookup_id": "   "})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_wrong_flavour_returns_404(self):
        request = self.factory.get(
            "/api/dine_flash/active_bookings/",
            {"order_lookup_id": self.lookup_id},
        )
        with patch("orders.views.project_name", "food_flash"):
            resp = list_active_dine_flash_bookings(request)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
