"""Dine Flash book_table active registry + additional booking tests."""
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory

from orders.views import book_table
from vendors.models import (
    AdminOutlet,
    DineFlashActiveBooking,
    DineFlashBookingLookup,
    Order,
    Vendor,
    VendorConfig,
)


class DineFlashSubmitActiveBookingRegistryTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.outlet = AdminOutlet.objects.create(
            customer_name="Dine Submit Registry Co",
            customer_id=93002,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Dine Submit Registry Outlet",
            alias_name="DSRO",
            location="City",
            place_id="place-dine-submit-reg-1",
            vendor_id=930002,
            location_id="LOC-DSR1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor, use_utilities=False)

    def _post(self, extra=None):
        payload = {
            "vendor_id": self.vendor.vendor_id,
            "customer_name": "Guest",
            "no_of_guests": 2,
            "qr_session": "qr-test-token",
        }
        if extra:
            payload.update(extra)
        request = self.factory.post("/api/book_table/", payload, format="json")
        request.user = AnonymousUser()
        with patch("orders.views.project_name", "dine_flash"), patch(
            "orders.views._validate_dine_flash_qr_session", return_value=(True, None)
        ), patch(
            "orders.views.reset_counters_if_new_business_day", return_value=None
        ), patch(
            "orders.views._schedule_dine_flash_booking_created_fcm"
        ):
            with self.captureOnCommitCallbacks(execute=True):
                return book_table(request)

    def test_qr_submit_registers_active_booking_and_lookup(self):
        resp = self._post({"order_lookup_id": "qr-key"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_id = resp.data["id"]
        self.assertEqual(DineFlashBookingLookup.objects.filter(order_lookup_id="qr-key").count(), 1)
        self.assertEqual(
            DineFlashBookingLookup.objects.get(order_lookup_id="qr-key").order_id,
            order_id,
        )
        self.assertEqual(DineFlashActiveBooking.objects.filter(order_id=order_id).count(), 1)

    def test_additional_booking_registers_without_updating_lookup(self):
        first = self._post({"order_lookup_id": "shared-key"})
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        first_order_id = first.data["id"]

        with patch("orders.views._validate_dine_flash_qr_session") as qr_mock:
            qr_mock.return_value = (True, None)
            second = self._post(
                {
                    "order_lookup_id": "shared-key",
                    "is_additional_booking": True,
                }
            )
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        second_order_id = second.data["id"]

        self.assertEqual(
            DineFlashBookingLookup.objects.get(order_lookup_id="shared-key").order_id,
            first_order_id,
        )
        self.assertEqual(
            DineFlashActiveBooking.objects.filter(order_lookup_id="shared-key").count(),
            2,
        )
        self.assertTrue(DineFlashActiveBooking.objects.filter(order_id=second_order_id).exists())

    def test_submit_without_order_lookup_id_creates_no_registry_row(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DineFlashActiveBooking.objects.count(), 0)

    def test_invalid_order_lookup_id_rejected(self):
        resp = self._post({"order_lookup_id": "x" * 256})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
