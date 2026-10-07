"""Super Admin-only company APIs: register_company, company_lists, update_company, update_company_id.

Super Admin = is_superuser (not DRF IsAdminUser: Company Admins are is_staff=True).
Successful request/response contracts must stay exactly as before.
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from orders.serializers import AdminOutletSerializer
from vendors.models import AdminOutlet, UserProfile

LICENCE_APPROVAL_PAYLOAD = {
    "authentication_status": "Approve",
    "product_registration_id": 77,
    "unique_identifier": "UID-77",
    "customer_id": 1001,
    "product_from_date": "2026-01-01T00:00:00Z",
    "product_to_date": "2027-01-01T00:00:00Z",
    "total_count": "10",
    "project_code": "DF",
    "web_login_count": 2,
    "android_tv_count": 3,
    "android_apk_count": 4,
    "keypad_device_count": 0,
    "led_display_count": 0,
    "outlet_count": 5,
    "locations": [],
    "displaymode": 1,
}


def company_lists_api_url():
    # companyadmin/urls.py names both the API and the HTML page "company_lists"; reverse() returns the page.
    return reverse("companyadmin:register-company").replace("register-company/", "company_lists/")


class CompanyApiAuthorizationTests(TestCase):
    def setUp(self):
        self.super_admin = User.objects.create_superuser(username="sa", password="pass12345")
        self.company_admin = User.objects.create_user(username="co_admin", password="pass12345", is_staff=True)
        self.outlet = AdminOutlet.objects.create(
            user=self.company_admin, customer_name="Acme", customer_email="acme@x.example", customer_id=1001
        )
        self.staff_user = User.objects.create_user(username="kitchen", password="pass12345")
        UserProfile.objects.create(user=self.staff_user, role="utility_user", admin_outlet=self.outlet)
        self.client = APIClient()

    # (method, url, payload)
    def endpoints(self):
        return [
            ("get", company_lists_api_url(), None),
            ("put", reverse("companyadmin:update_company"), {"customer_id": 1001, "authentication_status": "Blocked"}),
            ("put", reverse("companyadmin:update_company_id", args=[self.outlet.id]), {"customer_id": 5555}),
            ("post", reverse("companyadmin:register-company"), {"CustomerName": "Evil", "CustomerUsername": "evil"}),
        ]

    def call(self, method, url, payload):
        return getattr(self.client, method)(url, payload, format="json")

    def test_unauthenticated_is_rejected(self):
        for method, url, payload in self.endpoints():
            with self.subTest(url=url):
                self.assertEqual(self.call(method, url, payload).status_code, 401)
        self.outlet.refresh_from_db()
        self.assertEqual(self.outlet.customer_id, 1001)
        self.assertEqual(self.outlet.authentication_status, "Pending")
        self.assertFalse(User.objects.filter(username="evil").exists())

    def test_company_admin_is_forbidden(self):
        self.client.force_authenticate(self.company_admin)
        for method, url, payload in self.endpoints():
            with self.subTest(url=url):
                self.assertEqual(self.call(method, url, payload).status_code, 403)

    def test_staff_user_is_forbidden(self):
        self.client.force_authenticate(self.staff_user)
        for method, url, payload in self.endpoints():
            with self.subTest(url=url):
                self.assertEqual(self.call(method, url, payload).status_code, 403)

    def test_super_admin_company_lists_response_unchanged(self):
        self.client.force_authenticate(self.super_admin)
        paged = self.client.get(company_lists_api_url())
        self.assertEqual(paged.status_code, 200)
        self.assertEqual(set(paged.data.keys()), {"count", "next", "previous", "results"})
        expected = AdminOutletSerializer(AdminOutlet.objects.all().order_by("-created_at"), many=True).data
        self.assertEqual(json.loads(json.dumps(paged.data["results"])), json.loads(json.dumps(expected)))
        unpaged = self.client.get(company_lists_api_url(), {"all": "true"})
        self.assertEqual(json.loads(json.dumps(unpaged.data)), json.loads(json.dumps(expected)))

    def test_super_admin_update_company_id_unchanged(self):
        self.client.force_authenticate(self.super_admin)
        response = self.client.put(
            reverse("companyadmin:update_company_id", args=[self.outlet.id]), {"customer_id": 5555}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.outlet.refresh_from_db()
        self.assertEqual(self.outlet.customer_id, 5555)
        self.assertEqual(response.data, AdminOutletSerializer(self.outlet).data)

    def test_super_admin_update_company_licence_payload_unchanged(self):
        self.client.force_authenticate(self.super_admin)
        response = self.client.put(reverse("companyadmin:update_company"), LICENCE_APPROVAL_PAYLOAD, format="json")
        self.assertEqual(response.status_code, 200)
        self.outlet.refresh_from_db()
        self.assertEqual(self.outlet.authentication_status, "Approve")
        self.assertEqual(self.outlet.outlet_count, 5)
        self.assertEqual(response.data, AdminOutletSerializer(self.outlet).data)

    @override_settings(PROJECT_NAME="food_flash")
    def test_super_admin_register_company_unchanged(self):
        self.client.force_authenticate(self.super_admin)
        response = self.client.post(
            reverse("companyadmin:register-company"),
            {
                "CustomerName": "New Co",
                "CustomerEmail": "new@co.example",
                "CustomerUsername": "new_co_admin",
                "CustomerPassword": "pass12345",
                "PhoneNumber": "9876543210",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {"status": "success", "message": "Company registered successfully"})
        created = AdminOutlet.objects.get(user__username="new_co_admin")
        self.assertTrue(created.user.is_staff)
        self.assertFalse(created.user.is_superuser)

    def test_super_admin_with_jwt_like_ui(self):
        access = str(RefreshToken.for_user(self.super_admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get(company_lists_api_url()).status_code, 200)

    def test_session_auth_enforces_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.super_admin)
        response = client.put(reverse("companyadmin:update_company"), {"customer_id": 1001}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("CSRF", str(response.data))
