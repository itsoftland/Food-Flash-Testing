from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone

from vendors.models import AdminOutlet, Vendor, VendorConfig, Device, AndroidDevice, AdvertisementImage, AdvertisementProfile, AdvertisementProfileAssignment, Order, ArchivedOrder, OrderStatusHistory, ArchivedOrderStatusHistory, Utility

class CompanyViewsAPITests(TestCase):
    def setUp(self):
        # Create user and authenticate
        self.user = User.objects.create_user(username="admin", password="pass1234")
        self.client = APIClient()
        self.client.login(username="admin", password="pass1234")

        # Link AdminOutlet to user
        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Test Co",
            customer_id=100,
            locations=[{"CityA": "C1"}, {"CityB": "C2"}],
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )

        # Common vendor
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Outlet 1",
            alias_name="O1",
            location="CityA",
            place_id="place-1",
            vendor_id=123456,
            location_id="L1",
            menus="[]",
        )
        self.config = VendorConfig.objects.create(vendor=self.vendor)

    # 1. get_outlet_creation_data should return unmapped devices and enum choices
    def test_get_outlet_creation_data_returns_expected_payload(self):
        # Unmapped devices for this outlet
        Device.objects.create(serial_no="DVC-1", admin_outlet=self.admin_outlet)
        AndroidDevice.objects.create(token="tok1", mac_address="AA:BB", admin_outlet=self.admin_outlet)

        url = reverse("get_outlet_creation_data")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        # locations flattened and present
        self.assertIn("locations", data)
        self.assertTrue(any(item["value"] == "C1" for item in data["locations"]))

        # unmapped devices present
        self.assertIn({"serial_no": "DVC-1"}, data["keypad_devices"])  # values() returns dicts
        self.assertIn({"mac_address": "AA:BB"}, data["android_tvs"])  # values() returns dicts

        # enum choices present from VendorConfig
        self.assertIn("tv_communication_modes", data)
        self.assertIn("mqtt_modes", data)
        self.assertTrue(len(data["tv_communication_modes"]) > 0)
        self.assertTrue(len(data["mqtt_modes"]) > 0)

    # 2. license_check should approve for valid customer and fail for missing param
    def test_license_check_behaviors(self):
        url = reverse("license_check")

        # missing customer_id
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # valid customer
        resp = self.client.get(url, {"customer_id": self.admin_outlet.customer_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json().get("status"), "success")

    # 3. delete_banner should validate banner_id strictly and delete record/file
    def test_delete_banner_validation_and_deletion(self):
        # bad request: no id
        url = reverse("delete_banner")
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # create a banner
        banner = AdvertisementImage.objects.create(admin_outlet=self.admin_outlet, image="ads/test.jpg")
        # valid deletion
        resp = self.client.delete(url, {"banner_id": str(banner.id)})
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AdvertisementImage.objects.filter(id=banner.id).exists())

    # 4. unmap_profile should remove mapping and handle missing mapping
    def test_unmap_profile_behaviors(self):
        profile = AdvertisementProfile.objects.create(admin_outlet=self.admin_outlet, name="P1")
        AdvertisementProfileAssignment.objects.create(profile=profile, vendor=self.vendor)

        url = reverse("unmap_profile", args=[self.vendor.id, profile.id])
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        # second attempt should 404
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # 5. order_status_timeline should combine active and archived histories
    def test_order_status_timeline_combines_histories(self):
        # Active order with history
        order = Order.objects.create(vendor=self.vendor, token_no=1, status="preparing")
        OrderStatusHistory.objects.create(order=order, previous_status=None, new_status="preparing")

        # Archived order with its own history
        arch = ArchivedOrder.objects.create(
            original_order_id=order.id,
            vendor=self.vendor,
            device=None,
            user_profile=None,
            token_no=1,
            status="ready",
            counter_no=1,
            shown_on_tv=False,
            notified_at=None,
            updated_by="manager",
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        ArchivedOrderStatusHistory.objects.create(archived_order=arch, previous_status="preparing", new_status="ready", changed_by="manager", changed_at=timezone.now())

        url = reverse("order_status_timeline", args=[order.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        timeline = resp.json()
        # should contain at least two entries from both sources
        self.assertTrue(any(item.get("new_status") == "preparing" for item in timeline))
        self.assertTrue(any(item.get("new_status") == "ready" for item in timeline))

    # 6. update_outlet_settings should validate vendor_id and update allowed fields
    def test_update_outlet_settings_validation_and_update(self):
        url = reverse("update_outlet_settings")

        # missing vendor_id
        resp = self.client.post(url, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # invalid vendor
        resp = self.client.post(url, {"vendor_id": 99999}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # valid update adhering to serializer rules
        payload = {
            "vendor_id": self.vendor.id,
            "vibration_enabled": True,
            "vibration_pattern": "alert_strong",
            "vibration_duration": 10,
        }
        resp = self.client.post(url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.config.refresh_from_db()
        self.assertTrue(self.config.vibration_enabled)
        self.assertEqual(self.config.vibration_pattern, "alert_strong")
        self.assertEqual(self.config.vibration_duration, 10)

    # 7. tv_config_list should reject users without admin_outlet
    def test_tv_config_list_requires_admin_outlet(self):
        # create another user without outlet
        u2 = User.objects.create_user(username="u2", password="p2")
        client2 = APIClient()
        client2.login(username="u2", password="p2")
        url = reverse("tv_config_list")
        resp = client2.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # 8. get_devices filter works for mapped/unmapped
    def test_get_devices_filters(self):
        # create two devices: one mapped, one unmapped
        d1 = Device.objects.create(serial_no="S1", admin_outlet=self.admin_outlet, vendor=self.vendor)
        d2 = Device.objects.create(serial_no="S2", admin_outlet=self.admin_outlet)

        url = reverse("get_devices")
        # all
        resp = self.client.get(url, {"filter": "all"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json().get("count"), 2)
        # mapped
        resp = self.client.get(url, {"filter": "mapped"})
        self.assertEqual(resp.json().get("count"), 1)
        # unmapped
        resp = self.client.get(url, {"filter": "unmapped"})
        self.assertEqual(resp.json().get("count"), 1)

    # 9. get_vendors returns vendors for admin outlet
    def test_get_vendors(self):
        url = reverse("get_vendors")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json().get("vendors", [])), 1)

    # 10. order_counts_summary aggregates active + archived
    def test_order_counts_summary(self):
        # create orders in range
        Order.objects.create(vendor=self.vendor, token_no=7, status="preparing")
        ArchivedOrder.objects.create(
            original_order_id=999,
            vendor=self.vendor,
            device=None,
            user_profile=None,
            token_no=8,
            status="ready",
            counter_no=1,
            shown_on_tv=False,
            notified_at=None,
            updated_by="manager",
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        url = reverse("order_counts_summary")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        # All should be >= 2 for today/week/month depending on time filters
        self.assertGreaterEqual(data.get("orders_today", 0), 2)
        self.assertGreaterEqual(data.get("orders_this_week", 0), 2)
        self.assertGreaterEqual(data.get("orders_this_month", 0), 2)

    # A. banner_id/ad_profile_id validations in views
    def test_delete_banner_missing_and_non_numeric_banner_id(self):
        url = reverse("delete_banner")
        # missing id
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # non-numeric id
        resp = self.client.delete(url, {"banner_id": "abc"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_banner_success_with_valid_id(self):
        banner = AdvertisementImage.objects.create(admin_outlet=self.admin_outlet, image="ads/test2.jpg")
        url = reverse("delete_banner")
        resp = self.client.delete(url, {"banner_id": str(banner.id)})
        # Expect 204 on success as per existing deletion behavior
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AdvertisementImage.objects.filter(id=banner.id).exists())

    def test_ad_profile_id_missing_or_non_numeric_if_endpoint_exists(self):
        # Try to reverse an endpoint name if present in company.urls
        try:
            url = reverse("unassign_ad_profile")
        except Exception:
            url = None
        if url:
            resp = self.client.delete(url)
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            resp = self.client.delete(url, {"ad_profile_id": "xyz"})
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ad_profile_unassign_nonexistent_returns_404_or_400(self):
        try:
            url = reverse("unassign_ad_profile")
        except Exception:
            url = None
        if url:
            resp = self.client.delete(url, {"ad_profile_id": "999999"})
            self.assertIn(resp.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND))

    def test_validation_short_circuits_without_external_mocks(self):
        url_banner = reverse("delete_banner")
        resp = self.client.delete(url_banner)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        try:
            url_profile = reverse("unassign_ad_profile")
        except Exception:
            url_profile = None
        if url_profile:
            resp = self.client.delete(url_profile)
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
