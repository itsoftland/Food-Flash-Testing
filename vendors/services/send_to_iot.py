# server_sender.py
import json
import logging
import time
from uuid import uuid4

from django.conf import settings
from azure.iot.hub import IoTHubRegistryManager
from uamqp import Message, constants
from uamqp.errors import TokenExpired
from uamqp.message import MessageProperties

from vendors.order_utils import get_last_tokens

logger = logging.getLogger(__name__)

# Fetch the IoT Hub service connection string once
SERVICE_CONNECTION_STRING = getattr(settings, 'IOTHUB_PRIMARY_CONNECTION_STRING', None)

# Global RegistryManager + timestamp
_registry_manager = None
_registry_manager_created_at = 0
TOKEN_REFRESH_INTERVAL = 55 * 60  # 55 minutes

# Tuning knobs
BATCH_SIZE = 50
RETRY_ATTEMPTS = 2
RETRY_BASE_DELAY = 0.2  # seconds

def get_registry_manager():
    """
    Returns a global IoTHubRegistryManager instance.
    Recreates it if it doesn't exist or if the token is about to expire.
    """
    global _registry_manager, _registry_manager_created_at

    now_ts = time.time()
    if _registry_manager is None or (now_ts - _registry_manager_created_at > TOKEN_REFRESH_INTERVAL):
        _registry_manager = IoTHubRegistryManager(SERVICE_CONNECTION_STRING)
        _registry_manager_created_at = now_ts
        logger.info(f"[RegistryManager] Created new instance ID={id(_registry_manager)} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now_ts))}")
    else:
        logger.info(f"[RegistryManager] Reusing instance ID={id(_registry_manager)}")

    return _registry_manager


def get_azure_devices(vendor):
    """
    Send a message payload once to all IoT devices linked to the given vendor using AMQP batching.
    Returns a summary dict: {'sent': x, 'failed': y, 'failed_ids': [...]}
    """
    try:
        registry_manager = get_registry_manager()
        logger.info(f"Using RegistryManager ID: {id(registry_manager)}")

        config = vendor.config
        tokens = get_last_tokens(vendor, config.token_display_limit)
        payload = {
            "vendor_id": vendor.vendor_id,
            "mode": config.mqtt_mode,
            "total_count": len(tokens),
            "tokens": tokens
        }
        payload_str = json.dumps(payload)

        devices = list(vendor.iot_device_credentials.all())
        if not devices:
            logger.info("[get_azure_devices] No IoT devices for vendor %s", vendor.vendor_id)
            return {"sent": 0, "failed": 0, "failed_ids": []}

        # Acquire the underlying AMQP send client from the SDK's wrapper
        amqp_wrapper = registry_manager.amqp_svc_client
        send_client = amqp_wrapper.amqp_client

        total_sent = 0
        failed_ids = []

        # iterate in batches
        i = 0
        while i < len(devices):
            batch = devices[i: i + BATCH_SIZE]
            i += BATCH_SIZE

            # queue each device-targeted message
            queued_devices = []
            for dev in batch:
                try:
                    props = MessageProperties()
                    props.message_id = str(uuid4())
                    props.to = f"/devices/{dev.device_id}/messages/devicebound"
                    app_props = {
                        "server_sent_at": time.time(),
                        "target_device": dev.device_id
                    }
                    msg = Message(payload_str, properties=props, application_properties=app_props)
                    send_client.queue_message(msg)
                    queued_devices.append(dev.device_id)
                except Exception as e:
                    logger.exception("[get_azure_devices] Failed to queue for %s: %s", getattr(dev, "device_id", None), e)
                    failed_ids.append(getattr(dev, "device_id", None))

            # send the queued messages with retry handling
            attempt = 0
            while attempt <= RETRY_ATTEMPTS:
                try:
                    results = send_client.send_all_messages(close_on_done=False)
                    if results:
                        for idx_result, state in enumerate(results):
                            if state == constants.MessageState.SendFailed:
                                dev_id = queued_devices[idx_result] if idx_result < len(queued_devices) else None
                                failed_ids.append(dev_id)
                            else:
                                total_sent += 1
                    else:
                        total_sent += len(queued_devices)
                    break
                except TokenExpired:
                    logger.warning("[get_azure_devices] TokenExpired detected – recreating registry manager and send client")
                    # Recreate registry manager proactively
                    registry_manager = get_registry_manager()
                    amqp_wrapper = registry_manager.amqp_svc_client
                    send_client = amqp_wrapper.amqp_client
                    attempt += 1
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                    continue
                except Exception as ex:
                    logger.exception("[get_azure_devices] Batch send failed (attempt %d): %s", attempt, ex)
                    attempt += 1
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                    if attempt > RETRY_ATTEMPTS:
                        failed_ids.extend(queued_devices)
                        logger.error("[get_azure_devices] Giving up on this batch after %d attempts", attempt - 1)
                        break

            time.sleep(0.01)  # throttle

        sent_count = total_sent
        failed_count = len([f for f in failed_ids if f])
        logger.info("[get_azure_devices] Completed vendor=%s sent=%s failed=%s", vendor.vendor_id, sent_count, failed_count)
        return {"sent": sent_count, "failed": failed_count, "failed_ids": failed_ids}

    except Exception as e:
        logger.exception("[get_azure_devices] Unexpected error: %s", e)
        return {"sent": 0, "failed": 0, "failed_ids": []}
