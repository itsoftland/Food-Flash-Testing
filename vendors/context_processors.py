from django.conf import settings

def project_name(request):
    return {
        'PROJECT_NAME': getattr(settings, 'PROJECT_NAME')
    }
