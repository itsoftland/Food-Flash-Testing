"""
Dine Flash Buffet: buffet_items on GET manager/api/get_today_orders/.

Additive coverage only; does not change buffet_utilities_orders_summary or OrdersSerializer.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from vendors.models import (
    AdminOutlet,
    BuffetOrderItem,
    ChatMessage,
    Order,
    UserProfile,
    Utility,
    Vendor,
    VendorConfig,
)

_BUFFET_LINE_STATUSES = (
    "created",
    "preparing",
    "ready",
    "delivered",
    "cancelled",
    "operation_closed",
)


def _business_day_patch():
    return patch(
        "manager.views.get_vendor_business_day_range",
        return_value=(
            timezone.now() - timedelta(hours=12),
            timezone.now() + timedelta(hours=12),
        ),
    )


def _create_vendor(suffix, customer_id, vendor_id):
    company = User.objects.create_user(username=f"co_gto_{suffix}", password="pass")
    outlet = AdminOutlet.objects.create(
        user=company,
        customer_name=f"Co {suffix}",
        customer_id=customer_id,
        authentication_status="Approve",
    )
    vendor = Vendor.objects.create(
        admin_outlet=outlet,
        name=f"Outlet {suffix}",
        alias_name=suffix[:8],
        location="L1",
        vendor_id=vendor_id,
        location_id=suffix[:4].upper(),
        menus="[]",
    )
    VendorConfig.objects.create(vendor=vendor)
    return outlet, vendor


def _create_manager(outlet, vendor, username, role="outlet_manager", utilities=None):
    user = User.objects.create_user(username=username, password="secret123")
    profile = UserProfile.objects.create(
        user=user,
        name=username,
        role=role,
        admin_outlet=outlet,
        vendor=vendor,
    )
    if utilities:
        profile.assigned_utilities.set(utilities)
    return user, profile


def _today_order(vendor, token_no, *, status="created"):
    order = Order.objects.create(
        vendor=vendor,
        token_no=token_no,
        status=status,
        table_booking_no=str(token_no),
        customer_name="Guest",
        updated_by="customer",
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now())
    order.refresh_from_db()
    return order


@override_settings(PROJECT_NAME="dine_flash_buffet")
class GetTodayOrdersBuffetItemsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("manager:get_today_orders")
        self.outlet, self.vendor = _create_vendor("items", 99101, 991001)
        self.utility_a = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Burger Station",
            display_name="Burger",
            display_code="BG",
        )
        self.utility_b = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Pizza Station",
            display_name="Pizza",
            display_code="PZ",
        )
        self.manager_user, self.manager_profile = _create_manager(
            self.outlet, self.vendor, "gto_mgr"
        )
        self.client.force_authenticate(user=self.manager_user)

    def _get_listing(self):
        with patch("manager.views.project_name", "dine_flash_buffet"), _business_day_patch():
            return self.client.get(self.url)

    def _detail_for_token(self, resp, token_no):
        rows = resp.data.get("detail") or []
        matched = [r for r in rows if int(r.get("token_no", -1)) == token_no]
        self.assertEqual(len(matched), 1, resp.data)
        return matched[0]

    def test_multiple_items_and_utilities_on_one_order(self):
        order = _today_order(self.vendor, 101)
        BuffetOrderItem.objects.create(
            order=order,
            utility=self.utility_a,
            status="preparing",
            quantity=2,
            customizations=["No onion"],
            remarks="",
        )
        BuffetOrderItem.objects.create(
            order=order,
            utility=self.utility_b,
            status="ready",
            quantity=1,
            customizations=[],
            remarks="extra cheese",
        )
        resp = self._get_listing()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = self._detail_for_token(resp, 101)
        items = row["buffet_items"]
        self.assertEqual(len(items), 2)
        by_name = {i["utility_name"]: i for i in items}
        self.assertEqual(by_name["Burger"]["item_id"], items[0]["item_id"])
        self.assertEqual(by_name["Burger"]["utility_id"], self.utility_a.id)
        self.assertEqual(by_name["Burger"]["status"], "preparing")
        self.assertEqual(by_name["Burger"]["quantity"], 2)
        self.assertEqual(by_name["Burger"]["customizations"], ["No onion"])
        self.assertEqual(by_name["Pizza"]["status"], "ready")
        self.assertEqual(by_name["Pizza"]["remarks"], "extra cheese")

    def test_multi_order_buffet_items_mapped_to_correct_parent(self):
        utility_juice = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Juice Station",
            display_name="Juice",
            display_code="JC",
        )
        utility_sandwich = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Sandwich Station",
            display_name="Sandwich",
            display_code="SW",
        )

        order_a = _today_order(self.vendor, 201, status="created")
        order_b = _today_order(self.vendor, 202, status="preparing")

        item_a_burger = BuffetOrderItem.objects.create(
            order=order_a,
            utility=self.utility_a,
            status="preparing",
            quantity=2,
        )
        item_a_pizza = BuffetOrderItem.objects.create(
            order=order_a,
            utility=self.utility_b,
            status="ready",
            quantity=1,
        )
        item_b_juice = BuffetOrderItem.objects.create(
            order=order_b,
            utility=utility_juice,
            status="created",
            quantity=1,
        )
        item_b_sandwich = BuffetOrderItem.objects.create(
            order=order_b,
            utility=utility_sandwich,
            status="delivered",
            quantity=3,
        )

        order_a_item_ids = {item_a_burger.id, item_a_pizza.id}
        order_b_item_ids = {item_b_juice.id, item_b_sandwich.id}
        db_records = {
            item_a_burger.id: (
                self.utility_a.id,
                "Burger",
                "preparing",
                2,
            ),
            item_a_pizza.id: (
                self.utility_b.id,
                "Pizza",
                "ready",
                1,
            ),
            item_b_juice.id: (
                utility_juice.id,
                "Juice",
                "created",
                1,
            ),
            item_b_sandwich.id: (
                utility_sandwich.id,
                "Sandwich",
                "delivered",
                3,
            ),
        }

        resp = self._get_listing()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get("message"), "Today's orders retrieved successfully.")
        self.assertIn("count", resp.data)
        self.assertIn("detail", resp.data)
        for key in ("created", "preparing", "ready", "delivered", "cancelled", "unread"):
            self.assertIn(key, resp.data)

        detail = resp.data["detail"]
        detail_tokens = {int(row["token_no"]) for row in detail}
        self.assertIn(201, detail_tokens)
        self.assertIn(202, detail_tokens)

        row_a = self._detail_for_token(resp, 201)
        row_b = self._detail_for_token(resp, 202)
        self.assertEqual(row_a["id"], order_a.id)
        self.assertEqual(row_b["id"], order_b.id)
        self.assertEqual(row_a["status"], "created")
        self.assertEqual(row_b["status"], "preparing")

        items_a = row_a["buffet_items"]
        items_b = row_b["buffet_items"]
        self.assertEqual(len(items_a), 2)
        self.assertEqual(len(items_b), 2)

        ids_a = {item["item_id"] for item in items_a}
        ids_b = {item["item_id"] for item in items_b}
        self.assertEqual(ids_a, order_a_item_ids)
        self.assertEqual(ids_b, order_b_item_ids)
        self.assertFalse(ids_a & ids_b)

        for payload in items_a + items_b:
            uid, uname, st, qty = db_records[payload["item_id"]]
            self.assertEqual(payload["utility_id"], uid)
            self.assertEqual(payload["utility_name"], uname)
            self.assertEqual(payload["status"], st)
            self.assertEqual(payload["quantity"], qty)

        all_item_ids = [
            item["item_id"]
            for row in detail
            for item in (row.get("buffet_items") or [])
        ]
        self.assertEqual(len(all_item_ids), 4)
        self.assertEqual(len(all_item_ids), len(set(all_item_ids)))

    def test_all_six_item_statuses_included(self):
        order = _today_order(self.vendor, 102)
        for idx, st in enumerate(_BUFFET_LINE_STATUSES):
            util = self.utility_a if idx % 2 == 0 else self.utility_b
            BuffetOrderItem.objects.create(
                order=order,
                utility=util,
                status=st,
                quantity=1,
            )
        resp = self._get_listing()
        row = self._detail_for_token(resp, 102)
        returned_statuses = {i["status"] for i in row["buffet_items"]}
        self.assertEqual(returned_statuses, set(_BUFFET_LINE_STATUSES))

    def test_parent_status_and_counts_unaffected_by_item_statuses(self):
        order = _today_order(self.vendor, 103, status="created")
        BuffetOrderItem.objects.create(
            order=order, utility=self.utility_a, status="delivered", quantity=1
        )
        BuffetOrderItem.objects.create(
            order=order, utility=self.utility_b, status="cancelled", quantity=1
        )
        resp = self._get_listing()
        row = self._detail_for_token(resp, 103)
        self.assertEqual(row["status"], "created")
        self.assertGreaterEqual(resp.data.get("created", 0), 1)
        self.assertEqual(resp.data.get("delivered", 0), 0)

    def test_unread_fields_unchanged(self):
        order = _today_order(self.vendor, 104)
        BuffetOrderItem.objects.create(
            order=order, utility=self.utility_a, status="ready", quantity=1
        )
        ChatMessage.objects.create(
            vendor=self.vendor,
            token_no=104,
            booking_id=order.id,
            booking_no="104",
            created_date=timezone.now().date(),
            sender="user",
            is_send=True,
            is_read=False,
            message_text="Ping",
        )
        resp = self._get_listing()
        row = self._detail_for_token(resp, 104)
        self.assertGreaterEqual(row.get("new_notifications", 0), 1)
        self.assertGreaterEqual(resp.data.get("unread", 0), 1)
        self.assertEqual(len(row["buffet_items"]), 1)

    def test_order_without_items_has_empty_buffet_items(self):
        _today_order(self.vendor, 105)
        resp = self._get_listing()
        row = self._detail_for_token(resp, 105)
        self.assertEqual(row["buffet_items"], [])

    def test_null_utility_item_included(self):
        order = _today_order(self.vendor, 106)
        BuffetOrderItem.objects.create(
            order=order,
            utility=None,
            status="created",
            quantity=1,
            customizations=None,
        )
        resp = self._get_listing()
        row = self._detail_for_token(resp, 106)
        self.assertEqual(len(row["buffet_items"]), 1)
        item = row["buffet_items"][0]
        self.assertIsNone(item["utility_id"])
        self.assertEqual(item["utility_name"], "Unknown")
        self.assertEqual(item["customizations"], [])

    def test_assigned_utilities_on_profile_do_not_filter_items(self):
        order = _today_order(self.vendor, 107)
        BuffetOrderItem.objects.create(
            order=order, utility=self.utility_a, status="preparing", quantity=1
        )
        BuffetOrderItem.objects.create(
            order=order, utility=self.utility_b, status="ready", quantity=1
        )
        _, assigned_only_profile = _create_manager(
            self.outlet,
            self.vendor,
            "gto_assigned",
            role="utility_user",
            utilities=[self.utility_a],
        )
        self.client.force_authenticate(user=assigned_only_profile.user)
        resp = self._get_listing()
        row = self._detail_for_token(resp, 107)
        names = {i["utility_name"] for i in row["buffet_items"]}
        self.assertEqual(names, {"Burger", "Pizza"})

    def test_single_batched_buffet_item_query(self):
        _today_order(self.vendor, 201)
        o2 = _today_order(self.vendor, 202)
        o3 = _today_order(self.vendor, 203)
        for o in (o2, o3):
            BuffetOrderItem.objects.create(
                order=o, utility=self.utility_a, status="created", quantity=1
            )
        filter_calls = []

        original_filter = BuffetOrderItem.objects.filter

        def counting_filter(*args, **kwargs):
            filter_calls.append((args, kwargs))
            return original_filter(*args, **kwargs)

        with patch("manager.views.project_name", "dine_flash_buffet"), _business_day_patch(), patch(
            "manager.views.BuffetOrderItem.objects.filter",
            side_effect=counting_filter,
        ):
            resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(filter_calls), 1)
        self.assertIn("order_id__in", filter_calls[0][1])

    def test_query_count_does_not_scale_per_order(self):
        o1 = _today_order(self.vendor, 301)
        BuffetOrderItem.objects.create(
            order=o1, utility=self.utility_a, status="created", quantity=1
        )
        with patch("manager.views.project_name", "dine_flash_buffet"), _business_day_patch():
            with CaptureQueriesContext(connection) as one_ctx:
                self.client.get(self.url)
            one_count = len(one_ctx.captured_queries)

        for token in (302, 303, 304):
            o = _today_order(self.vendor, token)
            BuffetOrderItem.objects.create(
                order=o, utility=self.utility_a, status="preparing", quantity=1
            )
        with patch("manager.views.project_name", "dine_flash_buffet"), _business_day_patch():
            with CaptureQueriesContext(connection) as many_ctx:
                self.client.get(self.url)
            many_count = len(many_ctx.captured_queries)

        self.assertEqual(
            many_count,
            one_count,
            msg="Expected item batching: total queries should not grow per extra order",
        )

    @override_settings(PROJECT_NAME="dine_flash")
    def test_dine_flash_detail_has_no_buffet_items(self):
        order = _today_order(self.vendor, 501, status="preparing")
        BuffetOrderItem.objects.create(
            order=order,
            utility=self.utility_a,
            status="ready",
            quantity=1,
        )

        with patch("manager.views.project_name", "dine_flash"), _business_day_patch(), patch(
            "manager.views._attach_buffet_items_to_order_detail"
        ) as mock_attach, patch(
            "manager.views._build_buffet_items_by_order_id"
        ) as mock_build:
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        detail = resp.data.get("detail") or []
        self.assertTrue(detail)
        row = self._detail_for_token(resp, 501)
        self.assertEqual(row["id"], order.id)
        self.assertEqual(int(row["token_no"]), 501)
        self.assertEqual(row["status"], "preparing")
        self.assertIn("customer_name", row)

        for entry in detail:
            self.assertNotIn(
                "buffet_items",
                entry,
                msg="dine_flash must not attach buffet_items to get_today_orders detail",
            )

        mock_attach.assert_not_called()
        mock_build.assert_not_called()


@override_settings(PROJECT_NAME="food_flash")
class GetTodayOrdersBuffetItemsCrossFlavourTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("manager:get_today_orders")
        company = User.objects.create_user(username="ff_co", password="pass")
        outlet = AdminOutlet.objects.create(
            user=company,
            customer_name="Food Co",
            customer_id=99201,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=outlet,
            name="Food Outlet",
            alias_name="FO",
            location="L1",
            vendor_id=992001,
            location_id="FF01",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)
        mgr = User.objects.create_user(username="ff_mgr", password="secret123")
        UserProfile.objects.create(
            user=mgr,
            name="FF Mgr",
            role="outlet_manager",
            admin_outlet=outlet,
            vendor=self.vendor,
        )
        self.client.force_authenticate(user=mgr)
        order = Order.objects.create(
            vendor=self.vendor,
            token_no=1,
            status="preparing",
            counter_no=1,
            updated_by="customer",
        )
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now())
        util = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Counter",
            display_name="Counter",
            display_code="CT",
        )
        BuffetOrderItem.objects.create(
            order=order, utility=util, status="ready", quantity=1
        )

    def test_food_flash_detail_has_no_buffet_items(self):
        with patch("manager.views.project_name", "food_flash"), _business_day_patch():
            resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        detail = resp.data.get("detail") or []
        self.assertTrue(detail)
        self.assertNotIn("buffet_items", detail[0])
