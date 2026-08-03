"""
Hospital Flash get_booking_list tracking_url enrichment tests.

Hospital branch only — verifies canonical batch-primary URLs via
build_hospital_tracking_url without changing shared serializer behaviour.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate


def _order(
    *,
    order_id,
    booking_no,
    batch_id,
    utility_code="LAB",
    utility_name="Lab",
):
    utility = SimpleNamespace(display_code=utility_code, display_name=utility_name)
    return SimpleNamespace(
        id=order_id,
        table_booking_no=booking_no,
        registration_batch_id=batch_id,
        utility=utility,
        vendor=None,
        customer_name="Pat",
        phone_number=None,
        no_of_packs=None,
        remarks=None,
        status="waiting",
        created_at=None,
    )


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalBookingListTrackingUrlTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.batch = UUID("11111111-1111-1111-1111-111111111111")
        self.vendor = SimpleNamespace(
            id=1,
            vendor_id=10,
            location_id="L1",
            name="City Hospital",
        )

    def _auth_request(self, role="outlet_manager"):
        profile = MagicMock()
        profile.role = role
        profile.assigned_utilities = MagicMock()
        profile.assigned_utilities.all.return_value = MagicMock()
        profile.assigned_utilities.all.return_value.exists.return_value = False

        user = MagicMock()
        profiles = MagicMock()
        profiles.first.return_value = profile
        user.profile_roles = profiles
        user.username = "mgr"

        request = self.factory.get("/hospital_flash/manager/api/get_booking_list/")
        force_authenticate(request, user=user)
        return request, profile

    @patch("manager.views.build_hospital_tracking_url")
    @patch("manager.views._group_serialized_bookings")
    @patch("manager.views.BookingSerializer")
    @patch("manager.views._build_unread_notifications_map", return_value={})
    @patch("manager.views.get_vendor_business_day_range")
    @patch("manager.views._resolve_vendor_for_manager")
    @patch("manager.views.Order.objects")
    def test_multi_department_rows_share_canonical_url(
        self,
        mock_order_objects,
        mock_resolve_vendor,
        mock_day_range,
        _mock_unread,
        mock_serializer,
        mock_group,
        mock_build_url,
    ):
        from manager import views

        lab = _order(order_id=130, booking_no="Lab-1", batch_id=self.batch)
        ortho = _order(
            order_id=131,
            booking_no="Ortho-1",
            batch_id=self.batch,
            utility_code="ORTHO",
            utility_name="Ortho",
        )
        booking_list = [lab, ortho]

        mock_resolve_vendor.return_value = self.vendor
        mock_day_range.return_value = ("start", "end")

        day_qs = MagicMock()
        day_qs.select_related.return_value.order_by.return_value = booking_list
        primary_qs = MagicMock()
        primary_qs.only.return_value.order_by.return_value = [lab, ortho]
        mock_order_objects.filter.side_effect = [day_qs, primary_qs]

        mock_serializer.return_value.data = [
            {"id": 130, "tracking_url": None, "new_notifications": 0},
            {"id": 131, "tracking_url": None, "new_notifications": 0},
        ]
        mock_group.return_value = {"LAB": {"unread": 0, "bookings": []}}
        mock_build_url.return_value = (
            "http://testserver/hospital_flash/home/"
            "?location_id=L1&vendor_id=10&booking_no=Lab-1"
            "&booking_id=130&registration_batch_id="
            "11111111-1111-1111-1111-111111111111"
        )

        request, _profile = self._auth_request()
        with patch.object(views, "project_name", "hospital_flash"):
            response = views.get_booking_list(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(mock_build_url.call_count, 2)

        for call in mock_build_url.call_args_list:
            args = call.args
            self.assertIs(args[1], self.vendor)
            self.assertEqual(
                args[2],
                {"token": "Lab-1", "order_id": 130},
            )
            self.assertEqual(args[3], self.batch)

        rows = mock_serializer.return_value.data
        self.assertEqual(rows[0]["tracking_url"], mock_build_url.return_value)
        self.assertEqual(rows[1]["tracking_url"], mock_build_url.return_value)

    @patch("manager.views.build_hospital_tracking_url")
    @patch("manager.views._group_serialized_bookings")
    @patch("manager.views.BookingSerializer")
    @patch("manager.views._build_unread_notifications_map", return_value={})
    @patch("manager.views.get_vendor_business_day_range")
    @patch("manager.views._resolve_vendor_for_manager")
    @patch("manager.views.Order.objects")
    def test_legacy_row_without_batch_keeps_null_tracking_url(
        self,
        mock_order_objects,
        mock_resolve_vendor,
        mock_day_range,
        _mock_unread,
        mock_serializer,
        mock_group,
        mock_build_url,
    ):
        from manager import views

        legacy = _order(order_id=99, booking_no="Lab-9", batch_id=None)
        mock_resolve_vendor.return_value = self.vendor
        mock_day_range.return_value = ("start", "end")

        filter_qs = MagicMock()
        filter_qs.select_related.return_value.order_by.return_value = [legacy]
        mock_order_objects.filter.return_value = filter_qs

        mock_serializer.return_value.data = [
            {"id": 99, "tracking_url": None, "new_notifications": 0},
        ]
        mock_group.return_value = {}

        request, _profile = self._auth_request()
        with patch.object(views, "project_name", "hospital_flash"):
            response = views.get_booking_list(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_build_url.assert_not_called()
        self.assertIsNone(mock_serializer.return_value.data[0]["tracking_url"])
