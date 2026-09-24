from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from vendors.buffet_staff_username import build_buffet_internal_username
from vendors.models import AdminOutlet, AndroidAPK, UserProfile, Utility, Vendor, VendorConfig


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetStaffUsernameTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin_a = User.objects.create_user(
            username="buffet_admin_a", password="pass1234", is_staff=True
        )
        self.outlet_a = AdminOutlet.objects.create(
            user=self.admin_a,
            customer_name="Buffet Co A",
            customer_id=472,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor_a = Vendor.objects.create(
            admin_outlet=self.outlet_a,
            name="Buffet Branch A",
            alias_name="BA",
            location="Floor 1",
            vendor_id=100001,
            location_id="L-A",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor_a)
        self.utility_a = Utility.objects.create(
            vendor=self.vendor_a,
            utility_name="Kitchen",
            display_name="Kitchen",
            display_code="KT",
        )

        self.admin_b = User.objects.create_user(
            username="buffet_admin_b", password="pass1234", is_staff=True
        )
        self.outlet_b = AdminOutlet.objects.create(
            user=self.admin_b,
            customer_name="Buffet Co B",
            customer_id=815,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor_b = Vendor.objects.create(
            admin_outlet=self.outlet_b,
            name="Buffet Branch B",
            alias_name="BB",
            location="Floor 2",
            vendor_id=100002,
            location_id="L-B",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor_b)

        self.create_url = reverse("company:create_user")
        self.get_users_url = reverse("company:get_users")
        self.manager_login_url = reverse("buffet_outlet_manager_login")
        self.utility_login_url = reverse("buffet_utility_login")

    def _create_staff_payload(
        self, customer_id, vendor_id, username="ram", password="secret123", role="outlet_manager"
    ):
        return {
            "name": f"Staff {username}",
            "username": username,
            "password": password,
            "confirm_password": password,
            "role": role,
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

        user_a = User.objects.get(username=build_buffet_internal_username(self.outlet_a.id, "ram"))
        user_b = User.objects.get(username=build_buffet_internal_username(self.outlet_b.id, "ram"))
        self.assertNotEqual(user_a.username, user_b.username)
        self.assertTrue(user_a.username.startswith("bf:"))
        self.assertTrue(user_b.username.startswith("bf:"))

    def test_legacy_raw_user_blocks_same_company_create(self):
        legacy_user = User.objects.create_user(username="ram", password="legacy123")
        UserProfile.objects.create(
            user=legacy_user,
            name="Legacy Ram",
            role="outlet_manager",
            admin_outlet=self.outlet_a,
            vendor=self.vendor_a,
        )
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_user_response_returns_business_username(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="jay"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()["username"], "jay")
        self.assertNotIn("bf:", resp.json()["username"])

    def test_users_list_returns_business_username(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id),
            format="json",
        )
        resp = self.client.get(self.get_users_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in resp.json()["users"]]
        self.assertIn("ram", usernames)
        self.assertFalse(any(u.startswith("bf:") for u in usernames))

    def test_users_list_returns_legacy_username_unchanged(self):
        legacy_user = User.objects.create_user(username="ram", password="legacy123")
        UserProfile.objects.create(
            user=legacy_user,
            name="Legacy Ram",
            role="outlet_manager",
            admin_outlet=self.outlet_a,
            vendor=self.vendor_a,
        )
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.get(self.get_users_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in resp.json()["users"]]
        self.assertIn("ram", usernames)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_legacy_outlet_manager_login(self):
        legacy_user = User.objects.create_user(username="ram", password="legacy123")
        profile = UserProfile.objects.create(
            user=legacy_user,
            name="Legacy Ram",
            role="outlet_manager",
            admin_outlet=self.outlet_a,
            vendor=self.vendor_a,
        )
        resp = self.client.post(
            self.manager_login_url,
            {"username": "ram", "password": "legacy123", "customer_id": 472},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["user"]["username"], "ram")
        self.assertEqual(resp.json()["user"]["manager_id"], profile.id)
        self.assertIn("access", resp.json())
        self.assertIn("refresh", resp.json())

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_prefixed_outlet_manager_login_returns_business_username(self):
        self.client.force_authenticate(user=self.admin_a)
        create_resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, username="jay"),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        internal = build_buffet_internal_username(self.outlet_a.id, "jay")
        self.assertTrue(User.objects.filter(username=internal).exists())

        self.client.logout()
        resp = self.client.post(
            self.manager_login_url,
            {"username": "jay", "password": "secret123", "customer_id": 472},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["user"]["username"], "jay")
        self.assertNotIn("bf:", resp.json()["user"]["username"])
        self.assertEqual(resp.json()["user"]["role"], "Outlet Manager")
        self.assertIn("access", resp.json())

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_company_isolation_on_outlet_manager_login(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a.id, password="secretA"),
            format="json",
        )
        self.client.force_authenticate(user=self.admin_b)
        self.client.post(
            self.create_url,
            self._create_staff_payload(815, self.vendor_b.id, password="secretB"),
            format="json",
        )
        self.client.logout()

        wrong_company = self.client.post(
            self.manager_login_url,
            {"username": "ram", "password": "secretA", "customer_id": 815},
            format="json",
        )
        self.assertEqual(wrong_company.status_code, status.HTTP_401_UNAUTHORIZED)

        right_company = self.client.post(
            self.manager_login_url,
            {"username": "ram", "password": "secretB", "customer_id": 815},
            format="json",
        )
        self.assertEqual(right_company.status_code, status.HTTP_200_OK)
        self.assertEqual(right_company.json()["user"]["customer_id"], 815)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_prefixed_utility_login_contract(self):
        self.client.force_authenticate(user=self.admin_a)
        create_resp = self.client.post(
            self.create_url,
            self._create_staff_payload(
                472, self.vendor_a.id, username="kitchen", role="utility_user"
            ),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(
            username=build_buffet_internal_username(self.outlet_a.id, "kitchen")
        )
        profile = UserProfile.objects.get(user=user, role="utility_user")
        profile.assigned_utilities.add(self.utility_a)
        AndroidAPK.objects.create(
            token="old-token",
            apk_version="1.0.0",
            mac_address="AA:BB:CC:DD:EE:01",
            admin_outlet=self.outlet_a,
            user_profile=profile,
        )
        self.client.logout()

        resp = self.client.post(
            self.utility_login_url,
            {
                "username": "kitchen",
                "password": "secret123",
                "customer_id": 472,
                "mac_address": "AA:BB:CC:DD:EE:01",
                "token": "fcm-token",
                "apk_version": "1.0.5",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["message"], "Utility login processed.")
        self.assertTrue(body["device_approved"])
        self.assertTrue(body["utility_mapped"])
        self.assertEqual(body["user"]["username"], "kitchen")
        self.assertNotIn("bf:", body["user"]["username"])
        self.assertEqual(body["user"]["role"], "Utility User")
        self.assertEqual(body["user"]["manager_id"], profile.id)
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertIn("possible_statuses", body)

    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_legacy_utility_login(self):
        legacy_user = User.objects.create_user(username="kitchen_login", password="secret123")
        profile = UserProfile.objects.create(
            user=legacy_user,
            name="Kitchen Login",
            role="utility_user",
            admin_outlet=self.outlet_a,
            vendor=self.vendor_a,
        )
        profile.assigned_utilities.add(self.utility_a)
        AndroidAPK.objects.create(
            token="old-token",
            apk_version="1.0.0",
            mac_address="AA:BB:CC:DD:EE:02",
            admin_outlet=self.outlet_a,
            user_profile=profile,
        )
        resp = self.client.post(
            self.utility_login_url,
            {
                "username": "kitchen_login",
                "password": "secret123",
                "customer_id": 472,
                "mac_address": "AA:BB:CC:DD:EE:02",
                "token": "fcm-token-2",
                "apk_version": "1.0.5",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["user"]["username"], "kitchen_login")
        self.assertEqual(resp.json()["user"]["manager_id"], profile.id)

    @patch("manager.buffet_views.project_name", "dine_flash_buffet")
    @patch("orders.buffet_views.project_name", "dine_flash_buffet")
    def test_jwt_access_to_assigned_utilities(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(
                472, self.vendor_a.id, username="jwtuser", role="utility_user"
            ),
            format="json",
        )
        user = User.objects.get(
            username=build_buffet_internal_username(self.outlet_a.id, "jwtuser")
        )
        profile = UserProfile.objects.get(user=user, role="utility_user")
        profile.assigned_utilities.add(self.utility_a)
        AndroidAPK.objects.create(
            token="old-token",
            apk_version="1.0.0",
            mac_address="AA:BB:CC:DD:EE:03",
            admin_outlet=self.outlet_a,
            user_profile=profile,
        )
        self.client.logout()

        login_resp = self.client.post(
            self.utility_login_url,
            {
                "username": "jwtuser",
                "password": "secret123",
                "customer_id": 472,
                "mac_address": "AA:BB:CC:DD:EE:03",
                "token": "fcm-token-3",
                "apk_version": "1.0.5",
            },
            format="json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        token = login_resp.json()["access"]

        jwt_client = APIClient()
        jwt_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        assigned = jwt_client.get(reverse("manager:buffet_assigned_utilities"))
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        self.assertEqual(assigned.json()["user"]["manager_id"], profile.id)

    def test_company_admin_login_remains_raw(self):
        resp = self.client.post(
            reverse("login_api_view"),
            {"username": "buffet_admin_a", "password": "pass1234"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["user"]["role"], "Company")


@override_settings(PROJECT_NAME="dine_flash")
class NonBuffetStaffCreationUnchangedTests(TestCase):
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
        self.assertFalse(
            User.objects.filter(username=build_buffet_internal_username(self.outlet.id, "shared")).exists()
        )


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalUsernamePrefixUnchangedByBuffetHelpersTests(TestCase):
    def test_hospital_create_still_uses_hf_prefix(self):
        from vendors.hospital_staff_username import build_internal_username

        admin = User.objects.create_user(username="hfadmin", password="pass1234", is_staff=True)
        outlet = AdminOutlet.objects.create(
            user=admin,
            customer_name="Hospital Co",
            customer_id=300,
        )
        vendor = Vendor.objects.create(
            admin_outlet=outlet,
            name="Hospital Outlet",
            vendor_id=300001,
            location_id="H1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=vendor)
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.post(
            reverse("company:create_user"),
            {
                "name": "Dept User",
                "username": "ram",
                "password": "secret123",
                "confirm_password": "secret123",
                "role": "utility_user",
                "customer_id": 300,
                "vendor_id": vendor.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username=build_internal_username(outlet.id, "ram")).exists())
        self.assertFalse(
            User.objects.filter(username=build_buffet_internal_username(outlet.id, "ram")).exists()
        )
