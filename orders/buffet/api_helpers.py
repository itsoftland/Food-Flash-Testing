"""
Dine Flash Buffet HTTP helpers.

Tracking URL only. Must NOT be used by other product flavours.
"""
from urllib.parse import urlencode

from django.conf import settings
from django.urls import NoReverseMatch, reverse


def build_buffet_tracking_url(request, vendor, token_no):
    """
    Absolute customer tracking URL for the existing Buffet home flow.

    Contract: /dine_flash_buffet/home/?token_no=<token_no>&vendor_id=<vendor_id>
    """
    params = urlencode(
        {
            "token_no": token_no,
            "vendor_id": vendor.vendor_id,
        }
    )
    project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
    try:
        tracking_path = reverse("home")
        return request.build_absolute_uri(f"{tracking_path}?{params}")
    except NoReverseMatch:
        return request.build_absolute_uri(f"/{project}/home/?{params}")
