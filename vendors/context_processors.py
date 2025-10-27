from django.conf import settings

def project_info(request):
    return {
        'PROJECT_NAME': getattr(settings, 'PROJECT_NAME', 'unknown'),
        'PROJECT_DISPLAY_NAME': getattr(settings, 'PROJECT_DISPLAY_NAME', 'My App'),
        'APP_VERSION': getattr(settings, 'APP_VERSION', 'dev')
    }
