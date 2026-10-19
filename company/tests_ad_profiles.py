"""
Advertisement profile detail/update API tests.
"""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from company.ad_profile_edit import AD_PROFILE_EDIT_PROJECTS
from vendors.models import (
    AdminOutlet,
    AdvertisementImage,
    AdvertisementProfile,
    AdvertisementProfileAssignment,
    AdvertisementSlot,
    Vendor,
    VendorConfig,
)


@override_settings(PROJECT_NAME="dine_flash")
class AdvertisementProfileUpdateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="adprofile-admin", password="pass1234")
        self.other_user = User.objects.create_user(username="other-admin", password="pass1234")
        self.client = APIClient()
        self.client.login(username="adprofile-admin", password="pass1234")

        self.admin_outlet = AdminOutlet.objects.create(
            user=self.user,
            customer_name="Ad Profile Co",
            customer_id=93001,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.other_outlet = AdminOutlet.objects.create(
            user=self.other_user,
            customer_name="Other Co",
            customer_id=93002,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )

        self.vendor = Vendor.objects.create(
            admin_outlet=self.admin_outlet,
            name="Outlet 1",
            alias_name="O1",
            location="CityA",
            place_id="place-ad",
            vendor_id=930001,
            location_id="AD1",
            menus="[]",
        )
        VendorConfig.objects.create(vendor=self.vendor)

        self.image1 = AdvertisementImage.objects.create(
            admin_outlet=self.admin_outlet,
            image=SimpleUploadedFile("ad1.jpg", b"img1", content_type="image/jpeg"),
        )
        self.image2 = AdvertisementImage.objects.create(
            admin_outlet=self.admin_outlet,
            image=SimpleUploadedFile("ad2.jpg", b"img2", content_type="image/jpeg"),
        )

        self.profile = AdvertisementProfile.objects.create(
            admin_outlet=self.admin_outlet,
            name="Breakfast Ads",
            days_active=["Monday", "Tuesday"],
            priority=2,
        )
        self.profile.images.set([self.image1])
        AdvertisementSlot.objects.create(
            profile=self.profile,
            start_time="09:00",
            end_time="11:00",
        )
        AdvertisementProfileAssignment.objects.create(profile=self.profile, vendor=self.vendor)

        self.other_profile = AdvertisementProfile.objects.create(
            admin_outlet=self.other_outlet,
            name="Other Outlet Profile",
            days_active=["Friday"],
            priority=1,
        )
        self.other_outlet_image = AdvertisementImage.objects.create(
            admin_outlet=self.other_outlet,
            image=SimpleUploadedFile("other_ad.jpg", b"other", content_type="image/jpeg"),
        )

        self.no_outlet_user = User.objects.create_user(username="no-outlet-user", password="pass1234")

    def _detail_url(self, profile_id):
        return reverse("company:ad_profile_detail", args=[profile_id])

    def _update_url(self, profile_id):
        return reverse("company:ad_profile_update", args=[profile_id])

    def _payload(self, **overrides):
        data = {
            "name": "Updated Name",
            "date_start": None,
            "date_end": None,
            "days_active": ["Wednesday"],
            "priority": 3,
            "image_ids": [self.image2.id],
            "time_slots": [{"start": "10:00", "end": "12:00"}],
        }
        data.update(overrides)
        return data

    def test_detail_returns_time_slots_and_images(self):
        response = self.client.get(self._detail_url(self.profile.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = response.json()["profile"]
        self.assertEqual(profile["name"], "Breakfast Ads")
        self.assertEqual(len(profile["time_slots"]), 1)
        self.assertEqual(profile["time_slots"][0]["start"], "09:00")
        self.assertEqual(len(profile["images"]), 1)

    def test_update_success(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            self._payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.name, "Updated Name")
        self.assertEqual(self.profile.days_active, ["Wednesday"])
        self.assertEqual(self.profile.priority, 3)
        self.assertEqual(list(self.profile.images.values_list("id", flat=True)), [self.image2.id])
        slots = list(self.profile.slots.order_by("start_time"))
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].start_time.strftime("%H:%M"), "10:00")
        self.assertTrue(
            AdvertisementProfileAssignment.objects.filter(
                profile=self.profile, vendor=self.vendor
            ).exists()
        )

    def test_update_rejects_invalid_image_ids(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            self._payload(image_ids=[999999]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_rejects_overlapping_time_slots(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            self._payload(
                time_slots=[
                    {"start": "09:00", "end": "11:00"},
                    {"start": "10:00", "end": "12:00"},
                ]
            ),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_requires_dates_or_days(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            self._payload(days_active=[], date_start=None, date_end=None),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_update_profile_from_other_outlet(self):
        response = self.client.patch(
            self._update_url(self.other_profile.id),
            self._payload(),
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_detail_not_found_for_other_outlet(self):
        response = self.client.get(self._detail_url(self.other_profile.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_profile_still_works(self):
        url = reverse("company:create_advertisement_profile")
        payload = {
            "name": "New Profile",
            "days_active": ["Thursday"],
            "priority": 1,
            "image_ids": [self.image1.id],
            "time_slots": [],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            AdvertisementProfile.objects.filter(admin_outlet=self.admin_outlet, name="New Profile").exists()
        )

    def test_create_requires_image_ids_field(self):
        url = reverse("company:create_advertisement_profile")
        payload = {
            "name": "Missing Images Field",
            "days_active": ["Thursday"],
            "priority": 1,
            "time_slots": [],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_requires_time_slots_field(self):
        url = reverse("company:create_advertisement_profile")
        payload = {
            "name": "Missing Slots Field",
            "days_active": ["Thursday"],
            "priority": 1,
            "image_ids": [self.image1.id],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_omitting_image_ids_and_time_slots_preserves_them(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            {"name": "Renamed Only"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.name, "Renamed Only")
        self.assertEqual(list(self.profile.images.values_list("id", flat=True)), [self.image1.id])
        self.assertEqual(self.profile.slots.count(), 1)

    def test_patch_explicit_empty_image_ids_clears_images(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            self._payload(image_ids=[]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.images.count(), 0)

    def test_rejects_other_outlet_image_on_create(self):
        url = reverse("company:create_advertisement_profile")
        payload = {
            "name": "Bad Image Create",
            "days_active": ["Monday"],
            "priority": 1,
            "image_ids": [self.other_outlet_image.id],
            "time_slots": [],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_other_outlet_image_on_update(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            self._payload(image_ids=[self.other_outlet_image.id]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_detail_and_update_are_rejected(self):
        self.client.logout()
        detail = self.client.get(self._detail_url(self.profile.id))
        update = self.client.patch(
            self._update_url(self.profile.id),
            {"name": "Should Fail"},
            format="json",
        )
        self.assertIn(
            detail.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertIn(
            update.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_user_without_admin_outlet_cannot_detail_or_update(self):
        self.client.logout()
        self.client.login(username="no-outlet-user", password="pass1234")
        detail = self.client.get(self._detail_url(self.profile.id))
        update = self.client.patch(
            self._update_url(self.profile.id),
            {"name": "Should Fail"},
            format="json",
        )
        self.assertEqual(detail.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update.status_code, status.HTTP_403_FORBIDDEN)

    def test_clear_time_slots_on_update(self):
        response = self.client.patch(
            self._update_url(self.profile.id),
            self._payload(time_slots=[]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.slots.count(), 0)

    def test_detail_and_update_enabled_for_all_permitted_flavours(self):
        self.assertEqual(
            AD_PROFILE_EDIT_PROJECTS,
            frozenset({"dine_flash", "dine_flash_buffet", "hospital_flash"}),
        )
        for flavour in sorted(AD_PROFILE_EDIT_PROJECTS):
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                detail = self.client.get(self._detail_url(self.profile.id))
                self.assertEqual(detail.status_code, status.HTTP_200_OK)

                update = self.client.patch(
                    self._update_url(self.profile.id),
                    {"name": f"Updated under {flavour}"},
                    format="json",
                )
                self.assertEqual(update.status_code, status.HTTP_200_OK)
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.name, f"Updated under {flavour}")

    @override_settings(PROJECT_NAME="food_flash")
    def test_detail_and_update_return_404_for_unsupported_flavour(self):
        self.profile.name = "Breakfast Ads"
        self.profile.save(update_fields=["name"])

        detail = self.client.get(self._detail_url(self.profile.id))
        update = self.client.patch(
            self._update_url(self.profile.id),
            {"name": "Should Not Apply"},
            format="json",
        )
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(update.status_code, status.HTTP_404_NOT_FOUND)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.name, "Breakfast Ads")

    @override_settings(PROJECT_NAME="airline_flash")
    def test_create_and_list_still_work_for_unsupported_flavour(self):
        list_response = self.client.get(reverse("company:get_ad_profile"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            reverse("company:create_advertisement_profile"),
            {
                "name": "Created On Airline",
                "days_active": ["Monday"],
                "priority": 1,
                "image_ids": [self.image1.id],
                "time_slots": [],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)


class AdvertisementProfileListEditUiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="profile-list-ui", password="pass1234")
        AdminOutlet.objects.create(
            user=self.user,
            customer_name="UI Test Co",
            customer_id=94001,
            authentication_status="Approve",
            product_to_date=timezone.now() + timezone.timedelta(days=30),
        )
        self.web_client = Client()
        self.web_client.login(username="profile-list-ui", password="pass1234")

    def test_profile_list_includes_edit_ui_for_permitted_flavours(self):
        for flavour in sorted(AD_PROFILE_EDIT_PROJECTS):
            with self.subTest(flavour=flavour), override_settings(PROJECT_NAME=flavour):
                response = self.web_client.get(reverse("company:profile_list"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="editProfileModal"')
                self.assertContains(response, "window.AD_PROFILE_EDIT_ENABLED = true")

    @override_settings(PROJECT_NAME="food_flash")
    def test_profile_list_excludes_edit_ui_for_unsupported_flavour(self):
        response = self.web_client.get(reverse("company:profile_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="editProfileModal"')
        self.assertContains(response, "window.AD_PROFILE_EDIT_ENABLED = false")
