"""
Buffet Outlet Manager login API tests.

Covers the dedicated dine_flash_buffet outlet-manager login endpoint.
Does not modify Kitchen/utility-login behavior.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from vendors.models import AdminOutlet, UserProfile, Vendor, VendorConfig


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetOutletManagerLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse("buffet_outlet_manager_login")

        self.company_user = User.objects.create_user(
            username="buffet_company_a", password="pass1234", is_staff=True
        )
        self.admin_outlet = AdminOutlet.objects.create(
            user=self.company_user,
            customer_name="Buffet Co A",
            customer_id=96001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Outlet A",
            alias_name="OA",
            location="Floor 1",
            vendor_id=960001,
            location_id="BA1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)

        self.manager_user = User.objects.create_user(
            username="outlet_mgr", password="secret123"
        )
        self.manager_profile = UserProfile.objects.create(
            user=self.manager_user,
            name="Outlet Manager A",
            role="outlet_manager",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
        )

        other_company_user = User.objects.create_user(
            username="buffet_company_b", password="pass1234", is_staff=True
        )
        self.other_outlet = AdminOutlet.objects.create(
            user=other_company_user,
            customer_name="Buffet Co B",
            customer_id=96002,
            authentication_status="Approve",
        )
        self.other_vendor = Vendor.objects.create(
            admin_outlet=self.other_outlet,
            name="Outlet B",
            alias_name="OB",
            location="Floor 2",
            vendor_id=960002,
            location_id="BB1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.other_vendor)

    def _payload(self, **overrides):
        data = {
            "username": "outlet_mgr",
            "password": "secret123",
            "customer_id": self.admin_outlet.customer_id,
        }
        data.update(overrides)
        return data

    def _post(self, payload=None):
        return self.client.post(self.url, payload or self._payload(), format="json")

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_successful_login_returns_tokens_and_manager_info(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["message"], "Login successful")
        self.assertTrue(body["access"])
        self.assertTrue(body["refresh"])
        user_payload = body["user"]
        self.assertEqual(user_payload["username"], "outlet_mgr")
        self.assertEqual(user_payload["role"], "Outlet Manager")
        self.assertEqual(user_payload["manager_id"], self.manager_profile.id)
        self.assertEqual(user_payload["manager_name"], "Outlet Manager A")
        self.assertEqual(user_payload["vendor_id"], self.vendor.id)
        self.assertEqual(user_payload["vendor_name"], self.vendor.name)
        self.assertEqual(user_payload["customer_id"], self.admin_outlet.customer_id)
        self.assertEqual(user_payload["outlet_name"], self.admin_outlet.customer_name)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_successful_login_without_android_apk(self):
        # Device registration is intentionally not part of this login.
        from vendors.models import AndroidAPK

        self.assertFalse(AndroidAPK.objects.exists())
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.json())
        self.assertFalse(AndroidAPK.objects.exists())

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_invalid_password_rejected(self):
        resp = self._post(self._payload(password="wrong-password"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.json()["error"], "Invalid username or password.")

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_missing_username_rejected(self):
        resp = self._post(self._payload(username=""))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", resp.json()["error"])

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_missing_password_rejected(self):
        resp = self._post(self._payload(password=""))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", resp.json()["error"])

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_missing_customer_id_rejected(self):
        resp = self._post(self._payload(customer_id=""))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("customer_id", resp.json()["error"])

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_invalid_customer_id_rejected(self):
        resp = self._post(self._payload(customer_id=999999))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.json()["error"], "Invalid customer_id.")

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_wrong_company_rejected(self):
        resp = self._post(self._payload(customer_id=self.other_outlet.customer_id))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            resp.json()["error"],
            "Outlet manager does not belong to this customer.",
        )

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_utility_user_role_rejected(self):
        utility_user = User.objects.create_user(
            username="kitchen_user", password="secret123"
        )
        UserProfile.objects.create(
            user=utility_user,
            name="Kitchen User",
            role="utility_user",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
        )
        resp = self._post(
            self._payload(username="kitchen_user", password="secret123")
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            resp.json()["error"],
            "This user does not have the 'outlet_manager' role.",
        )

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_other_non_outlet_manager_roles_rejected(self):
        for role, username in (
            ("admin_manager", "admin_mgr"),
            ("order_manager", "order_mgr"),
            ("outlet_staff", "outlet_staff"),
        ):
            user = User.objects.create_user(username=username, password="secret123")
            UserProfile.objects.create(
                user=user,
                name=username,
                role=role,
                admin_outlet=self.admin_outlet,
                vendor=self.vendor,
            )
            resp = self._post(self._payload(username=username, password="secret123"))
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, role)
            self.assertEqual(
                resp.json()["error"],
                "This user does not have the 'outlet_manager' role.",
            )

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_outlet_manager_without_vendor_rejected(self):
        self.manager_profile.vendor = None
        self.manager_profile.save(update_fields=["vendor"])
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("not mapped to any vendor", resp.json()["error"])

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_vendor_company_mismatch_rejected(self):
        self.manager_profile.vendor = self.other_vendor
        self.manager_profile.save(update_fields=["vendor"])
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(
            "vendor does not belong to this customer",
            resp.json()["error"],
        )

    @patch("orders.buffet_views.project_name", "food_flash")
    def test_non_buffet_project_returns_404(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.json()["error"], "Not found.")

    @patch("orders.buffet_views.project_name", "dine_flash")
    def test_dine_flash_flavour_unchanged(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.buffet_views.project_name", "hospital_flash")
    def test_hospital_flash_flavour_unchanged(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("orders.buffet_views.project_name", "airline_flash")
    def test_airline_flash_flavour_unchanged(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetUtilityLoginRegressionTests(TestCase):
    """Confirm Kitchen utility-login still requires device fields and is untouched."""

    def setUp(self):
        self.client = APIClient()
        self.url = reverse("buffet_utility_login")
        company_user = User.objects.create_user(
            username="utility_company", password="pass1234", is_staff=True
        )
        self.admin_outlet = AdminOutlet.objects.create(
            user=company_user,
            customer_name="Utility Co",
            customer_id=97001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Kitchen Outlet",
            vendor_id=970001,
            location_id="KU1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)
        self.utility_user = User.objects.create_user(
            username="kitchen_login", password="secret123"
        )
        UserProfile.objects.create(
            user=self.utility_user,
            name="Kitchen Login",
            role="utility_user",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
        )

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_utility_login_still_requires_device_fields(self):
        resp = self.client.post(
            self.url,
            {
                "username": "kitchen_login",
                "password": "secret123",
                "customer_id": self.admin_outlet.customer_id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.json()["error"]
        self.assertIn("mac_address", error)
        self.assertIn("token", error)
        self.assertIn("apk_version", error)
