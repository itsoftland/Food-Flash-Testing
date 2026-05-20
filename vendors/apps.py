import logging

from django.apps import AppConfig


class VendorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vendors'

    def ready(self):
        import vendors.signals  # ✅ ensures the signal is registered
        import vendors.firebase  # ✅ your firebase init (keep this here)
        try:
            from vendors.fcm_log import probe_fcm_audit_log

            path = probe_fcm_audit_log()
            if path:
                logging.getLogger("vendors.views").info(
                    "[fcm_probe] audit log active path=%s", path
                )
            else:
                logging.getLogger("vendors.views").warning(
                    "[fcm_probe] could not resolve fcm.log path — check EXTERNAL_LOG_DIR in .env"
                )
        except Exception as exc:
            logging.getLogger("vendors.views").warning(
                "[fcm_probe] startup failed: %s", exc, exc_info=True
            )


