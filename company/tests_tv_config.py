"""
TV device configuration serializer/API tests for flavour-specific booking_fields rules.
"""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from company.serializers import TVDeviceConfigSerializer
from vendors.models import AdminOutlet, TVAdvertisement, TVDeviceConfig, Utility, Vendor, VendorConfig


class _TvConfigTestMixin:
    def setUp(self):
        self.user = User.objects.create_user(username="tvconfig-admin", password="pass1234")
        self.client = APIClient()
        self.client.login(username="tvconfig-admin", password="pass1234")

        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="TV Config Co",
            customer_id=92001,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Outlet 1",
            alias_name="O1",
            location="CityA",
            place_id="place-tv",
            vendor_id=920001,
            location_id="TV1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)
        self.utility = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Laboratory",
            display_name="Laboratory",
            display_code="LAB",
        )

    def _base_payload(self):
        return {
            "config_name": "Main TV",
            "show_qr": False,
            "items_to_show": 3,
            "utility_name_mode": "display_name",
            "screen_orientation": "landscape",
            "utilities": [self.utility.id],
        }

    def _create_url(self):
        return reverse("company:tv_config_create")

    def _make_ad(self, *, title, is_active=True, sequence=1):
        return TVAdvertisement.objects.create(
            admin_outlet=self.admin_outlet,
            title=title,
            media_file=SimpleUploadedFile(
                f"{title.replace(' ', '_').lower()}.jpg",
                b"fake-image-bytes",
                content_type="image/jpeg",
            ),
            media_type="image",
            sequence=sequence,
            is_active=is_active,
        )


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalTvConfigCreateTests(_TvConfigTestMixin, TestCase):
    def test_hospital_allows_empty_booking_fields(self):
        payload = self._base_payload()
        payload["booking_fields"] = []

        response = self.client.post(self._create_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        config = TVDeviceConfig.objects.get(admin_outlet=self.admin_outlet)
        self.assertEqual(config.booking_fields, [])

    def test_hospital_serializer_allows_empty_booking_fields(self):
        serializer = TVDeviceConfigSerializer(
            data={
                "admin_outlet": self.admin_outlet.id,
                "config_name": "Serializer TV",
                "show_qr": False,
                "items_to_show": 2,
                "booking_fields": [],
                "utility_name_mode": "display_name",
                "screen_orientation": "landscape",
                "utilities": [self.utility.id],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_hospital_persists_presentation_and_ad_settings(self):
        payload = self._base_payload()
        payload.update(
            {
                "booking_fields": [],
                "display_rows": 2,
                "display_columns": 3,
                "token_font_size": "large",
                "counter_font_size": "medium",
                "utility_font_size": "small",
                "token_text_color": "#111111",
                "counter_text_color": "#222222",
                "utility_text_color": "#333333",
                "header_font_size": "large",
                "header_font_style": "bold",
                "header_text_color": "#444444",
                "footer_enabled": True,
                "footer_texts": ["Welcome"],
                "footer_font_size": "16",
                "footer_text_color": "#555555",
                "audio_enabled": True,
                "announcement_language": "English",
                "blink_token": True,
                "blink_utility": False,
                "enable_ads": True,
                "ad_position": "left",
                "ad_interval": 10,
                "video_ad_mode": "play_full",
            }
        )

        response = self.client.post(self._create_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        config = TVDeviceConfig.objects.get(admin_outlet=self.admin_outlet)
        self.assertEqual(config.config_name, "Main TV")
        self.assertEqual(config.display_rows, 2)
        self.assertEqual(config.display_columns, 3)
        self.assertTrue(config.enable_ads)
        self.assertEqual(config.ad_position, "left")

    def test_hospital_serializer_representation_excludes_visibility_and_qr_fields(self):
        config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Lobby TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
            display_rows=2,
            display_columns=2,
            enable_ads=True,
            ad_position="right",
            show_customer_name=True,
            qr_placement="bottom-right",
        )
        data = TVDeviceConfigSerializer(config).data
        self.assertEqual(data["config_name"], "Lobby TV")
        self.assertEqual(data["display_rows"], 2)
        self.assertIn("enable_ads", data)
        self.assertNotIn("show_customer_name", data)
        self.assertNotIn("qr_placement", data)
        self.assertNotIn("device_ids", data)

    def test_hospital_tv_ads_list_allowed(self):
        response = self.client.get(reverse("company:tv_ads_list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("ads", response.json())

    def test_hospital_update_omitting_advertisement_ids_preserves_assignments(self):
        config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Ads TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
            enable_ads=True,
        )
        active_ad = self._make_ad(title="Active Ad", is_active=True, sequence=1)
        inactive_ad = self._make_ad(title="Inactive Ad", is_active=False, sequence=2)
        config.advertisements.set([active_ad, inactive_ad])

        url = reverse("company:tv_config_update", args=[config.id])
        response = self.client.patch(
            url,
            {"config_name": "Ads TV Renamed", "display_rows": 3},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        config.refresh_from_db()
        self.assertEqual(config.config_name, "Ads TV Renamed")
        self.assertEqual(config.display_rows, 3)
        self.assertEqual(
            set(config.advertisements.values_list("id", flat=True)),
            {active_ad.id, inactive_ad.id},
        )

    def test_hospital_update_preserves_inactive_ads_when_ids_partial(self):
        config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Partial Ads TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
            enable_ads=True,
        )
        active_ad = self._make_ad(title="Active Ad", is_active=True, sequence=1)
        inactive_ad = self._make_ad(title="Inactive Ad", is_active=False, sequence=2)
        config.advertisements.set([active_ad, inactive_ad])

        url = reverse("company:tv_config_update", args=[config.id])
        # Simulate UI sending only selectable/active ads.
        response = self.client.patch(
            url,
            {"advertisement_ids": [active_ad.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        config.refresh_from_db()
        self.assertEqual(
            set(config.advertisements.values_list("id", flat=True)),
            {active_ad.id, inactive_ad.id},
        )

    def test_hospital_representation_includes_assigned_advertisement_ids(self):
        config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Rep Ads TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
        )
        active_ad = self._make_ad(title="Active Ad", is_active=True, sequence=1)
        inactive_ad = self._make_ad(title="Inactive Ad", is_active=False, sequence=2)
        config.advertisements.set([active_ad, inactive_ad])

        data = TVDeviceConfigSerializer(config).data
        self.assertEqual(
            set(data["assigned_advertisement_ids"]),
            {active_ad.id, inactive_ad.id},
        )
        returned_ids = {ad["id"] for ad in data["advertisements"]}
        self.assertEqual(returned_ids, {active_ad.id, inactive_ad.id})


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashTvConfigCreateTests(_TvConfigTestMixin, TestCase):
    def test_dine_flash_rejects_empty_booking_fields(self):
        payload = self._base_payload()
        payload["booking_fields"] = []

        response = self.client.post(self._create_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("booking_fields", response.json().get("errors", {}))

    def test_dine_flash_accepts_booking_fields(self):
        payload = self._base_payload()
        payload["booking_fields"] = ["token"]

        response = self.client.post(self._create_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        config = TVDeviceConfig.objects.get(admin_outlet=self.admin_outlet)
        self.assertEqual(config.booking_fields, ["token"])


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashTvConfigCreateTests(_TvConfigTestMixin, TestCase):
    def test_food_flash_rejects_empty_booking_fields(self):
        payload = self._base_payload()
        payload["booking_fields"] = []

        response = self.client.post(self._create_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("booking_fields", response.json().get("errors", {}))

    def test_food_flash_tv_ads_list_forbidden(self):
        response = self.client.get(reverse("company:tv_ads_list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetTvConfigCreateTests(_TvConfigTestMixin, TestCase):
    def test_buffet_rejects_empty_booking_fields(self):
        payload = self._base_payload()
        payload["booking_fields"] = []

        response = self.client.post(self._create_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("booking_fields", response.json().get("errors", {}))


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashTvConfigCreateTests(_TvConfigTestMixin, TestCase):
    def test_airline_rejects_empty_booking_fields(self):
        payload = self._base_payload()
        payload["booking_fields"] = []

        response = self.client.post(self._create_url(), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("booking_fields", response.json().get("errors", {}))
