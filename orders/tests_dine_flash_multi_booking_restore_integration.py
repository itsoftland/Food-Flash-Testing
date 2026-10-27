"""Static integration checks for Dine Flash multi-booking restore wiring."""
from pathlib import Path

from django.test import SimpleTestCase


class DineFlashMultiBookingRestoreIntegrationTests(SimpleTestCase):
    def test_home_init_falls_back_only_on_confirmed_inactive(self):
        scripts = (
            Path(__file__).resolve().parent / "static/orders/js/scripts.js"
        ).read_text(encoding="utf-8")
        self.assertIn("restoreResult.reason !== \"selected_not_active\"", scripts)
        self.assertIn("__dineFlashApplySelectedBookingHomeView", scripts)

    def test_lookup_resume_waits_for_multi_booking_restore(self):
        resume = (
            Path(__file__).resolve().parent
            / "static/orders/js/dineflash/services/bookingLookupResumeService.js"
        ).read_text(encoding="utf-8")
        self.assertIn("whenRestoreSettled", resume)
        self.assertIn("tryMultiBookingSelectedResume", resume)
        self.assertIn("handledBySelected", resume)

    def test_buffet_modules_untouched_in_diff_scope(self):
        buffet_views = (
            Path(__file__).resolve().parent / "buffet_views.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("DineFlashActiveBooking", buffet_views)
