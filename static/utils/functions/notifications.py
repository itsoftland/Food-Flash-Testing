from firebase_admin import messaging
import json
import logging
from vendors.models import AndroidDevice

logger = logging.getLogger(__name__)

def notify_android_tv(vendor, data):
    android_devices = AndroidDevice.objects.filter(vendor=vendor)
    tokens = list(android_devices.values_list('token', flat=True))
    return send_firebase_admin_multicast(tokens, json.dumps(data))


def send_firebase_admin_multicast(fcm_tokens, data_payload):
    """
    Sends a true Firebase Admin SDK multicast data+notification message to multiple devices.
    """

    if not fcm_tokens:
        logger.warning("No FCM tokens provided for multicast.")
        return False, {"error": "No tokens to send"}

    try:
        message = messaging.MulticastMessage(
            data={
                "type": "ready_orders",
                "orders": data_payload  # Ensure this is a string, if JSON dump is needed
            },
            notification=messaging.Notification(
                title="Order Ready!",
                body="Order Status Send to Android TV"
            ),
            tokens=fcm_tokens,
        )
        response = messaging.send_each_for_multicast(message)

        failed_tokens = []
        for idx, resp in enumerate(response.responses):
            if not resp.success:
                failed_tokens.append(fcm_tokens[idx])

        if failed_tokens:
            logger.warning(f"Multicast partially failed: {len(failed_tokens)} failed tokens.")
            return False, {"failed_tokens": failed_tokens}

        logger.info(f"FCM multicast successful: {response.success_count} sent.")
        return True, {"success_count": response.success_count}

    except Exception as e:
        logger.exception("Multicast FCM error")
        return False, {"error": str(e)}