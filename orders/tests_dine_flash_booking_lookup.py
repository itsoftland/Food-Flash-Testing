"""
Dine Flash order_lookup_id booking recovery — backend scenario tests.

Covers Latest Booking Wins, optional book_table field, resolve API,
manager skip, CASCADE cleanup, and non–dine_flash flavour gating.
Does not exercise PushSubscription / Chat / browser_id generation.
Independent from Buffet order_lookup tests.
"""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory

from orders.dine_flash.booking_lookup import (
    DineFlashBookingLookupResolveStatus,
    normalize_order_lookup_id,
    resolve_dine_flash_booking_lookup,
    upsert_dine_flash_booking_lookup,
)
from orders.views import book_table, resolve_order_lookup
from vendors.models import (
    AdminOutlet,
    DineFlashBookingLookup,
    Order,
    Vendor,
    VendorConfig,
)


class DineFlashBookingLookupHelperTests(TestCase):
    def setUp(self):
        self.outlet = AdminOutlet.objects.create(
            customer_name="Dine Lookup Test Co",
            customer_id=92001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Dine Outlet",
            alias_name="DO",
            location="City",
            place_id="place-dine-lookup-1",
            vendor_id=920001,
            location_id="LOC-D1",
            menus="[]",
        )

    def _make_booking(self, token_no, booking_no):
        return Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            table_booking_no=booking_no,
            counter_no=1,
            updated_by="customer",
            status="waiting",
            customer_name="lookup_test",
        )

    def test_normalize_absent_and_invalid(self):
        self.assertIsNone(normalize_order_lookup_id(None))
        self.assertIsNone(normalize_order_lookup_id(""))
        self.assertIsNone(normalize_order_lookup_id("   "))
        self.assertIsNone(normalize_order_lookup_id("x" * 256))
        self.assertEqual(normalize_order_lookup_id("  abc  "), "abc")

    def test_upsert_absent_is_noop(self):
        order = self._make_booking(1, "1")
        self.assertIsNone(
            upsert_dine_flash_booking_lookup(order_lookup_id=None, order=order)
        )
        self.assertIsNone(
            upsert_dine_flash_booking_lookup(order_lookup_id="", order=order)
        )
        self.assertEqual(DineFlashBookingLookup.objects.count(), 0)

    def test_latest_booking_wins(self):
        o1 = self._make_booking(1, "A-1")
        o2 = self._make_booking(2, "A-2")
        key = "safari-S-uuid"
        upsert_dine_flash_booking_lookup(order_lookup_id=key, order=o1)
        upsert_dine_flash_booking_lookup(order_lookup_id=key, order=o2)
        self.assertEqual(
            DineFlashBookingLookup.objects.filter(order_lookup_id=key).count(), 1
        )
        mapping = DineFlashBookingLookup.objects.get(order_lookup_id=key)
        self.assertEqual(mapping.order_id, o2.id)

    def test_resolve_found_not_found_invalid(self):
        order = self._make_booking(7, "VIP-7")
        key = "resolve-key"
        upsert_dine_flash_booking_lookup(order_lookup_id=key, order=order)

        found = resolve_dine_flash_booking_lookup(order_lookup_id=key)
        self.assertEqual(found.status, DineFlashBookingLookupResolveStatus.FOUND)
        self.assertEqual(found.data["booking_id"], order.id)
        self.assertEqual(found.data["booking_no"], "VIP-7")
        self.assertEqual(found.data["vendor_id"], self.vendor.vendor_id)
        self.assertEqual(found.data["location_id"], self.vendor.location_id)

        self.assertEqual(
            resolve_dine_flash_booking_lookup(order_lookup_id="missing").status,
            DineFlashBookingLookupResolveStatus.NOT_FOUND,
        )
        self.assertEqual(
            resolve_dine_flash_booking_lookup(order_lookup_id=None).status,
            DineFlashBookingLookupResolveStatus.INVALID_INPUT,
        )

    def test_cascade_on_order_delete(self):
        order = self._make_booking(3, "3")
        key = "cascade-key"
        upsert_dine_flash_booking_lookup(order_lookup_id=key, order=order)
        self.assertTrue(
            DineFlashBookingLookup.objects.filter(order_lookup_id=key).exists()
        )
        order.delete()
        self.assertFalse(
            DineFlashBookingLookup.objects.filter(order_lookup_id=key).exists()
        )
        self.assertEqual(
            resolve_dine_flash_booking_lookup(order_lookup_id=key).status,
            DineFlashBookingLookupResolveStatus.NOT_FOUND,
        )

    def test_status_change_does_not_move_mapping(self):
        order = self._make_booking(4, "4")
        key = "status-key"
        upsert_dine_flash_booking_lookup(order_lookup_id=key, order=order)
        order.status = "ready"
        order.save(update_fields=["status"])
        mapping = DineFlashBookingLookup.objects.get(order_lookup_id=key)
        self.assertEqual(mapping.order_id, order.id)


class DineFlashBookTableLookupTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.outlet = AdminOutlet.objects.create(
            customer_name="Dine Submit Lookup Co",
            customer_id=92002,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Dine Submit Outlet",
            alias_name="DSO",
            location="City",
            place_id="place-dine-lookup-2",
            vendor_id=920002,
            location_id="LOC-D2",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor, use_utilities=False)

    def _customer_payload(self, extra=None):
        payload = {
            "vendor_id": self.vendor.vendor_id,
            "customer_name": "Guest",
            "no_of_guests": 2,
            "qr_session": "qr-test-token",
        }
        if extra:
            payload.update(extra)
        return payload

    def _post_book_table(self, payload, user=None):
        request = self.factory.post("/api/book_table/", payload, format="json")
        request.user = user if user is not None else AnonymousUser()
        with patch("orders.views.project_name", "dine_flash"), patch(
            "orders.views._validate_dine_flash_qr_session", return_value=(True, None)
        ), patch(
            "orders.views.reset_counters_if_new_business_day", return_value=None
        ), patch(
            "orders.views._schedule_dine_flash_booking_created_fcm"
        ):
            return book_table(request)

    def test_submit_without_order_lookup_id_creates_no_mapping(self):
        resp = self._post_book_table(self._customer_payload())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DineFlashBookingLookup.objects.count(), 0)

    def test_submit_with_order_lookup_id_creates_mapping(self):
        resp = self._post_book_table(
            self._customer_payload({"order_lookup_id": "  client-S  "})
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mapping = DineFlashBookingLookup.objects.get(order_lookup_id="client-S")
        self.assertEqual(mapping.order_id, resp.data["id"])

    def test_submit_latest_booking_wins(self):
        r1 = self._post_book_table(
            self._customer_payload({"order_lookup_id": "same-key"})
        )
        r2 = self._post_book_table(
            self._customer_payload({"order_lookup_id": "same-key"})
        )
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            DineFlashBookingLookup.objects.filter(order_lookup_id="same-key").count(),
            1,
        )
        self.assertEqual(
            DineFlashBookingLookup.objects.get(order_lookup_id="same-key").order_id,
            r2.data["id"],
        )

    def test_submit_invalid_order_lookup_id_rejected(self):
        resp = self._post_book_table(
            self._customer_payload({"order_lookup_id": "x" * 256})
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(DineFlashBookingLookup.objects.count(), 0)

    def test_manager_created_booking_skips_lookup_upsert(self):
        manager_user = MagicMock()
        manager_user.is_authenticated = True
        manager_profile = MagicMock()
        manager_profile.id = 99
        manager_profile.vendor = self.vendor
        profile_qs = MagicMock()
        profile_qs.select_related.return_value.order_by.return_value.first.return_value = (
            manager_profile
        )
        manager_user.profile_roles = profile_qs

        resp = self._post_book_table(
            {
                "customer_name": "Walk-in",
                "no_of_guests": 2,
                "order_lookup_id": "manager-should-skip",
            },
            user=manager_user,
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data.get("created_by"), "manager")
        self.assertEqual(DineFlashBookingLookup.objects.count(), 0)


class DineFlashResolveOrderLookupApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.outlet = AdminOutlet.objects.create(
            customer_name="Dine Resolve Lookup Co",
            customer_id=92003,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Dine Resolve Outlet",
            alias_name="DRO",
            location="City",
            place_id="place-dine-lookup-3",
            vendor_id=920003,
            location_id="LOC-D3",
            menus="[]",
        )
        self.order = Order.objects.create(
            vendor=self.vendor,
            token_no=42,
            table_booking_no="L-42",
            counter_no=1,
            updated_by="customer",
            status="waiting",
        )
        upsert_dine_flash_booking_lookup(order_lookup_id="api-key", order=self.order)

    def _post(self, body):
        request = self.factory.post(
            "/api/dine_flash/resolve_order_lookup/",
            body,
            format="json",
        )
        return resolve_order_lookup(request)

    @patch("orders.views.project_name", "dine_flash")
    def test_resolve_found(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "found")
        self.assertEqual(resp.data["booking_id"], self.order.id)
        self.assertEqual(resp.data["booking_no"], "L-42")
        self.assertEqual(resp.data["vendor_id"], self.vendor.vendor_id)
        self.assertEqual(resp.data["location_id"], "LOC-D3")

    @patch("orders.views.project_name", "dine_flash")
    def test_resolve_not_found(self):
        resp = self._post({"order_lookup_id": "missing"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.data["status"], "not_found")

    @patch("orders.views.project_name", "dine_flash")
    def test_resolve_invalid_input(self):
        resp = self._post({})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["status"], "invalid_input")

    @patch("orders.views.project_name", "hospital_flash")
    def test_resolve_hospital_returns_404(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.views.project_name", "dine_flash_buffet")
    def test_resolve_buffet_returns_404(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.views.project_name", "food_flash")
    def test_resolve_food_flash_returns_404(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.views.project_name", "airline_flash")
    def test_resolve_airline_flash_returns_404(self):
        resp = self._post({"order_lookup_id": "api-key"})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.views.project_name", "dine_flash")
    def test_resolve_does_not_mutate_order(self):
        before = Order.objects.get(pk=self.order.pk).status
        self._post({"order_lookup_id": "api-key"})
        after = Order.objects.get(pk=self.order.pk).status
        self.assertEqual(before, after)
