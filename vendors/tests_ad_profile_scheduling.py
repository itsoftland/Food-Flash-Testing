"""Regression tests for AdvertisementProfile.is_active_now scheduling."""

from datetime import date, datetime, time
from unittest.mock import patch

import pytz
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from vendors.models import (
    AdminOutlet,
    AdvertisementProfile,
    AdvertisementSlot,
    Vendor,
    VendorConfig,
)


def _vendor_local_now(vendor, local_dt):
    """Return a timezone-aware datetime as get_vendor_current_time would."""
    tz_name = vendor.config.timezone
    tz = pytz.timezone(tz_name)
    if timezone.is_naive(local_dt):
        return tz.localize(local_dt)
    return local_dt.astimezone(tz)


@patch("vendors.models.get_vendor_current_time")
class AdvertisementProfileIsActiveNowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ad-sched-user", password="pass")
        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Sched Co",
            customer_id=94001,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Outlet",
            alias_name="O",
            location="City",
            place_id="place-sched",
            vendor_id=940001,
            location_id="S1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor, timezone="Asia/Kolkata")

    def _profile(self, **kwargs):
        defaults = {"admin_outlet": self.admin_outlet, "name": "Test Profile"}
        defaults.update(kwargs)
        return AdvertisementProfile.objects.create(**defaults)

    def test_date_only_active_within_inclusive_range(self, mock_now):
        profile = self._profile(
            date_start=date(2026, 3, 1),
            date_end=date(2026, 3, 31),
            days_active=[],
        )
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 3, 15, 12, 0, 0)
        )
        self.assertTrue(profile.is_active_now(self.vendor))

    def test_date_only_inactive_outside_range(self, mock_now):
        profile = self._profile(
            date_start=date(2026, 3, 1),
            date_end=date(2026, 3, 31),
            days_active=[],
        )
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 4, 1, 12, 0, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))

    def test_identical_start_and_end_date_active_on_that_day(self, mock_now):
        profile = self._profile(
            date_start=date(2026, 6, 10),
            date_end=date(2026, 6, 10),
            days_active=[],
        )
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 6, 10, 8, 30, 0)
        )
        self.assertTrue(profile.is_active_now(self.vendor))
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 6, 11, 8, 30, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))

    def test_no_scheduling_mode_inactive(self, mock_now):
        profile = self._profile(days_active=[])
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 1, 15, 12, 0, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))

    def test_partial_dates_without_weekdays_inactive(self, mock_now):
        profile = self._profile(date_start=date(2026, 1, 1), days_active=[])
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 1, 15, 12, 0, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))

        profile_end_only = self._profile(date_end=date(2026, 12, 31), days_active=[])
        self.assertFalse(profile_end_only.is_active_now(self.vendor))

    def test_weekday_only_profile(self, mock_now):
        profile = self._profile(days_active=["Wednesday"])
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 3, 4, 10, 0, 0)
        )
        self.assertTrue(profile.is_active_now(self.vendor))
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 3, 5, 10, 0, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))

    def test_combined_date_and_weekday_requires_both(self, mock_now):
        profile = self._profile(
            date_start=date(2026, 3, 1),
            date_end=date(2026, 3, 31),
            days_active=["Wednesday"],
        )
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 3, 4, 10, 0, 0)
        )
        self.assertTrue(profile.is_active_now(self.vendor))
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 4, 1, 10, 0, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 3, 5, 10, 0, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))

    def test_days_active_all_supported(self, mock_now):
        profile = self._profile(days_active=["All"])
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 7, 29, 14, 0, 0)
        )
        self.assertTrue(profile.is_active_now(self.vendor))

    def test_time_slots_restrict_active_window(self, mock_now):
        profile = self._profile(
            date_start=date(2026, 5, 1),
            date_end=date(2026, 5, 31),
            days_active=[],
        )
        AdvertisementSlot.objects.create(
            profile=profile, start_time=time(9, 0), end_time=time(11, 0)
        )
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 5, 10, 10, 0, 0)
        )
        self.assertTrue(profile.is_active_now(self.vendor))
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 5, 10, 8, 0, 0)
        )
        self.assertFalse(profile.is_active_now(self.vendor))
        mock_now.return_value = _vendor_local_now(
            self.vendor, datetime(2026, 5, 10, 11, 0, 0)
        )
        self.assertTrue(profile.is_active_now(self.vendor))

    def test_uses_vendor_local_date_for_range(self, mock_now):
        self.vendor.config.timezone = "Pacific/Auckland"
        self.vendor.config.save()
        profile = self._profile(
            date_start=date(2026, 1, 1),
            date_end=date(2026, 1, 1),
            days_active=[],
        )
        nz = pytz.timezone("Pacific/Auckland")
        mock_now.return_value = nz.localize(datetime(2026, 1, 1, 23, 30, 0))
        self.assertTrue(profile.is_active_now(self.vendor))
