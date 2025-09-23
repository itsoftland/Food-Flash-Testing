# # server_sender.py
from azure.iot.hub import IoTHubRegistryManager
from django.conf import settings
import logging
from uamqp.errors import TokenExpired
from vendors.order_utils import get_last_tokens
import json
logger = logging.getLogger(__name__)

# # Fetch the IoT Hub service connection string once
SERVICE_CONNECTION_STRING = getattr(settings, 'IOTHUB_PRIMARY_CONNECTION_STRING', None)

# # Create the registry manager once and reuse
registry_manager = IoTHubRegistryManager(SERVICE_CONNECTION_STRING)

# def get_azure_devices(vendor):
#     """
#     Send a message to all IoT devices linked to the given vendor.
#     """
#     config = vendor.config
#     tokens = get_last_tokens(vendor, config.token_display_limit)
#     total_count = total_count = len(tokens)

#     payload = {
#         "vendor_id": vendor.vendor_id,
#         "mode": config.mqtt_mode,
#         "total_count": total_count,
#         "tokens": tokens
#     }
#     devices = vendor.iot_device_credentials.all()
#     for device in devices:
#         send_message_to_device(device.device_id, json.dumps(payload))

# def send_message_to_device(device_id, message):
#     global registry_manager
#     try:
#         registry_manager.send_c2d_message(device_id, message)
#         logger.info(f"✅ Sent message to {device_id}: {message}")
#     except TokenExpired:
#         logger.warning("⚠️ IoT Hub SAS token expired. Recreating registry manager...")
#         # Recreate the client with a new token
#         registry_manager = IoTHubRegistryManager(SERVICE_CONNECTION_STRING)
#         try:
#             registry_manager.send_c2d_message(device_id, message)
#             logger.info(f"✅ Retried and sent message to {device_id}: {message}")
#         except Exception as e:
#             logger.error(f"❌ Failed after retry to send message to {device_id}: {e}")
#     except Exception as e:
#         # Handles "C2D message send failure" and other issues
#         logger.error(f"❌ Failed to send C2D message to {device_id}: {e}")
# Add / ensure these imports at top of the file
import time
from uuid import uuid4
from uamqp import Message, constants
from uamqp.message import MessageProperties

# Tuning knobs (tune to your environment)
BATCH_SIZE = 50            # messages per batch
RETRY_ATTEMPTS = 2
RETRY_BASE_DELAY = 0.2     # seconds

def get_azure_devices(vendor):
    """
    Send a message payload once to all IoT devices linked to the given vendor using AMQP batching.
    Returns a summary dict: {'sent': x, 'failed': y, 'failed_ids': [...]}
    """
    global registry_manager

    try:
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
            batch = devices[i : i + BATCH_SIZE]
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
                    # results aligns positionally to queued messages
                    # inspect for per-message failures
                    if results:
                        for idx_result, state in enumerate(results):
                            if state == constants.MessageState.SendFailed:
                                # corresponding device id
                                dev_id = queued_devices[idx_result] if idx_result < len(queued_devices) else None
                                failed_ids.append(dev_id)
                            else:
                                total_sent += 1
                    else:
                        # If results is falsy, assume optimistic success for queued messages
                        total_sent += len(queued_devices)
                    break
                except TokenExpired:
                    logger.warning("[get_azure_devices] TokenExpired detected – recreating registry manager and send client")
                    # recreate client once; other callers should see updated global
                    registry_manager = IoTHubRegistryManager(SERVICE_CONNECTION_STRING)
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
                        # mark all queued devices in this batch as failed
                        failed_ids.extend(queued_devices)
                        logger.error("[get_azure_devices] Giving up on this batch after %d attempts", attempt - 1)
                        break

            # tiny throttle to avoid tight loop if many batches
            time.sleep(0.01)

        sent_count = total_sent
        failed_count = len([f for f in failed_ids if f])
        logger.info("[get_azure_devices] Completed vendor=%s sent=%s failed=%s", vendor.vendor_id, sent_count, failed_count)
        return {"sent": sent_count, "failed": failed_count, "failed_ids": failed_ids}

    except Exception as e:
        logger.exception("[get_azure_devices] Unexpected error: %s", e)
        return {"sent": 0, "failed": 0, "failed_ids": []}
