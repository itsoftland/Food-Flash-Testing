"""
Buffet Active Order Registry — Phase 1B submit wiring tests.

Verifies post-commit registration for QR and "+" paths without changing
BuffetOrderLookup Latest Order Wins semantics for additional orders.
"""
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory

from orders.buffet_views import buffet_submit_order
from vendors.models import (
    AdminOutlet,
    BuffetActiveOrder,
    BuffetOrderLookup,
    Order,
    Utility,
    Vendor,
)


class BuffetSubmitActiveOrderRegistryTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.outlet = AdminOutlet.objects.create(
            customer_name="Registry Submit Co",
            customer_id=92002,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Buffet Registry Submit Outlet",
            alias_name="BRSO",
            location="City",
            place_id="place-registry-submit-1",
            vendor_id=920002,
            location_id="LOC-RS1",
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
            with self.captureOnCommitCallbacks(execute=True):
                return buffet_submit_order(request)

    def test_qr_submit_upserts_lookup_and_registers_active_order(self):
        resp = self._submit({"order_lookup_id": "qr-key"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_id = resp.data["order_id"]

        self.assertEqual(BuffetOrderLookup.objects.filter(order_lookup_id="qr-key").count(), 1)
        self.assertEqual(
            BuffetOrderLookup.objects.get(order_lookup_id="qr-key").order_id,
            order_id,
        )
        self.assertEqual(BuffetActiveOrder.objects.filter(order_id=order_id).count(), 1)
        entry = BuffetActiveOrder.objects.get(order_id=order_id)
        self.assertEqual(entry.order_lookup_id, "qr-key")
        self.assertEqual(entry.token_no, resp.data["token_no"])
        self.assertEqual(entry.vendor_id, self.vendor.vendor_id)

    def test_additional_order_registers_without_updating_lookup(self):
        first = self._submit({"order_lookup_id": "shared-key"})
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        first_order_id = first.data["order_id"]

        second = self._submit(
            {
                "order_lookup_id": "shared-key",
                "is_additional_order": True,
            }
        )
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        second_order_id = second.data["order_id"]

        # Latest Order Wins pointer remains on the QR / primary order.
        self.assertEqual(BuffetOrderLookup.objects.filter(order_lookup_id="shared-key").count(), 1)
        self.assertEqual(
            BuffetOrderLookup.objects.get(order_lookup_id="shared-key").order_id,
            first_order_id,
        )

        # Registry holds both orders.
        self.assertEqual(
            BuffetActiveOrder.objects.filter(order_lookup_id="shared-key").count(),
            2,
        )
        self.assertTrue(BuffetActiveOrder.objects.filter(order_id=first_order_id).exists())
        self.assertTrue(BuffetActiveOrder.objects.filter(order_id=second_order_id).exists())

    def test_submit_without_order_lookup_id_creates_no_registry_row(self):
        resp = self._submit()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(BuffetActiveOrder.objects.count(), 0)
        self.assertEqual(BuffetOrderLookup.objects.count(), 0)

    def test_registry_registration_idempotent_for_same_order(self):
        resp = self._submit({"order_lookup_id": "idempotent-key"})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(id=resp.data["order_id"])

        from orders.buffet.active_order_registry import register_buffet_active_order

        register_buffet_active_order(order_lookup_id="idempotent-key", order=order)
        self.assertEqual(BuffetActiveOrder.objects.filter(order=order).count(), 1)

    def test_registry_failure_does_not_change_http_success(self):
        with patch(
            "orders.buffet_views.register_buffet_active_order",
            side_effect=RuntimeError("registry down"),
        ):
            resp = self._submit({"order_lookup_id": "fail-key"})

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Order.objects.filter(id=resp.data["order_id"]).exists())
        self.assertEqual(
            BuffetOrderLookup.objects.get(order_lookup_id="fail-key").order_id,
            resp.data["order_id"],
        )
        self.assertEqual(BuffetActiveOrder.objects.count(), 0)

    def test_invalid_items_rollback_creates_no_registry_row(self):
        resp = self._submit(
            {
                "order_lookup_id": "rollback-key",
                "items": [
                    {
                        "utility_id": 999999,
                        "quantity": 1,
                        "is_grouped": False,
                        "customizations": [],
                        "remarks": "",
                    }
                ],
            }
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(BuffetOrderLookup.objects.count(), 0)
        self.assertEqual(BuffetActiveOrder.objects.count(), 0)
