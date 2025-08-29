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
