"""
Buffet order_lookup_id recovery — backend scenario tests.

Covers Latest Order Wins, optional submit field, resolve API, CASCADE cleanup,
and non-buffet flavour gating. Does not exercise PushSubscription / Chat /
browser_id generation.
"""
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory

from orders.buffet.order_lookup import (
    BuffetOrderLookupResolveStatus,
    normalize_order_lookup_id,
    resolve_buffet_order_lookup,
    upsert_buffet_order_lookup,
)
from orders.buffet_views import buffet_submit_order, resolve_order_lookup
from vendors.models import (
    AdminOutlet,
    BuffetOrderLookup,
    Order,
    Utility,
    Vendor,
)


class BuffetOrderLookupHelperTests(TestCase):
    def setUp(self):
        self.outlet = AdminOutlet.objects.create(
            customer_name="Lookup Test Co",
            customer_id=91001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Buffet Outlet",
            alias_name="BO",
            location="City",
            place_id="place-lookup-1",
            vendor_id=910001,
            location_id="LOC-B1",
            menus="[]",
        )

    def _make_order(self, token_no):
        return Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            counter_no=1,
            updated_by="customer",
            status="created",
            customer_name="lookup_test",
        )

    def test_normalize_absent_and_invalid(self):
        self.assertIsNone(normalize_order_lookup_id(None))
        self.assertIsNone(normalize_order_lookup_id(""))
        self.assertIsNone(normalize_order_lookup_id("   "))
        self.assertIsNone(normalize_order_lookup_id("x" * 256))
        self.assertEqual(normalize_order_lookup_id("  abc  "), "abc")

    def test_upsert_absent_is_noop(self):
        order = self._make_order(1)
        self.assertIsNone(upsert_buffet_order_lookup(order_lookup_id=None, order=order))
        self.assertIsNone(upsert_buffet_order_lookup(order_lookup_id="", order=order))
        self.assertEqual(BuffetOrderLookup.objects.count(), 0)

    def test_latest_order_wins(self):
        o1 = self._make_order(1)
        o2 = self._make_order(2)
        key = "safari-S-uuid"
        upsert_buffet_order_lookup(order_lookup_id=key, order=o1)
        upsert_buffet_order_lookup(order_lookup_id=key, order=o2)
        self.assertEqual(BuffetOrderLookup.objects.filter(order_lookup_id=key).count(), 1)
        mapping = BuffetOrderLookup.objects.get(order_lookup_id=key)
        self.assertEqual(mapping.order_id, o2.id)

    def test_resolve_found_not_found_invalid(self):
        order = self._make_order(7)
        key = "resolve-key"
        upsert_buffet_order_lookup(order_lookup_id=key, order=order)

        found = resolve_buffet_order_lookup(order_lookup_id=key)
        self.assertEqual(found.status, BuffetOrderLookupResolveStatus.FOUND)
        self.assertEqual(found.data["token_no"], 7)
        self.assertEqual(found.data["vendor_id"], self.vendor.vendor_id)
        self.assertEqual(found.data["location_id"], self.vendor.location_id)

        self.assertEqual(
            resolve_buffet_order_lookup(order_lookup_id="missing").status,
            BuffetOrderLookupResolveStatus.NOT_FOUND,
        )
        self.assertEqual(
            resolve_buffet_order_lookup(order_lookup_id=None).status,
            BuffetOrderLookupResolveStatus.INVALID_INPUT,
        )

    def test_cascade_on_order_delete(self):
        order = self._make_order(3)
        key = "cascade-key"
        upsert_buffet_order_lookup(order_lookup_id=key, order=order)
        self.assertTrue(BuffetOrderLookup.objects.filter(order_lookup_id=key).exists())
        order.delete()
        self.assertFalse(BuffetOrderLookup.objects.filter(order_lookup_id=key).exists())
        self.assertEqual(
            resolve_buffet_order_lookup(order_lookup_id=key).status,
            BuffetOrderLookupResolveStatus.NOT_FOUND,
        )

    def test_status_change_does_not_move_mapping(self):
        order = self._make_order(4)
        key = "status-key"
        upsert_buffet_order_lookup(order_lookup_id=key, order=order)
        order.status = "ready"
        order.save(update_fields=["status"])
        mapping = BuffetOrderLookup.objects.get(order_lookup_id=key)
        self.assertEqual(mapping.order_id, order.id)


class BuffetSubmitOrderLookupTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.outlet = AdminOutlet.objects.create(
            customer_name="Submit Lookup Co",
            customer_id=91002,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Buffet Submit Outlet",
            alias_name="BSO",
            location="City",
            place_id="place-lookup-2",
            vendor_id=910002,
            location_id="LOC-B2",
            menus="[]",
        )
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Main Dish",
            display_name="Main Dish",
            display_code="MD",
        )

    def _submit(self, extra=None):
        payload = {
            "vendor_id": self.vendor.vendor_id,
            "table_number": "T1",
            "customer_name": "Guest",
            "phone_number": "9999999999",
            "items": [
                {
                    "utility_id": self.utility.id,
                    "quantity": 1,
                    "is_grouped": False,
                    "customizations": [],
                    "remarks": "",
                }
            ],
        }
        if extra:
            payload.update(extra)
        request = self.factory.post(
            "/api/buffet_submit_order/",
            payload,
            format="json",
        )
        with patch(
            "orders.buffet.order_create.reset_counters_if_new_business_day",
            return_value=None,
        ):
            return buffet_submit_order(request)

    def test_submit_without_order_lookup_id_creates_no_mapping(self):
        resp = self._submit()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BuffetOrderLookup.objects.count(), 0)
        self.assertTrue(Order.objects.filter(id=resp.data["order_id"]).exists())

    def test_submit_with_order_lookup_id_creates_mapping(self):
        resp = self._submit({"order_lookup_id": "  client-S  "})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mapping = BuffetOrderLookup.objects.get(order_lookup_id="client-S")
        self.assertEqual(mapping.order_id, resp.data["order_id"])

    def test_submit_latest_order_wins(self):
        r1 = self._submit({"order_lookup_id": "same-key"})
        r2 = self._submit({"order_lookup_id": "same-key"})
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BuffetOrderLookup.objects.filter(order_lookup_id="same-key").count(), 1)
        self.assertEqual(
            BuffetOrderLookup.objects.get(order_lookup_id="same-key").order_id,
            r2.data["order_id"],
        )

    def test_submit_invalid_order_lookup_id_rejected(self):
        resp = self._submit({"order_lookup_id": "x" * 256})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(BuffetOrderLookup.objects.count(), 0)


class BuffetResolveOrderLookupApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.outlet = AdminOutlet.objects.create(
            customer_name="Resolve Lookup Co",
            customer_id=91003,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Buffet Resolve Outlet",
            alias_name="BRO",
            location="City",
            place_id="place-lookup-3",
            vendor_id=910003,
            location_id="LOC-B3",
            menus="[]",
        )
        self.order = Order.objects.create(
            vendor=self.vendor,
            token_no=42,
            counter_no=1,
            updated_by="customer",
            status="created",
        )
        upsert_buffet_order_lookup(order_lookup_id="api-key", order=self.order)

    def _post(self, body):
        request = self.factory.post(
            "/api/buffet/resolve_order_lookup/",
            body,
            format="json",
        )
        return resolve_order_lookup(request)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_resolve_found(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "found")
        self.assertEqual(resp.data["token_no"], 42)
        self.assertEqual(resp.data["vendor_id"], self.vendor.vendor_id)
        self.assertEqual(resp.data["location_id"], "LOC-B3")

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_resolve_not_found(self):
        resp = self._post({"order_lookup_id": "missing"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.data["status"], "not_found")

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_resolve_invalid_input(self):
        resp = self._post({})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["status"], "invalid_input")

    @patch("orders.buffet_views.project_name", "hospital_flash")
    def test_resolve_non_buffet_returns_404(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.buffet_views.project_name", "dine_flash")
    def test_resolve_dine_flash_returns_404(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_resolve_does_not_mutate_order(self):
        before = Order.objects.get(pk=self.order.pk).status
        self._post({"order_lookup_id": "api-key"})
        after = Order.objects.get(pk=self.order.pk).status
        self.assertEqual(before, after)
