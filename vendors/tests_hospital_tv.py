"""
Hospital Flash TV MVP unit tests.

Covers payload building, query rules, transport dispatch, and manager trigger wiring.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from vendors.models import AdminOutlet, Order, Vendor, VendorConfig


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

    @patch("vendors.services.order_service.send_order_update", return_value=True)
    def test_mqtt_dispatch_path(self, mock_send):
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
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
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

    @patch("vendors.services.order_service.send_order_update", return_value=True)
    @patch("vendors.order_utils.get_last_tokens")
    def test_no_dependency_on_get_last_tokens(self, mock_get_last_tokens, mock_send):
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
        mock_send.assert_called_once()

    @patch("vendors.services.order_service.send_order_update", return_value=False)
    def test_mqtt_failure_does_not_raise(self, mock_send):
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
        mock_send.assert_called_once()


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
