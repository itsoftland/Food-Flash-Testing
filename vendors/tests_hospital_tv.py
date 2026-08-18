"""
Hospital Flash TV MVP unit tests.

Covers payload building, query rules, transport dispatch, and manager trigger wiring.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from vendors.models import AdminOutlet, AndroidDevice, Order, TVDeviceConfig, Utility, Vendor, VendorConfig


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalTvPayloadTests(TestCase):
    def setUp(self):
        self.admin_outlet = AdminOutlet.objects.create(
            customer_name="Hospital Co",
            customer_id=200,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="City Hospital",
            alias_name="CH",
            location="CityA",
            place_id="place-h1",
            vendor_id=705041,
            location_id="HL1",
            menus="[]",
        )
        self.config = VendorConfig.objects.create(
            vendor=self.vendor,
            token_display_limit=3,
            tv_communication_mode="MQTT",
            mqtt_mode="All",
        )
        self.now = timezone.now()
        self.start_dt = self.now - timedelta(hours=1)
        self.end_dt = self.now + timedelta(hours=1)

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

    def test_called_patient_appears_in_payload(self):
        from vendors.hospital_tv import build_hospital_tv_payload, get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="LAB-12", token_no=1)
        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        payload = build_hospital_tv_payload(self.vendor, booking_nos)

        self.assertEqual(booking_nos, ["LAB-12"])
        self.assertEqual(payload["tokens"], ["LAB-12"])
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(payload["vendor_id"], 705041)
        self.assertEqual(payload["mode"], "All")

    def test_completed_patient_removed_from_payload(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="LAB-12", token_no=1)
        self._create_order(status="completed", booking_no="ORTHO-5", token_no=2)

        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        self.assertEqual(booking_nos, ["LAB-12"])

    def test_cancelled_patient_removed_from_payload(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="XRAY-21", token_no=1)
        self._create_order(status="cancelled", booking_no="LAB-12", token_no=2)

        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        self.assertEqual(booking_nos, ["XRAY-21"])

    def test_business_day_filtering_excludes_out_of_range_orders(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        in_range = self._create_order(status="called", booking_no="LAB-12", token_no=1)
        out_range = self._create_order(status="called", booking_no="ORTHO-5", token_no=2)
        Order.objects.filter(pk=out_range.pk).update(
            created_at=self.now + timedelta(days=2),
            updated_at=self.now + timedelta(days=2),
        )

        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        self.assertEqual(booking_nos, [in_range.table_booking_no])

    def test_token_display_limit_respected(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="LAB-1", token_no=1, offset_minutes=1)
        self._create_order(status="called", booking_no="LAB-2", token_no=2, offset_minutes=2)
        self._create_order(status="called", booking_no="LAB-3", token_no=3, offset_minutes=3)
        self._create_order(status="called", booking_no="LAB-4", token_no=4, offset_minutes=4)

        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        self.assertEqual(len(booking_nos), 3)
        self.assertEqual(booking_nos, ["LAB-4", "LAB-3", "LAB-2"])

    def test_payload_uses_table_booking_no_not_token_no(self):
        from vendors.hospital_tv import build_hospital_tv_payload, get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="RAD-99", token_no=42)

        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        payload = build_hospital_tv_payload(self.vendor, booking_nos)

        self.assertEqual(payload["tokens"], ["RAD-99"])
        self.assertNotIn(42, payload["tokens"])

    def test_payload_tokens_are_strings_without_padding(self):
        from vendors.hospital_tv import build_hospital_tv_payload

        payload = build_hospital_tv_payload(self.vendor, ["LAB-12", "ORTHO-5"])

        self.assertEqual(payload["tokens"], ["LAB-12", "ORTHO-5"])
        self.assertTrue(all(isinstance(t, str) for t in payload["tokens"]))
        self.assertEqual(payload["total_count"], 2)
        self.assertNotIn(0, payload["tokens"])
        self.assertNotIn("", payload["tokens"])

    def test_blank_table_booking_no_excluded(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="LAB-12", token_no=1)
        self._create_order(status="called", booking_no="", token_no=2)
        Order.objects.filter(vendor=self.vendor, token_no=3).delete()
        Order.objects.create(
            vendor=self.vendor,
            token_no=3,
            table_booking_no=None,
            status="called",
            counter_no=1,
        )

        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        self.assertEqual(booking_nos, ["LAB-12"])

    def test_registration_snapshot_helper_returns_tokens_and_total_count(self):
        from vendors.hospital_tv import (
            _format_hospital_registration_called_at,
            build_hospital_tv_registration_snapshot,
        )

        lab = self._create_order(status="called", booking_no="LAB-12", token_no=1, offset_minutes=1)
        ortho = self._create_order(status="called", booking_no="ORTHO-5", token_no=2, offset_minutes=2)
        self._create_order(status="waiting", booking_no="CARDIO-3", token_no=3)

        self.vendor.refresh_from_db()
        snapshot = build_hospital_tv_registration_snapshot(self.vendor)

        self.assertEqual(
            snapshot["tokens"],
            [
                {
                    "token": "ORTHO-5",
                    "utility_id": ortho.utility_id,
                    "called_at": _format_hospital_registration_called_at(ortho.updated_at),
                },
                {
                    "token": "LAB-12",
                    "utility_id": lab.utility_id,
                    "called_at": _format_hospital_registration_called_at(lab.updated_at),
                },
            ],
        )
        self.assertEqual(snapshot["total_count"], 2)

    def test_registration_snapshot_enrichment_does_not_change_live_tv_payload(self):
        from vendors.hospital_tv import (
            build_hospital_tv_payload,
            build_hospital_tv_registration_snapshot,
            get_hospital_called_booking_nos,
        )

        self._create_order(status="called", booking_no="LAB-12", token_no=1)

        self.vendor.refresh_from_db()
        snapshot = build_hospital_tv_registration_snapshot(self.vendor)
        booking_nos = get_hospital_called_booking_nos(
            self.vendor, start_dt=self.start_dt, end_dt=self.end_dt
        )
        payload = build_hospital_tv_payload(self.vendor, booking_nos)

        self.assertTrue(all(isinstance(item, dict) for item in snapshot["tokens"]))
        self.assertEqual(payload["tokens"], ["LAB-12"])
        self.assertTrue(all(isinstance(item, str) for item in payload["tokens"]))


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalTvDispatchTests(TestCase):
    def setUp(self):
        self.admin_outlet = AdminOutlet.objects.create(
            customer_name="Hospital Co",
            customer_id=201,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="City Hospital",
            alias_name="CH",
            location="CityA",
            place_id="place-h2",
            vendor_id=705042,
            location_id="HL2",
            menus="[]",
        )
        self.now = timezone.now()
        self.start_dt = self.now - timedelta(hours=1)
        self.end_dt = self.now + timedelta(hours=1)

    def _create_called_order(self, booking_no):
        Order.objects.create(
            vendor=self.vendor,
            token_no=1,
            table_booking_no=booking_no,
            status="called",
            counter_no=1,
        )

    @patch("vendors.mqtt_client.publish_mqtt", return_value=True)
    def test_mqtt_dispatch_path(self, mock_publish):
        from vendors.hospital_tv import refresh_hospital_tv

        VendorConfig.objects.create(
            vendor=self.vendor,
            token_display_limit=8,
            tv_communication_mode="MQTT",
            mqtt_mode="All",
        )
        self._create_called_order("LAB-12")

        result = refresh_hospital_tv(self.vendor, start_dt=self.start_dt, end_dt=self.end_dt)

        self.assertTrue(result["success"])
        self.assertEqual(result["transport"], "MQTT")
        mock_publish.assert_called_once()
        args, kwargs = mock_publish.call_args
        self.assertEqual(args[0], self.vendor)
        payload = args[1]
        self.assertEqual(payload["tokens"], ["LAB-12"])
        self.assertEqual(payload["total_count"], 1)

    @patch("static.utils.functions.notifications.notify_android_tv", return_value=(True, {}))
    def test_firebase_dispatch_path(self, mock_notify):
        from vendors.hospital_tv import refresh_hospital_tv

        VendorConfig.objects.create(
            vendor=self.vendor,
            token_display_limit=8,
            tv_communication_mode="Firebase",
            mqtt_mode="All",
        )
        self._create_called_order("ORTHO-5")

        result = refresh_hospital_tv(self.vendor, start_dt=self.start_dt, end_dt=self.end_dt)

        self.assertTrue(result["success"])
        self.assertEqual(result["transport"], "Firebase")
        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        self.assertEqual(args[0], self.vendor)
        payload = args[1]
        self.assertEqual(payload["tokens"], ["ORTHO-5"])

    @patch("vendors.mqtt_client.publish_mqtt", return_value=True)
    @patch("vendors.order_utils.get_last_tokens")
    def test_no_dependency_on_get_last_tokens(self, mock_get_last_tokens, mock_publish):
        from vendors.hospital_tv import refresh_hospital_tv

        VendorConfig.objects.create(
            vendor=self.vendor,
            token_display_limit=8,
            tv_communication_mode="MQTT",
            mqtt_mode="All",
        )
        self._create_called_order("XRAY-21")

        refresh_hospital_tv(self.vendor, start_dt=self.start_dt, end_dt=self.end_dt)

        mock_get_last_tokens.assert_not_called()
        mock_publish.assert_called_once()

    @patch("vendors.mqtt_client.publish_mqtt", return_value=False)
    def test_mqtt_failure_does_not_raise(self, mock_publish):
        from vendors.hospital_tv import refresh_hospital_tv

        VendorConfig.objects.create(
            vendor=self.vendor,
            token_display_limit=8,
            tv_communication_mode="MQTT",
            mqtt_mode="All",
        )
        self._create_called_order("LAB-12")

        result = refresh_hospital_tv(self.vendor, start_dt=self.start_dt, end_dt=self.end_dt)

        self.assertFalse(result["success"])
        mock_publish.assert_called_once()


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalTvManagerTriggerTests(SimpleTestCase):
    def test_manager_patient_update_wires_tv_refresh_on_commit(self):
        from pathlib import Path

        source = Path(__file__).resolve().parents[1].joinpath(
            "manager", "hospital_views.py"
        ).read_text()
        self.assertIn("transaction.on_commit", source)
        self.assertIn("refresh_hospital_tv", source)
        self.assertIn("start_dt=s", source)
        self.assertIn("end_dt=e", source)


class HospitalTvCrossFlavourGuardTests(SimpleTestCase):
    def test_refresh_skipped_outside_hospital_flash(self):
        with override_settings(PROJECT_NAME="food_flash"):
            from vendors.hospital_tv import refresh_hospital_tv

            vendor = MagicMock()
            result = refresh_hospital_tv(vendor, start_dt=MagicMock(), end_dt=MagicMock())
            self.assertTrue(result.get("skipped"))

    def test_is_hospital_flash_guard(self):
        from vendors import hospital_tv

        with override_settings(PROJECT_NAME="hospital_flash"):
            self.assertTrue(hospital_tv.is_hospital_flash())
        with override_settings(PROJECT_NAME="dine_flash"):
            self.assertFalse(hospital_tv.is_hospital_flash())

    def test_registration_snapshot_helper_skipped_outside_hospital_flash(self):
        from vendors.hospital_tv import build_hospital_tv_registration_snapshot

        with override_settings(PROJECT_NAME="food_flash"):
            self.assertIsNone(build_hospital_tv_registration_snapshot(MagicMock()))


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalTvDepartmentFilterTests(TestCase):
    def setUp(self):
        self.admin_outlet = AdminOutlet.objects.create(
            customer_name="Hospital Co",
            customer_id=202,
            authentication_status="Approve",
        )
        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="City Hospital",
            alias_name="CH",
            location="CityA",
            place_id="place-h3",
            vendor_id=705043,
            location_id="HL3",
            menus="[]",
        )
        self.config = VendorConfig.objects.create(
            vendor=self.vendor,
            token_display_limit=8,
            tv_communication_mode="Firebase",
            mqtt_mode="All",
        )
        self.lab = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Laboratory",
            display_name="Laboratory",
            display_code="LAB",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )
        self.ortho = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Orthopedics",
            display_name="Orthopedics",
            display_code="ORTHO",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )
        self.xray = Utility.objects.create(
            vendor=self.vendor,
            utility_name="X-Ray",
            display_name="X-Ray",
            display_code="XRAY",
            department_type=Utility.DEPARTMENT_TYPE_INDIVIDUAL,
        )
        self.health_package = Utility.objects.create(
            vendor=self.vendor,
            utility_name="Health Package",
            display_name="Health Package",
            display_code="PKG",
            department_type=Utility.DEPARTMENT_TYPE_GROUP,
        )
        self.health_package.group_departments.set([self.lab, self.xray])

        self.now = timezone.now()
        self.start_dt = self.now - timedelta(hours=1)
        self.end_dt = self.now + timedelta(hours=1)

    def _create_order(self, *, status, booking_no, utility, token_no=1):
        return Order.objects.create(
            vendor=self.vendor,
            token_no=token_no,
            table_booking_no=booking_no,
            status=status,
            utility=utility,
            counter_no=1,
        )

    def _create_tv_config(self, utilities=None):
        tv_config = TVDeviceConfig.objects.create(
            admin_outlet=self.admin_outlet,
            config_name="Test TV",
            utility_name_mode="display_name",
            screen_orientation="landscape",
            booking_fields=[],
        )
        if utilities:
            tv_config.utilities.set(utilities)
        return tv_config

    def test_filter_single_department(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="LAB-12", utility=self.lab)
        self._create_order(status="called", booking_no="ORTHO-5", utility=self.ortho)

        booking_nos = get_hospital_called_booking_nos(
            self.vendor,
            start_dt=self.start_dt,
            end_dt=self.end_dt,
            utility_ids={self.lab.id},
        )
        self.assertEqual(booking_nos, ["LAB-12"])

    def test_filter_multiple_departments(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="LAB-12", utility=self.lab)
        self._create_order(status="called", booking_no="XRAY-7", utility=self.xray)
        self._create_order(status="called", booking_no="ORTHO-5", utility=self.ortho, token_no=2)

        booking_nos = get_hospital_called_booking_nos(
            self.vendor,
            start_dt=self.start_dt,
            end_dt=self.end_dt,
            utility_ids={self.lab.id, self.xray.id},
        )
        self.assertEqual(set(booking_nos), {"LAB-12", "XRAY-7"})

    def test_no_department_filter_shows_all(self):
        from vendors.hospital_tv import get_hospital_called_booking_nos

        self._create_order(status="called", booking_no="LAB-12", utility=self.lab)
        self._create_order(status="called", booking_no="ORTHO-5", utility=self.ortho, token_no=2)

        booking_nos = get_hospital_called_booking_nos(
            self.vendor,
            start_dt=self.start_dt,
            end_dt=self.end_dt,
            utility_ids=None,
        )
        self.assertEqual(set(booking_nos), {"LAB-12", "ORTHO-5"})

    def test_group_department_expands_members(self):
        from vendors.hospital_tv import resolve_tv_config_utility_ids

        tv_config = self._create_tv_config([self.health_package])
        utility_ids = resolve_tv_config_utility_ids(tv_config)
        self.assertEqual(utility_ids, {self.lab.id, self.xray.id})

    def test_empty_config_utilities_means_show_all(self):
        from vendors.hospital_tv import resolve_tv_config_utility_ids

        tv_config = self._create_tv_config([])
        self.assertIsNone(resolve_tv_config_utility_ids(tv_config))

    def test_build_hospital_tv_config_departments_empty_when_unselected(self):
        from vendors.hospital_tv import build_hospital_tv_config_departments

        tv_config = self._create_tv_config([])
        self.assertEqual(build_hospital_tv_config_departments(tv_config), [])

    def test_build_hospital_tv_config_departments_expands_groups(self):
        from vendors.hospital_tv import build_hospital_tv_config_departments

        tv_config = self._create_tv_config([self.health_package])
        departments = build_hospital_tv_config_departments(tv_config)
        self.assertEqual(
            departments,
            [
                {"id": self.lab.id, "name": "Laboratory"},
                {"id": self.xray.id, "name": "X-Ray"},
            ],
        )

    def test_registration_snapshot_respects_tv_config_departments(self):
        from vendors.hospital_tv import (
            _format_hospital_registration_called_at,
            build_hospital_tv_registration_snapshot,
        )

        lab_order = self._create_order(status="called", booking_no="LAB-12", utility=self.lab)
        self._create_order(status="called", booking_no="ORTHO-5", utility=self.ortho, token_no=2)

        tv_config = self._create_tv_config([self.lab])
        self.vendor.refresh_from_db()
        snapshot = build_hospital_tv_registration_snapshot(self.vendor, tv_config)

        self.assertEqual(
            snapshot["tokens"],
            [
                {
                    "token": "LAB-12",
                    "utility_id": self.lab.id,
                    "called_at": _format_hospital_registration_called_at(lab_order.updated_at),
                }
            ],
        )
        self.assertEqual(snapshot["total_count"], 1)

    @patch("static.utils.functions.notifications.notify_android_tv", return_value=(True, {}))
    def test_refresh_sends_per_config_firebase_payloads(self, mock_notify):
        from vendors.hospital_tv import refresh_hospital_tv

        self._create_order(status="called", booking_no="LAB-12", utility=self.lab)
        self._create_order(status="called", booking_no="ORTHO-5", utility=self.ortho, token_no=2)

        lab_config = self._create_tv_config([self.lab])
        ortho_config = self._create_tv_config([self.ortho])
        lab_config.config_name = "Lab TV"
        lab_config.save(update_fields=["config_name"])
        ortho_config.config_name = "Ortho TV"
        ortho_config.save(update_fields=["config_name"])

        AndroidDevice.objects.create(
            token="lab-tv-token",
            mac_address="AA:BB:CC:DD:EE:01",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
            tv_config=lab_config,
        )
        AndroidDevice.objects.create(
            token="ortho-tv-token",
            mac_address="AA:BB:CC:DD:EE:02",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
            tv_config=ortho_config,
        )

        result = refresh_hospital_tv(self.vendor, start_dt=self.start_dt, end_dt=self.end_dt)

        self.assertTrue(result["success"])
        self.assertEqual(mock_notify.call_count, 2)

        payloads = [call.args[1] for call in mock_notify.call_args_list]
        token_sets = [set(payload["tokens"]) for payload in payloads]
        self.assertIn({"LAB-12"}, token_sets)
        self.assertIn({"ORTHO-5"}, token_sets)

        sent_token_groups = []
        for call in mock_notify.call_args_list:
            tokens = call.kwargs.get("fcm_tokens")
            sent_token_groups.append(set(tokens or []))
        self.assertIn({"lab-tv-token"}, sent_token_groups)
        self.assertIn({"ortho-tv-token"}, sent_token_groups)

    @patch("static.utils.functions.notifications.notify_android_tv", return_value=(True, {}))
    def test_refresh_no_department_selection_shows_all(self, mock_notify):
        from vendors.hospital_tv import refresh_hospital_tv

        self._create_order(status="called", booking_no="LAB-12", utility=self.lab)
        self._create_order(status="called", booking_no="ORTHO-5", utility=self.ortho, token_no=2)

        all_config = self._create_tv_config([])
        AndroidDevice.objects.create(
            token="all-dept-token",
            mac_address="AA:BB:CC:DD:EE:03",
            admin_outlet=self.admin_outlet,
            vendor=self.vendor,
            tv_config=all_config,
        )

        refresh_hospital_tv(self.vendor, start_dt=self.start_dt, end_dt=self.end_dt)

        mock_notify.assert_called_once()
        payload = mock_notify.call_args.args[1]
        self.assertEqual(set(payload["tokens"]), {"LAB-12", "ORTHO-5"})
