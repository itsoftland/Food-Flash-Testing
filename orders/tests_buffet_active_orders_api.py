"""
Buffet Active Order Registry — Phase 3 Order Selector data API tests.

Isolated Registry read for future Order Selector. Does not exercise recovery,
Home, Push, or Chat.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory

from orders.buffet.active_order_registry import (
    list_selectable_buffet_active_orders,
    register_buffet_active_order,
    serialize_buffet_active_order_for_selector,
)
from orders.buffet.order_lookup import upsert_buffet_order_lookup
from orders.buffet_views import list_active_orders
from vendors.models import (
    AdminOutlet,
    BuffetActiveOrder,
    BuffetOrderItem,
    Order,
    Utility,
    Vendor,
    VendorConfig,
)


class BuffetActiveOrdersApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.outlet = AdminOutlet.objects.create(
            customer_name="Active Orders API Co",
            customer_id=93001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Buffet Active Orders Outlet",
            alias_name="BAO",
            location="City",
            place_id="place-active-orders-1",
            vendor_id=930001,
            location_id="LOC-AO1",
            menus="[]",
        )
        VendorConfig.objects.create(
            vendor=self.vendor,
            business_day_start_hour="00:00:00",
            timezone="UTC",
        )
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Main Dish",
            display_name="Main Dish",
            display_code="MD",
        )
        self.lookup_id = "selector-customer-key"

    def _make_order(self, token_no, *, item_status="created"):
        order = Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            counter_no=1,
            updated_by="customer",
            status="created",
            customer_name="selector_test",
        )
        BuffetOrderItem.objects.create(
            order=order,
            utility=self.utility,
            status=item_status,
            quantity=1,
        )
        register_buffet_active_order(order_lookup_id=self.lookup_id, order=order)
        return order

    def _get(self, params=None):
        request = self.factory.get("/api/buffet/active_orders/", params or {})
        return list_active_orders(request)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_lists_active_orders_with_latest_from_lookup(self):
        older = self._make_order(10)
        newer = self._make_order(11)
        upsert_buffet_order_lookup(order_lookup_id=self.lookup_id, order=newer)

        resp = self._get({"order_lookup_id": self.lookup_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 2)

        by_token = {row["token_number"]: row for row in resp.data}
        self.assertTrue(by_token[11]["is_latest"])
        self.assertFalse(by_token[10]["is_latest"])
        self.assertEqual(by_token[11]["vendor_id"], self.vendor.vendor_id)
        self.assertEqual(by_token[11]["order_lookup_id"], self.lookup_id)
        self.assertIn("created_at", by_token[11])
        self.assertNotIn("booking_id", by_token[11])
        self.assertNotIn("order_status", by_token[11])
        # Newest first
        self.assertEqual(resp.data[0]["token_number"], newer.token_no)
        self.assertEqual(resp.data[1]["token_number"], older.token_no)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_excludes_fully_cancelled_orders(self):
        active = self._make_order(20, item_status="created")
        cancelled = self._make_order(21, item_status="cancelled")
        upsert_buffet_order_lookup(order_lookup_id=self.lookup_id, order=active)

        # Phase 7: lifecycle sync removes inactive rows; selector also filters.
        from orders.buffet.active_order_registry import sync_buffet_active_order_lifecycle

        sync_buffet_active_order_lifecycle(order=cancelled)

        resp = self._get({"order_lookup_id": self.lookup_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([row["token_number"] for row in resp.data], [20])
        self.assertFalse(
            BuffetActiveOrder.objects.filter(order_id=cancelled.id).exists(),
            "cancelled order is removed from the Active Order Registry",
        )

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_excludes_orders_outside_business_day(self):
        active = self._make_order(30)
        stale = self._make_order(31)
        Order.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=3)
        )
        upsert_buffet_order_lookup(order_lookup_id=self.lookup_id, order=active)

        resp = self._get({"order_lookup_id": self.lookup_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([row["token_number"] for row in resp.data], [30])

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_invalid_order_lookup_id_rejected(self):
        resp = self._get({})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["status"], "invalid_input")

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_unknown_lookup_returns_empty_list(self):
        resp = self._get({"order_lookup_id": "missing-key"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])

    @patch("orders.buffet_views.project_name", "hospital_flash")
    def test_non_buffet_project_returns_404(self):
        self._make_order(40)
        resp = self._get({"order_lookup_id": self.lookup_id})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_helper_selectable_list_and_serializer_shape(self):
        order = self._make_order(50)
        upsert_buffet_order_lookup(order_lookup_id=self.lookup_id, order=order)
        entries = list_selectable_buffet_active_orders(order_lookup_id=self.lookup_id)
        self.assertEqual(len(entries), 1)
        payload = serialize_buffet_active_order_for_selector(entries[0], is_latest=True)
        self.assertEqual(
            set(payload.keys()),
            {"order_lookup_id", "vendor_id", "token_number", "created_at", "is_latest"},
        )
        self.assertTrue(payload["is_latest"])
