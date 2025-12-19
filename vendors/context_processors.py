from django.conf import settings
from vendors.models import VendorConfig

def project_info(request):
    return {
        'PROJECT_NAME': getattr(settings, 'PROJECT_NAME', 'unknown'),
        'PROJECT_DISPLAY_NAME': getattr(settings, 'PROJECT_DISPLAY_NAME', 'My App'),
        'APP_VERSION': getattr(settings, 'APP_VERSION', 'dev')
    }

def utilities_visibility(request):
    """
    Determines whether the Utilities sidebar should be visible
    for the currently logged-in company (AdminOutlet).

    Rule:
    - Show only if the company has at least one vendor
      with `use_utilities = True` in VendorConfig.
    """

    # 1. User must be authenticated
    if not request.user.is_authenticated:
        return {"SHOW_UTILITIES_SIDEBAR": False}

    # 2. User must be a company (AdminOutlet user)
    admin_outlet = getattr(request.user, "admin_outlet", None)
    if not admin_outlet:
        return {"SHOW_UTILITIES_SIDEBAR": False}

    # 3. Check if ANY vendor under this company has utilities enabled
    utilities_enabled = VendorConfig.objects.filter(
        vendor__admin_outlet=admin_outlet,
        use_utilities=True
    ).exists()

    return {
        "SHOW_UTILITIES_SIDEBAR": utilities_enabled
    }
