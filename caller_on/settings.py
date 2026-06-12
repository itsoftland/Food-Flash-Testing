import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta
import logging

# Load environment variables from .env file
load_dotenv()

SECURE_CROSS_ORIGIN_OPENER_POLICY = None

# === BASE DIRECTORIES ===
BASE_DIR = Path(__file__).resolve().parent.parent

# === SECURITY SETTINGS ===
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS").split(",")

CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS").split(",")
CORS_ALLOW_ALL_ORIGINS = True

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False

# === FIREBASE ===
FIREBASE_SERVICE_ACCOUNT_FILE = BASE_DIR / 'firebase' / 'service-account.json'
FIREBASE_PROJECT_ID = 'food-flash-711f9'

# === VAPID KEYS FOR PUSH NOTIFICATIONS ===
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {
    "sub": "mailto:sanju.softland@gmail.com"
}
VAPID_ADMIN_EMAIL = os.getenv("VAPID_ADMIN_EMAIL")
# === LICENSE PORTAL URL ===

LICENSE_PORTAL_URL = os.getenv("LICENSE_PORTAL_URL")

# IoT Hub configs
IOTHUB_NAME = os.getenv("IOTHUB_NAME")
IOTHUB_HOSTNAME = os.getenv("IOTHUB_HOSTNAME")
IOTHUB_POLICY_NAME = os.getenv("IOTHUB_POLICY_NAME")
IOTHUB_POLICY_KEY = os.getenv("IOTHUB_POLICY_KEY")
IOTHUB_API_VERSION = os.getenv("IOTHUB_API_VERSION")
IOTHUB_PRIMARY_KEY = os.getenv("IOTHUB_PRIMARY_KEY")
IOTHUB_SECONDARY_KEY = os.getenv("IOTHUB_SECONDARY_KEY")
IOTHUB_PRIMARY_CONNECTION_STRING = os.getenv("IOTHUB_PRIMARY_CONNECTION_STRING")
IOTHUB_SECONDARY_CONNECTION_STRING = os.getenv("IOTHUB_SECONDARY_CONNECTION_STRING")
IOTHUB_DEVICE_API_VERSION = os.getenv("IOTHUB_DEVICE_API_VERSION")
DATA_UPLOAD_MAX_NUMBER_FILES = int(os.getenv("DATA_UPLOAD_MAX_NUMBER_FILES", 100))
PROJECT_NAME = os.getenv("PROJECT_NAME")
print("PROJECT_NAME:", PROJECT_NAME)
PROJECT_DISPLAY_NAME = os.getenv("PROJECT_DISPLAY_NAME")
APP_VERSION = os.getenv("APP_VERSION")

# Dine Flash TV: last-resort lookback (hours) only if business-day + calendar filters match no rows.
# Set to 0 to disable. Default 24 limits stale rows vs the old 72h fallback.
DINE_FLASH_TV_SNAPSHOT_FALLBACK_HOURS = int(os.getenv("DINE_FLASH_TV_SNAPSHOT_FALLBACK_HOURS", "24"))


# === APPLICATIONS ===
INSTALLED_APPS = [
    # Core Django apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'corsheaders',
    'django_extensions',
    'django.contrib.humanize',
    'rest_framework_simplejwt.token_blacklist', 

    # Custom apps
    'orders',
    'vendors',
    'company',
    'companyadmin',
]

# === MIDDLEWARE ===
MIDDLEWARE = [
    'companyadmin.middleware.MaintenanceModeMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'caller_on.middlewares.RequestLoggingMiddleware',
    'caller_on.middlewares.CacheControlMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]



# Dine Flash only: outlet-manager API wall-clock tracing (no-op for other flavours).
if (PROJECT_NAME or "").strip().lower() == "dine_flash":
    MIDDLEWARE.insert(
        3,
        "manager.middleware.dine_flash_manager_perf.DineFlashManagerPerfMiddleware",
    )



# === TEMPLATES ===
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'vendors.context_processors.project_info',
                'vendors.context_processors.utilities_visibility',
                'core.context_processors.project_labels',
                'core.context_processors.project_icons',
                'core.context_processors.project_roles',
            ]
        },
    },
]


