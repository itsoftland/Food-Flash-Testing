import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

# Load environment variables from .env file
load_dotenv()

# === BASE DIRECTORIES ===
BASE_DIR = Path(__file__).resolve().parent.parent

# === SECURITY SETTINGS ===
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'fallback-secret-key')
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS").split(",")

CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "https://calleron.softlandindia.net").split(",")
CORS_ALLOW_ALL_ORIGINS = True

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True

# === FIREBASE ===
FIREBASE_SERVICE_ACCOUNT_FILE = BASE_DIR / 'firebase' / 'service-account.json'
FIREBASE_PROJECT_ID = 'food-flash-711f9'

# === VAPID KEYS FOR PUSH NOTIFICATIONS ===
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS = {
    "sub": "mailto:sanju.softland@gmail.com"
}
# === LICENSE PORTAL URL ===

LICENSE_PORTAL_URL = os.getenv("LICENSE_PORTAL_URL", "http://licencemanagement.softlandindia.net/public/login")


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
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

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
            ],
        },
    },
]

ROOT_URLCONF = 'caller_on.urls'
WSGI_APPLICATION = 'caller_on.wsgi.application'

# === DATABASE ===
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv("DB_NAME", "my_project_db"),
        'USER': os.getenv("DB_USER", "caller_on"),
        'PASSWORD': os.getenv("DB_PASSWORD", "sil@2025"),
        'HOST': os.getenv("DB_HOST", "localhost"),
        'PORT': os.getenv("DB_PORT", "3306"),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# === REST FRAMEWORK ===
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
}
# === JWT Configurations ===
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv("ACCESS_TOKEN_LIFETIME", "120"),)),   # 🔁 Default is 5 minutes
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv("REFRESH_TOKEN_LIFETIME", "7"))),      # 🔁 Default is 1 day
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}


# === LOGGING ===
LOG_DIR = BASE_DIR / 'foodflash_logs'
os.makedirs(LOG_DIR, exist_ok=True)

# LOGGING = {
#     "version": 1,
#     "disable_existing_loggers": False,
#     "formatters": {
#         "verbose": {
#             "format": "[{asctime}] {levelname} {name} {message}",
#             "style": "{",
#         },
#     },
#     "handlers": {
#         "file": {
#             "level": "ERROR",
#             "class": "logging.FileHandler",
#             "filename": LOG_DIR / "error.log",
#             "formatter": "verbose",
#         },
#         "requests_file": {
#             "level": "INFO",
#             "class": "logging.FileHandler",
#             "filename": LOG_DIR / "requests.log",
#             "formatter": "verbose",
#         },
#         "vendors_file": {
#             "level": "INFO",
#             "class": "logging.FileHandler",
#             "filename": LOG_DIR / "vendors.log",
#             "formatter": "verbose",
#         },
#         "orders_file": {
#             "level": "INFO",
#             "class": "logging.FileHandler",
#             "filename": LOG_DIR / "orders.log",
#             "formatter": "verbose",
#         },
#         "managers_file": {
#             "level": "INFO",
#             "class": "logging.FileHandler",
#             "filename": LOG_DIR / "managers.log",
#             "formatter": "verbose",
#         },
#     },
#     "loggers": {
#         "django": {
#             "handlers": ["file"],
#             "level": "ERROR",
#             "propagate": True,
#         },
#         "django.request": {
#             "handlers": ["requests_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "vendors.views": {
#             "handlers": ["vendors_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "vendors.utils": {
#             "handlers": ["vendors_file","managers_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "vendors.mqtt_client": {
#             "handlers": ["vendors_file","managers_file"],
#             "level": "INFO",
#             "propagate": False,
#         },  
#         "vendors.order_utils": {
#             "handlers": ["vendors_file", "managers_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "vendors.services.order_service": {
#             "handlers": ["vendors_file", "managers_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "orders.views": {
#             "handlers": ["orders_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "orders.utils": {
#             "handlers": ["orders_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "orders.scheduler": {
#             "handlers": ["orders_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#         "manager.views": {
#             "handlers": ["managers_file"],
#             "level": "INFO",
#             "propagate": False,
#             },
#         "static.utils.functions.queries": {
#             "handlers": ["orders_file","managers_file"],
#             "level": "INFO",
#             "propagate": False,     
#             },
#         "static.utils.functions.notifications": {
#             "handlers": ["orders_file","managers_file"],
#             "level": "INFO",
#             "propagate": False, 
#             },
#         "static.utils.functions.utils": {
#             "handlers": ["orders_file","managers_file"],
#             "level": "INFO",
#             "propagate": False,
#         },
#     },
# }
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
        "orders.views": {
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
    },
}


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

# === STATIC & MEDIA FILES ===
STATIC_URL = '/static/'
# To support project-level static
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),  # Project-level static folder
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
LOGIN_URL = '/login/'


# === DEFAULT PRIMARY KEY FIELD TYPE ===
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
