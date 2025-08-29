from django.apps import AppConfig

class VendorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vendors'

    def ready(self):
        # Import the firebase initialization to run it once when app is ready
        import vendors.firebase

    