ROOT_URLCONF = 'caller_on.urls'
WSGI_APPLICATION = 'caller_on.wsgi.application'

# === DATABASE ===
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv("DB_NAME"),
        'USER': os.getenv("DB_USER"),
        'PASSWORD': os.getenv("DB_PASSWORD"),
        'HOST': os.getenv("DB_HOST"),
        'PORT': os.getenv("DB_PORT"),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
        'CONN_MAX_AGE': int(os.getenv("DB_CONN_MAX_AGE", "60")),
        'CONN_HEALTH_CHECKS': os.getenv("DB_CONN_HEALTH_CHECKS", "true").lower() in ("true", "1", "yes"),
    }
}

# === REST FRAMEWORK ===
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}
# === JWT Configurations ===
def _jwt_access_token_lifetime():
    if PROJECT_NAME == "dine_flash_buffet":
        # KDS / utility apps: long-lived access token (default 24h).
        hours = int(os.getenv("DINE_FLASH_BUFFET_ACCESS_TOKEN_HOURS", "24"))
        return timedelta(hours=max(1, hours))
    return timedelta(minutes=int(os.getenv("ACCESS_TOKEN_LIFETIME", "5")))


def _jwt_refresh_token_lifetime():
    if PROJECT_NAME == "dine_flash_buffet":
        days = int(os.getenv("DINE_FLASH_BUFFET_REFRESH_TOKEN_DAYS", os.getenv("REFRESH_TOKEN_LIFETIME", "7")))
        return timedelta(days=max(1, days))
    return timedelta(days=int(os.getenv("REFRESH_TOKEN_LIFETIME", "1")))


SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': _jwt_access_token_lifetime(),
    'REFRESH_TOKEN_LIFETIME': _jwt_refresh_token_lifetime(),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}


def _default_log_dir() -> Path:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _resolve_external_log_dir() -> Path:
    """
    Resolve EXTERNAL_LOG_DIR from .env for the current OS.

    On Windows/IIS, Linux paths (/home/...) or slash-drive paths (/D:/...) from .env
    cause OSError WinError 123 (invalid path like '\\D:'). Fall back to BASE_DIR/logs.
    """
    raw = (os.getenv("EXTERNAL_LOG_DIR") or "").strip().strip('"').strip("'")
    if not raw or raw in (".", ".env"):
        return _default_log_dir()

    normalized = raw.replace("\\", "/").lower().rstrip("/")
    if normalized.endswith("/.env") or normalized == ".env":
        return _default_log_dir()

    # /D:/foo or /D:\foo → D:\foo (common mis-copy on Windows)
    if os.name == "nt" and len(raw) >= 3 and raw[0] == "/" and raw[1].isalpha() and raw[2] == ":":
        raw = raw[1:]

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (BASE_DIR / candidate).resolve()

    # Never write logs inside .env (misconfigured EXTERNAL_LOG_DIR=.env)
    if any(part.lower() == ".env" for part in candidate.parts):
        return _default_log_dir()

    if os.name == "nt":
        parts = candidate.parts
        # Unix-only absolute paths (/home, /var, …) are invalid on Windows
        if parts and parts[0] == "/" and not (len(parts) > 1 and len(parts[1]) == 1 and parts[1].endswith(":")):
            return _default_log_dir()
        drive = getattr(candidate, "drive", "") or ""
        if drive and len(drive) == 2 and drive[1] == ":" and not os.path.isdir(drive + "\\"):
            return _default_log_dir()

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except OSError:
        return _default_log_dir()


EXTERNAL_LOG_DIR = _resolve_external_log_dir()

from datetime import datetime
# === LOGGING BASE STRUCTURE ===
if PROJECT_NAME == 'airline_flash':
    BASE_LOG_DIR = EXTERNAL_LOG_DIR / 'airline_flash_logs'
elif PROJECT_NAME == 'dine_flash_buffet':
    BASE_LOG_DIR = EXTERNAL_LOG_DIR / 'dine_flash_buffet_logs'
