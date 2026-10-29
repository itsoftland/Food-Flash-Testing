from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from vendors.dine_flash_staff_username import build_dine_flash_internal_username
from vendors.models import AdminOutlet, UserProfile, Vendor, VendorConfig


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashStaffUsernameTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin_a = User.objects.create_user(username="admin_a", password="pass1234", is_staff=True)
        self.outlet_a = AdminOutlet.objects.create(
            user=self.admin_a,
            customer_name="Dine Co A",
            customer_id=472,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor_a1 = Vendor.objects.create(
            admin_outlet=self.outlet_a,
            name="Dine Branch A1",
            alias_name="A1",
            location="Floor 1",
            vendor_id=100001,
            location_id="L-A1",
            menus="[]",
        )
        self.vendor_a2 = Vendor.objects.create(
            admin_outlet=self.outlet_a,
            name="Dine Branch A2",
            alias_name="A2",
            location="Floor 2",
            vendor_id=100002,
            location_id="L-A2",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor_a1)
        VendorConfig.objects.create(vendor=self.vendor_a2)

        self.admin_b = User.objects.create_user(username="admin_b", password="pass1234", is_staff=True)
        self.outlet_b = AdminOutlet.objects.create(
            user=self.admin_b,
            customer_name="Dine Co B",
            customer_id=815,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor_b = Vendor.objects.create(
            admin_outlet=self.outlet_b,
            name="Dine Branch B",
            alias_name="B1",
            location="Block B",
            vendor_id=100003,
            location_id="L-B",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor_b)

        self.create_url = reverse("company:create_user")
        self.login_url = reverse("login_api_view")
        self.get_users_url = reverse("company:get_users")

    def _create_staff_payload(
        self, customer_id, vendor_id, username="ram", password="secret123", role="utility_user"
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

    def test_first_staff_username_creation_in_company(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        internal = build_dine_flash_internal_username(self.outlet_a.id, "ram")
        self.assertTrue(User.objects.filter(username=internal).exists())

    def test_same_business_username_different_companies_allowed(self):
        self.client.force_authenticate(user=self.admin_a)
        resp_a = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id),
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

        user_a = User.objects.get(username=build_dine_flash_internal_username(self.outlet_a.id, "ram"))
        user_b = User.objects.get(username=build_dine_flash_internal_username(self.outlet_b.id, "ram"))
        self.assertNotEqual(user_a.username, user_b.username)

    def test_duplicate_username_rejected_within_same_company(self):
        self.client.force_authenticate(user=self.admin_a)
        first = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id),
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id),
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        body = second.json()
        self.assertTrue(
            body == ["Username already exists."]
            or body.get("non_field_errors") == ["Username already exists."]
            or "Username already exists." in str(body)
        )

    def test_duplicate_username_rejected_across_vendors_same_company(self):
        self.client.force_authenticate(user=self.admin_a)
        first = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id),
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a2.id),
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_legacy_plain_username_login_with_customer_id(self):
        legacy_user = User.objects.create_user(username="ram", password="legacy123")
        UserProfile.objects.create(
            user=legacy_user,
            name="Legacy Ram",
            role="utility_user",
            admin_outlet=self.outlet_a,
            vendor=self.vendor_a1,
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

    def test_prefixed_account_login_with_business_username(self):
        self.client.force_authenticate(user=self.admin_a)
        create_resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="jay"),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)

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

    def test_wrong_company_id_rejected(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="jay"),
            format="json",
        )
        self.client.logout()

        resp = self.client.post(
            self.login_url,
            {
                "username": "jay",
                "password": "secret123",
                "role": "utility_user",
                "customer_id": 815,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", resp.json())

    def test_missing_customer_id_rejected(self):
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
        self.assertEqual(resp.json()["error"], "customer_id is required.")

    def test_invalid_customer_id_rejected(self):
        resp = self.client.post(
            self.login_url,
            {
                "username": "jay",
                "password": "secret123",
                "role": "utility_user",
                "customer_id": 999999,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_incorrect_requested_role_rejected(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="roleuser", role="utility_user"),
            format="json",
        )
        self.client.logout()

        resp = self.client.post(
            self.login_url,
            {
                "username": "roleuser",
                "password": "secret123",
                "role": "outlet_manager",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("outlet_manager", resp.json()["error"])

    def test_ambiguous_legacy_profiles_same_customer_id_rejected(self):
        outlet_twin = AdminOutlet.objects.create(
            user=User.objects.create_user(username="admin_a2", password="pass1234"),
            customer_name="Dine Co A Twin",
            customer_id=472,
        )
        legacy_user = User.objects.create_user(username="ambig", password="secret123")
        UserProfile.objects.create(
            user=legacy_user,
            name="Ambig One",
            role="utility_user",
            admin_outlet=self.outlet_a,
            vendor=self.vendor_a1,
        )
        UserProfile.objects.create(
            user=legacy_user,
            name="Ambig Two",
            role="utility_user",
            admin_outlet=outlet_twin,
            vendor=self.vendor_a2,
        )

        resp = self.client.post(
            self.login_url,
            {
                "username": "ambig",
                "password": "secret123",
                "role": "utility_user",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_single_profile_across_outlets_sharing_customer_id(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="multi"),
            format="json",
        )
        self.client.logout()

        AdminOutlet.objects.create(
            user=User.objects.create_user(username="admin_a3", password="pass1234"),
            customer_name="Dine Co A Twin",
            customer_id=472,
        )

        resp = self.client.post(
            self.login_url,
            {
                "username": "multi",
                "password": "secret123",
                "role": "utility_user",
                "customer_id": 472,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["user"]["username"], "multi")

    def test_login_response_username_unprefixed(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="jay"),
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
        self.assertNotIn("df:", data["user"]["username"])
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertIn("manager_id", data["user"])

    def test_create_user_duplicate_error_structure(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id),
            format="json",
        )
        dup = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id),
            format="json",
        )
        self.assertEqual(dup.status_code, status.HTTP_400_BAD_REQUEST)
        payload = dup.json()
        self.assertNotIn("username", payload)
        self.assertTrue(
            payload == ["Username already exists."]
            or payload.get("non_field_errors") == ["Username already exists."]
        )

    def test_successful_create_user_response_structure(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="ram"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertEqual(body["detail"], "User created successfully.")
        self.assertEqual(body["username"], "ram")
        self.assertEqual(body["role"], "utility_user")
        self.assertIn("vendor", body)
        self.assertIn("admin_outlet", body)

    def test_users_list_response_structure_and_business_username(self):
        self.client.force_authenticate(user=self.admin_a)
        self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="ram"),
            format="json",
        )
        resp = self.client.get(self.get_users_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["message"], "Users retrieved successfully.")
        self.assertIn("users", body)
        entry = next(u for u in body["users"] if u["username"] == "ram")
        self.assertIn("roles", entry)
        self.assertIn("id", entry)
        self.assertFalse(any(u["username"].startswith("df:") for u in body["users"]))

    def test_company_admin_login_unchanged(self):
        self.client.logout()
        resp = self.client.post(
            self.login_url,
            {"username": "admin_a", "password": "pass1234"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["user"]["role"], "Company")
        self.assertEqual(resp.json()["user"]["customer_id"], 472)

    def test_vendor_ownership_validation_rejects_foreign_vendor(self):
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_b.id),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vendor_id", resp.json())

    def test_duplicate_internal_username_integrity_error_returns_legacy_message(self):
        """Race-safe path: DB uniqueness conflict maps to existing Dashboard error text."""
        internal = build_dine_flash_internal_username(self.outlet_a.id, "raceuser")
        User.objects.create_user(username=internal, password="unused")
        self.client.force_authenticate(user=self.admin_a)
        resp = self.client.post(
            self.create_url,
            self._create_staff_payload(472, self.vendor_a1.id, username="raceuser"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        payload = resp.json()
        self.assertTrue(
            payload == ["Username already exists."]
            or payload.get("non_field_errors") == ["Username already exists."]
        )


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalFlashRegressionAfterDineFlashUsernameTests(TestCase):
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


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetFlashRegressionAfterDineFlashUsernameTests(TestCase):
    def test_buffet_create_still_uses_bf_prefix(self):
        from vendors.buffet_staff_username import build_buffet_internal_username

        admin = User.objects.create_user(username="bfadmin", password="pass1234", is_staff=True)
        outlet = AdminOutlet.objects.create(
            user=admin,
            customer_name="Buffet Co",
            customer_id=301,
        )
        vendor = Vendor.objects.create(
            admin_outlet=outlet,
            name="Buffet Outlet",
            vendor_id=301001,
            location_id="B1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=vendor)
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.post(
            reverse("company:create_user"),
            {
                "name": "Manager",
                "username": "ram",
                "password": "secret123",
                "confirm_password": "secret123",
                "role": "outlet_manager",
                "customer_id": 301,
                "vendor_id": vendor.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username=build_buffet_internal_username(outlet.id, "ram")).exists())
