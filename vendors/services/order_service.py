# vendors/services/order_service.py
import logging

from django.conf import settings

from vendors.mqtt_client import publish_mqtt
from vendors.order_utils import get_last_tokens

logger = logging.getLogger(__name__)


def send_order_update(vendor, payload=None):
    """Send an MQTT update with order tokens or a custom payload for a vendor.

    Args:
        vendor: The vendor object containing vendor details and configuration.
        payload: Optional custom payload dictionary. If None, default token list is sent.
    """
    config = vendor.config

    if payload is None:
        project = (getattr(settings, "PROJECT_NAME", "") or "").strip().lower()
        if project == "dine_flash":
            # Food-Flash token MQTT payloads do not include table/seat; TVs refresh on this topic.
            try:
                from vendors.models import AndroidDevice
                from vendors.utils import build_dine_flash_tv_booking_snapshot

                dev = (
                    AndroidDevice.objects.filter(vendor=vendor)
                    .exclude(tv_config__isnull=True)
                    .select_related("tv_config")
                    .first()
                )
                tv_cfg = dev.tv_config if dev else None
                payload = build_dine_flash_tv_booking_snapshot(vendor, tv_cfg, request=None)
            except Exception:
                logger.exception(
                    "Dine Flash MQTT: snapshot build failed vendor_pk=%s; falling back to token payload.",
                    getattr(vendor, "id", None),
                )
                payload = None

        if payload is None:
            tokens = get_last_tokens(vendor, config.token_display_limit)
            total_count = len(tokens)

            payload = {
                "vendor_id": vendor.vendor_id,
                "mode": config.mqtt_mode,
                "total_count": total_count,
                "tokens": tokens,
            }

    logger.info(f"📡 Sending MQTT update | Vendor: {vendor.name} (ID: {vendor.vendor_id}) | Mode: {config.mqtt_mode}")
    logger.debug(f"Payload: {payload}")

    if config.mqtt_mode == "All":
        result = publish_mqtt(vendor, payload)
        return result

    elif config.mqtt_mode == "Individual":
        for device in vendor.devices.all():
            result = publish_mqtt(vendor, payload)
            return result

    elif config.mqtt_mode == "Keypad":
        for device in vendor.devices.all():
            result = publish_mqtt(vendor, payload)
            return result

    
