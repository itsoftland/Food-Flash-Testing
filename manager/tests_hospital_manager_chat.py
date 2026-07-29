"""
Hospital Flash manager → patient chat unit tests.

Cross-flavour guard: exercises manager.hospital_views.manager_patient_message only.
Does not modify manager_patient_update or other flavour update paths.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate


def _manager_profile(role="outlet_manager", utility_ids=None):
    from vendors.models import Utility

    vendor = SimpleNamespace(
        id=1,
        name="City Hospital",
        alias_name="City Hospital",
        vendor_id="H1",
        location_id="L1",
        config=SimpleNamespace(vibration_pattern=None, vibration_duration=None),
    )
    profile = MagicMock()
    profile.role = role
    profile.name = "Mgr"
    profile.vendor = vendor
    assigned = MagicMock()
    if utility_ids is None:
        empty_qs = MagicMock()
        empty_qs.exists.return_value = False
        empty_qs.all.return_value = empty_qs
        empty_qs.prefetch_related.return_value = []
        assigned.exists.return_value = False
        assigned.all.return_value = empty_qs
    else:
        depts = []
        for uid in utility_ids:
            dept = SimpleNamespace(
                id=uid,
                department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
            )
            dept.group_departments = MagicMock(all=lambda: [])
            depts.append(dept)
        qs = MagicMock()
        qs.exists.return_value = True
        qs.all.return_value = qs
        qs.prefetch_related.return_value = depts
        qs.__iter__ = lambda self: iter(depts)
        assigned.exists.return_value = True
        assigned.all.return_value = qs
    profile.assigned_utilities = assigned
    return profile, vendor


def _booking(vendor, utility_id=10, status_value="waiting"):
    utility = SimpleNamespace(id=utility_id, display_name="Radiology")
    order = MagicMock()
    order.id = 42
    order.pk = 42
    order.token_no = 7
    order.table_booking_no = "RAD-7"
    order.customer_name = "Patient A"
    order.counter_no = 1
    order.status = status_value
    order.registration_batch_id = "batch-1"
    order.utility = utility
    order.utility_id = utility_id
    order.vendor = vendor
    return order


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalManagerPatientMessageTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _call(self, body, manager_profile):
        from manager.hospital_views import manager_patient_message

        user = MagicMock()
        profiles = MagicMock()
        profiles.exists.return_value = True
        profiles.first.return_value = manager_profile
        user.profile_roles = profiles
        request = self.factory.post(
            "/hospital_flash/manager/api/manager_patient_message/",
            body,
            format="json",
        )
        force_authenticate(request, user=user)
        return manager_patient_message(request)

    def test_404_outside_hospital_flash(self):
        from manager import hospital_views

        with patch.object(hospital_views, "project_name", "dine_flash"):
            response = hospital_views._hospital_flash_only_response()
        self.assertEqual(response.status_code, 404)

    def test_manager_patient_message_404_for_other_flavours(self):
        from manager import hospital_views

        for flavour in ("dine_flash", "dine_flash_buffet", "food_flash", "airline_flash"):
            with patch.object(hospital_views, "project_name", flavour):
                response = self._call({"booking_id": 1, "message": "hi"}, MagicMock())
            self.assertEqual(response.status_code, 404, flavour)

    @patch("manager.hospital_views.threading.Thread")
    @patch("manager.hospital_views.ChatMessage.objects.create")
    @patch("manager.hospital_views.VendorLogoSerializer")
    @patch("manager.hospital_views.get_vendor_current_time")
    @patch("manager.hospital_views.get_vendor_business_day_range")
    @patch("manager.hospital_views.Order.objects")
    def test_outlet_manager_sends_message(
        self,
        mock_order_objects,
        mock_day_range,
        mock_current_time,
        mock_logo,
        mock_chat_create,
        mock_thread,
    ):
        from manager import hospital_views

        manager, vendor = _manager_profile(role="outlet_manager")
        booking = _booking(vendor)
        mock_day_range.return_value = ("start", "end")
        mock_current_time.return_value = SimpleNamespace(date=lambda: "2026-07-29")
        mock_logo.return_value.data = {"logo_url": "https://example.com/logo.png"}
        mock_order_objects.select_related.return_value.filter.return_value.first.return_value = booking
        chat = SimpleNamespace(id=99)
        mock_chat_create.return_value = chat
        mock_thread.return_value = MagicMock()

        with patch.object(hospital_views, "project_name", "hospital_flash"):
            response = self._call({"booking_id": 42, "message": "Please proceed to desk 2"}, manager)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message_id"], 99)
        self.assertEqual(response.data["payload"]["type"], hospital_views.HOSPITAL_MANAGER_PUSH_TYPE)
        self.assertEqual(response.data["payload"]["status"], "Please proceed to desk 2")
        mock_chat_create.assert_called_once()
        create_kwargs = mock_chat_create.call_args.kwargs
        self.assertEqual(create_kwargs["sender"], "manager")
        self.assertEqual(create_kwargs["booking_id"], 42)
        self.assertEqual(create_kwargs["message_text"], "Please proceed to desk 2")
        mock_thread.assert_called_once()

    @patch("manager.hospital_views.threading.Thread")
    @patch("manager.hospital_views.ChatMessage.objects.create")
    @patch("manager.hospital_views.VendorLogoSerializer")
    @patch("manager.hospital_views.get_vendor_current_time")
    @patch("manager.hospital_views.get_vendor_business_day_range")
    @patch("manager.hospital_views.Order.objects")
    def test_accepts_message_text_alias(
        self,
        mock_order_objects,
        mock_day_range,
        mock_current_time,
        mock_logo,
        mock_chat_create,
        mock_thread,
    ):
        from manager import hospital_views

        manager, vendor = _manager_profile()
        booking = _booking(vendor)
        mock_day_range.return_value = ("start", "end")
        mock_current_time.return_value = SimpleNamespace(date=lambda: "2026-07-29")
        mock_logo.return_value.data = {"logo_url": ""}
        mock_order_objects.select_related.return_value.filter.return_value.first.return_value = booking
        mock_chat_create.return_value = SimpleNamespace(id=5)
        mock_thread.return_value = MagicMock()

        with patch.object(hospital_views, "project_name", "hospital_flash"):
            response = self._call({"booking_id": 42, "message_text": "Alias works"}, manager)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["payload"]["status"], "Alias works")

    def test_rejects_empty_message(self):
        from manager import hospital_views

        manager, _ = _manager_profile()
        with patch.object(hospital_views, "project_name", "hospital_flash"):
            response = self._call({"booking_id": 42, "message": "   "}, manager)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_oversized_message(self):
        from manager import hospital_views

        manager, _ = _manager_profile()
        with patch.object(hospital_views, "project_name", "hospital_flash"):
            response = self._call({"booking_id": 42, "message": "x" * 201}, manager)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("manager.hospital_views.get_vendor_business_day_range", return_value=("start", "end"))
    @patch("manager.hospital_views.Order.objects")
    def test_department_user_forbidden_for_unassigned_dept(self, mock_order_objects, _day_range):
        from manager import hospital_views

        manager, vendor = _manager_profile(role="utility_user", utility_ids=[10])
        booking = _booking(vendor, utility_id=99)
        mock_order_objects.select_related.return_value.filter.return_value.first.return_value = booking

        with patch.object(hospital_views, "project_name", "hospital_flash"):
            response = self._call({"booking_id": 42, "message": "Hello"}, manager)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_patient_update_actions_unchanged(self):
        """Regression: status endpoint remains status-only."""
        from manager.hospital_views import HOSPITAL_STATUS_ACTIONS

        self.assertEqual(HOSPITAL_STATUS_ACTIONS, frozenset({"called", "completed", "cancelled"}))
        self.assertNotIn("message", HOSPITAL_STATUS_ACTIONS)
