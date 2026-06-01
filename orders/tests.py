from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from orders.views import check_status
from vendors.models import Order


class BuffetCheckStatusTests(SimpleTestCase):
    @patch("orders.views.project_name", "dine_flash_buffet")
    @patch.object(Order.objects, "get")
    def test_unknown_token_returns_400_without_auto_create(self, mock_get):
        mock_get.side_effect = Order.DoesNotExist

        factory = APIRequestFactory()
        request = factory.post(
            "/check-status/",
            {"token_no": 400, "vendor_id": 1},
            format="json",
        )

        with patch("orders.views.OrdersSerializer") as mock_serializer:
            response = check_status(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid token", response.data["error"])
        mock_serializer.assert_not_called()
