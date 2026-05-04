import threading
import time

from django.http import JsonResponse
from django.shortcuts import render
from vendors.models import SiteConfig

# Avoid a SiteConfig DB round-trip on every request (hot path for APIs).
_SITE_CONFIG_TTL_SEC = 20.0
_site_config_cache = {"expires_monotonic": 0.0, "maintenance": False}
_site_config_lock = threading.Lock()


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        now = time.monotonic()
        if now >= _site_config_cache["expires_monotonic"]:
            with _site_config_lock:
                if now >= _site_config_cache["expires_monotonic"]:
                    try:
                        row = SiteConfig.objects.only("maintenance_mode").first()
                        _site_config_cache["maintenance"] = bool(
                            row and row.maintenance_mode
                        )
                    except Exception:
                        # Fail open; refresh TTL so a bad DB does not stampede queries.
                        _site_config_cache["maintenance"] = False
                    _site_config_cache["expires_monotonic"] = (
                        time.monotonic() + _SITE_CONFIG_TTL_SEC
                    )

        if _site_config_cache["maintenance"]:
            # Check if 'api/' is in the URL path (e.g., /vendors/api/, /company/api/)
            if '/api/' in request.path:
                return JsonResponse({
                    'status': 'maintenance',
                    'message': 'The system is under maintenance. Please try again shortly.'
                }, status=503)

            # For all non-API views (HTML pages), show maintenance page
            return render(request, 'companyadmin/maintenance.html', status=503)

        return self.get_response(request)
