"""Licence sync endpoint api/company-update/ (orders.views.update_admin_outlet).

Allowed: Super Admin (any company), Company Admin (own company), legacy Outlet (own company).
Writable: licence fields only — never customer_email, contact fields or user.
The UI payload (productAuthService.js updateCompanyInfo) and response must keep working unchanged.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from orders.serializers import AdminOutletSerializer
from vendors.models import AdminOutlet, UserProfile, Vendor


def licence_payload(customer_id, **extra):
    """Exactly the keys productAuthService.updateCompanyInfo sends."""
    payload = {
        "authentication_status": "Approve",
        "product_registration_id": 42,
        "unique_identifier": "UID-42",
        "customer_id": customer_id,
        "product_from_date": "2026-01-01T00:00:00Z",
        "product_to_date": "2027-01-01T00:00:00Z",
        "total_count": "12",
        "project_code": "DF",
        "web_login_count": 3,
        "android_tv_count": 2,
        "android_apk_count": 4,
        "keypad_device_count": 1,
        "led_display_count": 0,
        "outlet_count": 6,
        "locations": [{"name": "Kochi"}],
        "displaymode": 2,
    }
    payload.update(extra)
    return payload


class LicenceSyncAuthorizationTests(TestCase):
    def setUp(self):
        self.url = reverse("company_update_api")
        self.company_admin = User.objects.create_user(username="co_a", password="pass12345", is_staff=True)
        self.outlet = AdminOutlet.objects.create(
            user=self.company_admin,
            customer_name="Company A",
            customer_email="recovery@a.example",
            customer_contact_person="Alice",
            phone_number="9000000001",
            customer_id=1001,
        )
        other_admin = User.objects.create_user(username="co_b", password="pass12345", is_staff=True)
        self.other = AdminOutlet.objects.create(
            user=other_admin, customer_name="Company B", customer_email="recovery@b.example", customer_id=2002
        )
        self.super_admin = User.objects.create_superuser(username="sa", password="pass12345")
        self.client = APIClient()

    def put(self, payload):
        return self.client.put(self.url, payload, format="json")

    def test_company_admin_own_company_licence_sync_unchanged(self):
        self.client.force_authenticate(self.company_admin)
        response = self.put(licence_payload(1001))
        self.assertEqual(response.status_code, 200)
        self.outlet.refresh_from_db()
        self.assertEqual(self.outlet.authentication_status, "Approve")
        self.assertEqual(self.outlet.outlet_count, 6)
        self.assertEqual(self.outlet.locations, [{"name": "Kochi"}])
        self.assertEqual(response.data, AdminOutletSerializer(self.outlet).data)

    def test_customer_id_as_string_like_local_storage(self):
        self.client.force_authenticate(self.company_admin)
        self.assertEqual(self.put(licence_payload("1001")).status_code, 200)

    def test_company_admin_cannot_update_other_company(self):
        self.client.force_authenticate(self.company_admin)
        response = self.put(licence_payload(2002, authentication_status="Block"))
        self.assertEqual(response.status_code, 403)
        self.other.refresh_from_db()
        self.assertEqual(self.other.authentication_status, "Pending")

    def test_recovery_email_and_contact_fields_cannot_be_changed(self):
        for user in (self.company_admin, self.super_admin):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                response = self.put(
                    licence_payload(
                        1001,
                        customer_email="attacker@evil.example",
                        customer_name="Hijacked",
                        customer_contact_person="Mallory",
                        phone_number="9999999999",
                        user={"username": "hijacked", "password": "x"},
                    )
                )
                self.assertEqual(response.status_code, 200)
                self.outlet.refresh_from_db()
                self.assertEqual(self.outlet.customer_email, "recovery@a.example")
                self.assertEqual(self.outlet.customer_name, "Company A")
                self.assertEqual(self.outlet.customer_contact_person, "Alice")
                self.assertEqual(self.outlet.phone_number, "9000000001")
                self.assertEqual(self.outlet.user.username, "co_a")
                self.assertEqual(response.data["customer_email"], "recovery@a.example")

    def test_super_admin_can_sync_any_company(self):
        self.client.force_authenticate(self.super_admin)
        response = self.put(licence_payload(2002, authentication_status="Block"))
        self.assertEqual(response.status_code, 200)
        self.other.refresh_from_db()
        self.assertEqual(self.other.authentication_status, "Block")

    def test_legacy_outlet_account_own_company(self):
        outlet_user = User.objects.create_user(username="legacy_outlet", password="pass12345")
        Vendor.objects.create(
            user=outlet_user, admin_outlet=self.outlet, name="Outlet 1", vendor_id=900001, location_id="L1"
        )
        self.client.force_authenticate(outlet_user)
        self.assertEqual(self.put(licence_payload(1001)).status_code, 200)
        self.assertEqual(self.put(licence_payload(2002)).status_code, 403)

    def test_staff_profile_user_is_forbidden(self):
        staff = User.objects.create_user(username="kitchen", password="pass12345")
        UserProfile.objects.create(user=staff, role="utility_user", admin_outlet=self.outlet)
        self.client.force_authenticate(staff)
        self.assertEqual(self.put(licence_payload(1001)).status_code, 403)

    def test_non_staff_user_linked_to_company_is_forbidden(self):
        self.company_admin.is_staff = False
        self.company_admin.save()
        self.client.force_authenticate(self.company_admin)
        self.assertEqual(self.put(licence_payload(1001)).status_code, 403)

    def test_unauthenticated_is_rejected(self):
        self.assertEqual(self.put(licence_payload(1001)).status_code, 401)

    def test_jwt_bearer_like_ui(self):
        access = str(RefreshToken.for_user(self.company_admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.put(licence_payload(1001)).status_code, 200)

    def test_existing_error_responses_unchanged(self):
        self.client.force_authenticate(self.super_admin)
        missing = self.put({"authentication_status": "Approve"})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.data, {"error": "customer_id is required."})
        unknown = self.put(licence_payload(9999))
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(unknown.data, {"error": "AdminOutlet not found for this customer_id."})
