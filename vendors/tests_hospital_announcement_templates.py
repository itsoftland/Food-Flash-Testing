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

    def test_catalog_for_admin_omits_waiting(self):
        from vendors.hospital_announcement_templates import (
            ANNOUNCEMENT_TYPES,
            catalog_for_admin,
        )

        catalog = catalog_for_admin()
        ids = [t["id"] for t in catalog["types"]]
        # Waiting is not configurable in Company Admin (TTS path unused today).
        self.assertEqual(
            ids,
            [t for t in ANNOUNCEMENT_TYPES if t != "waiting"],
        )
        self.assertNotIn("waiting", ids)
        self.assertIn("waiting", ANNOUNCEMENT_TYPES)
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


@override_settings(PROJECT_NAME="hospital_flash")
class PreAnnouncementChatTemplateSerializerTests(SimpleTestCase):
    def test_blank_is_allowed(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={"vendor_id": 1, "pre_announcement_chat_template": ""}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["pre_announcement_chat_template"], "")

    def test_custom_requires_minutes_placeholder(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={"vendor_id": 1, "pre_announcement_chat_template": "Your turn is approaching."}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("pre_announcement_chat_template", serializer.errors)

    def test_custom_with_minutes_is_accepted(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={
                "vendor_id": 1,
                "pre_announcement_chat_template": (
                    "Your turn is approaching. Expected wait: {minutes} minute(s)"
                ),
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["pre_announcement_chat_template"],
            "Your turn is approaching. Expected wait: {minutes} minute(s)",
        )


@override_settings(PROJECT_NAME="food_flash")
class PreAnnouncementChatTemplateNonHospitalTests(SimpleTestCase):
    def test_update_serializer_clears_on_non_hospital(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={
                "vendor_id": 1,
                "phone_number_enabled": True,
                "pre_announcement_chat_template": "Wait {minutes} minutes",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get("pre_announcement_chat_template"), "")


@override_settings(PROJECT_NAME="hospital_flash")
class CompletedChatTemplateSerializerTests(SimpleTestCase):
    def test_blank_is_allowed(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={"vendor_id": 1, "completed_chat_template": ""}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["completed_chat_template"], "")

    def test_custom_without_department_is_accepted(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={"vendor_id": 1, "completed_chat_template": "Visit completed successfully."}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["completed_chat_template"],
            "Visit completed successfully.",
        )

    def test_custom_with_department_is_accepted(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={
                "vendor_id": 1,
                "completed_chat_template": "Thank you for visiting {department}",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["completed_chat_template"],
            "Thank you for visiting {department}",
        )


@override_settings(PROJECT_NAME="food_flash")
class CompletedChatTemplateNonHospitalTests(SimpleTestCase):
    def test_update_serializer_clears_on_non_hospital(self):
        from company.serializer.vendor_config import VendorConfigUpdateSerializer

        serializer = VendorConfigUpdateSerializer(
            data={
                "vendor_id": 1,
                "phone_number_enabled": True,
                "completed_chat_template": "Thank you for visiting {department}",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get("completed_chat_template"), "")

    def test_read_serializer_omits_field(self):
        from company.serializers import VendorConfigSerializer

        fields = VendorConfigSerializer().get_fields()
        self.assertNotIn("completed_chat_template", fields)
        self.assertNotIn("called_chat_template", fields)
        self.assertNotIn("pre_announcement_chat_template", fields)

    def test_read_serializer_omits_field_on_other_flavours(self):
        from django.test.utils import override_settings as override_project
        from company.serializers import VendorConfigSerializer

        for project_name in ("dine_flash", "dine_flash_buffet", "airline_flash"):
            with override_project(PROJECT_NAME=project_name):
                fields = VendorConfigSerializer().get_fields()
                self.assertNotIn("completed_chat_template", fields, project_name)


@override_settings(PROJECT_NAME="hospital_flash")
class CompletedChatTemplateReadSerializerTests(SimpleTestCase):
    def test_read_serializer_includes_hospital_chat_templates(self):
        from company.serializers import VendorConfigSerializer

        fields = VendorConfigSerializer().get_fields()
        self.assertIn("completed_chat_template", fields)
        self.assertIn("called_chat_template", fields)
        self.assertIn("pre_announcement_chat_template", fields)
