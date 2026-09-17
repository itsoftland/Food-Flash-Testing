import time

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from orders.buffet_table_qr import sign_buffet_table_qr, unsign_buffet_table_qr
from vendors.models import AdminOutlet, BuffetSavedTableQr, Vendor, VendorConfig


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetSavedTableQrApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="buffet_admin", password="pass1234")
        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Buffet Co",
            customer_id=501,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Outlet A",
            alias_name="OA",
            location="Floor 1",
            vendor_id=800701,
            location_id="B1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)

        self.other_user = User.objects.create_user(username="other_admin", password="pass1234")
        self.other_outlet = AdminOutlet.objects.create(
            user=self.other_user,
            customer_name="Other Co",
            customer_id=502,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.other_vendor = Vendor.objects.create(
            admin_outlet=self.other_outlet,
            name="Outlet X",
            alias_name="OX",
            location="Elsewhere",
            vendor_id=800702,
            location_id="X1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.other_vendor)

        self.list_url = reverse("company:buffet_saved_table_qrs")
        self.generate_url = reverse("company:generate_buffet_table_qr")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_generate_allows_duplicate_outlet_table(self):
        self._auth(self.user)
        payload = {"vendor_id": self.vendor.vendor_id, "table_no": "5"}
        first = self.client.post(self.generate_url, payload, format="json")
        time.sleep(1.1)  # TimestampSigner embeds second precision
        second = self.client.post(self.generate_url, payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertNotEqual(first.json()["qr_token"], second.json()["qr_token"])
        self.assertEqual(unsign_buffet_table_qr(first.json()["qr_token"])["table_no"], "5")
        self.assertEqual(unsign_buffet_table_qr(second.json()["qr_token"])["table_no"], "5")

    def test_save_list_view_payload_and_multiple_saves(self):
        self._auth(self.user)
        tokens = []
        for i in range(3):
            if i:
                time.sleep(1.1)
            generated = self.client.post(
                self.generate_url,
                {"vendor_id": self.vendor.vendor_id, "table_no": "5"},
                format="json",
            )
            self.assertEqual(generated.status_code, status.HTTP_200_OK)
            token = generated.json()["qr_token"]
            tokens.append(token)
            saved = self.client.post(
                self.list_url,
                {
                    "vendor_id": self.vendor.vendor_id,
                    "table_no": "5",
                    "qr_token": token,
                },
                format="json",
            )
            self.assertEqual(saved.status_code, status.HTTP_201_CREATED)
            self.assertEqual(saved.json()["qr_token"], token)

        listed = self.client.get(self.list_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        rows = listed.json()
        self.assertEqual(len(rows), 3)
        saved_tokens = {row["qr_token"] for row in rows}
        self.assertEqual(saved_tokens, set(tokens))
        for row in rows:
            self.assertIn("qr_url", row)
            self.assertIn("qr_token=", row["qr_url"])
            self.assertEqual(row["table_no"], "5")
            self.assertEqual(row["vendor_id"], str(self.vendor.vendor_id))

    def test_save_rejects_mismatched_token(self):
        self._auth(self.user)
        token = sign_buffet_table_qr(self.vendor.vendor_id, 5)
        resp = self.client.post(
            self.list_url,
            {
                "vendor_id": self.vendor.vendor_id,
                "table_no": "9",
                "qr_token": token,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_removes_only_list_entry(self):
        self._auth(self.user)
        token = sign_buffet_table_qr(self.vendor.vendor_id, 7)
        saved = BuffetSavedTableQr.objects.create(
            vendor=self.vendor,
            table_no="7",
            qr_token=token,
            created_by=self.user,
        )
        delete_url = reverse("company:delete_buffet_saved_table_qr", kwargs={"saved_id": saved.id})
        resp = self.client.delete(delete_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(BuffetSavedTableQr.objects.filter(id=saved.id).exists())
        # Token itself remains valid after delete.
        self.assertEqual(unsign_buffet_table_qr(token)["table_no"], "7")

    def test_cannot_list_or_delete_other_company_qr(self):
        foreign = BuffetSavedTableQr.objects.create(
            vendor=self.other_vendor,
            table_no="1",
            qr_token=sign_buffet_table_qr(self.other_vendor.vendor_id, 1),
            created_by=self.other_user,
        )
        self._auth(self.user)
        listed = self.client.get(self.list_url)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(listed.json(), [])

        delete_url = reverse("company:delete_buffet_saved_table_qr", kwargs={"saved_id": foreign.id})
        deleted = self.client.delete(delete_url)
        self.assertEqual(deleted.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(BuffetSavedTableQr.objects.filter(id=foreign.id).exists())

    def test_unauthenticated_rejected(self):
        resp = self.client.get(self.list_url)
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


@override_settings(PROJECT_NAME="food_flash")
class BuffetSavedTableQrOtherFlavourTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="ff_admin", password="pass1234")
        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Food Co",
            customer_id=601,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.client.force_authenticate(user=self.user)

    def test_saved_qr_api_not_supported_on_other_flavour(self):
        url = reverse("company:buffet_saved_table_qrs")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json().get("error"), "Not supported")
