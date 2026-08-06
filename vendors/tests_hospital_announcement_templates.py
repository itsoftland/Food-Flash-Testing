"""Unit tests for Hospital Flash announcement template helpers."""

from django.test import SimpleTestCase, override_settings


@override_settings(PROJECT_NAME="hospital_flash")
class HospitalAnnouncementTemplatesTests(SimpleTestCase):
    def test_normalize_empty_preserves_backward_compat(self):
        from vendors.hospital_announcement_templates import normalize_announcement_templates

        self.assertEqual(normalize_announcement_templates(None), {})
        self.assertEqual(normalize_announcement_templates({}), {})
        self.assertEqual(normalize_announcement_templates("bad"), {})

    def test_normalize_keeps_custom_and_template_selection(self):
        from vendors.hospital_announcement_templates import normalize_announcement_templates

        raw = {
            "called": {"selected": "template_a", "custom_text": ""},
            "waiting": {
                "selected": "custom",
                "custom_text": "Token {token} to {department}",
            },
            "ignored_type": {"selected": "default"},
            "completed": {"selected": "default", "custom_text": ""},
        }
        normalized = normalize_announcement_templates(raw)
        self.assertEqual(
            normalized,
            {
                "called": {"selected": "template_a", "custom_text": ""},
                "waiting": {
                    "selected": "custom",
                    "custom_text": "Token {token} to {department}",
                },
            },
        )

    def test_normalize_invalid_selection_falls_back_to_default(self):
        from vendors.hospital_announcement_templates import normalize_announcement_templates

        raw = {"called": {"selected": "not_a_real_option", "custom_text": "keep me"}}
        normalized = normalize_announcement_templates(raw)
        self.assertEqual(
            normalized,
            {"called": {"selected": "default", "custom_text": "keep me"}},
        )

    def test_get_vendor_announcement_templates_missing_config(self):
        from types import SimpleNamespace

        from vendors.hospital_announcement_templates import get_vendor_announcement_templates

        self.assertEqual(get_vendor_announcement_templates(None), {})
        self.assertEqual(get_vendor_announcement_templates(SimpleNamespace()), {})
        vendor = SimpleNamespace(config=SimpleNamespace())
        self.assertEqual(get_vendor_announcement_templates(vendor), {})

    def test_catalog_for_admin_has_all_types(self):
        from vendors.hospital_announcement_templates import (
            ANNOUNCEMENT_TYPES,
            catalog_for_admin,
        )

        catalog = catalog_for_admin()
        ids = [t["id"] for t in catalog["types"]]
        self.assertEqual(ids, list(ANNOUNCEMENT_TYPES))
        for type_def in catalog["types"]:
            option_ids = [o["id"] for o in type_def["options"]]
            self.assertEqual(
                option_ids, ["default", "template_a", "template_b", "custom"]
            )


@override_settings(PROJECT_NAME="food_flash")
class HospitalAnnouncementTemplatesNonHospitalTests(SimpleTestCase):
    def test_update_serializer_ignores_on_non_hospital(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={
                "vendor_id": 1,
                "phone_number_enabled": True,
                "announcement_templates": {
                    "called": {"selected": "template_a", "custom_text": ""}
                },
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        # Normalized to empty; view strips before save on non-hospital.
        self.assertEqual(serializer.validated_data.get("announcement_templates"), {})
