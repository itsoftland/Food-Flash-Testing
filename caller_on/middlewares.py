import logging

request_logger = logging.getLogger("django.request")

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        request_logger.info(
            f"{request.method} {request.get_full_path()} from {request.META.get('REMOTE_ADDR')} -> {response.status_code}"
        )
        return response

class CacheControlMiddleware:
    """
    Middleware to prevent caching of authenticated responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Prevent caching for authenticated users or paths that should be protected
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
            
        return response
