from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from vendors.models import AdminOutlet, UserProfile, Vendor, VendorConfig
from vendors.hospital_staff_username import build_internal_username


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalStaffUsernameTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin_a = User.objects.create_user(username="admin_a", password="pass1234", is_staff=True)
        self.outlet_a = AdminOutlet.objects.create(
            user=self.admin_a,
            customer_name="CityCare Hospital",
            customer_id=472,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor_a = Vendor.objects.create(
            admin_outlet=self.outlet_a,
            name="CityCare Branch",
            alias_name="CC",
            location="Block A",
            vendor_id=100001,
            location_id="L-A",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor_a)

        self.admin_b = User.objects.create_user(username="admin_b", password="pass1234", is_staff=True)
        self.outlet_b = AdminOutlet.objects.create(
            user=self.admin_b,
            customer_name="Vinod Hospital",
            customer_id=815,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor_b = Vendor.objects.create(
            admin_outlet=self.outlet_b,
            name="Vinod Branch",
            alias_name="VB",
            location="Block B",
            vendor_id=100002,
            location_id="L-B",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor_b)

        self.create_url = reverse("company:create_user")
        self.login_url = reverse("login_api_view")
        self.get_users_url = reverse("company:get_users")

    def _create_staff_payload(self, customer_id, vendor_id, username="ram", password="secret123"):
        return {
            "name": f"Staff {username}",
            "username": username,
            "password": password,
            "confirm_password": password,
            "role": "utility_user",
            "customer_id": customer_id,
            "vendor_id": vendor_id,
        }

    def test_same_username_same_company_rejected(self):
        self.client.force_authenticate(user=self.admin_a)
        payload = self._create_staff_payload(472, self.vendor_a.id)
        first = self.client.post(self.create_url, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(self.create_url, payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", second.json())

    def test_same_username_different_companies_allowed(self):
        self.client.force_authenticate(user=self.admin_a)
        resp_a = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id),
            format="json",
        )
        self.assertEqual(resp_a.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.admin_b)
        resp_b = self.client.post(
            self.create_url,
            self._create_staff_payload(815, self.vendor_b.id),
            format="json",
        )
        self.assertEqual(resp_b.status_code, status.HTTP_201_CREATED)

        user_a = User.objects.get(username=build_internal_username(self.outlet_a.id, "ram"))
        user_b = User.objects.get(username=build_internal_username(self.outlet_b.id, "ram"))
        self.assertNotEqual(user_a.username, user_b.username)

    def test_legacy_user_login(self):
        legacy_user = User.objects.create_user(username="ram", password="legacy123")
        UserProfile.objects.create(
            user=legacy_user,
            name="Legacy Ram",
            role="utility_user",
            admin_outlet=self.outlet_a,
            vendor=self.vendor_a,
        )

        resp = self.client.post(
            self.login_url,
            {
                "username": "ram",
                "password": "legacy123",
                "role": "utility_user",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["user"]["username"], "ram")

    def test_new_prefixed_user_login(self):
        self.client.force_authenticate(user=self.admin_a)
        create_resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="jay"),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        internal = build_internal_username(self.outlet_a.id, "jay")
        self.assertTrue(User.objects.filter(username=internal).exists())

        self.client.logout()
        login_resp = self.client.post(
            self.login_url,
            {
                "username": "jay",
                "password": "secret123",
                "role": "utility_user",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)

    def test_wrong_password_fails(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="jay"),
            format="json",
        )
        self.client.logout()

        resp = self.client.post(
            self.login_url,
            {
                "username": "jay",
                "password": "wrong-password",
                "role": "utility_user",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_response_returns_business_username(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="jay"),
            format="json",
        )
        self.client.logout()

        resp = self.client.post(
            self.login_url,
            {
                "username": "jay",
                "password": "secret123",
                "role": "utility_user",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["user"]["username"], "jay")
        self.assertNotIn("hf:", data["user"]["username"])
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertIn("manager_id", data["user"])

    def test_users_list_returns_business_username_for_prefixed_user(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="ram"),
            format="json",
        )

        resp = self.client.get(self.get_users_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in resp.json()["users"]]
        self.assertIn("ram", usernames)
        self.assertFalse(any(u.startswith("hf:") for u in usernames))

    def test_users_list_returns_legacy_username_unchanged(self):
        legacy_user = User.objects.create_user(username="ram", password="legacy123")
        UserProfile.objects.create(
            user=legacy_user,
            name="Legacy Ram",
            role="admin_manager",
            admin_outlet=self.outlet_a,
        )

        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.get(self.get_users_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in resp.json()["users"]]
        self.assertIn("ram", usernames)

    def test_create_user_response_returns_business_username(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="ram"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["username"], "ram")

    def test_jwt_access_to_protected_endpoint(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="jwtuser"),
            format="json",
        )
        self.client.logout()

        login_resp = self.client.post(
            self.login_url,
            {
                "username": "jwtuser",
                "password": "secret123",
                "role": "utility_user",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        token = login_resp.json()["access"]

        jwt_client = APIClient()
        jwt_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        booking_resp = jwt_client.get(reverse("manager:get_booking_list"))
        self.assertEqual(booking_resp.status_code, status.HTTP_200_OK)

    def test_hospital_login_requires_customer_id(self):
        resp = self.client.post(
            self.login_url,
            {
                "username": "jay",
                "password": "secret123",
                "role": "utility_user",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(PROJECT_NAME="dine_flash")
class NonHospitalStaffCreationUnchangedTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username="dfadmin", password="pass1234", is_staff=True)
        self.outlet = AdminOutlet.objects.create(
            user=self.admin,
            customer_name="Dine Co",
            customer_id=200,
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.outlet,
            name="Dine Outlet",
            vendor_id=200001,
            location_id="L1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)
        self.client.force_authenticate(user=self.admin)

    def test_global_username_uniqueness_still_applies(self):
        User.objects.create_user(username="shared", password="p1")
        resp = self.client.post(
            reverse("company:create_user"),
            {
                "name": "Staff",
                "username": "shared",
                "password": "secret123",
                "confirm_password": "secret123",
                "role": "utility_user",
                "customer_id": 200,
                "vendor_id": self.vendor.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
