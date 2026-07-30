"""
Hospital Flash order create service + customer adapter unit tests.

Cross-flavour guard: exercises orders.hospital.order_create and
orders.hospital_views.hospital_patient_submit only.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory

from orders.hospital.order_create import (
    HospitalOrderCreateStatus,
    build_hospital_remarks,
    expand_hospital_departments,
)


class BuildHospitalRemarksTests(SimpleTestCase):
    def test_mr_and_bill_and_extra(self):
        text = build_hospital_remarks("MR1", "B1", "note")
        self.assertEqual(text, "MR: MR1\nBill: B1\n\nnote")

    def test_empty_returns_none(self):
        self.assertIsNone(build_hospital_remarks(None, None, None))
        self.assertIsNone(build_hospital_remarks("", "  ", None))


class ExpandHospitalDepartmentsTests(SimpleTestCase):
    def test_expands_group_and_dedupes(self):
        from vendors.models import Utility

        ortho = SimpleNamespace(
            id=1,
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
            group_departments=MagicMock(all=lambda: []),
        )
        xray = SimpleNamespace(
            id=2,
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
            group_departments=MagicMock(all=lambda: []),
        )
        package = SimpleNamespace(
            id=10,
            department_type=Utility.DEPARTMENT_TYPE_GROUP,
            group_departments=MagicMock(all=lambda: [ortho, xray]),
        )
        # Select package then ortho again — ortho should appear once.
        expanded = expand_hospital_departments([package, ortho])
        self.assertEqual([d.id for d in expanded], [1, 2])


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalPatientSubmitAdapterTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def _post(self, body):
        from orders import hospital_views
        from orders.hospital_views import hospital_patient_submit

        request = self.factory.post(
            "/hospital_flash/api/hospital_patient_submit/",
            body,
            format="json",
        )
        with patch.object(hospital_views, "project_name", "hospital_flash"):
            return hospital_patient_submit(request)

    def test_404_outside_hospital_flash(self):
        from orders import hospital_views
        from orders.hospital_views import hospital_patient_submit

        request = self.factory.post(
            "/hospital_flash/api/hospital_patient_submit/",
            {"customer_name": "A", "utility_ids": [1]},
            format="json",
        )
        with patch.object(hospital_views, "project_name", "dine_flash"):
            response = hospital_patient_submit(request)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_requires_customer_name_before_vendor(self):
        response = self._post({"utility_ids": [1]})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "customer_name is required.")

    def test_requires_utility_ids(self):
        response = self._post({"customer_name": "Pat"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("utility_ids", response.data["error"])

    @patch("orders.hospital_views.create_hospital_orders")
    @patch("orders.hospital_views._resolve_vendor")
    def test_success_response_shape(self, mock_resolve, mock_create):
        vendor = SimpleNamespace(
            id=1,
            vendor_id="H1",
            location_id="L1",
            config=SimpleNamespace(use_utilities=True),
        )
        mock_resolve.return_value = (vendor, None)
        batch = UUID("11111111-1111-1111-1111-111111111111")
        departments = [
            {
                "order_id": 9,
                "utility_id": 3,
                "department_name": "Lab",
                "display_code": "LAB",
                "token": "LAB-1",
                "token_no": 1,
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

        response = self._post(
            {
                "vendor_id": "H1",
                "customer_name": "Pat",
                "utility_ids": [3],
                "mr_number": "M1",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["message"], "Patient registered successfully.")
        self.assertEqual(response.data["registration_batch_id"], str(batch))
        self.assertEqual(response.data["patient_name"], "Pat")
        self.assertEqual(response.data["departments"], departments)
        self.assertIn("tracking_url", response.data)
        self.assertIn("registration_batch_id=", response.data["tracking_url"])

        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["updated_by"], "customer")
        self.assertIsNone(kwargs["user_profile"])
        self.assertEqual(kwargs["mr_number"], "M1")