elif PROJECT_NAME == 'dine_flash':
    BASE_LOG_DIR = EXTERNAL_LOG_DIR / 'dine_flash_logs'
else:
    BASE_LOG_DIR = EXTERNAL_LOG_DIR / 'foodflash_logs'

# Create nested folders: year/month/day
today = datetime.now()
year_folder = str(today.year)
month_folder = today.strftime("%B")  
day_folder = f"{today.day:02d}"

LOG_DIR = BASE_LOG_DIR / year_folder / month_folder / day_folder
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Last resort: keep app bootable even if daily log folder cannot be created
    LOG_DIR = EXTERNAL_LOG_DIR
    LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "error.log",
            "formatter": "verbose",
        },
        "requests_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "requests.log",
            "formatter": "verbose",
        },
        "vendors_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "vendors.log",
            "formatter": "verbose",
        },
        "orders_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "orders.log",
            "formatter": "verbose",
        },
        "managers_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "managers.log",
            "formatter": "verbose",
        },
        "company_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": LOG_DIR / "company.log",
            "formatter": "verbose",
        },
        "fcm_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "fcm.log"),
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["file"],
            "level": "ERROR",  # keep Django internals quieter
            "propagate": True,
        },
        "django.request": {
            "handlers": ["requests_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.views": {
            "handlers": ["vendors_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.utils": {
            "handlers": ["vendors_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.mqtt_client": {
            "handlers": ["vendors_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.order_utils": {
            "handlers": ["vendors_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.services.order_service": {
            "handlers": ["vendors_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.services.send_to_iot": {
            "handlers": ["vendors_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.signals": {
            "handlers": ["vendors_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "vendors.dine_flash_tv_fcm": {
            "handlers": ["vendors_file", "managers_file", "fcm_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "orders.views": {
            "handlers": ["orders_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "orders.buffet_views": {
            "handlers": ["orders_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "orders.utils": {
            "handlers": ["orders_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "orders.scheduler": {
            "handlers": ["orders_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "manager.views": {
            "handlers": ["managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "manager.buffet_views": {
            "handlers": ["managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "manager.dine_flash_perf": {
            "handlers": ["managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "static.utils.functions.queries": {
            "handlers": ["orders_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "static.utils.functions.notifications": {
            "handlers": ["orders_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "static.utils.functions.utils": {
            "handlers": ["orders_file", "managers_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "company.views": {
            "handlers": ["company_file"],
            "level": "DEBUG",
            "propagate": False, 
        },
        "companyadmin.views": {
            "handlers": ["company_file"],
            "level": "DEBUG",
            "propagate": False, 
        },
        "dine_flash.fcm": {
            "handlers": ["fcm_file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# During local dev, also print WARNING+ from selected loggers to the runserver terminal
# (they still go to files above). Snapshot fallback messages use vendors.utils.
if DEBUG:
    LOGGING["handlers"]["console"] = {
        "level": "WARNING",
        "class": "logging.StreamHandler",
        "formatter": "verbose",
    }
    for _logger_name in ("vendors.utils", "static.utils.functions.utils"):
        _lg = LOGGING["loggers"].get(_logger_name)
        if _lg and "console" not in _lg["handlers"]:
            _lg["handlers"] = list(_lg["handlers"]) + ["console"]


# === PASSWORD VALIDATION ===
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# === TIME & LOCALIZATION ===
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Dine Flash TV QR: must match Android QrPayloadHelper.QR_ENCRYPTION_SECRET
QR_ENCRYPTION_SECRET = os.getenv("QR_ENCRYPTION_SECRET", "qflash-tv-qr-payload-v1")

# === STATIC & MEDIA FILES ===
STATIC_URL = "/"+PROJECT_NAME +'/static/'
# To support project-level static
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),  # Project-level static folder
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
if DEBUG:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
else:
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'


MEDIA_URL = "/"+PROJECT_NAME +'/media/'
MEDIA_ROOT = BASE_DIR / 'media'
LOGIN_URL = "/"+PROJECT_NAME +'/login/'


# === DEFAULT PRIMARY KEY FIELD TYPE ===
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'