"""
Dine Flash Buffet: manager utility_list includes active UtilityOption rows.

Flavour isolation: only PROJECT_NAME == dine_flash_buffet adds `options`.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate


def _opt(pk, name, is_active=True):
    return SimpleNamespace(id=pk, name=name, is_active=is_active)


def _util(pk, name="Dosa", options=None, prefix=None):
    util = SimpleNamespace(
        id=pk,
        utility_name=name,
        display_name=name,
        display_code=name[:4].upper(),
        token_mode="continuous",
        prefix=prefix,
    )
    util.options = MagicMock()
    util.options.all.return_value = list(options or [])
    return util


@override_settings(PROJECT_NAME="dine_flash_buffet")
class BuffetManagerUtilityListOptionsTests(SimpleTestCase):
    def setUp(self):
        import manager.views as views

        self.views = views
        self._project_patcher = patch.object(views, "project_name", "dine_flash_buffet")
        self._project_patcher.start()
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(username="buffet_mgr", is_authenticated=True)

    def tearDown(self):
        self._project_patcher.stop()

    def _call(self, utilities):
        vendor = SimpleNamespace(id=1, vendor_id="B001")
        qs = MagicMock()
        qs.order_by.return_value = qs
        qs.prefetch_related.return_value = utilities

        with patch.object(self.views, "_resolve_vendor_for_manager", return_value=vendor), patch.object(
            self.views.Utility.objects, "filter", return_value=qs
        ), patch.object(self.views, "_log_slow_manager_api"):
            request = self.factory.get("/dine_flash_buffet/manager/api/utility_list/")
            force_authenticate(request, user=self.user)
            return self.views.manager_utility_list(request)

    def test_includes_active_options_per_utility(self):
        utilities = [
            _util(
                1,
                "Dosa",
                options=[
                    _opt(10, "Plain", True),
                    _opt(11, "Masala", True),
                    _opt(12, "Retired", False),
                ],
            ),
            _util(2, "Idli", options=[]),
        ]
        response = self._call(utilities)
        self.assertEqual(response.status_code, 200)
        body = response.data
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(body["utilities"]), 2)

        dosa = body["utilities"][0]
        self.assertEqual(dosa["id"], 1)
        self.assertEqual(dosa["utility_name"], "Dosa")
        self.assertEqual(dosa["display_name"], "Dosa")
        self.assertEqual(dosa["display_code"], "DOSA")
        self.assertEqual(dosa["token_mode"], "continuous")
        self.assertIsNone(dosa["prefix"])
        self.assertEqual(
            dosa["options"],
            [
                {"id": 10, "name": "Plain", "is_active": True},
                {"id": 11, "name": "Masala", "is_active": True},
            ],
        )

        idli = body["utilities"][1]
        self.assertEqual(idli["id"], 2)
        self.assertEqual(idli["options"], [])

    def test_options_are_scoped_to_own_utility(self):
        utilities = [
            _util(1, "Dosa", options=[_opt(10, "Plain")]),
            _util(2, "Idli", options=[_opt(20, "Ghee")]),
        ]
        body = self._call(utilities).data
        self.assertEqual([o["id"] for o in body["utilities"][0]["options"]], [10])
        self.assertEqual([o["id"] for o in body["utilities"][1]["options"]], [20])


@override_settings(PROJECT_NAME="food_flash")
class OtherFlavourManagerUtilityListNoOptionsTests(SimpleTestCase):
    def setUp(self):
        import manager.views as views

        self.views = views
        self._project_patcher = patch.object(views, "project_name", "food_flash")
        self._project_patcher.start()
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(username="ff_mgr", is_authenticated=True)

    def tearDown(self):
        self._project_patcher.stop()

    def test_food_flash_utility_list_has_no_options_key(self):
        vendor = SimpleNamespace(id=1, vendor_id="F001")
        util = _util(1, "Counter")
        qs = MagicMock()
        qs.order_by.return_value = [util]

        with patch.object(self.views, "_resolve_vendor_for_manager", return_value=vendor), patch.object(
            self.views.Utility.objects, "filter", return_value=qs
        ), patch.object(self.views, "_log_slow_manager_api"):
            request = self.factory.get("/food_flash/manager/api/utility_list/")
            force_authenticate(request, user=self.user)
            response = self.views.manager_utility_list(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row = response.data["utilities"][0]
        self.assertNotIn("options", row)
        self.assertEqual(
            set(row.keys()),
            {
                "id",
                "utility_name",
                "display_name",
                "display_code",
                "token_mode",
                "prefix",
            },
        )
