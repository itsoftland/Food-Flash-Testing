"""
Hospital Flash Outlet Manager create-order unit tests.

Cross-flavour guard: exercises manager.hospital_views.hospital_create_order only.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from orders.hospital.order_create import HospitalOrderCreateStatus


def _manager_profile(role="outlet_manager", vendor_id="H1"):
    vendor = SimpleNamespace(
        id=1,
        name="City Hospital",
        alias_name="City Hospital",
        vendor_id=vendor_id,
        location_id="L1",
        config=SimpleNamespace(use_utilities=True),
    )
    profile = MagicMock()
    profile.id = 55
    profile.role = role
    profile.name = "Mgr"
    profile.vendor = vendor
    profile.vendor_id = vendor.id
    return profile, vendor


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalCreateOrderManagerTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _call(self, body, manager_profile):
        from manager import hospital_views
        from manager.hospital_views import hospital_create_order

        user = MagicMock()
        profiles = MagicMock()
        profiles.exists.return_value = True
        profiles.first.return_value = manager_profile
        user.profile_roles = profiles
        user.username = "mgr"
        request = self.factory.post(
            "/hospital_flash/manager/api/hospital_create_order/",
            body,
            format="json",
        )
        force_authenticate(request, user=user)
        with patch.object(hospital_views, "project_name", "hospital_flash"):
            return hospital_create_order(request)

    def test_404_outside_hospital_flash(self):
        from manager import hospital_views
        from manager.hospital_views import hospital_create_order

        manager, _vendor = _manager_profile()
        user = MagicMock()
        profiles = MagicMock()
        profiles.exists.return_value = True
        profiles.first.return_value = manager
        user.profile_roles = profiles
        request = self.factory.post(
            "/hospital_flash/manager/api/hospital_create_order/",
            {"customer_name": "Pat", "utility_ids": [1]},
            format="json",
        )
        force_authenticate(request, user=user)
        with patch.object(hospital_views, "project_name", "dine_flash"):
            response = hospital_create_order(request)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rejects_department_user(self):
        manager, _vendor = _manager_profile(role="utility_user")
        response = self._call(
            {"customer_name": "Pat", "utility_ids": [1]},
            manager,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Department users", response.data["message"])

    def test_rejects_unexpected_role(self):
        manager, _vendor = _manager_profile(role="web_user")
        response = self._call(
            {"customer_name": "Pat", "utility_ids": [1]},
            manager,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["message"], "You are not authorized to create orders.")

    @patch("manager.hospital_views.create_hospital_orders")
    @patch("manager.hospital_views.Vendor.objects")
    def test_admin_manager_allowed(self, mock_vendor_qs, mock_create):
        manager, vendor = _manager_profile(role="admin_manager")
        mock_vendor_qs.select_related.return_value.filter.return_value.first.return_value = vendor
        batch = UUID("33333333-3333-3333-3333-333333333333")
        mock_create.return_value = SimpleNamespace(
            status=HospitalOrderCreateStatus.CREATED,
            vendor=vendor,
            customer_name="Pat",
            registration_batch_id=batch,
            departments=[
                {
                    "order_id": 1,
                    "utility_id": 4,
                    "department_name": "Lab",
                    "display_code": "LAB",
                    "token": "LAB-1",
                    "token_no": 1,
                    "registration_batch_id": str(batch),
                }
            ],
        )
        response = self._call(
            {"customer_name": "Pat", "utility_ids": [4]},
            manager,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_create.call_args.kwargs["updated_by"], "manager")

    @patch("manager.hospital_views.create_hospital_orders")
    @patch("manager.hospital_views.Vendor.objects")
    def test_vendor_id_mismatch_forbidden(self, mock_vendor_qs, mock_create):
        manager, vendor = _manager_profile(vendor_id="H1")
        mock_vendor_qs.select_related.return_value.filter.return_value.first.return_value = vendor

        response = self._call(
            {
                "vendor_id": "OTHER",
                "customer_name": "Pat",
                "utility_ids": [1],
            },
            manager,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("does not match", response.data["error"])
        mock_create.assert_not_called()

    @patch("manager.hospital_views.create_hospital_orders")
    @patch("manager.hospital_views.Vendor.objects")
    def test_success_attributes_manager(self, mock_vendor_qs, mock_create):
        manager, vendor = _manager_profile()
        mock_vendor_qs.select_related.return_value.filter.return_value.first.return_value = vendor
        batch = UUID("22222222-2222-2222-2222-222222222222")
        departments = [
            {
                "order_id": 11,
                "utility_id": 4,
                "department_name": "Ortho",
                "display_code": "ORT",
                "token": "ORT-2",
                "token_no": 2,
                "registration_batch_id": str(batch),
            }
        ]
        mock_create.return_value = SimpleNamespace(
            status=HospitalOrderCreateStatus.CREATED,
            vendor=vendor,
            customer_name="Pat",
            registration_batch_id=batch,
            departments=departments,
        )

        response = self._call(
            {
                "vendor_id": "H1",
                "customer_name": "Pat",
                "utility_ids": [4],
                "phone_number": "999",
            },
            manager,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["message"],
            "Patient registered successfully by manager.",
        )
        self.assertEqual(response.data["manager_id"], 55)
        self.assertEqual(response.data["departments"], departments)
        self.assertIn("tracking_url", response.data)

        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["updated_by"], "manager")
        self.assertIs(kwargs["user_profile"], manager)
        self.assertEqual(kwargs["vendor"], vendor)
        self.assertEqual(kwargs["phone_number"], "999")
