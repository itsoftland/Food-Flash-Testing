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

from vendors.models import AdminOutlet, AndroidDevice, Order, TVDeviceConfig, Utility, Vendor, VendorConfig


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

    def _create_order(self, *, status, booking_no, token_no, offset_minutes=0, utility=None):
        order = Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            table_booking_no=booking_no,
            status=status,
            customer_name="Patient",
            counter_no=1,
            utility=utility,
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

        self._create_order(status="called", booking_no="LAB-12", token_no=1, offset_minutes=1)
        self._create_order(status="called", booking_no="ORTHO-5", token_no=2, offset_minutes=2)
        self._create_order(status="waiting", booking_no="CARDIO-3", token_no=3)

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["mapped"])
        self.assertEqual(data["vendor_id"], 705041)
        self.assertIn("hospital_flash", data)
        self.assertEqual(data["hospital_flash"]["tokens"], ["ORTHO-5", "LAB-12"])
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
        self.assertEqual(tv_config_payload["departments"], [])

    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_tv_config_includes_individual_departments(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        ortho = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Ortho Internal",
            display_name="Ortho",
            display_code="ORTHO",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )
        xray = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Xray Internal",
            display_name="Xray",
            display_code="XRAY",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )

        tv_config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="reception",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
        )
        tv_config.utilities.set([ortho, xray])
        self.device.tv_config = tv_config
        self.device.save(update_fields=["tv_config"])

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        departments = response.json()["tv_config"]["departments"]
        self.assertEqual(
            departments,
            [
                {"id": ortho.id, "name": "Ortho"},
                {"id": xray.id, "name": "Xray"},
            ],
        )

    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_tv_config_expands_group_departments(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        ortho = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Ortho Internal",
            display_name="Ortho",
            display_code="ORTHO",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )
        xray = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Xray Internal",
            display_name="Xray",
            display_code="XRAY",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )
        group = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Group A",
            display_name="Group A",
            display_code="GRP",
            department_type=Utility.DEPARTMENT_TYPE_GROUP,
        )
        group.group_departments.set([ortho, xray])

        tv_config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Group TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
        )
        tv_config.utilities.set([group])
        self.device.tv_config = tv_config
        self.device.save(update_fields=["tv_config"])

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        departments = response.json()["tv_config"]["departments"]
        department_ids = {item["id"] for item in departments}
        self.assertEqual(department_ids, {ortho.id, xray.id})
        self.assertNotIn(group.id, department_ids)
        self.assertEqual(
            departments,
            [
                {"id": ortho.id, "name": "Ortho"},
                {"id": xray.id, "name": "Xray"},
            ],
        )

    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_tv_config_department_name_falls_back_to_utility_name(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        lab = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Laboratory",
            display_name="",
            display_code="LAB",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )

        tv_config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Lab TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
        )
        tv_config.utilities.set([lab])
        self.device.tv_config = tv_config
        self.device.save(update_fields=["tv_config"])

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json()["tv_config"]["departments"],
            [{"id": lab.id, "name": "Laboratory"}],
        )

    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_registration_filters_by_tv_config_departments(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        lab = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Laboratory",
            display_name="Laboratory",
            display_code="LAB",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )
        ortho = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Orthopedics",
            display_name="Orthopedics",
            display_code="ORTHO",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )

        self._create_order(status="called", booking_no="LAB-12", token_no=1, utility=lab)
        self._create_order(status="called", booking_no="ORTHO-5", token_no=2, utility=ortho)

        tv_config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Laboratory TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
        )
        tv_config.utilities.set([lab])
        self.device.tv_config = tv_config
        self.device.save(update_fields=["tv_config"])

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["hospital_flash"]["tokens"], ["LAB-12"])
        self.assertEqual(data["hospital_flash"]["total_count"], 1)


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

    @patch("vendors.views.project_name", "dine_flash")
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
        self.assertNotIn("departments", data.get("tv_config") or {})
        mock_dine_snapshot.assert_called_once()


@override_settings(PROJECT_NAME="food_flash")
class FoodFlashTvRegistrationIsolationTests(_HospitalTvRegistrationMixin, TestCase):
    @patch("vendors.views.project_name", "food_flash")
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_food_flash_registration_has_no_hospital_snapshot(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertNotIn("hospital_flash", data)
        self.assertNotIn("dine_flash", data)
        self.assertNotIn("departments", data.get("tv_config") or {})


@override_settings(PROJECT_NAME="dine_flash_buffet")
class DineFlashBuffetTvRegistrationIsolationTests(_HospitalTvRegistrationMixin, TestCase):
    @patch("vendors.views.project_name", "dine_flash_buffet")
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_buffet_registration_has_no_hospital_snapshot(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertNotIn("hospital_flash", data)
        self.assertNotIn("dine_flash", data)
        self.assertNotIn("departments", data.get("tv_config") or {})


@override_settings(PROJECT_NAME="airline_flash")
class AirlineFlashTvRegistrationIsolationTests(_HospitalTvRegistrationMixin, TestCase):
    @patch("vendors.views.project_name", "airline_flash")
    @patch("vendors.views.get_mqtt_config_for_vendor")
    def test_airline_registration_has_no_hospital_snapshot(self, mock_mqtt):
        mock_mqtt.return_value = {"topic": "FF/705041/ALL", "host": "mqtt.test"}

        response = self._register()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertNotIn("hospital_flash", data)
        self.assertNotIn("dine_flash", data)
        self.assertNotIn("departments", data.get("tv_config") or {})
