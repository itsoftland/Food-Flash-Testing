from datetime import datetime, time, timedelta
from unittest import mock

import pytz
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from company.views import _resolve_buffet_vendor_tz
from static.utils.functions.utils import get_time_ranges
from vendors.models import AdminOutlet, ArchivedOrder, Order, Vendor, VendorConfig


class BuffetOrderCountsSummaryTests(TestCase):
    """Vendor-local calendar counts for dine_flash_buffet order_counts_summary only."""

    def setUp(self):
        self.user = User.objects.create_user(username="buffet_summary_admin", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Buffet Summary Co",
            customer_id=502,
            locations=[{"City": "C1"}],
            authentication_status="Approve",
            product_to_date=timezone.now() + timedelta(days=30),
        )

    def _vendor(self, name, vendor_id, tz_name):
        vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name=name,
            alias_name=name,
            location="City",
            vendor_id=vendor_id,
            location_id="L1",
            menus="[]",
        )
        VendorConfig.objects.create(
            vendor=vendor,
            timezone=tz_name,
            business_day_start_hour=time(6, 0),
        )
        return vendor

    def _order_at(self, vendor, created_at):
        order = Order.objects.create(
            vendor=vendor,
            token_no=created_at.minute + vendor.vendor_id % 1000,
            status="created",
        )
        Order.objects.filter(pk=order.pk).update(created_at=created_at)
        order.refresh_from_db()
        return order

    def _archived_at(self, vendor, created_at, token_no):
        return ArchivedOrder.objects.create(
            original_order_id=token_no,
            vendor=vendor,
            device=None,
            user_profile=None,
            token_no=token_no,
            status="ready",
            counter_no=1,
            shown_on_tv=False,
            notified_at=None,
            updated_by="manager",
            created_at=created_at,
            updated_at=created_at,
        )

    def _get_summary(self):
        return self.client.get(reverse("company:order_counts_summary"))

    def _get_filtered_total(self, **params):
        url = reverse("company:get_orders")
        resp = self.client.get(url, params)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.json()["meta"]["total"]

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_asia_kolkata_today_summary_count(self):
        vendor = self._vendor("Kolkata", 502001, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 5, 0, 0))
        self._order_at(vendor, fixed_now - timedelta(hours=2))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 18, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["orders_today"], 1)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_utc_vendor_today_summary_count(self):
        vendor = self._vendor("UTC", 502002, "UTC")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 12, 0, 0))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 17, 1, 0, 0)))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 23, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_today"], 1)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_multiple_vendors_different_timezones(self):
        kolkata = self._vendor("K", 502003, "Asia/Kolkata")
        utc = self._vendor("U", 502004, "UTC")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 5, 0, 0))

        self._order_at(kolkata, pytz.UTC.localize(datetime(2026, 3, 16, 18, 30, 0)))
        self._order_at(utc, pytz.UTC.localize(datetime(2026, 3, 17, 1, 0, 0)))
        self._order_at(utc, pytz.UTC.localize(datetime(2026, 3, 16, 20, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_today"], 2)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_active_and_archived_orders_included(self):
        vendor = self._vendor("Both", 502005, "UTC")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 12, 0, 0))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 17, 8, 0, 0)))
        self._archived_at(vendor, pytz.UTC.localize(datetime(2026, 3, 17, 9, 0, 0)), token_no=88)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_today"], 2)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_today_includes_full_local_calendar_day(self):
        vendor = self._vendor("FullDay", 502006, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 5, 0, 0))  # 10:30 IST
        # Late in local day but still before next midnight (23:30 IST Mar 17)
        late_local_day = pytz.UTC.localize(datetime(2026, 3, 17, 18, 0, 0))
        self._order_at(vendor, late_local_day)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_today"], 1)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_this_week_boundaries(self):
        vendor = self._vendor("Week", 502007, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 18, 6, 0, 0))
        monday_local = pytz.UTC.localize(datetime(2026, 3, 16, 18, 30, 0))
        prior_sunday = pytz.UTC.localize(datetime(2026, 3, 14, 18, 30, 0))

        self._order_at(vendor, monday_local)
        self._order_at(vendor, prior_sunday)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_this_week"], 1)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_this_month_boundaries(self):
        vendor = self._vendor("Month", 502008, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 10, 0, 0))
        month_start = pytz.UTC.localize(datetime(2026, 2, 28, 18, 30, 0))
        before_month = pytz.UTC.localize(datetime(2026, 2, 28, 12, 0, 0))

        self._order_at(vendor, month_start)
        self._order_at(vendor, before_month)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_this_month"], 1)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_invalid_timezone_falls_back_to_utc(self):
        vendor = self._vendor("Bad TZ", 502009, "Invalid/Timezone")
        self.assertIs(_resolve_buffet_vendor_tz(vendor), pytz.UTC)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_summary_matches_filtered_orders_for_same_ranges(self):
        vendor = self._vendor("Parity", 502010, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 5, 0, 0))
        self._order_at(vendor, fixed_now - timedelta(hours=1))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 18, 0, 0)))
        self._archived_at(
            vendor,
            fixed_now - timedelta(minutes=30),
            token_no=91,
        )

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            summary = self._get_summary().json()
            today_filtered = self._get_filtered_total(range="today")
            week_filtered = self._get_filtered_total(range="this_week")
            month_filtered = self._get_filtered_total(range="this_month")

        self.assertEqual(summary["orders_today"], today_filtered)
        self.assertEqual(summary["orders_this_week"], week_filtered)
        self.assertEqual(summary["orders_this_month"], month_filtered)
        self.assertEqual(summary["orders_today"], 2)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_response_json_structure_unchanged(self):
        vendor = self._vendor("Shape", 502011, "UTC")
        self._order_at(vendor, timezone.now())
        resp = self._get_summary()
        data = resp.json()
        self.assertEqual(set(data.keys()), {"orders_today", "orders_this_week", "orders_this_month"})
        for key in data:
            self.assertIsInstance(data[key], int)

    @override_settings(PROJECT_NAME="food_flash")
    def test_food_flash_retains_utc_get_time_ranges(self):
        vendor = self._vendor("FF", 602001, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 2, 0, 0))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 20, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            with mock.patch("static.utils.functions.utils.get_time_ranges", wraps=get_time_ranges):
                resp = self._get_summary()
        self.assertEqual(resp.json()["orders_today"], 0)

    @override_settings(PROJECT_NAME="dine_flash")
    def test_dine_flash_retains_utc_get_time_ranges(self):
        vendor = self._vendor("DF", 602002, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 2, 0, 0))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 20, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_today"], 0)

    @override_settings(PROJECT_NAME="hospital_flash")
    def test_hospital_flash_retains_utc_get_time_ranges(self):
        vendor = self._vendor("HF", 602003, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 2, 0, 0))
        self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 20, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_summary()
        self.assertEqual(resp.json()["orders_today"], 0)