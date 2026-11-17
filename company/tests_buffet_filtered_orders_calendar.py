from datetime import datetime, time, timedelta
from unittest import mock

import pytz
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from company.views import _buffet_vendor_calendar_bounds_utc, _resolve_buffet_vendor_tz
from static.utils.functions.utils import get_vendor_business_day_range
from vendors.models import AdminOutlet, ArchivedOrder, Order, Vendor, VendorConfig


class BuffetFilteredOrdersCalendarTests(TestCase):
    """Vendor-local calendar date filters for dine_flash_buffet filtered_orders only."""

    def setUp(self):
        self.user = User.objects.create_user(username="buffet_admin", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Buffet Co",
            customer_id=501,
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

    def _get_filtered(self, **params):
        url = reverse("company:get_orders")
        return self.client.get(url, params)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_asia_kolkata_today_includes_local_calendar_day(self):
        vendor = self._vendor("Kolkata Outlet", 501001, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 5, 0, 0))  # 10:30 IST
        inside = fixed_now - timedelta(hours=2)  # 08:30 IST same local day
        before_local_day = pytz.UTC.localize(datetime(2026, 3, 16, 18, 0, 0))  # 23:30 IST prior day

        self._order_at(vendor, inside)
        self._order_at(vendor, before_local_day)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="today")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertEqual(len(ids), 1)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_utc_vendor_today_uses_utc_midnight_window(self):
        vendor = self._vendor("UTC Outlet", 501002, "UTC")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 12, 0, 0))
        inside = pytz.UTC.localize(datetime(2026, 3, 17, 1, 0, 0))
        outside = pytz.UTC.localize(datetime(2026, 3, 16, 23, 0, 0))

        inside_order = self._order_at(vendor, inside)
        self._order_at(vendor, outside)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="today")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertEqual(ids, {inside_order.id})

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_multiple_vendors_different_timezones(self):
        kolkata = self._vendor("K", 501003, "Asia/Kolkata")
        utc = self._vendor("U", 501004, "UTC")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 5, 0, 0))

        k_order = self._order_at(
            kolkata,
            pytz.UTC.localize(datetime(2026, 3, 16, 18, 30, 0)),  # 00:00 IST Mar 17
        )
        u_order = self._order_at(
            utc,
            pytz.UTC.localize(datetime(2026, 3, 17, 1, 0, 0)),
        )
        self._order_at(utc, pytz.UTC.localize(datetime(2026, 3, 16, 20, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="today")
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertEqual(ids, {k_order.id, u_order.id})

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_this_week_starts_monday_local(self):
        vendor = self._vendor("Week", 501005, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 18, 6, 0, 0))  # Wed 11:30 IST
        monday_local = pytz.UTC.localize(datetime(2026, 3, 16, 18, 30, 0))  # Mon 00:00 IST
        prior_sunday = pytz.UTC.localize(datetime(2026, 3, 14, 18, 30, 0))

        included = self._order_at(vendor, monday_local)
        self._order_at(vendor, prior_sunday)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="this_week")
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertEqual(ids, {included.id})

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_this_month_starts_first_local_day(self):
        vendor = self._vendor("Month", 501006, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 10, 0, 0))
        month_start = pytz.UTC.localize(datetime(2026, 2, 28, 18, 30, 0))  # Mar 1 00:00 IST
        before_month = pytz.UTC.localize(datetime(2026, 2, 28, 12, 0, 0))

        included = self._order_at(vendor, month_start)
        self._order_at(vendor, before_month)

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="this_month")
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertEqual(ids, {included.id})

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_custom_range_inclusive_end_date(self):
        vendor = self._vendor("Custom", 501007, "Asia/Kolkata")
        on_end = pytz.UTC.localize(datetime(2026, 3, 10, 18, 0, 0))  # 23:30 IST Mar 10
        after_end = pytz.UTC.localize(datetime(2026, 3, 11, 18, 31, 0))  # just after midnight Mar 11 IST

        included = self._order_at(vendor, on_end)
        self._order_at(vendor, after_end)

        resp = self._get_filtered(
            **{
                "range": "custom",
                "from": "2026-03-10",
                "to": "2026-03-10",
            }
        )
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertEqual(ids, {included.id})

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_archived_orders_included(self):
        vendor = self._vendor("Arch", 501008, "UTC")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 12, 0, 0))
        archived = self._archived_at(
            vendor,
            pytz.UTC.localize(datetime(2026, 3, 17, 8, 0, 0)),
            token_no=77,
        )

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="today")
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertIn(archived.id, ids)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_invalid_timezone_falls_back_to_utc(self):
        vendor = self._vendor("Bad TZ", 501009, "Invalid/Timezone")
        self.assertIs(_resolve_buffet_vendor_tz(vendor), pytz.UTC)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_missing_timezone_on_config_defaults_to_utc(self):
        vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="No TZ",
            alias_name="No TZ",
            location="City",
            vendor_id=501010,
            location_id="L1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=vendor, timezone="", business_day_start_hour=time(0, 0))
        self.assertEqual(str(_resolve_buffet_vendor_tz(vendor)), "UTC")

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_invalid_custom_range_returns_no_orders(self):
        vendor = self._vendor("Custom bad", 501011, "UTC")
        self._order_at(vendor, timezone.now())

        resp = self._get_filtered(
            range="custom",
            **{"from": "not-a-date", "to": "2026-03-01"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["meta"]["total"], 0)

        resp = self._get_filtered(
            range="custom",
            **{"from": "2026-03-05", "to": "2026-03-01"},
        )
        self.assertEqual(resp.json()["meta"]["total"], 0)

    def test_business_day_helper_unchanged(self):
        vendor = self._vendor("Business", 501012, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 3, 0, 0))  # 08:30 IST; before 06:00 business roll for "current" day logic
        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            start, end = get_vendor_business_day_range(vendor)
        # Business day should still anchor at 06:00 local, not calendar midnight.
        kolkata = pytz.timezone("Asia/Kolkata")
        expected_start = kolkata.localize(datetime(2026, 3, 17, 6, 0, 0)).astimezone(pytz.UTC)
        self.assertEqual(start, expected_start)
        self.assertLess(end - start, timedelta(days=1, minutes=1))
        self.assertGreater(end - start, timedelta(hours=23))

    @override_settings(PROJECT_NAME="dine_flash")
    def test_dine_flash_still_uses_shared_date_range_helper(self):
        vendor = self._vendor("DF", 601001, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 2, 0, 0))  # 07:30 IST
        # Outside UTC "today" start (Mar 17 00:00 UTC) but inside IST calendar morning
        order = self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 20, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="today")
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertNotIn(order.id, ids)

    @override_settings(PROJECT_NAME="hospital_flash")
    def test_hospital_flash_still_uses_shared_date_range_helper(self):
        vendor = self._vendor("HF", 701001, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 2, 0, 0))
        order = self._order_at(vendor, pytz.UTC.localize(datetime(2026, 3, 16, 20, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="today")
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertNotIn(order.id, ids)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_calendar_bounds_helper_today(self):
        vendor = self._vendor("Bounds", 501013, "Asia/Kolkata")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 10, 0, 0))
        start, end = _buffet_vendor_calendar_bounds_utc(vendor, "today", now_utc=fixed_now)
        kolkata = pytz.timezone("Asia/Kolkata")
        expected_start = kolkata.localize(datetime(2026, 3, 17, 0, 0, 0)).astimezone(pytz.UTC)
        expected_end = kolkata.localize(datetime(2026, 3, 18, 0, 0, 0)).astimezone(pytz.UTC)
        self.assertEqual(start, expected_start)
        self.assertEqual(end, expected_end)

    @override_settings(PROJECT_NAME="dine_flash_buffet")
    def test_outlet_filter_limits_vendor_clauses(self):
        v1 = self._vendor("A", 501014, "UTC")
        v2 = self._vendor("B", 501015, "UTC")
        fixed_now = pytz.UTC.localize(datetime(2026, 3, 17, 12, 0, 0))
        o1 = self._order_at(v1, pytz.UTC.localize(datetime(2026, 3, 17, 9, 0, 0)))
        self._order_at(v2, pytz.UTC.localize(datetime(2026, 3, 17, 9, 0, 0)))

        with mock.patch("company.views.timezone.now", return_value=fixed_now):
            resp = self._get_filtered(range="today", outlet_id=v1.id)
        ids = {row["id"] for row in resp.json()["data"]}
        self.assertEqual(ids, {o1.id})