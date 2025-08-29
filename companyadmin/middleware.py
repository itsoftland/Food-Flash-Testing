from django.http import JsonResponse
from django.shortcuts import render
from vendors.models import SiteConfig

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            config = SiteConfig.objects.first()
            if config and config.maintenance_mode:
                # Check if 'api/' is in the URL path (e.g., /vendors/api/, /company/api/)
                if '/api/' in request.path:
                    return JsonResponse({
                        'status': 'maintenance',
                        'message': 'The system is under maintenance. Please try again shortly.'
                    }, status=503)

                # For all non-API views (HTML pages), show maintenance page
                return render(request, 'companyadmin/maintenance.html', status=503)
        except Exception as e:
            # Optional: log the exception
            pass  # Fail-safe: let the app run if DB has an issue

        return self.get_response(request)
