import firebase_admin
from firebase_admin import credentials
from django.conf import settings

if not firebase_admin._apps:
    cred = credentials.Certificate(str(settings.FIREBASE_SERVICE_ACCOUNT_FILE))
    firebase_admin.initialize_app(cred)
