"""
Hospital Flash TV registration bootstrap tests.

Verifies register_android_device() returns the current called-patient snapshot
for hospital_flash only, without affecting other flavours.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from vendors.models import AdminOutlet, AndroidDevice, Order, TVDeviceConfig, Vendor, VendorConfig


class _HospitalTvRegistrationMixin:
    def setUp(self):
        self.client = APIClient()
        self.admin_outlet = AdminOutlet.objects.create(
            customer_name="Hospital Co",
            customer_id=91010,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="City Hospital",
            alias_name="CH",
            location="CityA",
            place_id="place-hreg",
            vendor_id=705041,
            location_id="HLREG",
            menus="[]",
        )
        self.config = VendorConfig.objects.create(
            vendor=self.vendor,
            token_display_limit=8,
            tv_communication_mode="MQTT",
            mqtt_mode="All",
        )
        self.device = AndroidDevice.objects.create(
            token="tv-token-1",
            mac_address="AA:BB:CC:DD:EE:99",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
        )
        self.now = timezone.now()
        self.start_dt = self.now - timedelta(hours=1)
        self.end_dt = self.now + timedelta(hours=1)
        self.url = reverse("vendors:register-android-device")

    def _register(self):
        return self.client.post(
            self.url,
            {
                "token": "tv-token-1",
                "customer_id": self.admin_outlet.customer_id,
                "mac_address": self.device.mac_address,
            },
            format="json",
        )

    def _create_order(self, *, status, booking_no, token_no, offset_minutes=0):
        order = Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            table_booking_no=booking_no,
            status=status,
            customer_name="Patient",
            counter_no=1,
        )
        if offset_minutes:
            Order.objects.filter(pk=order.pk).update(
                created_at=self.now + timedelta(minutes=offset_minutes),
                updated_at=self.now + timedelta(minutes=offset_minutes),
            )
            order.refresh_from_db()
        return order


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalTvRegistrationBootstrapTests(_HospitalTvRegistrationMixin, TestCase):
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_includes_called_patients_snapshot(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        self._create_order(status="called", booking_no="LAB-12", token_no=1)
        self._create_order(status="called", booking_no="ORTHO-5", token_no=2)
        self._create_order(status="waiting", booking_no="CARDIO-3", token_no=3)

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["mapped"])
        self.assertEqual(data["vendor_id"], 705041)
        self.assertIn("hospital_flash", data)
        self.assertEqual(data["hospital_flash"]["tokens"], ["LAB-12", "ORTHO-5"])
        self.assertEqual(data["hospital_flash"]["total_count"], 2)
        self.assertNotIn("dine_flash", data)

    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_empty_snapshot_when_no_called_patients(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        self._create_order(status="waiting", booking_no="CARDIO-3", token_no=1)

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["hospital_flash"]["tokens"], [])
        self.assertEqual(data["hospital_flash"]["total_count"], 0)

    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_respects_ordering_and_token_display_limit(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}
        self.config.token_display_limit = 2
        self.config.save(update_fields=["token_display_limit"])

        self._create_order(status="called", booking_no="LAB-1", token_no=1, offset_minutes=1)
        self._create_order(status="called", booking_no="LAB-2", token_no=2, offset_minutes=2)
        self._create_order(status="called", booking_no="LAB-3", token_no=3, offset_minutes=3)

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["hospital_flash"]["tokens"], ["LAB-3", "LAB-2"])
        self.assertEqual(data["hospital_flash"]["total_count"], 2)

    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_tv_config_includes_hospital_presentation_fields(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}
        tv_config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Lobby Display",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
            display_rows=2,
            display_columns=3,
            token_font_size="large",
            enable_ads=True,
            ad_position="left",
            ad_interval=12,
            video_ad_mode="play_full",
        )
        self.device.tv_config = tv_config
        self.device.save(update_fields=["tv_config"])

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tv_config_payload = response.json()["tv_config"]
        self.assertEqual(tv_config_payload["config_name"], "Lobby Display")
        self.assertEqual(tv_config_payload["display_rows"], 2)
        self.assertEqual(tv_config_payload["display_columns"], 3)
        self.assertTrue(tv_config_payload["enable_ads"])
        self.assertEqual(tv_config_payload["ad_position"], "left")
        self.assertEqual(tv_config_payload["ad_interval"], 12)
        self.assertEqual(tv_config_payload["video_ad_mode"], "play_full")
        self.assertIn("ad_items", tv_config_payload)
        self.assertNotIn("show_customer_name", tv_config_payload)
        self.assertNotIn("qr_placement", tv_config_payload)
        self.assertNotIn("show_no_of_packs", tv_config_payload)


@override_settings(PROJECT_NAME="dine_flash")
class DineFlashTvRegistrationIsolationTests(_HospitalTvRegistrationMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.tv_config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Dine TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=["token"],
        )
        self.device.tv_config = self.tv_config
        self.device.save(update_fields=["tv_config"])

    @patch("vendors.views.build_dine_flash_tv_booking_snapshot")
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_dine_flash_registration_unchanged_without_hospital_snapshot(
        self, mock_mqtt, mock_dine_snapshot
    ):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}
        mock_dine_snapshot.return_value = {
            "counts": {"waiting": 1, "active_tables": 0, "ongoing_tables": 0},
            "displayed_counts": {"waiting": 1, "active_tables": 0, "ongoing_tables": 0},
        }

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("dine_flash", data)
        self.assertNotIn("hospital_flash", data)
        mock_dine_snapshot.assert_called_once()


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashTvRegistrationIsolationTests(_HospitalTvRegistrationMixin, TestCase):
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_food_flash_registration_has_no_hospital_snapshot(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertNotIn("hospital_flash", data)
        self.assertNotIn("dine_flash", data)


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetTvRegistrationIsolationTests(_HospitalTvRegistrationMixin, TestCase):
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_buffet_registration_has_no_hospital_snapshot(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertNotIn("hospital_flash", data)
        self.assertNotIn("dine_flash", data)


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashTvRegistrationIsolationTests(_HospitalTvRegistrationMixin, TestCase):
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_airline_registration_has_no_hospital_snapshot(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertNotIn("hospital_flash", data)
        self.assertNotIn("dine_flash", data)
