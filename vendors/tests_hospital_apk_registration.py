"""
Hospital Flash APK registration reuse tests.

Hospital Department Users (role=utility_user) reuse the existing
register_android_apk() Buffet utility_user path.

These tests call the real view with mocked ORM so they run without a
MySQL CREATE DATABASE privilege (local hospital_flash_user limitation).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory

from vendors.views import register_android_apk


def _admin_outlet(customer_id=91001):
    return SimpleNamespace(id=1, customer_id=customer_id)


def _utility_user(admin_outlet, user_id=42):
    vendor = SimpleNamespace(id=7, name="City Hospital")
    return SimpleNamespace(
        id=user_id,
        name="Radiology Desk",
        role="utility_user",
        admin_outlet=admin_outlet,
        vendor=vendor,
    )


def _device(*, admin_outlet, user_profile=None, token="old-token", apk_version="0.9.0"):
    device = MagicMock()
    device.admin_outlet = admin_outlet
    device.user_profile = user_profile
    device.token = token
    device.apk_version = apk_version
    device.mac_address = "AA:BB:CC:DD:EE:01"
    device.save = MagicMock()
    return device


class _ApkRegistrationViewMixin:
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin_outlet = _admin_outlet()
        self.utility_user = _utility_user(self.admin_outlet)
        self.config_payload = {
            "phone_number_enabled": True,
            "utilities_enabled": True,
        }

    def _post(self, payload):
        request = self.factory.post(
            "/vendors/api/register_android_apk/",
            payload,
            format="json",
        )
        return register_android_apk(request)

    def _payload(self, **overrides):
        data = {
            "token": "fcm-token-hospital-1",
            "customer_id": self.admin_outlet.customer_id,
            "mac_address": "AA:BB:CC:DD:EE:01",
            "apk_version": "1.0.0",
            "manager_id": self.utility_user.id,
        }
        data.update(overrides)
        return data


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalUtilityApkRegistrationTests(_ApkRegistrationViewMixin, SimpleTestCase):
    @patch("vendors.views.build_vendor_config_payload")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_hospital_utility_user_registration_succeeds(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs, mock_config
    ):
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.return_value = self.utility_user
        mock_apk_qs.filter.return_value.first.return_value = None
        created = _device(admin_outlet=self.admin_outlet, user_profile=self.utility_user)
        mock_apk_qs.create.return_value = created
        mock_config.return_value = self.config_payload

        response = self._post(self._payload())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mapped"])
        self.assertEqual(response.data["manager_id"], self.utility_user.id)
        self.assertEqual(response.data["manager_name"], "Radiology Desk")
        self.assertEqual(response.data["config"], self.config_payload)
        mock_apk_qs.create.assert_called_once_with(
            token="fcm-token-hospital-1",
            mac_address="AA:BB:CC:DD:EE:01",
            apk_version="1.0.0",
            admin_outlet=self.admin_outlet,
            user_profile=self.utility_user,
        )
        # utility_user must be in allowed roles for hospital_flash
        _, kwargs = mock_profile_qs.get.call_args
        self.assertIn("utility_user", kwargs["role__in"])

    @patch("vendors.views.build_vendor_config_payload")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_hospital_utility_user_apk_update_succeeds(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs, mock_config
    ):
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.return_value = self.utility_user
        existing = _device(
            admin_outlet=self.admin_outlet,
            user_profile=self.utility_user,
        )
        mock_apk_qs.filter.return_value.first.return_value = existing
        mock_config.return_value = self.config_payload

        response = self._post(
            self._payload(token="fcm-token-updated", apk_version="1.1.0")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mapped"])
        self.assertEqual(response.data["manager_id"], self.utility_user.id)
        self.assertEqual(existing.token, "fcm-token-updated")
        self.assertEqual(existing.apk_version, "1.1.0")
        self.assertEqual(existing.user_profile, self.utility_user)
        existing.save.assert_called_once()
        mock_apk_qs.create.assert_not_called()

    @patch("vendors.views.build_vendor_config_payload")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_android_apk_user_profile_set_correctly(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs, mock_config
    ):
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.return_value = self.utility_user
        mock_apk_qs.filter.return_value.first.return_value = None
        created = _device(admin_outlet=self.admin_outlet, user_profile=self.utility_user)
        mock_apk_qs.create.return_value = created
        mock_config.return_value = self.config_payload

        response = self._post(self._payload())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        create_kwargs = mock_apk_qs.create.call_args.kwargs
        self.assertIs(create_kwargs["user_profile"], self.utility_user)
        self.assertEqual(create_kwargs["user_profile"].role, "utility_user")

    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_invalid_customer_rejected(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs
    ):
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = None

        response = self._post(self._payload(customer_id=999999))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "Customer not found.")
        mock_profile_qs.get.assert_not_called()
        mock_apk_qs.create.assert_not_called()

    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_invalid_role_rejected(self, mock_outlet_qs, mock_profile_qs, mock_apk_qs):
        from vendors.models import UserProfile

        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.side_effect = UserProfile.DoesNotExist

        response = self._post(self._payload(manager_id=999))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Invalid manager ID for this customer.")
        mock_apk_qs.create.assert_not_called()

    @patch("vendors.views.build_vendor_config_payload")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_hospital_utility_manager_id_alias_accepted(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs, mock_config
    ):
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.return_value = self.utility_user
        mock_apk_qs.filter.return_value.first.return_value = None
        created = _device(admin_outlet=self.admin_outlet, user_profile=self.utility_user)
        mock_apk_qs.create.return_value = created
        mock_config.return_value = self.config_payload

        payload = self._payload()
        payload.pop("manager_id")
        payload["utility_manager_id"] = self.utility_user.id
        response = self._post(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mapped"])
        mock_profile_qs.get.assert_called_once()
        self.assertEqual(mock_profile_qs.get.call_args.kwargs["id"], self.utility_user.id)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetUtilityApkRegistrationRegressionTests(_ApkRegistrationViewMixin, SimpleTestCase):
    @patch("vendors.views.build_vendor_config_payload")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_buffet_utility_user_registration_still_works(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs, mock_config
    ):
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.return_value = self.utility_user
        mock_apk_qs.filter.return_value.first.return_value = None
        created = _device(admin_outlet=self.admin_outlet, user_profile=self.utility_user)
        mock_apk_qs.create.return_value = created
        mock_config.return_value = self.config_payload

        response = self._post(self._payload())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mapped"])
        _, kwargs = mock_profile_qs.get.call_args
        self.assertIn("utility_user", kwargs["role__in"])
        self.assertIs(
            mock_apk_qs.create.call_args.kwargs["user_profile"], self.utility_user
        )

    @patch("vendors.views.build_vendor_config_payload")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_buffet_utility_manager_id_alias_still_works(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs, mock_config
    ):
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.return_value = self.utility_user
        mock_apk_qs.filter.return_value.first.return_value = None
        created = _device(admin_outlet=self.admin_outlet, user_profile=self.utility_user)
        mock_apk_qs.create.return_value = created
        mock_config.return_value = self.config_payload

        payload = self._payload()
        payload.pop("manager_id")
        payload["utility_manager_id"] = self.utility_user.id
        response = self._post(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["mapped"])


class NonHospitalFlavourApkRegistrationIsolationTests(_ApkRegistrationViewMixin, SimpleTestCase):
    """utility_user must remain rejected outside Buffet/Hospital flavours."""

    def _assert_utility_user_rejected(self, mock_outlet_qs, mock_profile_qs, mock_apk_qs):
        from vendors.models import UserProfile

        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.side_effect = UserProfile.DoesNotExist

        response = self._post(self._payload())

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Invalid manager ID for this customer.")
        _, kwargs = mock_profile_qs.get.call_args
        self.assertNotIn("utility_user", kwargs["role__in"])
        mock_apk_qs.create.assert_not_called()

    @override_settings(PROJECT_NAME="food_flash")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_food_flash_rejects_utility_user(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs
    ):
        self._assert_utility_user_rejected(mock_outlet_qs, mock_profile_qs, mock_apk_qs)

    @override_settings(PROJECT_NAME="dine_flash")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_dine_flash_rejects_utility_user(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs
    ):
        self._assert_utility_user_rejected(mock_outlet_qs, mock_profile_qs, mock_apk_qs)

    @override_settings(PROJECT_NAME="airline_flash")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_airline_flash_rejects_utility_user(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs
    ):
        self._assert_utility_user_rejected(mock_outlet_qs, mock_profile_qs, mock_apk_qs)

    @override_settings(PROJECT_NAME="food_flash")
    @patch("vendors.views.build_vendor_config_payload")
    @patch("vendors.views.AndroidAPK.objects")
    @patch("vendors.views.UserProfile.objects")
    @patch("vendors.views.AdminOutlet.objects")
    def test_food_flash_outlet_manager_still_registers_without_user_profile_link(
        self, mock_outlet_qs, mock_profile_qs, mock_apk_qs, mock_config
    ):
        """Non-utility flavours still accept managers but do not set user_profile on create."""
        outlet_manager = SimpleNamespace(
            id=11,
            name="Outlet Manager",
            role="outlet_manager",
            admin_outlet=self.admin_outlet,
            vendor=SimpleNamespace(id=7),
        )
        mock_outlet_qs.filter.return_value.order_by.return_value.first.return_value = (
            self.admin_outlet
        )
        mock_profile_qs.get.return_value = outlet_manager
        mock_apk_qs.filter.return_value.first.return_value = None
        created = _device(admin_outlet=self.admin_outlet, user_profile=None)
        mock_apk_qs.create.return_value = created
        mock_config.return_value = self.config_payload

        response = self._post(
            self._payload(manager_id=outlet_manager.id, mac_address="AA:BB:CC:DD:EE:99")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["mapped"])
        self.assertIsNone(mock_apk_qs.create.call_args.kwargs["user_profile"])
        _, kwargs = mock_profile_qs.get.call_args
        self.assertNotIn("utility_user", kwargs["role__in"])
        self.assertIn("outlet_manager", kwargs["role__in"])
